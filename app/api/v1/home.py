from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.question_send import QuestionSend, QuestionSendStatus
from app.models.user import User
from app.schemas.question_loop import (
    HomeSummaryResponse,
    PendingReceivedQuestionSummary,
    QuestionUserSummary,
    SentQuestionSummary,
)
from app.services.question_loop_service import HomeSummary, QuestionLoopService

router = APIRouter(prefix="/home", tags=["home"])


def get_question_loop_service() -> QuestionLoopService:
    return QuestionLoopService()


@router.get("/summary", response_model=HomeSummaryResponse)
def get_home_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[QuestionLoopService, Depends(get_question_loop_service)],
) -> HomeSummaryResponse:
    summary = service.get_home_summary(db, user=current_user)
    return _home_summary_response(summary)


def _home_summary_response(summary: HomeSummary) -> HomeSummaryResponse:
    return HomeSummaryResponse(
        familyConnected=summary.family_connected,
        familyId=summary.family_id,
        role=summary.role,
        connectedToChild=summary.connected_to_child,
        connectedToParent=summary.connected_to_parent,
        todayCompletedCount=summary.today_completed_count,
        pendingReceivedQuestion=_pending_received_question(summary.pending_received_question),
        latestSentQuestion=_sent_question(summary.latest_sent_question),
        aiStatus=summary.ai_status,
    )


def _pending_received_question(
    question: QuestionSend | None,
) -> PendingReceivedQuestionSummary | None:
    if question is None:
        return None
    return PendingReceivedQuestionSummary(
        questionSendId=question.id,
        sender=QuestionUserSummary(
            userId=question.sender.id,
            displayName=question.sender.display_name,
            profileImageUrl=question.sender.profile_image_url,
            role=question.sender.role,
        ),
        receivedAt=question.sent_at,
        read=question.read_at is not None,
        readAt=question.read_at,
    )


def _sent_question(question: QuestionSend | None) -> SentQuestionSummary | None:
    if question is None:
        return None
    return SentQuestionSummary(
        questionSendId=question.id,
        recipient=QuestionUserSummary(
            userId=question.recipient.id,
            displayName=question.recipient.display_name,
            profileImageUrl=question.recipient.profile_image_url,
            role=question.recipient.role,
        ),
        questionText=question.question_text,
        sentAt=question.sent_at,
        read=question.read_at is not None,
        readAt=question.read_at,
        answered=question.answered_at is not None or question.status == QuestionSendStatus.ANSWERED,
        answeredAt=question.answered_at,
        aiStatus=None,
    )
