from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.dependencies import bearer_scheme, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.answer import AnswerStatus
from app.models.question_send import QuestionSend, QuestionSendStatus
from app.models.user import User
from app.schemas.answers import (
    AiCallbackRequest,
    AiCallbackResponse,
    AnswerProgressResponse,
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
from app.services.ai_callback_service import (
    AiCallbackService,
    AnswerIdMismatchError,
    InvalidCallbackTokenError,
    InvalidPipelineResultError,
)
from app.services.ai_callback_service import AnswerNotFoundError as AiCallbackAnswerNotFoundError
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
from app.services.realtime_service import RealtimeService
from app.services.storage_service import StorageService
from app.services.thumbnail_service import ThumbnailService

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
    settings: Annotated[Settings, Depends(get_settings)],
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
) -> AiJobService:
    return AiJobService(settings=settings, storage_service=storage_service)


def get_thumbnail_service(
    settings: Annotated[Settings, Depends(get_settings)],
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
) -> ThumbnailService:
    return ThumbnailService(settings=settings, storage_service=storage_service)


def get_realtime_service(settings: Annotated[Settings, Depends(get_settings)]) -> RealtimeService:
    return RealtimeService(settings=settings)


def get_ai_callback_service(
    settings: Annotated[Settings, Depends(get_settings)],
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
    realtime_service: Annotated[RealtimeService, Depends(get_realtime_service)],
) -> AiCallbackService:
    return AiCallbackService(
        settings=settings,
        storage_service=storage_service,
        realtime_service=realtime_service,
    )


@router.post(
    "/upload-url",
    response_model=AnswerUploadUrlResponse,
    status_code=status.HTTP_201_CREATED,
    summary="답변 영상 업로드 URL 발급",
    description=(
        "답변 영상을 업로드할 수 있는 signed URL을 발급합니다. "
        "실제 업로드 완료 후 별도로 답변 제출(POST /answers)을 호출해야 합니다."
    ),
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


@router.post(
    "",
    response_model=AnswerSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="답변 제출",
    description=(
        "업로드된 영상으로 답변을 제출합니다. "
        "제출 즉시 status는 processing이 되며, AI 처리 파이프라인이 백그라운드로 트리거됩니다."
    ),
)
def submit_answer(
    payload: AnswerSubmitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[AnswerService, Depends(get_answer_service)],
    ai_job_service: Annotated[AiJobService, Depends(get_ai_job_service)],
    thumbnail_service: Annotated[ThumbnailService, Depends(get_thumbnail_service)],
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
    background_tasks.add_task(thumbnail_service.generate_thumbnail, db, answer=answer)

    return AnswerSubmitResponse(
        answerId=answer.id,
        questionSendId=answer.question_send_id,
        status=answer.status,
        submittedAt=answer.submitted_at,
    )


@router.get(
    "/{answer_id}/clip",
    response_model=ClipDetailResponse,
    summary="답변 클립 상세 조회",
    description=(
        "AI 처리가 완료된 답변의 비디오 클립 상세 정보(영상 URL, 썸네일, 자막, 요약 등)를 "
        "조회합니다. 처리가 아직 완료되지 않은 경우 404를 반환합니다."
    ),
)
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
        questionText=answer.question_send.question_text,
        videoUrl=service.resolve_video_url(video_clip),
        videoDurationSeconds=answer.video_duration_seconds,
        thumbnailUrl=service.resolve_thumbnail_url(answer),
        transcript=video_clip.transcript,
        transcriptSegments=video_clip.transcript_segments,
        title=video_clip.title,
        quote=video_clip.quote,
        oneLineSummary=video_clip.one_line_summary,
        emotionTags=video_clip.emotion_tags,
        fourcutTitle=video_clip.fourcut_title,
    )


@router.get(
    "/{answer_id}/progress",
    response_model=AnswerProgressResponse,
    summary="답변 AI 처리 진행률 조회",
    description=(
        "답변의 AI 처리 진행 상태를 조회합니다. status가 processing이 아니면 AI 서버를 호출하지 "
        "않고 즉시 반환합니다. processing인 경우 AI 서버의 job 상태를 폴링해서 진행률, 현재 "
        "처리 단계, 예상 남은 시간, aiJobStatus(AI 서버 자체 job 상태)를 함께 내려줍니다. "
        "status는 이 백엔드의 answers.status를 그대로 반영하므로, AI 서버가 처리를 끝내고도 "
        "콜백이 아직 도착하지 않은 구간에서는 status=processing이면서 aiJobStatus=completed일 "
        "수 있다 — 이 조합으로 '처리 중'과 '완료 후 콜백 대기 중'을 구분할 수 있다."
    ),
)
def get_answer_progress(
    answer_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    clip_service: Annotated[ClipService, Depends(get_clip_service)],
    ai_job_service: Annotated[AiJobService, Depends(get_ai_job_service)],
) -> AnswerProgressResponse:
    try:
        answer = clip_service.get_answer_for_family(db, user=current_user, answer_id=answer_id)
    except ActiveFamilyRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except AnswerNotFoundError as exc:
        raise _not_found("Answer was not found") from exc

    if answer.status != AnswerStatus.PROCESSING or answer.ai_job_id is None:
        return AnswerProgressResponse(answerId=answer.id, status=answer.status)

    progress = ai_job_service.get_job_progress(ai_job_id=answer.ai_job_id)
    if progress is None:
        return AnswerProgressResponse(answerId=answer.id, status=answer.status)

    return AnswerProgressResponse(
        answerId=answer.id,
        status=answer.status,
        progress=progress.get("progress"),
        currentStepLabel=progress.get("currentStepLabel"),
        estimatedRemainingSeconds=progress.get("estimatedRemainingSeconds"),
        aiJobStatus=progress.get("status"),
    )


@router.post(
    "/{answer_id}/ai-callback",
    response_model=AiCallbackResponse,
    summary="AI 처리 결과 콜백 수신",
    description=(
        "AI 서버가 답변 영상 처리 결과(성공/실패)를 전달하는 콜백 엔드포인트입니다. "
        "사용자 로그인 토큰이 아닌 별도의 callbackToken(Bearer)으로 인증합니다."
    ),
)
def receive_ai_callback(
    answer_id: int,
    payload: AiCallbackRequest,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[AiCallbackService, Depends(get_ai_callback_service)],
) -> AiCallbackResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        answer = service.handle_callback(
            db,
            answer_id=answer_id,
            callback_token=credentials.credentials,
            payload=payload,
        )
    except AiCallbackAnswerNotFoundError as exc:
        raise _not_found("Answer was not found") from exc
    except InvalidCallbackTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid callback token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (AnswerIdMismatchError, InvalidPipelineResultError) as exc:
        raise _bad_request(str(exc)) from exc

    return AiCallbackResponse(answerId=answer.id, status=answer.status)


@router.get(
    "/questions",
    response_model=ReceivedQuestionsResponse,
    summary="받은 질문 목록 조회",
    description=(
        "현재 사용자가 받은 질문 목록을 조회합니다. "
        "unansweredOnly로 미답변만 필터링하거나 sort로 정렬 기준을 지정할 수 있습니다."
    ),
)
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


@router.get(
    "/questions/{question_send_id}",
    response_model=ReceivedQuestionDetail,
    summary="받은 질문 상세 조회",
    description="받은 질문 하나의 상세 정보를 조회합니다.",
)
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


@router.patch(
    "/questions/{question_send_id}/read",
    response_model=ReadQuestionResponse,
    summary="받은 질문 읽음 처리",
    description="받은 질문을 읽음 상태로 표시합니다.",
)
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
        answerId=question.answer.id if question.answer is not None else None,
    )


def _is_answered(question: QuestionSend) -> bool:
    return question.answered_at is not None or question.status == QuestionSendStatus.ANSWERED


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _unsupported_media_type(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail)
