from pydantic import BaseModel, field_serializer
from typing import Optional
from datetime import datetime, timezone

class CodeSubmission(BaseModel):
    language: str
    question_title: str
    code: str

class CodeFeedback(BaseModel):
    pass_status: bool
    readability_score: Optional[int]
    efficiency_score: Optional[int]
    suggestions: Optional[list[str]]
    errors: Optional[list[str]]
    corrected_code: Optional[str]
    raw_ai_feedback: str
    similarity_score: Optional[float] = None
    is_similar_to_sample: Optional[bool] = None


class SampleAnswerCreate(BaseModel):
    question_title: str
    language: str
    ideal_code: str

class SubmissionRead(BaseModel):
    id: int
    language: str
    code: str
    created_at: datetime
    pass_status: Optional[bool]
    readability_score: Optional[int]
    efficiency_score: Optional[int]
    suggestions: Optional[str]
    errors: Optional[str]
    corrected_code: Optional[str]
    raw_ai_feedback: Optional[str]
    similarity_score: Optional[float]
    is_similar_to_sample: Optional[bool]

    model_config = {
        "from_attributes": True  # ✅ Required for SQLAlchemy objects in Pydantic v2
    }

    # created_at is stored in UTC without a timezone; mark it as UTC so the
    # browser converts it to the user's local time
    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
