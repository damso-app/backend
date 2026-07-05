from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class OAuthProvider(StrEnum):
    KAKAO = "kakao"


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        Index("ux_social_accounts_provider_user", "provider", "provider_user_id", unique=True),
        Index("ix_social_accounts_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[OAuthProvider] = mapped_column(
        Enum(
            OAuthProvider,
            name="oauth_provider",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )
    provider_user_id: Mapped[str] = mapped_column(String(191), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    user: Mapped["User"] = relationship(back_populates="social_accounts")
