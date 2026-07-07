from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.question_send import QuestionSend, QuestionSendStatus
from app.models.user import User
from app.schemas.answers import (
    AnswerSubmitRequest,
    AnswerSubmitResponse,
    AnswerUploadUrlRequest,
    AnswerUploadUrlResponse,
)
from app.schemas.clips import ClipDetailResponse
from app.schemas.question_loop import (
    QuestionUserSummary,
    ReadQuestionResponse,
    ReceivedQuestionDetail,
    ReceivedQuestionItem,
    ReceivedQuestionsResponse,
)
from app.services.ai_job_service import AiJobService
from app.services.answer_service import (
    AlreadyAnsweredError,
    AnswerService,
    NotRecipientError,
    QuestionSendNotFoundError,
    UnsupportedVideoMimeTypeError,
)
from app.services.clip_service import (
    ActiveFamilyRequiredError,
    AnswerNotFoundError,
    ClipNotReadyError,
    ClipService,
)
from app.services.question_loop_service import (
    QuestionLoopService,
    ReceivedQuestionNotFoundError,
)
from app.services.storage_service import StorageService

router = APIRouter(prefix="/answers", tags=["answers"])


def get_question_loop_service() -> QuestionLoopService:
    return QuestionLoopService()


def get_storage_service() -> StorageService:
    return StorageService()


def get_answer_service(
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
) -> AnswerService:
    return AnswerService(storage_service=storage_service)


def get_clip_service(
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
) -> ClipService:
    return ClipService(storage_service=storage_service)


def get_ai_job_service(
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
) -> AiJobService:
    return AiJobService(storage_service=storage_service)


@router.post(
    "/upload-url",
    response_model=AnswerUploadUrlResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_answer_upload_url(
    payload: AnswerUploadUrlRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[AnswerService, Depends(get_answer_service)],
) -> AnswerUploadUrlResponse:
    try:
        upload_url, expires_at = service.create_upload_url(
            db,
            user=current_user,
            question_send_id=payload.question_send_id,
            video_mime_type=payload.video_mime_type,
        )
    except QuestionSendNotFoundError as exc:
        raise _not_found("Question send was not found") from exc
    except NotRecipientError as exc:
        raise _forbidden(str(exc)) from exc
    except AlreadyAnsweredError as exc:
        raise _conflict(str(exc)) from exc
    except UnsupportedVideoMimeTypeError as exc:
        raise _unsupported_media_type(str(exc)) from exc

    return AnswerUploadUrlResponse(uploadUrl=upload_url, expiresAt=expires_at)


@router.post("", response_model=AnswerSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_answer(
    payload: AnswerSubmitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[AnswerService, Depends(get_answer_service)],
    ai_job_service: Annotated[AiJobService, Depends(get_ai_job_service)],
    background_tasks: BackgroundTasks,
) -> AnswerSubmitResponse:
    try:
        answer = service.submit_answer(
            db,
            user=current_user,
            question_send_id=payload.question_send_id,
            video_mime_type=payload.video_mime_type,
            video_duration_seconds=payload.video_duration_seconds,
            video_size_bytes=payload.video_size_bytes,
        )
    except QuestionSendNotFoundError as exc:
        raise _not_found("Question send was not found") from exc
    except NotRecipientError as exc:
        raise _forbidden(str(exc)) from exc
    except AlreadyAnsweredError as exc:
        raise _conflict(str(exc)) from exc
    except UnsupportedVideoMimeTypeError as exc:
        raise _unsupported_media_type(str(exc)) from exc

    background_tasks.add_task(ai_job_service.dispatch_job, db, answer=answer)

    return AnswerSubmitResponse(
        answerId=answer.id,
        questionSendId=answer.question_send_id,
        status=answer.status,
        submittedAt=answer.submitted_at,
    )


@router.get("/{answer_id}/clip", response_model=ClipDetailResponse)
def get_answer_clip(
    answer_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[ClipService, Depends(get_clip_service)],
) -> ClipDetailResponse:
    try:
        answer, video_clip = service.get_clip_detail(
            db,
            user=current_user,
            answer_id=answer_id,
        )
    except ActiveFamilyRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (AnswerNotFoundError, ClipNotReadyError) as exc:
        raise _not_found("Clip was not found") from exc

    return ClipDetailResponse(
        answerId=answer.id,
        videoUrl=service.resolve_video_url(video_clip),
        thumbnailUrl=service.resolve_thumbnail_url(answer),
        transcript=video_clip.transcript,
        transcriptSegments=video_clip.transcript_segments,
        title=video_clip.title,
        quote=video_clip.quote,
        oneLineSummary=video_clip.one_line_summary,
        emotionTags=video_clip.emotion_tags,
        fourcutTitle=video_clip.fourcut_title,
    )


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


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _unsupported_media_type(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail)
