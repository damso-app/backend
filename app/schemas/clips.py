from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.answer import AnswerStatus


class ClipSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ClipGridItem(ClipSchema):
    answer_id: int = Field(alias="answerId")
    status: AnswerStatus
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")


class ClipGridGroup(ClipSchema):
    date: date
    clips: list[ClipGridItem]


class ClipGridResponse(ClipSchema):
    groups: list[ClipGridGroup]


class ClipDetailResponse(ClipSchema):
    answer_id: int = Field(alias="answerId")
    question_text: str = Field(alias="questionText")
    video_url: str | None = Field(default=None, alias="videoUrl")
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")
    transcript: str | None = None
    transcript_segments: list | None = Field(default=None, alias="transcriptSegments")
    title: str | None = None
    quote: str | None = None
    one_line_summary: str | None = Field(default=None, alias="oneLineSummary")
    emotion_tags: list | None = Field(default=None, alias="emotionTags")
    fourcut_title: str | None = Field(default=None, alias="fourcutTitle")
