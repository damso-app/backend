import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import create_ai_callback_token
from app.models.answer import Answer
from app.services.storage_service import StorageService
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

        answer.ai_job_id = f"JOB_{answer.id}"
        db.commit()

        payload = self._build_payload(answer)

        try:
            response = httpx.post(
                f"{self._settings.ai_server_base_url}{_AI_JOBS_PATH}",
                json=payload,
                timeout=self._settings.ai_job_request_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Failed to dispatch AI job for answer_id=%s", answer.id)

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
        media_url = self._storage_service.generate_read_url(gs_uri=answer.video_origin_url)
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
