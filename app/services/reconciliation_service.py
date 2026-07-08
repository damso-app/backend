import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.answer import Answer, AnswerStatus
from app.schemas.answers import AiCallbackRequest
from app.services.ai_callback_service import AiCallbackService, InvalidPipelineResultError

logger = logging.getLogger(__name__)

_AI_JOBS_PATH = "/api/v1/ai/jobs"
_TERMINAL_JOB_STATUSES = ("completed", "failed")


@dataclass(frozen=True)
class ReconciliationSummary:
    checked: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0


class ReconciliationService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        callback_service: AiCallbackService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._callback_service = callback_service or AiCallbackService(settings=self._settings)

    def reconcile_stuck_answers(self, db: Session) -> ReconciliationSummary:
        if not self._settings.ai_server_base_url:
            return ReconciliationSummary()

        cutoff = datetime.now(UTC) - timedelta(
            minutes=self._settings.ai_stuck_processing_threshold_minutes
        )
        stuck_answers = list(
            db.scalars(
                select(Answer).where(
                    Answer.status == AnswerStatus.PROCESSING,
                    Answer.ai_job_id.is_not(None),
                    Answer.updated_at < cutoff,
                )
            )
        )

        summary = {"completed": 0, "failed": 0, "skipped": 0}
        for answer in stuck_answers:
            outcome = self._reconcile_one(db, answer=answer)
            summary[outcome] += 1

        return ReconciliationSummary(checked=len(stuck_answers), **summary)

    def _reconcile_one(self, db: Session, *, answer: Answer) -> str:
        try:
            response = httpx.get(
                f"{self._settings.ai_server_base_url}{_AI_JOBS_PATH}/{answer.ai_job_id}",
                params={"includeResult": "true"},
                headers=self._request_headers(),
                timeout=self._settings.ai_job_request_timeout_seconds,
            )
        except httpx.HTTPError:
            logger.exception("Reconciliation poll failed for answer_id=%s", answer.id)
            return "skipped"

        if response.status_code == 404:
            self._callback_service.mark_lost(db, answer=answer)
            return "failed"
        if response.status_code != 200:
            logger.warning(
                "Unexpected reconciliation poll status %s for answer_id=%s",
                response.status_code,
                answer.id,
            )
            return "skipped"

        data = response.json()
        job_status = data.get("status")
        result = data.get("result")
        if job_status not in _TERMINAL_JOB_STATUSES or not result:
            return "skipped"

        payload = AiCallbackRequest(
            answerId=result.get("answerId", str(answer.id)),
            transcript=result.get("transcript"),
            segments=result.get("segments"),
            warnings=result.get("warnings"),
            pipelineResults=result.get("pipelineResults") or {},
        )
        try:
            self._callback_service.apply_result(db, answer=answer, payload=payload)
        except InvalidPipelineResultError:
            logger.exception("Reconciliation result invalid for answer_id=%s", answer.id)
            return "skipped"

        return job_status

    def _request_headers(self) -> dict[str, str]:
        if self._settings.ai_server_api_key is None:
            return {}
        return {
            "Authorization": f"Bearer {self._settings.ai_server_api_key.get_secret_value()}"
        }
