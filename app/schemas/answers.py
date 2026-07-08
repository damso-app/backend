from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.answer import AnswerStatus


class AnswerSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AnswerUploadUrlRequest(AnswerSchema):
    question_send_id: int = Field(alias="questionSendId")
    video_mime_type: str = Field(alias="videoMimeType")


class AnswerUploadUrlResponse(AnswerSchema):
    upload_url: str = Field(alias="uploadUrl")
    expires_at: datetime = Field(alias="expiresAt")


class AnswerSubmitRequest(AnswerSchema):
    question_send_id: int = Field(alias="questionSendId")
    video_mime_type: str = Field(alias="videoMimeType")
    video_duration_seconds: int = Field(alias="videoDurationSeconds", gt=0)
    video_size_bytes: int = Field(alias="videoSizeBytes", gt=0)


class AnswerSubmitResponse(AnswerSchema):
    answer_id: int = Field(alias="answerId")
    question_send_id: int = Field(alias="questionSendId")
    status: AnswerStatus
    submitted_at: datetime = Field(alias="submittedAt")


class AiCallbackRequest(AnswerSchema):
    answer_id: str = Field(alias="answerId")
    transcript: str | None = None
    segments: list[dict] | None = None
    warnings: list[str] | None = None
    pipeline_results: dict[str, dict] = Field(alias="pipelineResults")


class AiCallbackResponse(AnswerSchema):
    answer_id: int = Field(alias="answerId")
    status: AnswerStatus


class AnswerProgressResponse(AnswerSchema):
    answer_id: int = Field(alias="answerId")
    status: AnswerStatus
    progress: int | None = None
    current_step_label: str | None = Field(default=None, alias="currentStepLabel")
    estimated_remaining_seconds: float | None = Field(
        default=None, alias="estimatedRemainingSeconds"
    )
