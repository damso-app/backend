from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.question_send import QuestionSend
    from app.models.user import User


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class AnswerStatus(StrEnum):
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        Index("ux_answers_question_send_id", "question_send_id", unique=True),
        Index("ix_answers_user_submitted_at", "user_id", "submitted_at"),
        Index("ix_answers_family_created_at", "family_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    question_send_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("question_sends.id"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )
    family_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("families.id"),
        nullable=False,
    )
    video_origin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    video_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[AnswerStatus] = mapped_column(
        Enum(
            AnswerStatus,
            name="answer_status",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
        default=AnswerStatus.SUBMITTED,
        server_default=AnswerStatus.SUBMITTED.value,
    )
    ai_retryable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    ai_fallback_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    ai_input_context: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    question_send: Mapped["QuestionSend"] = relationship()
    user: Mapped["User"] = relationship()
    family: Mapped["Family"] = relationship()
