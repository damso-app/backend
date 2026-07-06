from dataclasses import dataclass
from datetime import UTC, datetime, time

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.family import Family, FamilyStatus
from app.models.family_member import FamilyMember, FamilyMemberRole, FamilyMemberStatus
from app.models.question_recommendation import (
    QuestionDepth,
    QuestionRecommendation,
    QuestionRecommendationStatus,
)
from app.models.question_send import QuestionSend, QuestionSendSource, QuestionSendStatus
from app.models.user import User, UserRole


class QuestionLoopServiceError(Exception):
    pass


class ActiveFamilyRequiredError(QuestionLoopServiceError):
    pass


class InvalidRecipientError(QuestionLoopServiceError):
    pass


class RecommendationNotFoundError(QuestionLoopServiceError):
    pass


class ReceivedQuestionNotFoundError(QuestionLoopServiceError):
    pass


class InvalidQuestionPayloadError(QuestionLoopServiceError):
    pass


@dataclass(frozen=True)
class HomeSummary:
    family_connected: bool
    family_id: int | None
    role: UserRole | None
    connected_to_child: bool
    connected_to_parent: bool
    today_completed_count: int
    pending_received_question: QuestionSend | None
    latest_sent_question: QuestionSend | None
    ai_status: str | None


class QuestionLoopService:
    def get_home_summary(self, db: Session, *, user: User) -> HomeSummary:
        membership = self._active_membership(db, user_id=user.id)
        if membership is None:
            return HomeSummary(
                family_connected=False,
                family_id=None,
                role=user.role,
                connected_to_child=False,
                connected_to_parent=False,
                today_completed_count=0,
                pending_received_question=None,
                latest_sent_question=None,
                ai_status=None,
            )

        family_id = membership.family_id
        connected_to_child = self._family_has_role(
            db,
            family_id=family_id,
            role=FamilyMemberRole.CHILD,
            excluding_user_id=user.id,
        )
        connected_to_parent = self._family_has_any_role(
            db,
            family_id=family_id,
            roles=(FamilyMemberRole.MOTHER, FamilyMemberRole.FATHER),
            excluding_user_id=user.id,
        )

        today_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
        today_completed_count = db.scalar(
            select(func.count(QuestionSend.id)).where(
                QuestionSend.family_id == family_id,
                QuestionSend.answered_at.is_not(None),
                QuestionSend.answered_at >= today_start,
            )
        )

        pending_received_question = db.scalar(
            select(QuestionSend)
            .where(
                QuestionSend.recipient_user_id == user.id,
                QuestionSend.status == QuestionSendStatus.SENT,
                QuestionSend.answered_at.is_(None),
            )
            .order_by(QuestionSend.sent_at.desc(), QuestionSend.id.desc())
            .limit(1)
        )
        latest_sent_question = db.scalar(
            select(QuestionSend)
            .where(QuestionSend.sender_user_id == user.id)
            .order_by(QuestionSend.sent_at.desc(), QuestionSend.id.desc())
            .limit(1)
        )

        return HomeSummary(
            family_connected=True,
            family_id=family_id,
            role=user.role,
            connected_to_child=connected_to_child,
            connected_to_parent=connected_to_parent,
            today_completed_count=today_completed_count or 0,
            pending_received_question=pending_received_question,
            latest_sent_question=latest_sent_question,
            ai_status=None,
        )

    def list_recipients(self, db: Session, *, user: User) -> list[FamilyMember]:
        membership = self._require_active_membership(db, user=user)
        return list(
            db.scalars(
                select(FamilyMember)
                .join(User, User.id == FamilyMember.user_id)
                .where(
                    FamilyMember.family_id == membership.family_id,
                    FamilyMember.user_id != user.id,
                    FamilyMember.status == FamilyMemberStatus.ACTIVE,
                    User.deleted_at.is_(None),
                )
                .order_by(FamilyMember.id.asc())
            )
        )

    def list_recommendations(
        self,
        db: Session,
        *,
        depth: QuestionDepth,
        limit: int,
    ) -> list[QuestionRecommendation]:
        return list(
            db.scalars(
                select(QuestionRecommendation)
                .where(
                    QuestionRecommendation.depth == depth,
                    QuestionRecommendation.status == QuestionRecommendationStatus.ACTIVE,
                )
                .order_by(func.random())
                .limit(limit)
            )
        )

    def send_question(
        self,
        db: Session,
        *,
        sender: User,
        recipient_user_id: int,
        depth: QuestionDepth | None,
        question_text: str | None,
        recommendation_id: int | None,
    ) -> QuestionSend:
        membership = self._require_active_membership(db, user=sender)
        recipient_membership = self._active_membership(db, user_id=recipient_user_id)
        if recipient_user_id == sender.id:
            raise InvalidRecipientError("Cannot send a question to yourself")
        if recipient_membership is None or recipient_membership.family_id != membership.family_id:
            raise InvalidRecipientError("Recipient is not in the same family")

        recommendation = None
        source = QuestionSendSource.CUSTOM
        resolved_depth = depth
        resolved_text = (question_text or "").strip()

        if recommendation_id is not None:
            recommendation = db.scalar(
                select(QuestionRecommendation)
                .where(
                    QuestionRecommendation.id == recommendation_id,
                    QuestionRecommendation.status == QuestionRecommendationStatus.ACTIVE,
                )
                .limit(1)
            )
            if recommendation is None:
                raise RecommendationNotFoundError("Question recommendation was not found")
            source = QuestionSendSource.RECOMMENDATION
            resolved_depth = recommendation.depth
            resolved_text = recommendation.question_text

        if resolved_depth is None or not resolved_text:
            raise InvalidQuestionPayloadError("Question text and depth are required")

        question_send = QuestionSend(
            sender_user_id=sender.id,
            recipient_user_id=recipient_user_id,
            family_id=membership.family_id,
            question_text=resolved_text,
            depth=resolved_depth,
            source=source,
            recommendation_id=recommendation.id if recommendation is not None else None,
            status=QuestionSendStatus.SENT,
        )
        db.add(question_send)
        db.commit()
        db.refresh(question_send)
        return question_send

    def list_received_questions(
        self,
        db: Session,
        *,
        user: User,
        unanswered_only: bool,
        sort: str,
    ) -> list[QuestionSend]:
        statement = select(QuestionSend).where(QuestionSend.recipient_user_id == user.id)
        if unanswered_only:
            statement = statement.where(
                QuestionSend.answered_at.is_(None),
                QuestionSend.status != QuestionSendStatus.ANSWERED,
            )
        if sort == "unanswered_first":
            statement = statement.order_by(
                case(
                    (
                        and_(
                            QuestionSend.answered_at.is_(None),
                            QuestionSend.status != QuestionSendStatus.ANSWERED,
                        ),
                        0,
                    ),
                    else_=1,
                ),
                QuestionSend.sent_at.desc(),
                QuestionSend.id.desc(),
            )
        else:
            statement = statement.order_by(QuestionSend.sent_at.desc(), QuestionSend.id.desc())
        return list(db.scalars(statement))

    def get_received_question(
        self,
        db: Session,
        *,
        user: User,
        question_send_id: int,
    ) -> QuestionSend:
        question_send = db.scalar(
            select(QuestionSend)
            .where(
                QuestionSend.id == question_send_id,
                QuestionSend.recipient_user_id == user.id,
            )
            .limit(1)
        )
        if question_send is None:
            raise ReceivedQuestionNotFoundError("Received question was not found")
        return question_send

    def mark_received_question_read(
        self,
        db: Session,
        *,
        user: User,
        question_send_id: int,
    ) -> QuestionSend:
        question_send = self.get_received_question(
            db,
            user=user,
            question_send_id=question_send_id,
        )
        if question_send.read_at is None:
            question_send.read_at = datetime.now(UTC)
            db.commit()
            db.refresh(question_send)
        return question_send

    def _require_active_membership(self, db: Session, *, user: User) -> FamilyMember:
        membership = self._active_membership(db, user_id=user.id)
        if membership is None:
            raise ActiveFamilyRequiredError("Active family is required")
        return membership

    @staticmethod
    def _active_membership(db: Session, *, user_id: int) -> FamilyMember | None:
        return db.scalar(
            select(FamilyMember)
            .join(Family, Family.id == FamilyMember.family_id)
            .where(
                FamilyMember.user_id == user_id,
                FamilyMember.status == FamilyMemberStatus.ACTIVE,
                Family.status == FamilyStatus.ACTIVE,
                Family.deleted_at.is_(None),
            )
            .limit(1)
        )

    @staticmethod
    def _family_has_role(
        db: Session,
        *,
        family_id: int,
        role: FamilyMemberRole,
        excluding_user_id: int,
    ) -> bool:
        return (
            db.scalar(
                select(FamilyMember.id)
                .where(
                    FamilyMember.family_id == family_id,
                    FamilyMember.user_id != excluding_user_id,
                    FamilyMember.member_role == role,
                    FamilyMember.status == FamilyMemberStatus.ACTIVE,
                )
                .limit(1)
            )
            is not None
        )

    @staticmethod
    def _family_has_any_role(
        db: Session,
        *,
        family_id: int,
        roles: tuple[FamilyMemberRole, ...],
        excluding_user_id: int,
    ) -> bool:
        return (
            db.scalar(
                select(FamilyMember.id)
                .where(
                    FamilyMember.family_id == family_id,
                    FamilyMember.user_id != excluding_user_id,
                    FamilyMember.member_role.in_(roles),
                    FamilyMember.status == FamilyMemberStatus.ACTIVE,
                )
                .limit(1)
            )
            is not None
        )
