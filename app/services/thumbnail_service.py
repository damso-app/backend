import logging
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.answer import Answer
from app.services.storage_service import StorageService
from app.services.video_paths import thumbnail_object_path

logger = logging.getLogger(__name__)

_THUMBNAIL_CONTENT_TYPE = "image/jpeg"
_CAPTURE_OFFSET = "00:00:01"
_FFMPEG_TIMEOUT_SECONDS = 30


class ThumbnailService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        storage_service: StorageService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._storage_service = storage_service or StorageService()

    def generate_thumbnail(self, db: Session, *, answer: Answer) -> None:
        """Extract a frame from the original video and store it as the
        answer's thumbnail. Runs independently of the AI pipeline (fire-and-
        forget background task) — a failure here just leaves thumbnail_url
        null, it doesn't affect answer submission or AI processing."""
        object_path = thumbnail_object_path(
            family_id=answer.family_id,
            question_send_id=answer.question_send_id,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "original"
            thumbnail_path = Path(tmp_dir) / "thumbnail.jpg"

            try:
                self._storage_service.download_to_file(
                    gs_uri=answer.video_origin_url,
                    destination_path=str(video_path),
                )
                self._extract_frame(video_path, thumbnail_path)
                thumbnail_url = self._storage_service.upload_file(
                    object_path=object_path,
                    source_path=str(thumbnail_path),
                    content_type=_THUMBNAIL_CONTENT_TYPE,
                )
            except Exception:
                # Deliberately broad: this is a best-effort background task
                # (fire-and-forget from submit_answer) whose failure must
                # never surface anywhere else — thumbnail_url just stays
                # null. Covers StorageServiceError, subprocess failures, a
                # misconfigured storage backend, or anything else.
                logger.exception(
                    "Failed to generate thumbnail for answer_id=%s", answer.id
                )
                return

        answer.thumbnail_url = thumbnail_url
        db.commit()

    @staticmethod
    def _extract_frame(video_path: Path, thumbnail_path: Path) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                _CAPTURE_OFFSET,
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(thumbnail_path),
            ],
            check=True,
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
