from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.family import Family
    from app.models.user import User


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class FamilyMemberRole(StrEnum):
    CHILD = "child"
    PARENT = "parent"
    MEMBER = "member"


class FamilyMemberStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    LEFT = "left"
    REMOVED = "removed"


class FamilyMember(Base):
    __tablename__ = "family_members"
    __table_args__ = (
        Index("ux_family_members_family_user", "family_id", "user_id", unique=True),
        Index("ix_family_members_user_status", "user_id", "status"),
        Index("ix_family_members_family_status", "family_id", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_role: Mapped[FamilyMemberRole] = mapped_column(
        Enum(
            FamilyMemberRole,
            name="family_member_role",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )
    status: Mapped[FamilyMemberStatus] = mapped_column(
        Enum(
            FamilyMemberStatus,
            name="family_member_status",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
        default=FamilyMemberStatus.ACTIVE,
        server_default=FamilyMemberStatus.ACTIVE.value,
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    family: Mapped["Family"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="family_members")
