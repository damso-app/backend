from collections.abc import Iterator
from datetime import UTC, datetime
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.answers import get_storage_service
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, create_ai_callback_token
from app.db.session import Base, get_db
from app.main import app
from app.models.answer import Answer, AnswerStatus
from app.models.family import Family, FamilyStatus
from app.models.family_member import FamilyMember, FamilyMemberRole, FamilyMemberStatus
from app.models.question_recommendation import QuestionDepth
from app.models.question_send import QuestionSend, QuestionSendSource, QuestionSendStatus
from app.models.user import User, UserRole
from app.models.video_clip import VideoClip, VideoClipAiResult
from app.services.ai_job_service import AiJobService
from app.services.realtime_service import RealtimeService
from app.services.storage_service import StorageNotConfiguredError, StorageService


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
        return (
            f"https://fake-gcs.example.com/{object_path}?content_type={content_type}",
            datetime(2026, 7, 6, 10, 15, tzinfo=UTC),
        )

    def generate_read_url(self, *, gs_uri: str, expire_minutes: int | None = None) -> str:
        # Extract bucket and path from gs://bucket/path
        parts = gs_uri.replace("gs://", "").split("/", 1)
        if len(parts) == 2:
            return f"https://fake-gcs-read.example.com/{parts[1]}"
        return f"https://fake-gcs-read.example.com/{gs_uri}"


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        jwt_algorithm="HS256",
        access_token_expire_minutes=15,
        login_code_expire_minutes=5,
        ai_callback_token_expire_minutes=120,
        gcs_bucket_name="test-bucket",
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


def auth_headers(public_id: str, settings: Settings) -> dict[str, str]:
    token = create_access_token(subject=public_id, provider="damso", settings=settings)
    return {"Authorization": f"Bearer {token}"}


def bearer_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_user(db: Session, *, public_id: str, role: UserRole) -> User:
    user = User(public_id=public_id, display_name=public_id, role=role)
    db.add(user)
    db.flush()
    return user


def create_family_with_members(session_factory: sessionmaker[Session]) -> dict[str, int | str]:
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
        return {
            "family_id": family.id,
            "child_id": child.id,
            "child_public_id": child.public_id,
            "mother_id": mother.id,
            "mother_public_id": mother.public_id,
        }


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
    video_duration_seconds: int = 10,
) -> int:
    with session_factory() as db:
        answer = Answer(
            question_send_id=question_send_id,
            user_id=user_id,
            family_id=family_id,
            video_origin_url="gs://test-bucket/answers/1/1/original.mp4",
            video_mime_type="video/mp4",
            video_duration_seconds=video_duration_seconds,
            video_size_bytes=1024,
            thumbnail_url="gs://test-bucket/answers/1/1/thumbnail.jpg",
            ai_input_context={
                "send_user": "child_public_id",
                "send_role": "자녀",
                "question": "요즘 가장 마음에 남는 일은 무엇인가요?",
                "receive_user": "mother_public_id",
                "receive_role": "엄마",
            },
            status=AnswerStatus.SUBMITTED,
        )
        db.add(answer)
        db.commit()
        return answer.id


# ==============================================================================
# AiJobService Tests
# ==============================================================================


def test_ai_job_service_skips_when_ai_server_base_url_not_configured(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that dispatch_job returns early and doesn't call httpx when
    ai_server_base_url is empty."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    settings = Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        ai_server_base_url="",  # explicitly empty
    )

    service = AiJobService(settings=settings, storage_service=FakeStorageService())

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        with mock.patch("httpx.post") as mock_post:
            service.dispatch_job(db, answer=answer)
            mock_post.assert_not_called()


def test_ai_job_service_calls_httpx_when_configured(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that dispatch_job calls httpx.post with correct payload when
    ai_server_base_url is set."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    settings = Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        jwt_algorithm="HS256",
        ai_server_base_url="https://ai-server.example.com",
        ai_job_request_timeout_seconds=5.0,
        ai_edited_video_upload_url_expire_minutes=120,
        ai_callback_token_expire_minutes=120,
        app_base_url="https://app.example.com",
        api_v1_prefix="/api/v1",
        gcs_bucket_name="test-bucket",
    )

    service = AiJobService(settings=settings, storage_service=FakeStorageService())

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        with mock.patch("httpx.post") as mock_post:
            mock_post.return_value.raise_for_status = mock.MagicMock()
            service.dispatch_job(db, answer=answer)
            mock_post.assert_called_once()

            # Verify the call details
            call_args = mock_post.call_args
            assert call_args is not None
            assert (
                call_args[0][0] == "https://ai-server.example.com/api/v1/ai/jobs"
            ), "Should call correct AI server endpoint"

            # Verify payload structure
            payload = call_args[1]["json"]
            assert payload["jobId"] == f"JOB_{answer_id}", "jobId should match answer.ai_job_id"
            assert payload["answerId"] == str(answer_id), "answerId should be stringified"
            assert payload["questionId"] == str(question_send_id), "questionId should match"
            assert payload["providerMode"] == "auto", "providerMode should be auto"
            assert payload["includeDownstream"] is True, "includeDownstream should be true"
            assert (
                payload["callbackUrl"]
                == f"https://app.example.com/api/v1/answers/{answer_id}/ai-callback"
            ), "callbackUrl should be correctly formed"
            assert "callbackToken" in payload, "payload should include callbackToken"
            assert payload["mediaUrl"] is not None, "mediaUrl should be set"
            assert payload["editedVideoUploadUrl"] is not None, "editedVideoUploadUrl should be set"
            assert (
                payload["send_user"] == "child_public_id"
            ), "send_user from ai_input_context should be in payload"
            assert (
                payload["receive_role"] == "엄마"
            ), "receive_role from ai_input_context should be in payload"


def test_ai_job_service_sends_authorization_header_when_api_key_configured(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that dispatch_job sends an Authorization header when
    ai_server_api_key is set, and omits it otherwise."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    base_kwargs = {
        "_env_file": None,
        "jwt_secret_key": "unit-test-jwt-secret-with-at-least-32-bytes",
        "jwt_algorithm": "HS256",
        "ai_server_base_url": "https://ai-server.example.com",
        "ai_job_request_timeout_seconds": 5.0,
        "ai_edited_video_upload_url_expire_minutes": 120,
        "ai_callback_token_expire_minutes": 120,
        "app_base_url": "https://app.example.com",
        "api_v1_prefix": "/api/v1",
        "gcs_bucket_name": "test-bucket",
    }

    with_key_settings = Settings(**base_kwargs, ai_server_api_key=SecretStr("secret-ai-key"))
    service = AiJobService(settings=with_key_settings, storage_service=FakeStorageService())
    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        with mock.patch("httpx.post") as mock_post:
            mock_post.return_value.raise_for_status = mock.MagicMock()
            service.dispatch_job(db, answer=answer)
            headers = mock_post.call_args[1]["headers"]
            assert headers == {"Authorization": "Bearer secret-ai-key"}

    without_key_settings = Settings(**base_kwargs)
    service = AiJobService(settings=without_key_settings, storage_service=FakeStorageService())
    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        with mock.patch("httpx.post") as mock_post:
            mock_post.return_value.raise_for_status = mock.MagicMock()
            service.dispatch_job(db, answer=answer)
            headers = mock_post.call_args[1]["headers"]
            assert headers == {}


def test_ai_job_service_sets_ai_job_id_before_http_call(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that answer.ai_job_id is set and committed before the HTTP call is made."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    settings = Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        jwt_algorithm="HS256",
        ai_server_base_url="https://ai-server.example.com",
        ai_job_request_timeout_seconds=5.0,
        ai_edited_video_upload_url_expire_minutes=120,
        ai_callback_token_expire_minutes=120,
        app_base_url="https://app.example.com",
        api_v1_prefix="/api/v1",
        gcs_bucket_name="test-bucket",
    )

    service = AiJobService(settings=settings, storage_service=FakeStorageService())

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        assert answer.ai_job_id is None, "ai_job_id should initially be None"

        with mock.patch("httpx.post") as mock_post:
            mock_post.return_value.raise_for_status = mock.MagicMock()
            service.dispatch_job(db, answer=answer)

        # Verify ai_job_id was set and committed
        db.refresh(answer)
        assert answer.ai_job_id == f"JOB_{answer_id}", "ai_job_id should be set"


def test_ai_job_service_handles_http_error_gracefully(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that httpx.HTTPError is caught and logged, but no exception is raised."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    settings = Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        jwt_algorithm="HS256",
        ai_server_base_url="https://ai-server.example.com",
        ai_job_request_timeout_seconds=5.0,
        ai_edited_video_upload_url_expire_minutes=120,
        ai_callback_token_expire_minutes=120,
        app_base_url="https://app.example.com",
        api_v1_prefix="/api/v1",
        gcs_bucket_name="test-bucket",
    )

    service = AiJobService(settings=settings, storage_service=FakeStorageService())

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        with mock.patch("httpx.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection failed")
            # Should not raise even though httpx.post fails
            service.dispatch_job(db, answer=answer)
            assert answer.ai_job_id is not None, "ai_job_id should be set despite HTTP error"


def test_ai_job_service_uses_long_expiry_for_media_url(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """mediaUrl must survive AI queueing time, not just the default 15min GCS
    signed URL expiry (regression for the short-lived mediaUrl bug)."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    settings = Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        ai_server_base_url="https://ai-server.example.com",
        ai_edited_video_upload_url_expire_minutes=120,
        app_base_url="https://app.example.com",
        gcs_bucket_name="test-bucket",
    )
    storage_service = FakeStorageService()
    service = AiJobService(settings=settings, storage_service=storage_service)

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        video_origin_url = answer.video_origin_url
        with mock.patch("httpx.post") as mock_post, mock.patch.object(
            storage_service, "generate_read_url", wraps=storage_service.generate_read_url
        ) as mock_read_url:
            mock_post.return_value.raise_for_status = mock.MagicMock()
            service.dispatch_job(db, answer=answer)

    mock_read_url.assert_called_once_with(gs_uri=video_origin_url, expire_minutes=120)


def test_ai_job_service_skips_when_app_base_url_missing(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """If AI_SERVER_BASE_URL is set but APP_BASE_URL isn't, callbackUrl would be
    a broken relative path -- dispatch should skip instead of sending it."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    settings = Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        ai_server_base_url="https://ai-server.example.com",
        app_base_url=None,
    )
    service = AiJobService(settings=settings, storage_service=FakeStorageService())

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        with mock.patch("httpx.post") as mock_post:
            service.dispatch_job(db, answer=answer)
            mock_post.assert_not_called()
        assert answer.ai_job_id is None, "should skip before assigning ai_job_id"


def test_ai_job_service_swallows_payload_build_errors(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """A StorageServiceError raised while assembling the payload (e.g. GCS
    misconfigured) must not escape the background task unhandled."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    settings = Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        ai_server_base_url="https://ai-server.example.com",
        app_base_url="https://app.example.com",
        gcs_bucket_name="test-bucket",
    )
    storage_service = FakeStorageService()
    service = AiJobService(settings=settings, storage_service=storage_service)

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        with mock.patch.object(
            storage_service,
            "generate_upload_url",
            side_effect=StorageNotConfiguredError("GCS_BUCKET_NAME is not configured"),
        ):
            # Should not raise even though payload assembly fails.
            service.dispatch_job(db, answer=answer)
            assert answer.ai_job_id is not None, "ai_job_id should still be committed"


# ==============================================================================
# RealtimeService Tests
# ==============================================================================


def test_realtime_service_skips_when_not_configured(
    auth_settings: Settings,
) -> None:
    """Test that broadcast methods return early when supabase settings are not configured."""
    settings = Settings(
        _env_file=None,
        supabase_url=None,
        supabase_service_role_key=None,
    )
    service = RealtimeService(settings=settings)

    with mock.patch("httpx.post") as mock_post:
        service.broadcast_answer_completed(
            family_id=1,
            answer_id=1,
            thumbnail_url="https://example.com/thumb.jpg",
        )
        mock_post.assert_not_called()

    with mock.patch("httpx.post") as mock_post:
        service.broadcast_answer_failed(family_id=1, answer_id=1)
        mock_post.assert_not_called()


def test_realtime_service_broadcasts_answer_completed(
    auth_settings: Settings,
) -> None:
    """Test that broadcast_answer_completed calls httpx.post with correct payload."""
    settings = Settings(
        _env_file=None,
        supabase_url="https://supabase.example.com",
        supabase_service_role_key=SecretStr("test-service-role-key"),
    )
    service = RealtimeService(settings=settings)

    with mock.patch("httpx.post") as mock_post:
        mock_post.return_value.raise_for_status = mock.MagicMock()
        service.broadcast_answer_completed(
            family_id=123,
            answer_id=456,
            thumbnail_url="https://example.com/thumb.jpg",
        )
        mock_post.assert_called_once()

        call_args = mock_post.call_args
        assert call_args is not None
        assert call_args[0][0] == "https://supabase.example.com/realtime/v1/api/broadcast"

        body = call_args[1]["json"]
        assert body["messages"][0]["topic"] == "family:123"
        assert body["messages"][0]["event"] == "answer_status_updated"
        assert body["messages"][0]["payload"]["answer_id"] == 456
        assert body["messages"][0]["payload"]["status"] == "completed"
        assert body["messages"][0]["payload"]["thumbnail_url"] == "https://example.com/thumb.jpg"

        headers = call_args[1]["headers"]
        assert headers["apikey"] == "test-service-role-key"
        assert headers["Authorization"] == "Bearer test-service-role-key"


def test_realtime_service_broadcasts_answer_failed(
    auth_settings: Settings,
) -> None:
    """Test that broadcast_answer_failed calls httpx.post with correct payload."""
    settings = Settings(
        _env_file=None,
        supabase_url="https://supabase.example.com",
        supabase_service_role_key=SecretStr("test-service-role-key"),
    )
    service = RealtimeService(settings=settings)

    with mock.patch("httpx.post") as mock_post:
        mock_post.return_value.raise_for_status = mock.MagicMock()
        service.broadcast_answer_failed(family_id=123, answer_id=456)
        mock_post.assert_called_once()

        call_args = mock_post.call_args
        assert call_args is not None
        body = call_args[1]["json"]
        assert body["messages"][0]["payload"]["answer_id"] == 456
        assert body["messages"][0]["payload"]["status"] == "failed"
        assert "thumbnail_url" not in body["messages"][0]["payload"]


def test_realtime_service_handles_http_error_gracefully(
    auth_settings: Settings,
) -> None:
    """Test that httpx.HTTPError is caught and logged, but no exception is raised."""
    settings = Settings(
        _env_file=None,
        supabase_url="https://supabase.example.com",
        supabase_service_role_key=SecretStr("test-service-role-key"),
    )
    service = RealtimeService(settings=settings)

    with mock.patch("httpx.post") as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection failed")
        # Should not raise even though httpx.post fails
        service.broadcast_answer_completed(
            family_id=123,
            answer_id=456,
            thumbnail_url="https://example.com/thumb.jpg",
        )


# ==============================================================================
# AI Callback Route Tests
# ==============================================================================


def test_ai_callback_happy_path_completed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test successful AI callback with completed status."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    callback_token = create_ai_callback_token(answer_id=answer_id, settings=auth_settings)

    payload = {
        "answerId": str(answer_id),
        "transcript": "이건 테스트 영상입니다.",
        "segments": [{"start": 0, "end": 5, "text": "이건"}],
        "warnings": None,
        "pipelineResults": {
            "AI-008": {
                "status": "completed",
                "retryable": False,
            },
            "AI-003": {
                "diaryTitle": "테스트 다이어리",
                "oneLineSummary": "한 줄 요약",
            },
            "AI-004": {
                "representativeQuote": "대표 인용구",
            },
            "AI-005": {
                "emotionTags": ["행복", "감사"],
            },
            "AI-009": {
                "fourCutTitle": "네컷 제목",
            },
        },
    }

    with mock.patch.object(RealtimeService, "broadcast_answer_completed"):
        response = client.post(
            f"/api/v1/answers/{answer_id}/ai-callback",
            headers=bearer_headers(callback_token),
            json=payload,
        )

    assert response.status_code == 200
    result = response.json()
    assert result["answerId"] == answer_id
    assert result["status"] == "completed"

    # Verify video_clip was created
    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        assert answer.status == AnswerStatus.COMPLETED

        video_clip = db.scalar(
            select(VideoClip).where(VideoClip.answer_id == answer_id)
        )
        assert video_clip is not None
        assert video_clip.transcript == "이건 테스트 영상입니다."
        assert video_clip.title == "테스트 다이어리"
        assert video_clip.one_line_summary == "한 줄 요약"
        assert video_clip.quote == "대표 인용구"
        assert video_clip.emotion_tags == ["행복", "감사"]
        assert video_clip.fourcut_title == "네컷 제목"

        ai_result = db.scalar(
            select(VideoClipAiResult).where(VideoClipAiResult.video_clip_id == video_clip.id)
        )
        assert ai_result is not None
        assert ai_result.ai_raw_response == payload["pipelineResults"]


def test_ai_callback_accepts_result_nested_body(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """The AI server has been observed nesting transcript/segments/
    pipelineResults under a "result" key instead of the documented flat
    body — the callback endpoint must still accept it."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    callback_token = create_ai_callback_token(answer_id=answer_id, settings=auth_settings)

    payload = {
        "answerId": answer_id,
        "result": {
            "transcript": "이건 테스트 영상입니다.",
            "segments": [{"start": 0, "end": 5, "text": "이건"}],
            "pipelineResults": {
                "AI-008": {"status": "completed", "retryable": False},
                "AI-003": {"diaryTitle": "테스트 다이어리"},
            },
        },
    }

    with mock.patch.object(RealtimeService, "broadcast_answer_completed"):
        response = client.post(
            f"/api/v1/answers/{answer_id}/ai-callback",
            headers=bearer_headers(callback_token),
            json=payload,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        assert answer.status == AnswerStatus.COMPLETED
        video_clip = db.scalar(select(VideoClip).where(VideoClip.answer_id == answer_id))
        assert video_clip is not None
        assert video_clip.transcript == "이건 테스트 영상입니다."
        assert video_clip.title == "테스트 다이어리"


def test_ai_callback_accepts_non_numeric_answer_id_string(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Some AI server docs show answerId as a prefixed id (e.g. "ans_001")
    rather than the plain numeric string this backend actually issues —
    the schema must not reject that at the type level."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    callback_token = create_ai_callback_token(answer_id=answer_id, settings=auth_settings)

    payload = {
        "answerId": f"ans_{answer_id}",
        "pipelineResults": {"AI-008": {"status": "failed", "retryable": True}},
    }

    response = client.post(
        f"/api/v1/answers/{answer_id}/ai-callback",
        headers=bearer_headers(callback_token),
        json=payload,
    )

    # A prefixed answerId doesn't match this backend's plain numeric answer_id,
    # so it's correctly rejected as a mismatch (400) rather than a schema-level
    # 422 — the important thing is that parsing itself doesn't blow up.
    assert response.status_code == 400


def test_ai_callback_happy_path_failed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test successful AI callback with failed status."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    callback_token = create_ai_callback_token(answer_id=answer_id, settings=auth_settings)

    payload = {
        "answerId": str(answer_id),
        "transcript": None,
        "segments": None,
        "warnings": ["일부 처리 실패"],
        "pipelineResults": {
            "AI-008": {
                "status": "failed",
                "retryable": True,
            },
            "AI-010": {
                "fallbackUsed": True,
            },
        },
    }

    with mock.patch.object(RealtimeService, "broadcast_answer_failed"):
        response = client.post(
            f"/api/v1/answers/{answer_id}/ai-callback",
            headers=bearer_headers(callback_token),
            json=payload,
        )

    assert response.status_code == 200
    result = response.json()
    assert result["answerId"] == answer_id
    assert result["status"] == "failed"

    # Verify no video_clip was created
    with session_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.id == answer_id))
        assert answer.status == AnswerStatus.FAILED
        assert answer.ai_retryable is True
        assert answer.ai_fallback_used is True

        video_clip = db.scalar(
            select(VideoClip).where(VideoClip.answer_id == answer_id)
        )
        assert video_clip is None


def test_ai_callback_missing_auth_token_returns_401(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that missing auth token returns 401."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    payload = {
        "answerId": str(answer_id),
        "transcript": None,
        "segments": None,
        "warnings": None,
        "pipelineResults": {
            "AI-008": {"status": "completed"},
        },
    }

    # No Authorization header
    response = client.post(
        f"/api/v1/answers/{answer_id}/ai-callback",
        json=payload,
    )

    assert response.status_code == 401


def test_ai_callback_invalid_token_returns_401(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that invalid token returns 401."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    payload = {
        "answerId": str(answer_id),
        "transcript": None,
        "segments": None,
        "warnings": None,
        "pipelineResults": {
            "AI-008": {"status": "completed"},
        },
    }

    response = client.post(
        f"/api/v1/answers/{answer_id}/ai-callback",
        headers=bearer_headers("invalid-token"),
        json=payload,
    )

    assert response.status_code == 401


def test_ai_callback_token_for_different_answer_returns_401(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that a token issued for a different answer_id returns 401."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id_1 = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    # Create second answer
    question_send_id_2 = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id_2 = create_answer(
        session_factory,
        question_send_id=question_send_id_2,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    # Create token for answer 1 but use it for answer 2
    callback_token = create_ai_callback_token(answer_id=answer_id_1, settings=auth_settings)

    payload = {
        "answerId": str(answer_id_2),
        "transcript": None,
        "segments": None,
        "warnings": None,
        "pipelineResults": {
            "AI-008": {"status": "completed"},
        },
    }

    response = client.post(
        f"/api/v1/answers/{answer_id_2}/ai-callback",
        headers=bearer_headers(callback_token),
        json=payload,
    )

    assert response.status_code == 401


def test_ai_callback_nonexistent_answer_returns_404(
    client: TestClient,
    auth_settings: Settings,
) -> None:
    """Test that callback for nonexistent answer returns 404."""
    callback_token = create_ai_callback_token(answer_id=999999, settings=auth_settings)

    payload = {
        "answerId": "999999",
        "transcript": None,
        "segments": None,
        "warnings": None,
        "pipelineResults": {
            "AI-008": {"status": "completed"},
        },
    }

    response = client.post(
        "/api/v1/answers/999999/ai-callback",
        headers=bearer_headers(callback_token),
        json=payload,
    )

    assert response.status_code == 404


def test_ai_callback_answer_id_mismatch_returns_400(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that answerId in body not matching path returns 400."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    callback_token = create_ai_callback_token(answer_id=answer_id, settings=auth_settings)

    payload = {
        "answerId": "999999",  # Different from path
        "transcript": None,
        "segments": None,
        "warnings": None,
        "pipelineResults": {
            "AI-008": {"status": "completed"},
        },
    }

    response = client.post(
        f"/api/v1/answers/{answer_id}/ai-callback",
        headers=bearer_headers(callback_token),
        json=payload,
    )

    assert response.status_code == 400


def test_ai_callback_invalid_pipeline_status_returns_400(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that invalid AI-008.status returns 400."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    callback_token = create_ai_callback_token(answer_id=answer_id, settings=auth_settings)

    payload = {
        "answerId": str(answer_id),
        "transcript": None,
        "segments": None,
        "warnings": None,
        "pipelineResults": {
            "AI-008": {"status": "unknown"},  # Invalid status
        },
    }

    response = client.post(
        f"/api/v1/answers/{answer_id}/ai-callback",
        headers=bearer_headers(callback_token),
        json=payload,
    )

    assert response.status_code == 400


def test_ai_callback_idempotent_on_already_completed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that calling callback on already-completed answer is idempotent."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    callback_token = create_ai_callback_token(answer_id=answer_id, settings=auth_settings)

    payload = {
        "answerId": str(answer_id),
        "transcript": "test",
        "segments": None,
        "warnings": None,
        "pipelineResults": {
            "AI-008": {"status": "completed"},
            "AI-003": {"diaryTitle": "제목", "oneLineSummary": "요약"},
            "AI-004": {"representativeQuote": "인용구"},
            "AI-005": {"emotionTags": ["감정"]},
            "AI-009": {"fourCutTitle": "네컷"},
        },
    }

    # First call
    with mock.patch.object(RealtimeService, "broadcast_answer_completed") as mock_broadcast_1:
        response1 = client.post(
            f"/api/v1/answers/{answer_id}/ai-callback",
            headers=bearer_headers(callback_token),
            json=payload,
        )
    assert response1.status_code == 200
    assert mock_broadcast_1.call_count == 1

    # Second call - should not trigger broadcast again
    with mock.patch.object(RealtimeService, "broadcast_answer_completed") as mock_broadcast_2:
        response2 = client.post(
            f"/api/v1/answers/{answer_id}/ai-callback",
            headers=bearer_headers(callback_token),
            json=payload,
        )
    assert response2.status_code == 200
    assert (
        mock_broadcast_2.call_count == 0
    ), "broadcast should not be called on idempotent second call"

    # Verify video_clip wasn't duplicated
    with session_factory() as db:
        video_clips = db.query(VideoClip).filter(VideoClip.answer_id == answer_id).all()
        assert len(video_clips) == 1, "Should have exactly one video_clip"


def test_ai_callback_idempotent_on_already_failed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Test that calling callback on already-failed answer is idempotent."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    callback_token = create_ai_callback_token(answer_id=answer_id, settings=auth_settings)

    payload = {
        "answerId": str(answer_id),
        "transcript": None,
        "segments": None,
        "warnings": None,
        "pipelineResults": {
            "AI-008": {"status": "failed", "retryable": True},
            "AI-010": {"fallbackUsed": False},
        },
    }

    # First call
    with mock.patch.object(RealtimeService, "broadcast_answer_failed") as mock_broadcast_1:
        response1 = client.post(
            f"/api/v1/answers/{answer_id}/ai-callback",
            headers=bearer_headers(callback_token),
            json=payload,
        )
    assert response1.status_code == 200
    assert mock_broadcast_1.call_count == 1

    # Second call - should not trigger broadcast again
    with mock.patch.object(RealtimeService, "broadcast_answer_failed") as mock_broadcast_2:
        response2 = client.post(
            f"/api/v1/answers/{answer_id}/ai-callback",
            headers=bearer_headers(callback_token),
            json=payload,
        )
    assert response2.status_code == 200
    assert (
        mock_broadcast_2.call_count == 0
    ), "broadcast should not be called on idempotent second call"


def test_ai_callback_concurrent_race_does_not_500(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """Regression for the video_clips unique-constraint race: if a video_clip
    for this answer already exists (as if a concurrent callback delivery won
    first), this request must not crash with an unhandled IntegrityError/500."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    # Simulate a concurrent callback delivery that already inserted the
    # video_clip row (but hasn't -- or in this simulation, won't -- update
    # answers.status, since that update isn't part of what races here).
    with session_factory() as db:
        db.add(
            VideoClip(
                answer_id=answer_id,
                video_url="gs://test-bucket/answers/1/1/edited.mp4",
            )
        )
        db.commit()

    callback_token = create_ai_callback_token(answer_id=answer_id, settings=auth_settings)
    payload = {
        "answerId": str(answer_id),
        "transcript": "test",
        "segments": None,
        "warnings": None,
        "pipelineResults": {
            "AI-008": {"status": "completed"},
            "AI-003": {"diaryTitle": "제목", "oneLineSummary": "요약"},
        },
    }

    with mock.patch.object(RealtimeService, "broadcast_answer_completed") as mock_broadcast:
        response = client.post(
            f"/api/v1/answers/{answer_id}/ai-callback",
            headers=bearer_headers(callback_token),
            json=payload,
        )

    assert response.status_code == 200, "must not surface the IntegrityError as a 500"
    assert mock_broadcast.call_count == 0, "the losing side of the race must not re-broadcast"

    with session_factory() as db:
        clips = db.query(VideoClip).filter(VideoClip.answer_id == answer_id).all()
        assert len(clips) == 1, "video_clip must not be duplicated"


# ==============================================================================
# Settings DI Regression Test
# ==============================================================================


def test_ai_callback_token_di_regression(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    """
    Regression test: Verify that auth_settings.jwt_secret_key is properly used for
    callback token validation, confirming that settings DI works correctly.
    """
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    answer_id = create_answer(
        session_factory,
        question_send_id=question_send_id,
        user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    # Create token using the overridden auth_settings
    callback_token = create_ai_callback_token(answer_id=answer_id, settings=auth_settings)

    payload = {
        "answerId": str(answer_id),
        "transcript": "test",
        "segments": None,
        "warnings": None,
        "pipelineResults": {
            "AI-008": {"status": "completed"},
            "AI-003": {"diaryTitle": "제목", "oneLineSummary": "요약"},
            "AI-004": {"representativeQuote": "인용구"},
            "AI-005": {"emotionTags": ["감정"]},
            "AI-009": {"fourCutTitle": "네컷"},
        },
    }

    # The route should accept the token because it's using the same settings
    response = client.post(
        f"/api/v1/answers/{answer_id}/ai-callback",
        headers=bearer_headers(callback_token),
        json=payload,
    )

    assert response.status_code == 200, "Token created with auth_settings should be valid in route"
    result = response.json()
    assert result["status"] == "completed"
