from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.users import (
    AgreementsStatusResponse,
    AgreementsSubmitRequest,
    AgreementsSubmitResponse,
    AgreementStatusItem,
    OnboardingStatusResponse,
    RoleUpdateRequest,
    RoleUpdateResponse,
)
from app.services.onboarding_service import (
    OnboardingService,
    RequiredAgreementsIncompleteError,
)
from app.services.user_agreement_service import (
    AgreementSubmission,
    UserAgreementService,
)

router = APIRouter(prefix="/users", tags=["users"])


def get_user_agreement_service() -> UserAgreementService:
    return UserAgreementService()


def get_onboarding_service() -> OnboardingService:
    return OnboardingService()


@router.get("/me/onboarding", response_model=OnboardingStatusResponse)
def get_my_onboarding_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
) -> OnboardingStatusResponse:
    result = service.get_status(db, user=current_user)
    return OnboardingStatusResponse(
        userId=result.user_id,
        role=result.role,
        requiredAgreementsCompleted=result.required_agreements_completed,
        familyId=result.family_id,
        familyMemberRole=result.family_member_role,
        familyConnected=result.family_connected,
        onboardingCompleted=result.onboarding_completed,
    )


@router.patch("/me/role", response_model=RoleUpdateResponse)
def update_my_role(
    payload: RoleUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
) -> RoleUpdateResponse:
    try:
        user = service.update_role(db, user=current_user, role=payload.role)
    except RequiredAgreementsIncompleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Required agreements are incomplete",
        ) from exc

    return RoleUpdateResponse(userId=user.id, role=user.role)


@router.get("/me/agreements", response_model=AgreementsStatusResponse)
def get_my_agreements(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[UserAgreementService, Depends(get_user_agreement_service)],
) -> AgreementsStatusResponse:
    statuses = service.get_status(db, user=current_user)
    return AgreementsStatusResponse(
        requiredAgreementsCompleted=service.required_completed(statuses),
        agreements=[
            AgreementStatusItem(type=status.type, agreed=status.agreed, agreedAt=status.agreed_at)
            for status in statuses
        ],
    )


@router.post("/me/agreements", response_model=AgreementsSubmitResponse)
def save_my_agreements(
    payload: AgreementsSubmitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[UserAgreementService, Depends(get_user_agreement_service)],
) -> AgreementsSubmitResponse:
    statuses = service.save(
        db,
        user=current_user,
        submissions=[
            AgreementSubmission(type=item.type, agreed=item.agreed)
            for item in payload.agreements
        ],
    )
    return AgreementsSubmitResponse(
        requiredAgreementsCompleted=service.required_completed(statuses),
    )
