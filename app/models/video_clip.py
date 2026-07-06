from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.answer import Answer


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class VideoClip(Base):
    __tablename__ = "video_clips"
    __table_args__ = (Index("ux_video_clips_answer_id", "answer_id", unique=True),)

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    answer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("answers.id"),
        nullable=False,
    )
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_segments: Mapped[list | None] = mapped_column(JSON_TYPE, nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    one_line_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    emotion_tags: Mapped[list | None] = mapped_column(JSON_TYPE, nullable=True)
    fourcut_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
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

    answer: Mapped["Answer"] = relationship()


class VideoClipAiResult(Base):
    __tablename__ = "video_clip_ai_results"
    __table_args__ = (Index("ix_video_clip_ai_results_video_clip_id", "video_clip_id"),)

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    video_clip_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("video_clips.id"),
        nullable=False,
    )
    ai_raw_response: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    video_clip: Mapped["VideoClip"] = relationship()
