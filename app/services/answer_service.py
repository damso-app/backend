from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.answer import Answer, AnswerStatus
from app.models.family_member import FamilyMember, FamilyMemberRole
from app.models.question_send import QuestionSend, QuestionSendStatus
from app.models.user import User
from app.services.storage_service import StorageService

_MIME_TYPE_EXTENSIONS = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "video/3gpp": "3gp",
}

_ROLE_LABELS = {
    FamilyMemberRole.CHILD: "자녀",
    FamilyMemberRole.MOTHER: "엄마",
    FamilyMemberRole.FATHER: "아빠",
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
            ai_input_context=self._build_ai_input_context(db, question_send=question_send),
        )
        db.add(answer)

        question_send.answered_at = now
        question_send.status = QuestionSendStatus.ANSWERED

        try:
            db.commit()
        except IntegrityError as exc:
            # Two near-simultaneous submissions for the same question_send can
            # both pass the check in _require_answerable_question_send above;
            # the unique index (ux_answers_question_send_id) is the real guard.
            db.rollback()
            raise AlreadyAnsweredError("This question has already been answered") from exc

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

    def _build_ai_input_context(
        self,
        db: Session,
        *,
        question_send: QuestionSend,
    ) -> dict[str, str | None]:
        return {
            "send_user": question_send.sender.display_name,
            "send_role": self._member_role_label(
                db,
                family_id=question_send.family_id,
                user_id=question_send.sender_user_id,
            ),
            "question": question_send.question_text,
            "receive_user": question_send.recipient.display_name,
            "receive_role": self._member_role_label(
                db,
                family_id=question_send.family_id,
                user_id=question_send.recipient_user_id,
            ),
        }

    @staticmethod
    def _member_role_label(db: Session, *, family_id: int, user_id: int) -> str | None:
        member_role = db.scalar(
            select(FamilyMember.member_role)
            .where(
                FamilyMember.family_id == family_id,
                FamilyMember.user_id == user_id,
            )
            .limit(1)
        )
        return _ROLE_LABELS.get(member_role) if member_role is not None else None

    @staticmethod
    def _object_path(*, family_id: int, question_send_id: int, video_mime_type: str) -> str:
        extension = _MIME_TYPE_EXTENSIONS.get(video_mime_type)
        if extension is None:
            raise UnsupportedVideoMimeTypeError(
                f"Unsupported video mime type: {video_mime_type}"
            )
        return f"answers/{family_id}/{question_send_id}/original.{extension}"
