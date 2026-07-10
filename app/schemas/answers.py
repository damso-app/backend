from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    answer_id: int | str = Field(alias="answerId")
    transcript: str | None = None
    segments: list[dict] | None = None
    warnings: list[str] | None = None
    pipeline_results: dict[str, dict] = Field(alias="pipelineResults")

    @model_validator(mode="before")
    @classmethod
    def _unwrap_result(cls, data: Any) -> Any:
        # The AI server has been observed nesting transcript/segments/
        # pipelineResults under a "result" key (matching its job-status GET
        # response shape) instead of the documented flat callback body. Accept
        # either: fall back to the nested value only when the flat one is
        # absent, so this stays a no-op once the AI server sends flat bodies.
        if not isinstance(data, dict):
            return data
        result = data.get("result")
        if not isinstance(result, dict):
            return data
        merged = dict(data)
        for key in ("transcript", "segments", "warnings", "pipelineResults"):
            if key not in merged and key in result:
                merged[key] = result[key]
        return merged


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
    # The AI server's own job status (e.g. "processing"/"completed"/"failed"),
    # distinct from `status` above which is always this backend's answers.status.
    # AI-side "completed" can arrive well before our callback does, so the
    # frontend can use this to show a distinct "finishing up" state instead of
    # a generic "processing" the whole time.
    ai_job_status: str | None = Field(default=None, alias="aiJobStatus")
