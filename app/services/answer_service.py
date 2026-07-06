from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.answer import Answer, AnswerStatus
from app.models.question_send import QuestionSend, QuestionSendStatus
from app.models.user import User
from app.services.storage_service import StorageService

_MIME_TYPE_EXTENSIONS = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "video/3gpp": "3gp",
}


class AnswerServiceError(Exception):
    pass


class QuestionSendNotFoundError(AnswerServiceError):
    pass


class NotRecipientError(AnswerServiceError):
    pass


class AlreadyAnsweredError(AnswerServiceError):
    pass


class UnsupportedVideoMimeTypeError(AnswerServiceError):
    pass


class AnswerService:
    def __init__(self, storage_service: StorageService | None = None) -> None:
        self._storage_service = storage_service or StorageService()

    def create_upload_url(
        self,
        db: Session,
        *,
        user: User,
        question_send_id: int,
        video_mime_type: str,
    ) -> tuple[str, datetime]:
        question_send = self._require_answerable_question_send(
            db,
            user=user,
            question_send_id=question_send_id,
        )
        object_path = self._object_path(
            family_id=question_send.family_id,
            question_send_id=question_send_id,
            video_mime_type=video_mime_type,
        )
        return self._storage_service.generate_upload_url(
            object_path=object_path,
            content_type=video_mime_type,
        )

    def submit_answer(
        self,
        db: Session,
        *,
        user: User,
        question_send_id: int,
        video_mime_type: str,
        video_duration_seconds: int,
        video_size_bytes: int,
    ) -> Answer:
        question_send = self._require_answerable_question_send(
            db,
            user=user,
            question_send_id=question_send_id,
        )
        object_path = self._object_path(
            family_id=question_send.family_id,
            question_send_id=question_send_id,
            video_mime_type=video_mime_type,
        )
        settings = get_settings()
        now = datetime.now(UTC)

        answer = Answer(
            question_send_id=question_send_id,
            user_id=user.id,
            family_id=question_send.family_id,
            video_origin_url=f"gs://{settings.gcs_bucket_name}/{object_path}",
            video_mime_type=video_mime_type,
            video_duration_seconds=video_duration_seconds,
            video_size_bytes=video_size_bytes,
            status=AnswerStatus.SUBMITTED,
            submitted_at=now,
        )
        db.add(answer)

        question_send.answered_at = now
        question_send.status = QuestionSendStatus.ANSWERED

        db.commit()
        db.refresh(answer)
        return answer

    def _require_answerable_question_send(
        self,
        db: Session,
        *,
        user: User,
        question_send_id: int,
    ) -> QuestionSend:
        question_send = db.scalar(
            select(QuestionSend).where(QuestionSend.id == question_send_id).limit(1)
        )
        if question_send is None:
            raise QuestionSendNotFoundError("Question send was not found")
        if question_send.recipient_user_id != user.id:
            raise NotRecipientError("Only the recipient can answer this question")

        existing_answer = db.scalar(
            select(Answer.id).where(Answer.question_send_id == question_send_id).limit(1)
        )
        if existing_answer is not None:
            raise AlreadyAnsweredError("This question has already been answered")

        return question_send

    @staticmethod
    def _object_path(*, family_id: int, question_send_id: int, video_mime_type: str) -> str:
        extension = _MIME_TYPE_EXTENSIONS.get(video_mime_type)
        if extension is None:
            raise UnsupportedVideoMimeTypeError(
                f"Unsupported video mime type: {video_mime_type}"
            )
        return f"answers/{family_id}/{question_send_id}/original.{extension}"
