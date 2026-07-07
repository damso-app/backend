from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.family_member import FamilyMember
    from app.models.user import User


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class FamilyStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Family(Base):
    __tablename__ = "families"
    __table_args__ = (
        Index("ux_families_public_id", "public_id", unique=True),
        Index("ux_families_invite_code", "invite_code", unique=True),
        Index("ix_families_created_by_user_id", "created_by_user_id"),
        Index("ix_families_status", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    invite_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )
    status: Mapped[FamilyStatus] = mapped_column(
        Enum(
            FamilyStatus,
            name="family_status",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
        default=FamilyStatus.ACTIVE,
        server_default=FamilyStatus.ACTIVE.value,
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

    created_by_user: Mapped["User"] = relationship(
        back_populates="created_families",
        foreign_keys=[created_by_user_id],
    )
    members: Mapped[list["FamilyMember"]] = relationship(
        back_populates="family",
        cascade="all, delete-orphan",
    )
