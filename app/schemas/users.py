from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.family_member import FamilyMemberRole
from app.models.user import UserRole
from app.models.user_agreement import AgreementType


class UserSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AgreementStatusItem(UserSchema):
    type: AgreementType
    display_name: str = Field(alias="displayName")
    description: str
    agreed: bool
    agreed_at: datetime | None = Field(default=None, alias="agreedAt")


class AgreementsStatusResponse(UserSchema):
    required_agreements_completed: bool = Field(alias="requiredAgreementsCompleted")
    agreements: list[AgreementStatusItem]


class AgreementSubmitItem(UserSchema):
    type: AgreementType
    agreed: bool


class AgreementsSubmitRequest(UserSchema):
    agreements: list[AgreementSubmitItem]


class AgreementsSubmitResponse(UserSchema):
    required_agreements_completed: bool = Field(alias="requiredAgreementsCompleted")


class OnboardingStatusResponse(UserSchema):
    user_id: int = Field(alias="userId")
    role: UserRole | None
    required_agreements_completed: bool = Field(alias="requiredAgreementsCompleted")
    family_id: int | None = Field(alias="familyId")
    family_member_role: FamilyMemberRole | None = Field(alias="familyMemberRole")
    family_connected: bool = Field(alias="familyConnected")
    onboarding_completed: bool = Field(alias="onboardingCompleted")


class RoleUpdateRequest(UserSchema):
    role: UserRole


class RoleUpdateResponse(UserSchema):
    user_id: int = Field(alias="userId")
    role: UserRole
