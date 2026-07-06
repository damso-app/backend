from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.families import (
    FamilyCreateRequest,
    FamilyCreateResponse,
    FamilyInvitationResponse,
    FamilyJoinRequest,
    FamilyJoinResponse,
    InviteValidationResponse,
)
from app.services.family_service import (
    AlreadyInFamilyError,
    FamilyService,
    InviteCodeNotFoundError,
    RequiredAgreementsIncompleteError,
    RoleRequiredError,
)

router = APIRouter(prefix="/families", tags=["families"])


def get_family_service(settings: Annotated[Settings, Depends(get_settings)]) -> FamilyService:
    return FamilyService(settings)


@router.post("", response_model=FamilyCreateResponse)
def create_family(
    payload: FamilyCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[FamilyService, Depends(get_family_service)],
) -> FamilyCreateResponse:
    try:
        result = service.create_family(
            db,
            user=current_user,
            family_name=payload.family_name,
        )
    except RequiredAgreementsIncompleteError as exc:
        raise _bad_request("Required agreements are incomplete") from exc
    except RoleRequiredError as exc:
        raise _bad_request("User role is required") from exc
    except AlreadyInFamilyError as exc:
        raise _conflict("User already belongs to a family") from exc

    return FamilyCreateResponse(
        familyId=result.family_id,
        familyName=result.family_name,
        inviteCode=result.invite_code,
        inviteUrl=result.invite_url,
        memberRole=result.member_role,
    )


@router.get("/me/invitation", response_model=FamilyInvitationResponse)
def get_my_family_invitation(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[FamilyService, Depends(get_family_service)],
) -> FamilyInvitationResponse:
    try:
        result = service.get_my_invitation(db, user=current_user)
    except RequiredAgreementsIncompleteError as exc:
        raise _bad_request("Required agreements are incomplete") from exc
    except InviteCodeNotFoundError as exc:
        raise _not_found("Family invitation was not found") from exc

    return FamilyInvitationResponse(
        familyId=result.family_id,
        familyName=result.family_name,
        inviteCode=result.invite_code,
        inviteUrl=result.invite_url,
    )


@router.get("/invitations/{invite_code}", response_model=InviteValidationResponse)
def validate_invite_code(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[FamilyService, Depends(get_family_service)],
    invite_code: str,
) -> InviteValidationResponse:
    try:
        result = service.validate_invite_code(
            db,
            user=current_user,
            invite_code=invite_code,
        )
    except RequiredAgreementsIncompleteError as exc:
        raise _bad_request("Required agreements are incomplete") from exc
    except InviteCodeNotFoundError as exc:
        raise _not_found("Invite code was not found") from exc

    return InviteValidationResponse(
        inviteCode=result.invite_code,
        familyId=result.family_id,
        familyName=result.family_name,
        available=result.available,
    )


@router.post("/join", response_model=FamilyJoinResponse)
def join_family(
    payload: FamilyJoinRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[FamilyService, Depends(get_family_service)],
) -> FamilyJoinResponse:
    try:
        result = service.join_family(
            db,
            user=current_user,
            invite_code=payload.invite_code,
        )
    except RequiredAgreementsIncompleteError as exc:
        raise _bad_request("Required agreements are incomplete") from exc
    except RoleRequiredError as exc:
        raise _bad_request("User role is required") from exc
    except AlreadyInFamilyError as exc:
        raise _conflict("User already belongs to a family") from exc
    except InviteCodeNotFoundError as exc:
        raise _not_found("Invite code was not found") from exc

    return FamilyJoinResponse(
        familyId=result.family_id,
        familyName=result.family_name,
        memberRole=result.member_role,
        familyConnected=result.family_connected,
    )


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
