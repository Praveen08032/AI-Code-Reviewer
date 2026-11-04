"""The contract for Gemini's structured static review (not execution results)."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Explanation = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class StructuredReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    correctness_status: Literal["correct", "incorrect", "uncertain"]
    correctness_reason: Explanation
    readability_score: int = Field(ge=0, le=10)
    efficiency_score: int = Field(ge=0, le=10)
    errors: list[Explanation] = Field(max_length=40)
    missing_items: list[Explanation] = Field(max_length=40)
    suggestions: list[Explanation] = Field(max_length=40)
    corrected_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40000)]

    @classmethod
    def provider_schema(cls):
        schema = cls.model_json_schema()
        # Gemini's response_schema endpoint rejects this JSON Schema keyword.
        # Keep extra="forbid" for local validation of the actual response.
        schema.pop("additionalProperties", None)
        return schema

    def markdown(self) -> str:
        sections = [f"### Correctness\nStatus: {self.correctness_status}\nReason: {self.correctness_reason}"]
        for heading, items in [("Bugs", self.errors), ("Missing items", self.missing_items), ("Suggestions", self.suggestions)]:
            sections.append(f"### {heading}\n" + "\n".join(f"* {item}" for item in items or ["None"]))
        sections.append(f"### Scores\nReadability: {self.readability_score}/10\nEfficiency: {self.efficiency_score}/10")
        # A source string can contain triple backticks. A longer fence preserves it.
        fence = "```"
        while fence in self.corrected_code:
            fence += "`"
        sections.append(f"### Improved Version\n{fence}\n{self.corrected_code}\n{fence}")
        return "\n\n".join(sections)
