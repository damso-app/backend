from collections.abc import Iterator
from datetime import UTC, datetime
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.answers import get_storage_service
from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models.answer import Answer
from app.models.family import Family, FamilyStatus
from app.models.family_member import FamilyMember, FamilyMemberRole, FamilyMemberStatus
from app.models.question_recommendation import QuestionDepth
from app.models.question_send import QuestionSend, QuestionSendSource, QuestionSendStatus
from app.models.user import User, UserRole
from app.services.answer_service import AlreadyAnsweredError, AnswerService
from app.services.storage_service import StorageService


class FakeStorageService(StorageService):
    def __init__(self) -> None:  # no super().__init__: avoid touching real GCS/ADC
        pass

    def generate_upload_url(
        self,
        *,
        object_path: str,
        content_type: str,
    ) -> tuple[str, datetime]:
        return (
            f"https://fake-gcs.example.com/{object_path}?content_type={content_type}",
            datetime(2026, 7, 6, 10, 15, tzinfo=UTC),
        )


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        jwt_algorithm="HS256",
        access_token_expire_minutes=15,
        login_code_expire_minutes=5,
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


def test_upload_url_and_submit_answer_happy_path(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    headers = auth_headers(str(ids["mother_public_id"]), auth_settings)

    upload_url_response = client.post(
        "/api/v1/answers/upload-url",
        headers=headers,
        json={"questionSendId": question_send_id, "videoMimeType": "video/mp4"},
    )
    assert upload_url_response.status_code == 201
    upload_body = upload_url_response.json()
    assert upload_body["uploadUrl"].startswith("https://fake-gcs.example.com/")
    assert f"answers/{ids['family_id']}/{question_send_id}/original.mp4" in upload_body["uploadUrl"]
    assert upload_body["expiresAt"] == "2026-07-06T10:15:00Z"

    submit_response = client.post(
        "/api/v1/answers",
        headers=headers,
        json={
            "questionSendId": question_send_id,
            "videoMimeType": "video/mp4",
            "videoDurationSeconds": 42,
            "videoSizeBytes": 10485760,
        },
    )
    assert submit_response.status_code == 201
    submit_body = submit_response.json()
    assert submit_body["questionSendId"] == question_send_id
    assert submit_body["status"] == "submitted"
    assert submit_body["answerId"] is not None

    with session_factory() as db:
        question_send = db.scalar(
            select(QuestionSend).where(QuestionSend.id == question_send_id)
        )
        assert question_send.status == QuestionSendStatus.ANSWERED
        assert question_send.answered_at is not None


def test_submit_answer_assembles_ai_input_context(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    submit_response = client.post(
        "/api/v1/answers",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
        json={
            "questionSendId": question_send_id,
            "videoMimeType": "video/mp4",
            "videoDurationSeconds": 10,
            "videoSizeBytes": 1024,
        },
    )
    assert submit_response.status_code == 201

    with session_factory() as db:
        answer = db.scalar(
            select(Answer).where(Answer.question_send_id == question_send_id)
        )
        assert answer.ai_input_context == {
            "send_user": ids["child_public_id"],
            "send_role": "자녀",
            "question": "요즘 가장 마음에 남는 일은 무엇인가요?",
            "receive_user": ids["mother_public_id"],
            "receive_role": "엄마",
        }


def test_upload_url_rejects_non_recipient(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    response = client.post(
        "/api/v1/answers/upload-url",
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
        json={"questionSendId": question_send_id, "videoMimeType": "video/mp4"},
    )

    assert response.status_code == 403


def test_upload_url_unknown_question_send_returns_404(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)

    response = client.post(
        "/api/v1/answers/upload-url",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
        json={"questionSendId": 999999, "videoMimeType": "video/mp4"},
    )

    assert response.status_code == 404


def test_upload_url_rejects_unsupported_mime_type(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    response = client.post(
        "/api/v1/answers/upload-url",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
        json={"questionSendId": question_send_id, "videoMimeType": "image/png"},
    )

    assert response.status_code == 415


def test_submit_answer_twice_conflicts(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )
    headers = auth_headers(str(ids["mother_public_id"]), auth_settings)
    payload = {
        "questionSendId": question_send_id,
        "videoMimeType": "video/mp4",
        "videoDurationSeconds": 10,
        "videoSizeBytes": 1024,
    }

    first_response = client.post("/api/v1/answers", headers=headers, json=payload)
    assert first_response.status_code == 201

    second_response = client.post("/api/v1/answers", headers=headers, json=payload)
    assert second_response.status_code == 409


def test_submit_answer_race_condition_returns_conflict_not_500(
    session_factory: sessionmaker[Session],
) -> None:
    """Two near-simultaneous submissions can both pass the check in
    _require_answerable_question_send before either commits. The unique index
    (ux_answers_question_send_id) is the real guard — its IntegrityError must
    surface as AlreadyAnsweredError, not an unhandled 500."""
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    with session_factory() as db:
        mother = db.scalar(select(User).where(User.public_id == ids["mother_public_id"]))
        question_send = db.scalar(
            select(QuestionSend).where(QuestionSend.id == question_send_id)
        )

        # Simulate a concurrent request that already won the race and
        # committed its Answer row after this request's own check already
        # passed (that check itself is bypassed below via mock.patch.object,
        # since a single synchronous session can't otherwise reproduce the
        # interleaving).
        db.add(
            Answer(
                question_send_id=question_send_id,
                user_id=mother.id,
                family_id=question_send.family_id,
                video_origin_url="gs://test-bucket/answers/1/1/original.mp4",
                video_mime_type="video/mp4",
                video_duration_seconds=10,
                video_size_bytes=1024,
            )
        )
        db.commit()

        service = AnswerService(storage_service=FakeStorageService())
        with mock.patch.object(
            AnswerService,
            "_require_answerable_question_send",
            return_value=question_send,
        ):
            with pytest.raises(AlreadyAnsweredError):
                service.submit_answer(
                    db,
                    user=mother,
                    question_send_id=question_send_id,
                    video_mime_type="video/mp4",
                    video_duration_seconds=10,
                    video_size_bytes=1024,
                )


def test_submit_answer_missing_field_is_rejected(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    question_send_id = create_question_send(
        session_factory,
        sender_user_id=int(ids["child_id"]),
        recipient_user_id=int(ids["mother_id"]),
        family_id=int(ids["family_id"]),
    )

    response = client.post(
        "/api/v1/answers",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
        json={"questionSendId": question_send_id, "videoMimeType": "video/mp4"},
    )

    assert response.status_code == 422
