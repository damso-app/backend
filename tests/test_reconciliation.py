from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.answers import get_storage_service
from app.core.config import Settings, get_settings
from app.db.session import Base, get_db
from app.main import app
from app.models.answer import Answer, AnswerStatus
from app.models.family import Family, FamilyStatus
from app.models.family_member import FamilyMember, FamilyMemberRole, FamilyMemberStatus
from app.models.question_recommendation import QuestionDepth
from app.models.question_send import QuestionSend, QuestionSendSource, QuestionSendStatus
from app.models.user import User, UserRole
from app.models.video_clip import VideoClip
from app.services.ai_callback_service import AiCallbackService
from app.services.ai_job_service import AiJobService
from app.services.reconciliation_service import ReconciliationService
from app.services.storage_service import StorageService


class FakeStorageService(StorageService):
    def __init__(self) -> None:  # no super().__init__: avoid touching real GCS/ADC
        pass

    def generate_upload_url(
        self,
        *,
        object_path: str,
        content_type: str,
        expire_minutes: int | None = None,
    ) -> tuple[str, datetime]:
        return (f"signed-upload:{object_path}", datetime.now(UTC))

    def generate_read_url(self, *, gs_uri: str, expire_minutes: int | None = None) -> str:
        return f"signed:{gs_uri}"


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        jwt_algorithm="HS256",
        gcs_bucket_name="test-bucket",
        app_base_url="https://backend.example.com",
        ai_server_base_url="https://ai-server.example.com",
        ai_job_request_timeout_seconds=5.0,
        ai_stuck_processing_threshold_minutes=20,
        internal_trigger_token="trigger-secret",
    )


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        yield SessionLocal
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> Iterator[TestClient]:
    def override_settings() -> Settings:
        return auth_settings

    def override_db() -> Iterator[Session]:
        with session_factory() as request_db:
            yield request_db

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage_service] = FakeStorageService
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def create_user(db: Session, *, public_id: str, role: UserRole) -> User:
    user = User(public_id=public_id, display_name=public_id, role=role)
    db.add(user)
    db.flush()
    return user


def create_family_with_members(session_factory: sessionmaker[Session]) -> dict[str, int]:
    with session_factory() as db:
        child = create_user(db, public_id="child_public_id", role=UserRole.CHILD)
        mother = create_user(db, public_id="mother_public_id", role=UserRole.MOTHER)
        family = Family(
            public_id="family_public_id",
            name="담소 가족",
            created_by_user_id=child.id,
            status=FamilyStatus.ACTIVE,
        )
        db.add(family)
        db.flush()
        db.add_all(
            [
                FamilyMember(
                    family_id=family.id,
                    user_id=child.id,
                    member_role=FamilyMemberRole.CHILD,
                    status=FamilyMemberStatus.ACTIVE,
                ),
                FamilyMember(
                    family_id=family.id,
                    user_id=mother.id,
                    member_role=FamilyMemberRole.MOTHER,
                    status=FamilyMemberStatus.ACTIVE,
                ),
            ]
        )
        db.commit()
        return {"family_id": family.id, "child_id": child.id, "mother_id": mother.id}


def create_question_send(
    session_factory: sessionmaker[Session],
    *,
    sender_user_id: int,
    recipient_user_id: int,
    family_id: int,
) -> int:
    with session_factory() as db:
        question_send = QuestionSend(
            sender_user_id=sender_user_id,
            recipient_user_id=recipient_user_id,
            family_id=family_id,
            question_text="요즘 가장 마음에 남는 일은 무엇인가요?",
            depth=QuestionDepth.TINY,
            source=QuestionSendSource.CUSTOM,
            status=QuestionSendStatus.SENT,
        )
        db.add(question_send)
        db.commit()
        return question_send.id


def create_answer(
    session_factory: sessionmaker[Session],
    *,
    question_send_id: int,
    user_id: int,
    family_id: int,
    status: AnswerStatus = AnswerStatus.SUBMITTED,
    ai_job_id: str | None = None,
    updated_at: datetime | None = None,
) -> int:
    with session_factory() as db:
        answer = Answer(
            question_send_id=question_send_id,
            user_id=user_id,
            family_id=family_id,
            video_origin_url="gs://test-bucket/answers/1/1/original.mp4",
            video_mime_type="video/mp4",
            video_duration_seconds=10,
            video_size_bytes=1024,
            ai_job_id=ai_job_id,
            status=status,
        )
        db.add(answer)
        db.commit()
        answer_id = answer.id

        if updated_at is not None:
            # onupdate=func.now() only fills in when the column is absent from
            # the UPDATE values, so an explicit value here is honored as-is.
            db.execute(update(Answer).where(Answer.id == answer_id).values(updated_at=updated_at))
            db.commit()

        return answer_id


def _stale_time() -> datetime:
    return datetime.now(UTC) - timedelta(minutes=30)


def _job_response(*, status: str, answer_id: int, pipeline_results: dict | None = None) -> dict:
    return {
        "jobId": f"JOB_{answer_id}",
        "answerId": str(answer_id),
        "status": status,
        "result": (
            {
                "answerId": str(answer_id),
                "transcript": "실제 전사 텍스트",
                "segments": [{"startMs": 0, "endMs": 1000, "text": "실제 전사 텍스트"}],
                "warnings": [],
                "pipelineResults": pipeline_results or {},
            }
            if pipeline_results is not None
            else None
        ),
    }


# ==============================================================================
# ReconciliationService tests
# ==============================================================================


def test_reconcile_skips_when_ai_server_not_configured(
    session_factory: sessionmaker[Session],
) -> None:
    settings = Settings(_env_file=None, jwt_secret_key="x" * 32, gcs_bucket_name="test-bucket")
    service = ReconciliationService(settings=settings)

    with session_factory() as db, mock.patch("httpx.get") as mock_get:
        summary = service.reconcile_stuck_answers(db)
        mock_get.assert_not_called()

    assert summary.checked == 0
    assert summary.completed == 0
    assert summary.failed == 0
    assert summary.skipped == 0


def test_reconcile_only_targets_stuck_processing_answers(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    fresh_qs = create_question_send(
        session_factory,
        sender_user_id=ids["child_id"],
        recipient_user_id=ids["mother_id"],
        family_id=ids["family_id"],
    )
    stale_processing_qs = create_question_send(
        session_factory,
        sender_user_id=ids["child_id"],
        recipient_user_id=ids["mother_id"],
        family_id=ids["family_id"],
    )
    fresh_processing_qs = create_question_send(
        session_factory,
        sender_user_id=ids["child_id"],
        recipient_user_id=ids["mother_id"],
        family_id=ids["family_id"],
    )

    # not processing -> never a reconciliation candidate
    create_answer(
        session_factory,
        question_send_id=fresh_qs,
        user_id=ids["mother_id"],
        family_id=ids["family_id"],
        status=AnswerStatus.SUBMITTED,
    )
    # processing but stale -> the one candidate
    stale_answer_id = create_answer(
        session_factory,
        question_send_id=stale_processing_qs,
        user_id=ids["mother_id"],
        family_id=ids["family_id"],
        status=AnswerStatus.PROCESSING,
        ai_job_id=f"JOB_{stale_processing_qs}",
        updated_at=_stale_time(),
    )
    # processing but recently updated -> not stuck yet
    create_answer(
        session_factory,
        question_send_id=fresh_processing_qs,
        user_id=ids["mother_id"],
        family_id=ids["family_id"],
        status=AnswerStatus.PROCESSING,
        ai_job_id=f"JOB_{fresh_processing_qs}",
    )

    service = ReconciliationService(settings=auth_settings)

    with session_factory() as db, mock.patch("httpx.get") as mock_get:
        mock_get.return_value = httpx.Response(
            200, json=_job_response(status="processing", answer_id=stale_answer_id)
        )
        summary = service.reconcile_stuck_answers(db)
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        assert called_url.endswith(f"/api/v1/ai/jobs/JOB_{stale_processing_qs}")

    assert summary.checked == 1
    assert summary.skipped == 1


def test_reconcile_redispatches_stuck_submitted_answer(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """A dispatch that never reached the AI server leaves the answer stuck at
    SUBMITTED (never advances to PROCESSING), so it must be retried by
    re-running dispatch_job rather than polled like a PROCESSING answer."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=ids["child_id"],
        recipient_user_id=ids["mother_id"],
        family_id=ids["family_id"],
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=ids["mother_id"],
        family_id=ids["family_id"],
        status=AnswerStatus.SUBMITTED,
        ai_job_id=None,
        updated_at=_stale_time(),
    )

    service = ReconciliationService(
        settings=auth_settings,
        ai_job_service=AiJobService(settings=auth_settings, storage_service=FakeStorageService()),
    )

    with session_factory() as db, mock.patch("httpx.post") as mock_post, mock.patch(
        "httpx.get"
    ) as mock_get:
        mock_post.return_value.raise_for_status = mock.MagicMock()
        summary = service.reconcile_stuck_answers(db)
        mock_get.assert_not_called()
        mock_post.assert_called_once()

    assert summary.checked == 1
    assert summary.redispatched == 1
    assert summary.completed == 0
    assert summary.failed == 0
    assert summary.skipped == 0

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        assert answer.status == AnswerStatus.PROCESSING
        assert answer.ai_job_id == f"JOB_{answer_id}"


def test_reconcile_leaves_fresh_submitted_answer_alone(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=ids["child_id"],
        recipient_user_id=ids["mother_id"],
        family_id=ids["family_id"],
    )
    create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=ids["mother_id"],
        family_id=ids["family_id"],
        status=AnswerStatus.SUBMITTED,
    )

    service = ReconciliationService(
        settings=auth_settings,
        ai_job_service=AiJobService(settings=auth_settings, storage_service=FakeStorageService()),
    )

    with session_factory() as db, mock.patch("httpx.post") as mock_post:
        summary = service.reconcile_stuck_answers(db)
        mock_post.assert_not_called()

    assert summary.checked == 0
    assert summary.redispatched == 0


def test_reconcile_completes_stuck_answer_from_poll(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=ids["child_id"],
        recipient_user_id=ids["mother_id"],
        family_id=ids["family_id"],
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=ids["mother_id"],
        family_id=ids["family_id"],
        status=AnswerStatus.PROCESSING,
        ai_job_id=f"JOB_{question_send_id}",
        updated_at=_stale_time(),
    )

    pipeline_results = {
        "AI-003": {"diaryTitle": "제목", "oneLineSummary": "요약"},
        "AI-004": {"representativeQuote": "인용구"},
        "AI-005": {"emotionTags": ["고마움"]},
        "AI-008": {"status": "completed"},
        "AI-009": {"fourCutTitle": "네컷 제목"},
    }

    service = ReconciliationService(
        settings=auth_settings,
        callback_service=AiCallbackService(
            settings=auth_settings, storage_service=FakeStorageService()
        ),
    )

    with session_factory() as db, mock.patch("httpx.get") as mock_get, mock.patch(
        "httpx.post"
    ) as mock_post:
        mock_get.return_value = httpx.Response(
            200,
            json=_job_response(
                status="completed", answer_id=answer_id, pipeline_results=pipeline_results
            ),
        )
        mock_post.side_effect = httpx.ConnectError("no realtime broadcast in tests")
        summary = service.reconcile_stuck_answers(db)

    assert summary.checked == 1
    assert summary.completed == 1

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        assert answer.status == AnswerStatus.COMPLETED
        video_clip = db.scalar(select(VideoClip).where(VideoClip.answer_id == answer_id))
        assert video_clip is not None
        assert video_clip.title == "제목"
        assert video_clip.quote == "인용구"


def test_reconcile_fails_stuck_answer_from_poll(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=ids["child_id"],
        recipient_user_id=ids["mother_id"],
        family_id=ids["family_id"],
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=ids["mother_id"],
        family_id=ids["family_id"],
        status=AnswerStatus.PROCESSING,
        ai_job_id=f"JOB_{question_send_id}",
        updated_at=_stale_time(),
    )

    pipeline_results = {
        "AI-008": {"status": "failed", "retryable": True},
        "AI-010": {"fallbackUsed": True},
    }

    service = ReconciliationService(
        settings=auth_settings,
        callback_service=AiCallbackService(
            settings=auth_settings, storage_service=FakeStorageService()
        ),
    )

    with session_factory() as db, mock.patch("httpx.get") as mock_get, mock.patch(
        "httpx.post"
    ) as mock_post:
        mock_get.return_value = httpx.Response(
            200,
            json=_job_response(
                status="failed", answer_id=answer_id, pipeline_results=pipeline_results
            ),
        )
        mock_post.side_effect = httpx.ConnectError("no realtime broadcast in tests")
        summary = service.reconcile_stuck_answers(db)

    assert summary.failed == 1

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        assert answer.status == AnswerStatus.FAILED
        assert answer.ai_retryable is True
        assert answer.ai_fallback_used is True


def test_reconcile_marks_lost_on_404(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=ids["child_id"],
        recipient_user_id=ids["mother_id"],
        family_id=ids["family_id"],
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=ids["mother_id"],
        family_id=ids["family_id"],
        status=AnswerStatus.PROCESSING,
        ai_job_id=f"JOB_{question_send_id}",
        updated_at=_stale_time(),
    )

    service = ReconciliationService(settings=auth_settings)

    with session_factory() as db, mock.patch("httpx.get") as mock_get, mock.patch(
        "httpx.post"
    ) as mock_post:
        mock_get.return_value = httpx.Response(404, json={"detail": "job not found"})
        mock_post.side_effect = httpx.ConnectError("no realtime broadcast in tests")
        summary = service.reconcile_stuck_answers(db)

    assert summary.failed == 1

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        assert answer.status == AnswerStatus.FAILED
        assert answer.ai_retryable is True
        video_clip = db.scalar(select(VideoClip).where(VideoClip.answer_id == answer_id))
        assert video_clip is None


def test_reconcile_handles_http_error_gracefully(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=ids["child_id"],
        recipient_user_id=ids["mother_id"],
        family_id=ids["family_id"],
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=ids["mother_id"],
        family_id=ids["family_id"],
        status=AnswerStatus.PROCESSING,
        ai_job_id=f"JOB_{question_send_id}",
        updated_at=_stale_time(),
    )

    service = ReconciliationService(settings=auth_settings)

    with session_factory() as db, mock.patch("httpx.get") as mock_get:
        mock_get.side_effect = httpx.ConnectError("AI server unreachable")
        summary = service.reconcile_stuck_answers(db)

    assert summary.skipped == 1

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        assert answer.status == AnswerStatus.PROCESSING


# ==============================================================================
# Endpoint auth tests
# ==============================================================================


def test_reconcile_endpoint_requires_token(client: TestClient) -> None:
    response = client.post("/api/v1/internal/answers/reconcile")
    assert response.status_code == 401


def test_reconcile_endpoint_rejects_wrong_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/internal/answers/reconcile",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_reconcile_endpoint_returns_503_when_token_not_configured(
    session_factory: sessionmaker[Session],
) -> None:
    settings_without_token = Settings(
        _env_file=None,
        jwt_secret_key="x" * 32,
        gcs_bucket_name="test-bucket",
    )

    def override_settings() -> Settings:
        return settings_without_token

    def override_db() -> Iterator[Session]:
        with session_factory() as request_db:
            yield request_db

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as unconfigured_client:
            response = unconfigured_client.post(
                "/api/v1/internal/answers/reconcile",
                headers={"Authorization": "Bearer anything"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_reconcile_endpoint_accepts_correct_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/internal/answers/reconcile",
        headers={"Authorization": "Bearer trigger-secret"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "checked": 0,
        "completed": 0,
        "failed": 0,
        "skipped": 0,
        "redispatched": 0,
    }
