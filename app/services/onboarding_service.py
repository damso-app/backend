from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.family import Family, FamilyStatus
from app.models.family_member import FamilyMember, FamilyMemberRole, FamilyMemberStatus
from app.models.user import User, UserRole
from app.services.user_agreement_service import UserAgreementService


class OnboardingError(Exception):
    pass


class RequiredAgreementsIncompleteError(OnboardingError):
    pass


@dataclass(frozen=True)
class OnboardingStatus:
    user_id: int
    role: UserRole | None
    required_agreements_completed: bool
    family_id: int | None
    family_member_role: FamilyMemberRole | None
    family_connected: bool
    onboarding_completed: bool


class OnboardingService:
    def __init__(
        self,
        *,
        agreement_service: UserAgreementService | None = None,
    ) -> None:
        self._agreement_service = agreement_service or UserAgreementService()

    def get_status(self, db: Session, *, user: User) -> OnboardingStatus:
        required_agreements_completed = self._agreement_service.has_completed_required(
            db,
            user=user,
        )
        membership = self._active_membership(db, user_id=user.id)
        family_connected = membership is not None

        return OnboardingStatus(
            user_id=user.id,
            role=user.role,
            required_agreements_completed=required_agreements_completed,
            family_id=membership.family_id if membership is not None else None,
            family_member_role=membership.member_role if membership is not None else None,
            family_connected=family_connected,
            onboarding_completed=(
                required_agreements_completed and user.role is not None and family_connected
            ),
        )

    def update_role(self, db: Session, *, user: User, role: UserRole) -> User:
        if not self._agreement_service.has_completed_required(db, user=user):
            raise RequiredAgreementsIncompleteError("Required agreements are incomplete")

        user.role = role
        user.role_selected_at = datetime.now(UTC)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def _active_membership(db: Session, *, user_id: int) -> FamilyMember | None:
        return db.scalar(
            select(FamilyMember)
            .join(Family, Family.id == FamilyMember.family_id)
            .where(
                FamilyMember.user_id == user_id,
                FamilyMember.status == FamilyMemberStatus.ACTIVE,
                Family.status == FamilyStatus.ACTIVE,
                Family.deleted_at.is_(None),
            )
            .limit(1)
        )
