from pydantic import AnyUrl, BaseModel, ConfigDict, Field


class KakaoTokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str = Field(min_length=1)
    token_type: str = Field(min_length=1)
    refresh_token: str | None = None
    expires_in: int | None = None
    refresh_token_expires_in: int | None = None
    scope: str | None = None


class KakaoUserInfo(BaseModel):
    kakao_id: str = Field(min_length=1)
    nickname: str | None = None
    email: str | None = None
    profile_image_url: AnyUrl | None = None


class LoginCodeExchangeRequest(BaseModel):
    login_code: str = Field(alias="loginCode", min_length=1)


class AccessTokenResponse(BaseModel):
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="bearer", alias="tokenType")
