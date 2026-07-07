import re
from dataclasses import dataclass
from datetime import UTC, datetime
from secrets import choice, token_urlsafe
from string import ascii_uppercase, digits
from urllib.parse import urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.family import Family, FamilyStatus
from app.models.family_member import FamilyMember, FamilyMemberRole, FamilyMemberStatus
from app.models.user import User, UserRole
from app.services.user_agreement_service import UserAgreementService

INVITE_CODE_ALPHABET = ascii_uppercase + digits
INVITE_CODE_LENGTH = 6


class FamilyServiceError(Exception):
    pass


class AlreadyInFamilyError(FamilyServiceError):
    pass


class OwnFamilyInviteError(FamilyServiceError):
    pass


class InviteCodeNotFoundError(FamilyServiceError):
    pass


class RequiredAgreementsIncompleteError(FamilyServiceError):
    pass


class RoleRequiredError(FamilyServiceError):
    pass


@dataclass(frozen=True)
class FamilyInvitation:
    family_id: int
    family_name: str
    invite_code: str
    invite_url: str


@dataclass(frozen=True)
class FamilyCreateResult:
    family_id: int
    family_name: str
    invite_code: str
    invite_url: str
    member_role: FamilyMemberRole


@dataclass(frozen=True)
class InviteValidationResult:
    invite_code: str
    family_id: int
    family_name: str
    available: bool


@dataclass(frozen=True)
class FamilyJoinResult:
    family_id: int
    family_name: str
    member_role: FamilyMemberRole
    family_connected: bool


class FamilyService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        agreement_service: UserAgreementService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._agreement_service = agreement_service or UserAgreementService()

    def create_family(
        self,
        db: Session,
        *,
        user: User,
        family_name: str | None,
    ) -> FamilyCreateResult:
        self._ensure_ready_for_family_flow(db, user=user)
        if self._active_membership(db, user_id=user.id) is not None:
            raise AlreadyInFamilyError("User already belongs to a family")

        invite_code = self._generate_invite_code(db)
        family = Family(
            public_id=self._generate_public_id(db),
            name=self._default_family_name(user, family_name=family_name),
            invite_code=invite_code,
            created_by_user_id=user.id,
            status=FamilyStatus.ACTIVE,
        )
        db.add(family)
        db.flush()

        member_role = self._member_role_for_user(user)
        now = datetime.now(UTC)
        db.add(
            FamilyMember(
                family_id=family.id,
                user_id=user.id,
                member_role=member_role,
                status=FamilyMemberStatus.ACTIVE,
                joined_at=now,
            )
        )
        db.commit()
        db.refresh(family)

        return FamilyCreateResult(
            family_id=family.id,
            family_name=family.name,
            invite_code=self._display_invite_code(invite_code),
            invite_url=self._invite_url(invite_code),
            member_role=member_role,
        )

    def get_my_invitation(self, db: Session, *, user: User) -> FamilyInvitation:
        self._ensure_agreements_completed(db, user=user)
        membership = self._active_membership(db, user_id=user.id)
        if membership is None:
            raise InviteCodeNotFoundError("Family invitation is not available")

        family = membership.family
        if not family.invite_code:
            raise InviteCodeNotFoundError("Family invitation is not available")

        return FamilyInvitation(
            family_id=family.id,
            family_name=family.name,
            invite_code=self._display_invite_code(family.invite_code),
            invite_url=self._invite_url(family.invite_code),
        )

    def validate_invite_code(
        self,
        db: Session,
        *,
        user: User,
        invite_code: str,
    ) -> InviteValidationResult:
        self._ensure_agreements_completed(db, user=user)
        family = self._family_by_invite_code(db, invite_code=invite_code)
        if family is None:
            raise InviteCodeNotFoundError("Invite code was not found")

        return InviteValidationResult(
            invite_code=self._display_invite_code(
                family.invite_code or self._normalize_invite_code(invite_code)
            ),
            family_id=family.id,
            family_name=family.name,
            available=True,
        )

    def join_family(
        self,
        db: Session,
        *,
        user: User,
        invite_code: str,
    ) -> FamilyJoinResult:
        self._ensure_ready_for_family_flow(db, user=user)
        normalized_invite_code = self._normalize_invite_code(invite_code)
        active_membership = self._active_membership(db, user_id=user.id)
        if active_membership is not None:
            if (
                active_membership.family.created_by_user_id == user.id
                and active_membership.family.invite_code == normalized_invite_code
            ):
                raise OwnFamilyInviteError("Cannot join own family invitation")
            raise AlreadyInFamilyError("User already belongs to a family")

        family = self._family_by_invite_code(db, invite_code=normalized_invite_code)
        if family is None:
            raise InviteCodeNotFoundError("Invite code was not found")
        if family.created_by_user_id == user.id:
            raise OwnFamilyInviteError("Cannot join own family invitation")

        member_role = self._member_role_for_user(user)
        try:
            db.add(
                FamilyMember(
                    family_id=family.id,
                    user_id=user.id,
                    member_role=member_role,
                    status=FamilyMemberStatus.ACTIVE,
                    joined_at=datetime.now(UTC),
                )
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise AlreadyInFamilyError("User already belongs to this family") from exc

        return FamilyJoinResult(
            family_id=family.id,
            family_name=family.name,
            member_role=member_role,
            family_connected=True,
        )

    def _ensure_ready_for_family_flow(self, db: Session, *, user: User) -> None:
        self._ensure_agreements_completed(db, user=user)
        if user.role is None:
            raise RoleRequiredError("User role is required")

    def _ensure_agreements_completed(self, db: Session, *, user: User) -> None:
        if not self._agreement_service.has_completed_required(db, user=user):
            raise RequiredAgreementsIncompleteError("Required agreements are incomplete")

    @staticmethod
    def _member_role_for_user(user: User) -> FamilyMemberRole:
        if user.role == UserRole.MOTHER:
            return FamilyMemberRole.MOTHER
        if user.role == UserRole.FATHER:
            return FamilyMemberRole.FATHER
        return FamilyMemberRole.CHILD

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

    @staticmethod
    def _family_by_invite_code(db: Session, *, invite_code: str) -> Family | None:
        normalized_invite_code = FamilyService._normalize_invite_code(invite_code)
        return db.scalar(
            select(Family)
            .where(
                Family.invite_code == normalized_invite_code,
                Family.status == FamilyStatus.ACTIVE,
                Family.deleted_at.is_(None),
            )
            .limit(1)
        )

    def _generate_invite_code(self, db: Session) -> str:
        for _ in range(20):
            invite_code = self._new_invite_code()
            exists = db.scalar(
                select(Family.id).where(Family.invite_code == invite_code).limit(1)
            )
            if exists is None:
                return invite_code

        raise FamilyServiceError("Failed to generate invite code")

    @staticmethod
    def _new_invite_code() -> str:
        return "".join(choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))

    def _generate_public_id(self, db: Session) -> str:
        for _ in range(5):
            public_id = token_urlsafe(18)[:32]
            exists = db.scalar(select(Family.id).where(Family.public_id == public_id).limit(1))
            if exists is None:
                return public_id

        raise FamilyServiceError("Failed to generate family public_id")

    @staticmethod
    def _default_family_name(user: User, *, family_name: str | None) -> str:
        cleaned_name = family_name.strip() if family_name is not None else ""
        if cleaned_name:
            return cleaned_name

        display_name = (user.display_name or "").strip()
        if display_name:
            return f"{display_name}의 가족"
        return "나의 가족"

    def _invite_url(self, invite_code: str) -> str:
        callback_url = self._settings.frontend_oauth_callback_url
        base = "http://localhost:3000" if callback_url is None else self._origin(str(callback_url))
        return f"{base}/invite?{urlencode({'code': self._display_invite_code(invite_code)})}"

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, "", "", ""))

    @staticmethod
    def _normalize_invite_code(invite_code: str) -> str:
        return re.sub(r"[-\s]+", "", invite_code).upper()

    @staticmethod
    def _display_invite_code(invite_code: str) -> str:
        normalized = FamilyService._normalize_invite_code(invite_code)
        if len(normalized) != INVITE_CODE_LENGTH:
            return normalized
        return f"{normalized[:3]}-{normalized[3:]}"
