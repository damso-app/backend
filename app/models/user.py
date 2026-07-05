from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.family_member import FamilyMember
    from app.models.oauth_login_code import OAuthLoginCode
    from app.models.social_account import SocialAccount


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class UserRole(StrEnum):
    CHILD = "child"
    PARENT = "parent"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ux_users_public_id", "public_id", unique=True),
        Index("ix_users_role_status", "role", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[UserRole | None] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=True,
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(
            UserStatus,
            name="user_status",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )
    role_selected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    social_accounts: Mapped[list["SocialAccount"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    oauth_login_codes: Mapped[list["OAuthLoginCode"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    created_families: Mapped[list["Family"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="Family.created_by_user_id",
    )
    family_members: Mapped[list["FamilyMember"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
