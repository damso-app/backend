import logging

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_BROADCAST_PATH = "/realtime/v1/api/broadcast"
_BROADCAST_TIMEOUT_SECONDS = 5.0
_ANSWER_STATUS_EVENT = "answer_status_updated"


class RealtimeService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def broadcast_answer_completed(
        self,
        *,
        family_id: int,
        answer_id: int,
        thumbnail_url: str | None,
    ) -> None:
        self._broadcast(
            family_id=family_id,
            payload={
                "answer_id": answer_id,
                "status": "completed",
                "thumbnail_url": thumbnail_url,
            },
        )

    def broadcast_answer_failed(self, *, family_id: int, answer_id: int) -> None:
        self._broadcast(
            family_id=family_id,
            payload={"answer_id": answer_id, "status": "failed"},
        )

    def _broadcast(self, *, family_id: int, payload: dict[str, object]) -> None:
        if not self._settings.supabase_url or not self._settings.supabase_service_role_key:
            return

        service_role_key = self._settings.supabase_service_role_key.get_secret_value()
        url = f"{str(self._settings.supabase_url).rstrip('/')}{_BROADCAST_PATH}"
        body = {
            "messages": [
                {
                    "topic": f"family:{family_id}",
                    "event": _ANSWER_STATUS_EVENT,
                    "payload": payload,
                }
            ]
        }

        try:
            response = httpx.post(
                url,
                json=body,
                headers={
                    "apikey": service_role_key,
                    "Authorization": f"Bearer {service_role_key}",
                },
                timeout=_BROADCAST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Failed to broadcast realtime event for family_id=%s", family_id)
