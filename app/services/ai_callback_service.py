from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import AiCallbackTokenError, verify_ai_callback_token
from app.models.answer import Answer, AnswerStatus
from app.models.video_clip import VideoClip, VideoClipAiResult
from app.schemas.answers import AiCallbackRequest
from app.services.realtime_service import RealtimeService
from app.services.storage_service import StorageService
from app.services.video_paths import edited_video_object_path

_AI_STEP_STATUS = "AI-008"
_AI_STEP_DIARY = "AI-003"
_AI_STEP_QUOTE = "AI-004"
_AI_STEP_EMOTION = "AI-005"
_AI_STEP_FOURCUT = "AI-009"
_AI_STEP_FALLBACK = "AI-010"


class AiCallbackServiceError(Exception):
    pass


class AnswerNotFoundError(AiCallbackServiceError):
    pass


class InvalidCallbackTokenError(AiCallbackServiceError):
    pass


class AnswerIdMismatchError(AiCallbackServiceError):
    pass


class InvalidPipelineResultError(AiCallbackServiceError):
    pass


class AiCallbackService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        storage_service: StorageService | None = None,
        realtime_service: RealtimeService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._storage_service = storage_service or StorageService()
        self._realtime_service = realtime_service or RealtimeService(settings=self._settings)

    def handle_callback(
        self,
        db: Session,
        *,
        answer_id: int,
        callback_token: str,
        payload: AiCallbackRequest,
    ) -> Answer:
        try:
            verify_ai_callback_token(
                callback_token,
                answer_id=answer_id,
                settings=self._settings,
            )
        except AiCallbackTokenError as exc:
            raise InvalidCallbackTokenError("Invalid callback token") from exc

        answer = db.scalar(select(Answer).where(Answer.id == answer_id).limit(1))
        if answer is None:
            raise AnswerNotFoundError("Answer was not found")

        if payload.answer_id != str(answer_id):
            raise AnswerIdMismatchError("answerId in the request body does not match the path")

        if answer.status in (AnswerStatus.COMPLETED, AnswerStatus.FAILED):
            return answer

        ai_008 = payload.pipeline_results.get(_AI_STEP_STATUS, {})
        pipeline_status = ai_008.get("status")

        if pipeline_status == "completed":
            self._complete(db, answer=answer, payload=payload)
        elif pipeline_status == "failed":
            self._fail(db, answer=answer, ai_008=ai_008, payload=payload)
        else:
            raise InvalidPipelineResultError(
                f"Unexpected {_AI_STEP_STATUS}.status: {pipeline_status!r}"
            )

        return answer

    def _complete(self, db: Session, *, answer: Answer, payload: AiCallbackRequest) -> None:
        ai_003 = payload.pipeline_results.get(_AI_STEP_DIARY, {})
        ai_004 = payload.pipeline_results.get(_AI_STEP_QUOTE, {})
        ai_005 = payload.pipeline_results.get(_AI_STEP_EMOTION, {})
        ai_009 = payload.pipeline_results.get(_AI_STEP_FOURCUT, {})

        video_clip = VideoClip(
            answer_id=answer.id,
            video_url=self._edited_video_gs_uri(answer),
            transcript=payload.transcript,
            transcript_segments=payload.segments,
            title=ai_003.get("diaryTitle"),
            one_line_summary=ai_003.get("oneLineSummary"),
            quote=ai_004.get("representativeQuote"),
            emotion_tags=ai_005.get("emotionTags"),
            fourcut_title=ai_009.get("fourCutTitle"),
        )
        db.add(video_clip)
        try:
            db.flush()
        except IntegrityError:
            # A concurrent callback for the same answer already won this race
            # (ux_video_clips_answer_id). Treat this delivery as a no-op retry
            # instead of surfacing an unhandled 500 to the AI server.
            db.rollback()
            return

        db.add(
            VideoClipAiResult(
                video_clip_id=video_clip.id,
                ai_raw_response=payload.pipeline_results,
            )
        )

        answer.status = AnswerStatus.COMPLETED
        db.commit()

        self._realtime_service.broadcast_answer_completed(
            family_id=answer.family_id,
            answer_id=answer.id,
            thumbnail_url=self._resolve_thumbnail_url(answer),
        )

    def _fail(
        self,
        db: Session,
        *,
        answer: Answer,
        ai_008: dict,
        payload: AiCallbackRequest,
    ) -> None:
        ai_010 = payload.pipeline_results.get(_AI_STEP_FALLBACK, {})

        answer.status = AnswerStatus.FAILED
        answer.ai_retryable = bool(ai_008.get("retryable", False))
        answer.ai_fallback_used = bool(ai_010.get("fallbackUsed", False))
        db.commit()

        self._realtime_service.broadcast_answer_failed(
            family_id=answer.family_id,
            answer_id=answer.id,
        )

    def _edited_video_gs_uri(self, answer: Answer) -> str:
        object_path = edited_video_object_path(
            family_id=answer.family_id,
            question_send_id=answer.question_send_id,
        )
        return f"gs://{self._settings.gcs_bucket_name}/{object_path}"

    def _resolve_thumbnail_url(self, answer: Answer) -> str | None:
        if answer.thumbnail_url is None:
            return None
        return self._storage_service.generate_read_url(gs_uri=answer.thumbnail_url)
