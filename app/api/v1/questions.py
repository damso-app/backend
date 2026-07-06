from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.family_member import FamilyMember
from app.models.question_recommendation import QuestionDepth, QuestionRecommendation
from app.models.question_send import QuestionSend, QuestionSendStatus
from app.models.user import User
from app.schemas.question_loop import (
    QuestionRecipientItem,
    QuestionRecipientsResponse,
    QuestionRecommendationItem,
    QuestionRecommendationsResponse,
    QuestionSendRequest,
    QuestionSendResponse,
)
from app.services.question_loop_service import (
    ActiveFamilyRequiredError,
    InvalidQuestionPayloadError,
    InvalidRecipientError,
    QuestionLoopService,
    RecommendationNotFoundError,
)

router = APIRouter(prefix="/questions", tags=["questions"])


def get_question_loop_service() -> QuestionLoopService:
    return QuestionLoopService()


@router.get("/recipients", response_model=QuestionRecipientsResponse)
def list_question_recipients(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[QuestionLoopService, Depends(get_question_loop_service)],
) -> QuestionRecipientsResponse:
    try:
        recipients = service.list_recipients(db, user=current_user)
    except ActiveFamilyRequiredError as exc:
        raise _bad_request("Active family is required") from exc

    return QuestionRecipientsResponse(
        recipients=[_recipient_item(member) for member in recipients],
    )


@router.get("/recommendations", response_model=QuestionRecommendationsResponse)
def list_question_recommendations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[QuestionLoopService, Depends(get_question_loop_service)],
    depth: Annotated[QuestionDepth, Query()],
    limit: Annotated[int, Query(ge=1, le=20)] = 3,
) -> QuestionRecommendationsResponse:
    _ = current_user
    recommendations = service.list_recommendations(db, depth=depth, limit=limit)
    return QuestionRecommendationsResponse(
        recommendations=[_recommendation_item(item) for item in recommendations],
    )


@router.post("", response_model=QuestionSendResponse)
def send_question(
    payload: QuestionSendRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[QuestionLoopService, Depends(get_question_loop_service)],
) -> QuestionSendResponse:
    try:
        question_send = service.send_question(
            db,
            sender=current_user,
            recipient_user_id=payload.recipient_user_id,
            depth=payload.depth,
            question_text=payload.question_text,
            recommendation_id=payload.recommendation_id,
        )
    except ActiveFamilyRequiredError as exc:
        raise _bad_request("Active family is required") from exc
    except InvalidRecipientError as exc:
        raise _bad_request(str(exc)) from exc
    except InvalidQuestionPayloadError as exc:
        raise _bad_request("Question text and depth are required") from exc
    except RecommendationNotFoundError as exc:
        raise _not_found("Question recommendation was not found") from exc

    return _question_send_response(question_send)


def _recipient_item(member: FamilyMember) -> QuestionRecipientItem:
    return QuestionRecipientItem(
        userId=member.user.id,
        displayName=member.user.display_name,
        profileImageUrl=member.user.profile_image_url,
        role=member.user.role,
        memberRole=member.member_role,
    )


def _recommendation_item(item: QuestionRecommendation) -> QuestionRecommendationItem:
    return QuestionRecommendationItem(
        recommendationId=item.id,
        questionText=item.question_text,
        depth=item.depth,
        category=item.category,
    )


def _question_send_response(question_send: QuestionSend) -> QuestionSendResponse:
    return QuestionSendResponse(
        questionSendId=question_send.id,
        recipientUserId=question_send.recipient_user_id,
        questionText=question_send.question_text,
        depth=question_send.depth,
        source=question_send.source,
        sentAt=question_send.sent_at,
        read=question_send.read_at is not None,
        answered=_is_answered(question_send),
    )


def _is_answered(question_send: QuestionSend) -> bool:
    return (
        question_send.answered_at is not None
        or question_send.status == QuestionSendStatus.ANSWERED
    )


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
