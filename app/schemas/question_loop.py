from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.family_member import FamilyMemberRole
from app.models.question_recommendation import QuestionDepth
from app.models.question_send import QuestionSendSource, QuestionSendStatus
from app.models.user import UserRole


class QuestionLoopSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class QuestionUserSummary(QuestionLoopSchema):
    user_id: int = Field(alias="userId")
    display_name: str | None = Field(alias="displayName")
    profile_image_url: str | None = Field(default=None, alias="profileImageUrl")
    role: UserRole | None = None


class QuestionRecipientItem(QuestionUserSummary):
    member_role: FamilyMemberRole = Field(alias="memberRole")


class QuestionRecipientsResponse(QuestionLoopSchema):
    recipients: list[QuestionRecipientItem]


class QuestionRecommendationItem(QuestionLoopSchema):
    recommendation_id: int = Field(alias="recommendationId")
    question_text: str = Field(alias="questionText")
    depth: QuestionDepth
    category: str | None = None
    target_role: UserRole | None = Field(default=None, alias="targetRole")


class QuestionRecommendationsResponse(QuestionLoopSchema):
    recommendations: list[QuestionRecommendationItem]


class QuestionSendRequest(QuestionLoopSchema):
    recipient_user_id: int = Field(alias="recipientUserId")
    depth: QuestionDepth | None = None
    recommendation_id: int | None = Field(default=None, alias="recommendationId")
    question_text: str | None = Field(default=None, alias="questionText", max_length=1000)

    @model_validator(mode="after")
    def validate_question_source(self) -> "QuestionSendRequest":
        if self.recommendation_id is None and not (self.question_text or "").strip():
            raise ValueError("questionText is required for custom questions")
        if self.recommendation_id is None and self.depth is None:
            raise ValueError("depth is required for custom questions")
        return self


class QuestionSendResponse(QuestionLoopSchema):
    question_send_id: int = Field(alias="questionSendId")
    recipient_user_id: int = Field(alias="recipientUserId")
    question_text: str = Field(alias="questionText")
    depth: QuestionDepth
    source: QuestionSendSource
    sent_at: datetime = Field(alias="sentAt")
    read: bool
    answered: bool


class ReceivedQuestionItem(QuestionLoopSchema):
    question_send_id: int = Field(alias="questionSendId")
    sender: QuestionUserSummary
    question_text: str = Field(alias="questionText")
    depth: QuestionDepth
    received_at: datetime = Field(alias="receivedAt")
    read: bool
    read_at: datetime | None = Field(default=None, alias="readAt")
    answered: bool
    answered_at: datetime | None = Field(default=None, alias="answeredAt")
    status: QuestionSendStatus
    answer_id: int | None = Field(default=None, alias="answerId")


class ReceivedQuestionsResponse(QuestionLoopSchema):
    questions: list[ReceivedQuestionItem]


class ReceivedQuestionDetail(ReceivedQuestionItem):
    source: QuestionSendSource
    recommendation_id: int | None = Field(default=None, alias="recommendationId")


class ReadQuestionResponse(QuestionLoopSchema):
    question_send_id: int = Field(alias="questionSendId")
    read: bool
    read_at: datetime = Field(alias="readAt")


class SentQuestionSummary(QuestionLoopSchema):
    question_send_id: int = Field(alias="questionSendId")
    recipient: QuestionUserSummary
    question_text: str = Field(alias="questionText")
    sent_at: datetime = Field(alias="sentAt")
    read: bool
    read_at: datetime | None = Field(default=None, alias="readAt")
    answered: bool
    answered_at: datetime | None = Field(default=None, alias="answeredAt")
    ai_status: str | None = Field(default=None, alias="aiStatus")


class PendingReceivedQuestionSummary(QuestionLoopSchema):
    question_send_id: int = Field(alias="questionSendId")
    sender: QuestionUserSummary
    received_at: datetime = Field(alias="receivedAt")
    read: bool
    read_at: datetime | None = Field(default=None, alias="readAt")


class HomeSummaryResponse(QuestionLoopSchema):
    family_connected: bool = Field(alias="familyConnected")
    family_id: int | None = Field(alias="familyId")
    role: UserRole | None
    connected_to_child: bool = Field(alias="connectedToChild")
    connected_to_parent: bool = Field(alias="connectedToParent")
    today_completed_count: int = Field(alias="todayCompletedCount")
    pending_received_question: PendingReceivedQuestionSummary | None = Field(
        default=None,
        alias="pendingReceivedQuestion",
    )
    latest_sent_question: SentQuestionSummary | None = Field(
        default=None,
        alias="latestSentQuestion",
    )
    ai_status: str | None = Field(default=None, alias="aiStatus")
