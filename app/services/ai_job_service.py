import logging

import httpx
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import AccessTokenError, create_ai_callback_token
from app.models.answer import Answer, AnswerStatus
from app.services.storage_service import StorageService, StorageServiceError
from app.services.video_paths import edited_video_object_path

logger = logging.getLogger(__name__)

_AI_JOBS_PATH = "/api/v1/ai/jobs"
_EDITED_VIDEO_CONTENT_TYPE = "video/mp4"
_PROVIDER_MODE = "auto"


class AiJobService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        storage_service: StorageService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._storage_service = storage_service or StorageService()

    def dispatch_job(self, db: Session, *, answer: Answer) -> None:
        if not self._settings.ai_server_base_url:
            return
        if not self._settings.app_base_url:
            logger.warning(
                "AI_SERVER_BASE_URL is set but APP_BASE_URL is not configured; "
                "skipping AI job dispatch for answer_id=%s",
                answer.id,
            )
            return

        answer.ai_job_id = f"JOB_{answer.id}"
        db.commit()

        try:
            payload = self._build_payload(answer)
            response = httpx.post(
                f"{self._settings.ai_server_base_url}{_AI_JOBS_PATH}",
                json=payload,
                headers=self._request_headers(),
                timeout=self._settings.ai_job_request_timeout_seconds,
            )
            response.raise_for_status()
        except (httpx.HTTPError, StorageServiceError, AccessTokenError):
            logger.exception("Failed to dispatch AI job for answer_id=%s", answer.id)
            return

        # A fast job may already have completed and delivered its callback by the
        # time this call returns, so only advance from submitted (never clobber a
        # concurrently-set completed/failed status).
        db.execute(
            update(Answer)
            .where(Answer.id == answer.id, Answer.status == AnswerStatus.SUBMITTED)
            .values(status=AnswerStatus.PROCESSING)
        )
        db.commit()

    def _request_headers(self) -> dict[str, str]:
        if self._settings.ai_server_api_key is None:
            return {}
        return {
            "Authorization": f"Bearer {self._settings.ai_server_api_key.get_secret_value()}"
        }

    def _build_payload(self, answer: Answer) -> dict[str, object]:
        object_path = edited_video_object_path(
            family_id=answer.family_id,
            question_send_id=answer.question_send_id,
        )
        edited_video_upload_url, _ = self._storage_service.generate_upload_url(
            object_path=object_path,
            content_type=_EDITED_VIDEO_CONTENT_TYPE,
            expire_minutes=self._settings.ai_edited_video_upload_url_expire_minutes,
        )
        media_url = self._storage_service.generate_read_url(
            gs_uri=answer.video_origin_url,
            expire_minutes=self._settings.ai_edited_video_upload_url_expire_minutes,
        )
        callback_token = create_ai_callback_token(answer_id=answer.id, settings=self._settings)
        ai_input_context: dict[str, str | None] = answer.ai_input_context or {}

        return {
            "jobId": answer.ai_job_id,
            "answerId": str(answer.id),
            "questionId": str(answer.question_send_id),
            "send_user": ai_input_context.get("send_user"),
            "send_role": ai_input_context.get("send_role"),
            "question": ai_input_context.get("question"),
            "receive_user": ai_input_context.get("receive_user"),
            "receive_role": ai_input_context.get("receive_role"),
            "mediaUrl": media_url,
            "mediaDurationSeconds": answer.video_duration_seconds,
            "editedVideoUploadUrl": edited_video_upload_url,
            "includeDownstream": True,
            "providerMode": _PROVIDER_MODE,
            "callbackUrl": self._callback_url(answer),
            "callbackToken": callback_token,
        }

    def _callback_url(self, answer: Answer) -> str:
        base_url = (self._settings.app_base_url or "").rstrip("/")
        return f"{base_url}{self._settings.api_v1_prefix}/answers/{answer.id}/ai-callback"
