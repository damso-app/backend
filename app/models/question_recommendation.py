from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Enum, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class QuestionDepth(StrEnum):
    TINY = "tiny"
    MEDIUM = "medium"
    DEEP = "deep"


class QuestionRecommendationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class QuestionRecommendation(Base):
    __tablename__ = "question_recommendations"
    __table_args__ = (
        Index("ix_question_recommendations_depth_status", "depth", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[QuestionDepth] = mapped_column(
        Enum(
            QuestionDepth,
            name="question_depth",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[QuestionRecommendationStatus] = mapped_column(
        Enum(
            QuestionRecommendationStatus,
            name="question_recommendation_status",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
        default=QuestionRecommendationStatus.ACTIVE,
        server_default=QuestionRecommendationStatus.ACTIVE.value,
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
