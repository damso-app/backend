from pydantic import BaseModel, ConfigDict, Field

from app.models.family_member import FamilyMemberRole


class FamilySchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class FamilyCreateRequest(FamilySchema):
    family_name: str | None = Field(default=None, alias="familyName", max_length=100)


class FamilyCreateResponse(FamilySchema):
    family_id: int = Field(alias="familyId")
    family_name: str = Field(alias="familyName")
    invite_code: str = Field(alias="inviteCode")
    invite_url: str = Field(alias="inviteUrl")
    member_role: FamilyMemberRole = Field(alias="memberRole")


class FamilyInvitationResponse(FamilySchema):
    family_id: int = Field(alias="familyId")
    family_name: str = Field(alias="familyName")
    invite_code: str = Field(alias="inviteCode")
    invite_url: str = Field(alias="inviteUrl")


class InviteValidationResponse(FamilySchema):
    invite_code: str = Field(alias="inviteCode")
    family_id: int = Field(alias="familyId")
    family_name: str = Field(alias="familyName")
    available: bool


class FamilyJoinRequest(FamilySchema):
    invite_code: str = Field(alias="inviteCode", min_length=1)


class FamilyJoinResponse(FamilySchema):
    family_id: int = Field(alias="familyId")
    family_name: str = Field(alias="familyName")
    member_role: FamilyMemberRole = Field(alias="memberRole")
    family_connected: bool = Field(alias="familyConnected")
