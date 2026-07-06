from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.question_send import QuestionSend, QuestionSendStatus
from app.models.user import User
from app.schemas.question_loop import (
    QuestionUserSummary,
    ReadQuestionResponse,
    ReceivedQuestionDetail,
    ReceivedQuestionItem,
    ReceivedQuestionsResponse,
)
from app.services.question_loop_service import (
    QuestionLoopService,
    ReceivedQuestionNotFoundError,
)

router = APIRouter(prefix="/answers", tags=["answers"])


def get_question_loop_service() -> QuestionLoopService:
    return QuestionLoopService()


@router.get("/questions", response_model=ReceivedQuestionsResponse)
def list_received_questions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[QuestionLoopService, Depends(get_question_loop_service)],
    unanswered_only: Annotated[bool, Query(alias="unansweredOnly")] = False,
    sort: Annotated[Literal["latest", "unanswered_first"], Query()] = "latest",
) -> ReceivedQuestionsResponse:
    questions = service.list_received_questions(
        db,
        user=current_user,
        unanswered_only=unanswered_only,
        sort=sort,
    )
    return ReceivedQuestionsResponse(
        questions=[_received_question_item(question) for question in questions],
    )


@router.get("/questions/{question_send_id}", response_model=ReceivedQuestionDetail)
def get_received_question(
    question_send_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[QuestionLoopService, Depends(get_question_loop_service)],
) -> ReceivedQuestionDetail:
    try:
        question = service.get_received_question(
            db,
            user=current_user,
            question_send_id=question_send_id,
        )
    except ReceivedQuestionNotFoundError as exc:
        raise _not_found("Received question was not found") from exc

    return ReceivedQuestionDetail(
        **_received_question_item(question).model_dump(by_alias=True),
        source=question.source,
        recommendationId=question.recommendation_id,
    )


@router.patch("/questions/{question_send_id}/read", response_model=ReadQuestionResponse)
def mark_received_question_read(
    question_send_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[QuestionLoopService, Depends(get_question_loop_service)],
) -> ReadQuestionResponse:
    try:
        question = service.mark_received_question_read(
            db,
            user=current_user,
            question_send_id=question_send_id,
        )
    except ReceivedQuestionNotFoundError as exc:
        raise _not_found("Received question was not found") from exc

    if question.read_at is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Read timestamp was not set",
        )

    return ReadQuestionResponse(
        questionSendId=question.id,
        read=True,
        readAt=question.read_at,
    )


def _received_question_item(question: QuestionSend) -> ReceivedQuestionItem:
    return ReceivedQuestionItem(
        questionSendId=question.id,
        sender=QuestionUserSummary(
            userId=question.sender.id,
            displayName=question.sender.display_name,
            profileImageUrl=question.sender.profile_image_url,
            role=question.sender.role,
        ),
        questionText=question.question_text,
        depth=question.depth,
        receivedAt=question.sent_at,
        read=question.read_at is not None,
        readAt=question.read_at,
        answered=_is_answered(question),
        answeredAt=question.answered_at,
        status=question.status,
    )


def _is_answered(question: QuestionSend) -> bool:
    return question.answered_at is not None or question.status == QuestionSendStatus.ANSWERED


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
