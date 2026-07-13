from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.home import get_question_loop_service
from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models.family import Family, FamilyStatus
from app.models.family_member import FamilyMember, FamilyMemberRole, FamilyMemberStatus
from app.models.question_recommendation import (
    QuestionDepth,
    QuestionRecommendation,
    QuestionRecommendationStatus,
)
from app.models.question_send import QuestionSend, QuestionSendSource, QuestionSendStatus
from app.models.user import User, UserRole
from app.services.question_loop_service import QuestionLoopService


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
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def auth_headers(public_id: str, settings: Settings) -> dict[str, str]:
    token = create_access_token(
        subject=public_id,
        provider="damso",
        settings=settings,
    )
    return {"Authorization": f"Bearer {token}"}


def create_user(
    db: Session,
    *,
    public_id: str,
    display_name: str,
    role: UserRole,
) -> User:
    user = User(public_id=public_id, display_name=display_name, role=role)
    db.add(user)
    db.flush()
    return user


def create_family_with_members(
    session_factory: sessionmaker[Session],
) -> dict[str, int | str]:
    with session_factory() as db:
        child = create_user(
            db,
            public_id="child_public_id",
            display_name="자녀",
            role=UserRole.CHILD,
        )
        mother = create_user(
            db,
            public_id="mother_public_id",
            display_name="엄마",
            role=UserRole.MOTHER,
        )
        father = create_user(
            db,
            public_id="father_public_id",
            display_name="아빠",
            role=UserRole.FATHER,
        )
        family = Family(
            public_id="family_public_id",
            name="담소 가족",
            invite_code="ABC123",
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
                FamilyMember(
                    family_id=family.id,
                    user_id=father.id,
                    member_role=FamilyMemberRole.FATHER,
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
            "father_id": father.id,
            "father_public_id": father.public_id,
        }


def create_question_send(
    db: Session,
    *,
    sender_user_id: int,
    recipient_user_id: int,
    family_id: int,
    question_text: str = "오늘 가장 좋았던 순간은 언제였나요?",
    sent_at: datetime | None = None,
    read_at: datetime | None = None,
    answered_at: datetime | None = None,
    status: QuestionSendStatus = QuestionSendStatus.SENT,
) -> QuestionSend:
    question_send = QuestionSend(
        sender_user_id=sender_user_id,
        recipient_user_id=recipient_user_id,
        family_id=family_id,
        question_text=question_text,
        depth=QuestionDepth.TINY,
        source=QuestionSendSource.CUSTOM,
        sent_at=sent_at or datetime.now(UTC),
        read_at=read_at,
        answered_at=answered_at,
        status=status,
    )
    db.add(question_send)
    db.flush()
    return question_send


def test_question_recipients_exclude_current_user(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)

    response = client.get(
        "/api/v1/questions/recipients",
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
    )

    assert response.status_code == 200
    recipients = response.json()["recipients"]
    assert {item["userId"] for item in recipients} == {ids["mother_id"], ids["father_id"]}
    assert ids["child_id"] not in {item["userId"] for item in recipients}


def test_question_recommendations_are_filtered_by_depth(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    with session_factory() as db:
        db.add_all(
            [
                QuestionRecommendation(
                    question_text="가볍게 웃었던 일은 무엇인가요?",
                    depth=QuestionDepth.TINY,
                    status=QuestionRecommendationStatus.ACTIVE,
                ),
                QuestionRecommendation(
                    question_text="오래 기억하고 싶은 선택은 무엇인가요?",
                    depth=QuestionDepth.DEEP,
                    status=QuestionRecommendationStatus.ACTIVE,
                ),
                QuestionRecommendation(
                    question_text="보관된 질문",
                    depth=QuestionDepth.TINY,
                    status=QuestionRecommendationStatus.ARCHIVED,
                ),
            ]
        )
        db.commit()

    response = client.get(
        f"/api/v1/questions/recommendations?recipient_user_id={ids['mother_id']}&depth=tiny&limit=10",
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["depth"] for item in body["recommendations"]] == ["tiny"]
    assert [item["questionText"] for item in body["recommendations"]] == [
        "가볍게 웃었던 일은 무엇인가요?"
    ]
    assert body["recommendations"][0]["targetRole"] is None


def test_question_recommendations_are_filtered_by_recipient_role(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    with session_factory() as db:
        db.add_all(
            [
                QuestionRecommendation(
                    question_text="엄마 전용 질문",
                    depth=QuestionDepth.TINY,
                    category="일상",
                    target_role=UserRole.MOTHER,
                    status=QuestionRecommendationStatus.ACTIVE,
                ),
                QuestionRecommendation(
                    question_text="아빠 전용 질문",
                    depth=QuestionDepth.TINY,
                    category="일상",
                    target_role=UserRole.FATHER,
                    status=QuestionRecommendationStatus.ACTIVE,
                ),
                QuestionRecommendation(
                    question_text="공통 질문",
                    depth=QuestionDepth.TINY,
                    category="일상",
                    target_role=None,
                    status=QuestionRecommendationStatus.ACTIVE,
                ),
            ]
        )
        db.commit()

    mother_response = client.get(
        (
            "/api/v1/questions/recommendations"
            f"?recipient_user_id={ids['mother_id']}&depth=tiny&limit=10"
        ),
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
    )
    father_response = client.get(
        (
            "/api/v1/questions/recommendations"
            f"?recipient_user_id={ids['father_id']}&depth=tiny&limit=10"
        ),
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
    )

    assert mother_response.status_code == 200
    mother_questions = {
        item["questionText"] for item in mother_response.json()["recommendations"]
    }
    assert mother_questions == {"엄마 전용 질문", "공통 질문"}
    assert "아빠 전용 질문" not in mother_questions

    assert father_response.status_code == 200
    father_questions = {
        item["questionText"] for item in father_response.json()["recommendations"]
    }
    assert father_questions == {"아빠 전용 질문", "공통 질문"}
    assert "엄마 전용 질문" not in father_questions


def test_question_recommendations_apply_category_and_depth_filters(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    with session_factory() as db:
        db.add_all(
            [
                QuestionRecommendation(
                    question_text="일상 tiny",
                    depth=QuestionDepth.TINY,
                    category="일상",
                    target_role=UserRole.MOTHER,
                    status=QuestionRecommendationStatus.ACTIVE,
                ),
                QuestionRecommendation(
                    question_text="추억 tiny",
                    depth=QuestionDepth.TINY,
                    category="추억",
                    target_role=UserRole.MOTHER,
                    status=QuestionRecommendationStatus.ACTIVE,
                ),
                QuestionRecommendation(
                    question_text="일상 deep",
                    depth=QuestionDepth.DEEP,
                    category="일상",
                    target_role=UserRole.MOTHER,
                    status=QuestionRecommendationStatus.ACTIVE,
                ),
            ]
        )
        db.commit()

    response = client.get(
        (
            "/api/v1/questions/recommendations"
            f"?recipient_user_id={ids['mother_id']}&depth=tiny&category=일상&limit=10"
        ),
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
    )

    assert response.status_code == 200
    assert [item["questionText"] for item in response.json()["recommendations"]] == [
        "일상 tiny"
    ]


def test_question_recommendations_reject_invalid_recipients(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    with session_factory() as db:
        outsider = create_user(
            db,
            public_id="other_family_mother",
            display_name="다른 가족 엄마",
            role=UserRole.MOTHER,
        )
        other_family = Family(
            public_id="other_family",
            name="다른 가족",
            invite_code="XYZ789",
            created_by_user_id=outsider.id,
            status=FamilyStatus.ACTIVE,
        )
        db.add(other_family)
        db.flush()
        db.add(
            FamilyMember(
                family_id=other_family.id,
                user_id=outsider.id,
                member_role=FamilyMemberRole.MOTHER,
                status=FamilyMemberStatus.ACTIVE,
            )
        )
        inactive_parent = create_user(
            db,
            public_id="inactive_parent",
            display_name="비활성 부모",
            role=UserRole.MOTHER,
        )
        db.flush()
        db.add(
            FamilyMember(
                family_id=int(ids["family_id"]),
                user_id=inactive_parent.id,
                member_role=FamilyMemberRole.MOTHER,
                status=FamilyMemberStatus.LEFT,
            )
        )
        db.commit()
        outsider_id = outsider.id
        inactive_parent_id = inactive_parent.id

    base_url = "/api/v1/questions/recommendations"
    headers = auth_headers(str(ids["child_public_id"]), auth_settings)
    missing_response = client.get(f"{base_url}?recipient_user_id=999999", headers=headers)
    other_family_response = client.get(
        f"{base_url}?recipient_user_id={outsider_id}",
        headers=headers,
    )
    child_response = client.get(f"{base_url}?recipient_user_id={ids['child_id']}", headers=headers)
    inactive_response = client.get(
        f"{base_url}?recipient_user_id={inactive_parent_id}",
        headers=headers,
    )

    assert missing_response.status_code == 404
    assert other_family_response.status_code == 403
    assert child_response.status_code == 400
    assert inactive_response.status_code == 400


def test_demo_mode_question_recommendations_use_demo_child_family(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    auth_settings.enable_demo_mode = True
    auth_settings.demo_user_id = int(ids["child_id"])
    with session_factory() as db:
        db.add_all(
            [
                QuestionRecommendation(
                    question_text="데모 엄마 질문",
                    depth=QuestionDepth.TINY,
                    target_role=UserRole.MOTHER,
                    status=QuestionRecommendationStatus.ACTIVE,
                ),
                QuestionRecommendation(
                    question_text="데모 아빠 질문",
                    depth=QuestionDepth.TINY,
                    target_role=UserRole.FATHER,
                    status=QuestionRecommendationStatus.ACTIVE,
                ),
            ]
        )
        db.commit()

    response = client.get(
        f"/api/v1/questions/recommendations?recipient_user_id={ids['mother_id']}&limit=10",
        headers={"X-Demo-Mode": "true"},
    )

    assert response.status_code == 200
    assert [item["questionText"] for item in response.json()["recommendations"]] == [
        "데모 엄마 질문"
    ]


def test_send_question_appears_in_recipient_answers_and_does_not_block_sending(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)

    send_response = client.post(
        "/api/v1/questions",
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
        json={
            "recipientUserId": ids["mother_id"],
            "depth": "medium",
            "questionText": "요즘 가장 마음에 남는 일은 무엇인가요?",
        },
    )

    assert send_response.status_code == 200
    sent_body = send_response.json()
    assert sent_body["recipientUserId"] == ids["mother_id"]
    assert sent_body["read"] is False
    assert sent_body["answered"] is False

    received_response = client.get(
        "/api/v1/answers/questions",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
    )
    assert received_response.status_code == 200
    assert [item["questionSendId"] for item in received_response.json()["questions"]] == [
        sent_body["questionSendId"]
    ]

    mother_send_response = client.post(
        "/api/v1/questions",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
        json={
            "recipientUserId": ids["child_id"],
            "depth": "tiny",
            "questionText": "오늘 점심은 맛있었나요?",
        },
    )
    assert mother_send_response.status_code == 200


def test_send_recommended_question_must_match_recipient_role(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    with session_factory() as db:
        recommendation = QuestionRecommendation(
            question_text="아빠에게만 보낼 추천 질문",
            depth=QuestionDepth.TINY,
            target_role=UserRole.FATHER,
            status=QuestionRecommendationStatus.ACTIVE,
        )
        db.add(recommendation)
        db.commit()
        recommendation_id = recommendation.id

    response = client.post(
        "/api/v1/questions",
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
        json={
            "recipientUserId": ids["mother_id"],
            "recommendationId": recommendation_id,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Recommendation is not available for this recipient"}


def test_received_question_detail_and_read_are_recipient_only(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    with session_factory() as db:
        question = create_question_send(
            db,
            sender_user_id=int(ids["child_id"]),
            recipient_user_id=int(ids["mother_id"]),
            family_id=int(ids["family_id"]),
        )
        db.commit()
        question_id = question.id

    forbidden_detail = client.get(
        f"/api/v1/answers/questions/{question_id}",
        headers=auth_headers(str(ids["father_public_id"]), auth_settings),
    )
    assert forbidden_detail.status_code == 404

    detail_response = client.get(
        f"/api/v1/answers/questions/{question_id}",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["read"] is False

    forbidden_read = client.patch(
        f"/api/v1/answers/questions/{question_id}/read",
        headers=auth_headers(str(ids["father_public_id"]), auth_settings),
    )
    assert forbidden_read.status_code == 404

    read_response = client.patch(
        f"/api/v1/answers/questions/{question_id}/read",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
    )
    assert read_response.status_code == 200
    assert read_response.json()["read"] is True
    assert read_response.json()["readAt"] is not None


def test_unanswered_filter_only_returns_pending_questions(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    now = datetime.now(UTC)
    with session_factory() as db:
        pending = create_question_send(
            db,
            sender_user_id=int(ids["child_id"]),
            recipient_user_id=int(ids["mother_id"]),
            family_id=int(ids["family_id"]),
            question_text="아직 답하지 않은 질문",
            sent_at=now,
        )
        answered = create_question_send(
            db,
            sender_user_id=int(ids["child_id"]),
            recipient_user_id=int(ids["mother_id"]),
            family_id=int(ids["family_id"]),
            question_text="이미 답한 질문",
            sent_at=now - timedelta(minutes=1),
            answered_at=now,
            status=QuestionSendStatus.ANSWERED,
        )
        db.commit()
        pending_id = pending.id
        answered_id = answered.id

    response = client.get(
        "/api/v1/answers/questions?unansweredOnly=true",
        headers=auth_headers(str(ids["mother_public_id"]), auth_settings),
    )

    assert response.status_code == 200
    question_ids = [item["questionSendId"] for item in response.json()["questions"]]
    assert question_ids == [pending_id]
    assert answered_id not in question_ids


def test_send_question_rejects_self_and_non_family_recipient(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    with session_factory() as db:
        outsider = create_user(
            db,
            public_id="outsider_public_id",
            display_name="외부 사용자",
            role=UserRole.MOTHER,
        )
        db.commit()
        outsider_id = outsider.id

    self_response = client.post(
        "/api/v1/questions",
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
        json={
            "recipientUserId": ids["child_id"],
            "depth": "tiny",
            "questionText": "나에게 보내는 질문",
        },
    )
    outsider_response = client.post(
        "/api/v1/questions",
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
        json={
            "recipientUserId": outsider_id,
            "depth": "tiny",
            "questionText": "가족이 아닌 사람에게 보내는 질문",
        },
    )

    assert self_response.status_code == 400
    assert self_response.json() == {"detail": "Cannot send a question to yourself"}
    assert outsider_response.status_code == 400
    assert outsider_response.json() == {"detail": "Recipient is not in the same family"}


def test_home_summary_returns_question_states_and_completed_count(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    now = datetime.now(UTC)
    with session_factory() as db:
        answered_sent = create_question_send(
            db,
            sender_user_id=int(ids["child_id"]),
            recipient_user_id=int(ids["mother_id"]),
            family_id=int(ids["family_id"]),
            question_text="답변 완료된 질문",
            read_at=now - timedelta(minutes=10),
            answered_at=now - timedelta(minutes=5),
            status=QuestionSendStatus.ANSWERED,
        )
        pending_received = create_question_send(
            db,
            sender_user_id=int(ids["mother_id"]),
            recipient_user_id=int(ids["child_id"]),
            family_id=int(ids["family_id"]),
            question_text="자녀에게 온 미답변 질문",
            sent_at=now,
        )
        db.commit()
        answered_sent_id = answered_sent.id
        pending_received_id = pending_received.id

    response = client.get(
        "/api/v1/home/summary",
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["familyConnected"] is True
    assert body["familyId"] == ids["family_id"]
    assert body["role"] == "child"
    assert body["connectedToParent"] is True
    assert body["connectedToChild"] is False
    assert body["todayCompletedCount"] == 1
    assert body["pendingReceivedQuestion"]["questionSendId"] == pending_received_id
    assert body["pendingReceivedQuestion"]["read"] is False
    assert body["latestSentQuestion"]["questionSendId"] == answered_sent_id
    assert body["latestSentQuestion"]["read"] is True
    assert body["latestSentQuestion"]["answered"] is True
    assert body["aiStatus"] is None


def test_home_summary_completed_count_uses_korea_day_boundary(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    ids = create_family_with_members(session_factory)
    with session_factory() as db:
        create_question_send(
            db,
            sender_user_id=int(ids["child_id"]),
            recipient_user_id=int(ids["mother_id"]),
            family_id=int(ids["family_id"]),
            question_text="한국 시간 오늘 새벽 답변",
            sent_at=datetime(2026, 7, 5, 15, 20, tzinfo=UTC),
            answered_at=datetime(2026, 7, 5, 15, 30, tzinfo=UTC),
            status=QuestionSendStatus.ANSWERED,
        )
        create_question_send(
            db,
            sender_user_id=int(ids["child_id"]),
            recipient_user_id=int(ids["mother_id"]),
            family_id=int(ids["family_id"]),
            question_text="한국 시간 어제 답변",
            sent_at=datetime(2026, 7, 5, 14, 50, tzinfo=UTC),
            answered_at=datetime(2026, 7, 5, 14, 59, tzinfo=UTC),
            status=QuestionSendStatus.ANSWERED,
        )
        db.commit()

    app.dependency_overrides[get_question_loop_service] = lambda: QuestionLoopService(
        now_provider=lambda: datetime(2026, 7, 5, 16, 0, tzinfo=UTC),
    )

    response = client.get(
        "/api/v1/home/summary",
        headers=auth_headers(str(ids["child_public_id"]), auth_settings),
    )
    app.dependency_overrides.pop(get_question_loop_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["todayCompletedCount"] == 1
