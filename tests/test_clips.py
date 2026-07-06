from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.answers import get_storage_service
from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models.answer import Answer, AnswerStatus
from app.models.family import Family, FamilyStatus
from app.models.family_member import FamilyMember, FamilyMemberRole, FamilyMemberStatus
from app.models.question_recommendation import QuestionDepth
from app.models.question_send import QuestionSend, QuestionSendSource, QuestionSendStatus
from app.models.user import User, UserRole
from app.models.video_clip import VideoClip
from app.services.storage_service import StorageService


class FakeStorageService(StorageService):
    def __init__(self) -> None:  # no super().__init__: avoid touching real GCS/ADC
        pass

    def generate_read_url(self, *, gs_uri: str) -> str:
        return f"signed:{gs_uri}"


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


def create_answer(
    session_factory: sessionmaker[Session],
    *,
    family_id: int,
    user_id: int,
    status: AnswerStatus = AnswerStatus.COMPLETED,
    created_at: datetime | None = None,
    thumbnail_url: str | None = None,
) -> int:
    with session_factory() as db:
        question_send = QuestionSend(
            sender_user_id=user_id,
            recipient_user_id=user_id,
            family_id=family_id,
            question_text="질문",
            depth=QuestionDepth.TINY,
            source=QuestionSendSource.CUSTOM,
            status=QuestionSendStatus.ANSWERED,
        )
        db.add(question_send)
        db.flush()

        answer = Answer(
            question_send_id=question_send.id,
            user_id=user_id,
            family_id=family_id,
            status=status,
            thumbnail_url=thumbnail_url,
            submitted_at=created_at or datetime.now(UTC),
            created_at=created_at or datetime.now(UTC),
        )
        db.add(answer)
        db.commit()
        return answer.id


def test_grid_groups_by_kst_date_and_includes_thumbnail(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    # 2026-07-05 15:05 UTC == 2026-07-06 00:05 KST -> falls into the 07-06 bucket
    answer_id = create_answer(
        session_factory,
        family_id=int(ids["family_id"]),
        user_id=int(ids["mother_id"]),
        created_at=datetime(2026, 7, 5, 15, 5, tzinfo=UTC),
        thumbnail_url="gs://damso-videos/thumb.jpg",
    )

    response = client.get(
        "/api/v1/clips",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["groups"] == [
        {
            "date": "2026-07-06",
            "clips": [
                {
                    "answerId": answer_id,
                    "status": "completed",
                    "thumbnailUrl": "signed:gs://damso-videos/thumb.jpg",
                }
            ],
        }
    ]


def test_grid_requires_active_family(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    with session_factory() as db:
        outsider = create_user(db, public_id="outsider_public_id", role=UserRole.CHILD)
        db.commit()
        outsider_public_id = outsider.public_id

    response = client.get(
        "/api/v1/clips",
        headers=auth_headers(outsider_public_id, auth_settings),
    )

    assert response.status_code == 400


def test_grid_only_returns_own_family_answers(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    create_answer(
        session_factory,
        family_id=int(ids["family_id"]),
        user_id=int(ids["mother_id"]),
    )

    with session_factory() as db:
        other_child = create_user(db, public_id="other_child", role=UserRole.CHILD)
        other_family = Family(
            public_id="other_family",
            name="다른 가족",
            created_by_user_id=other_child.id,
            status=FamilyStatus.ACTIVE,
        )
        db.add(other_family)
        db.flush()
        db.add(
            FamilyMember(
                family_id=other_family.id,
                user_id=other_child.id,
                member_role=FamilyMemberRole.CHILD,
                status=FamilyMemberStatus.ACTIVE,
            )
        )
        db.commit()
        other_child_public_id = other_child.public_id

    response = client.get(
        "/api/v1/clips",
        headers=auth_headers(other_child_public_id, auth_settings),
    )

    assert response.status_code == 200
    assert response.json()["groups"] == []


def test_clip_detail_returns_signed_urls(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    answer_id = create_answer(
        session_factory,
        family_id=int(ids["family_id"]),
        user_id=int(ids["mother_id"]),
        thumbnail_url="gs://damso-videos/thumb.jpg",
    )
    with session_factory() as db:
        db.add(
            VideoClip(
                answer_id=answer_id,
                video_url="gs://damso-videos/edited.mp4",
                title="제목",
                quote="명대사",
            )
        )
        db.commit()

    # any active family member can view, not just the submitter
    response = client.get(
        f"/api/v1/answers/{answer_id}/clip",
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answerId"] == answer_id
    assert body["videoUrl"] == "signed:gs://damso-videos/edited.mp4"
    assert body["thumbnailUrl"] == "signed:gs://damso-videos/thumb.jpg"
    assert body["title"] == "제목"
    assert body["quote"] == "명대사"


def test_clip_detail_not_ready_returns_404(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    answer_id = create_answer(
        session_factory,
        family_id=int(ids["family_id"]),
        user_id=int(ids["mother_id"]),
        status=AnswerStatus.PROCESSING,
    )

    response = client.get(
        f"/api/v1/answers/{answer_id}/clip",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
    )

    assert response.status_code == 404


def test_clip_detail_rejects_other_family(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    answer_id = create_answer(
        session_factory,
        family_id=int(ids["family_id"]),
        user_id=int(ids["mother_id"]),
    )
    with session_factory() as db:
        db.add(VideoClip(answer_id=answer_id, video_url="gs://damso-videos/edited.mp4"))
        db.commit()

    with session_factory() as db:
        other_child = create_user(db, public_id="other_child", role=UserRole.CHILD)
        other_family = Family(
            public_id="other_family",
            name="다른 가족",
            created_by_user_id=other_child.id,
            status=FamilyStatus.ACTIVE,
        )
        db.add(other_family)
        db.flush()
        db.add(
            FamilyMember(
                family_id=other_family.id,
                user_id=other_child.id,
                member_role=FamilyMemberRole.CHILD,
                status=FamilyMemberStatus.ACTIVE,
            )
        )
        db.commit()
        other_child_public_id = other_child.public_id

    response = client.get(
        f"/api/v1/answers/{answer_id}/clip",
        headers=auth_headers(other_child_public_id, auth_settings),
    )

    assert response.status_code == 404
