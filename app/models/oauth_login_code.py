from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class LoginCodeStatus(StrEnum):
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"


class OAuthLoginCode(Base):
    __tablename__ = "oauth_login_codes"
    __table_args__ = (
        Index("ux_oauth_login_codes_code_hash", "code_hash", unique=True),
        Index("ix_oauth_login_codes_user_status", "user_id", "status"),
        Index("ix_oauth_login_codes_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[LoginCodeStatus] = mapped_column(
        Enum(
            LoginCodeStatus,
            name="login_code_status",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
        default=LoginCodeStatus.ACTIVE,
        server_default=LoginCodeStatus.ACTIVE.value,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="oauth_login_codes")
