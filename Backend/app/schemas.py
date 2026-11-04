from pydantic import BaseModel, field_serializer, field_validator, computed_field, Field
from typing import Optional, Literal
from .ai_utils import parse_ai_feedback, is_perfect_review
from datetime import datetime, timezone
from .limits import MAX_CODE_CHARS, MAX_TASK_CHARS, MAX_TITLE_CHARS, language_id, non_blank

class CodeSubmission(BaseModel):
    language: str
    question_title: str = Field(default="", max_length=MAX_TITLE_CHARS)
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)
    review_mode: Literal["exercise", "custom"] = "exercise"
    task_description: str = Field(default="", max_length=MAX_TASK_CHARS)

    _language = field_validator("language")(language_id)
    _code = field_validator("code")(non_blank)

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
    correctness_status: Literal["correct", "incorrect", "uncertain"] = "uncertain"
    correctness_reason: str = ""
    review_complete: bool = False
    missing_items: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def is_perfect(self) -> bool:
        return self.pass_status and is_perfect_review({
            "review_complete": self.review_complete, "correctness_status": self.correctness_status,
            "readability_score": self.readability_score, "efficiency_score": self.efficiency_score,
            "errors": self.errors, "suggestions": self.suggestions, "missing_items": self.missing_items,
        })


class SampleAnswerCreate(BaseModel):
    question_title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    language: str
    ideal_code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)

    _language = field_validator("language")(language_id)
    _content = field_validator("question_title", "ideal_code")(non_blank)

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

    @computed_field
    @property
    def missing_items(self) -> list[str]:
        return parse_ai_feedback(self.raw_ai_feedback or "")["missing_items"]

    @computed_field
    @property
    def review_complete(self) -> bool:
        return parse_ai_feedback(self.raw_ai_feedback or "")["review_complete"]

    @field_serializer("pass_status")
    def validated_pass_status(self, value):
        review = parse_ai_feedback(self.raw_ai_feedback or "")
        return bool(value and review["review_complete"] and review["correctness_status"] == "correct" and
                    not review["errors"] and not review["missing_items"] and
                    (review["readability_score"] or 0) >= 5 and (review["efficiency_score"] or 0) >= 5)

    @computed_field
    @property
    def is_perfect(self) -> bool:
        return bool(self.pass_status and is_perfect_review(parse_ai_feedback(self.raw_ai_feedback or "")))

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
