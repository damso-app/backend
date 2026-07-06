from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_agreement import AgreementType, UserAgreement

REQUIRED_AGREEMENT_TYPES: tuple[AgreementType, ...] = (
    AgreementType.TERMS_OF_SERVICE,
    AgreementType.PRIVACY_POLICY,
    AgreementType.CAMERA_MICROPHONE_NOTICE,
)


@dataclass(frozen=True)
class AgreementStatus:
    type: AgreementType
    agreed: bool
    agreed_at: datetime | None


@dataclass(frozen=True)
class AgreementSubmission:
    type: AgreementType
    agreed: bool


class UserAgreementService:
    def get_status(self, db: Session, *, user: User) -> list[AgreementStatus]:
        agreements = self._agreement_map(db, user_id=user.id)
        return [
            AgreementStatus(
                type=agreement_type,
                agreed=agreements[agreement_type].agreed
                if agreement_type in agreements
                else False,
                agreed_at=agreements[agreement_type].agreed_at
                if agreement_type in agreements
                else None,
            )
            for agreement_type in REQUIRED_AGREEMENT_TYPES
        ]

    def save(
        self,
        db: Session,
        *,
        user: User,
        submissions: list[AgreementSubmission],
    ) -> list[AgreementStatus]:
        agreements = self._agreement_map(db, user_id=user.id)
        now = datetime.now(UTC)

        for submission in submissions:
            agreement = agreements.get(submission.type)
            if agreement is None:
                agreement = UserAgreement(
                    user_id=user.id,
                    agreement_type=submission.type,
                    agreed=submission.agreed,
                    agreed_at=now if submission.agreed else None,
                )
                db.add(agreement)
                agreements[submission.type] = agreement
                continue

            if submission.agreed and not agreement.agreed:
                agreement.agreed = True
                agreement.agreed_at = now
            elif not submission.agreed and not agreement.agreed:
                agreement.agreed = False
                agreement.agreed_at = None

        db.commit()
        return self.get_status(db, user=user)

    @staticmethod
    def required_completed(statuses: list[AgreementStatus]) -> bool:
        return all(status.agreed for status in statuses)

    def has_completed_required(self, db: Session, *, user: User) -> bool:
        return self.required_completed(self.get_status(db, user=user))

    @staticmethod
    def _agreement_map(db: Session, *, user_id: int) -> dict[AgreementType, UserAgreement]:
        agreements = db.scalars(
            select(UserAgreement).where(UserAgreement.user_id == user_id)
        ).all()
        return {agreement.agreement_type: agreement for agreement in agreements}
