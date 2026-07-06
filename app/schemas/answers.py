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
