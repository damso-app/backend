from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.question_recommendation import QuestionDepth

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.question_recommendation import QuestionRecommendation
    from app.models.user import User


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class QuestionSendSource(StrEnum):
    RECOMMENDATION = "recommendation"
    CUSTOM = "custom"


class QuestionSendStatus(StrEnum):
    SENT = "sent"
    ANSWERED = "answered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class QuestionSend(Base):
    __tablename__ = "question_sends"
    __table_args__ = (
        Index("ix_question_sends_recipient_status", "recipient_user_id", "status"),
        Index("ix_question_sends_sender_status", "sender_user_id", "status"),
        Index("ix_question_sends_family_sent_at", "family_id", "sent_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    sender_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )
    recipient_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )
    family_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("families.id"),
        nullable=False,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[QuestionDepth] = mapped_column(
        Enum(
            QuestionDepth,
            name="question_depth",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )
    source: Mapped[QuestionSendSource] = mapped_column(
        Enum(
            QuestionSendSource,
            name="question_send_source",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("question_recommendations.id"),
        nullable=True,
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[QuestionSendStatus] = mapped_column(
        Enum(
            QuestionSendStatus,
            name="question_send_status",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
        default=QuestionSendStatus.SENT,
        server_default=QuestionSendStatus.SENT.value,
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

    sender: Mapped["User"] = relationship(foreign_keys=[sender_user_id])
    recipient: Mapped["User"] = relationship(foreign_keys=[recipient_user_id])
    family: Mapped["Family"] = relationship()
    recommendation: Mapped["QuestionRecommendation | None"] = relationship()
