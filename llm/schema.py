"""Input and output contracts for POST /tasks/triage. Closed lists are Literals (enums)."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["bug", "feature", "chore", "question", "other"]
Priority = Literal["low", "normal", "high"]
MAX_TEXT = 500


class TriageIn(BaseModel):
    text: str = Field(max_length=MAX_TEXT)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


class TriageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a model that adds fields is a failure, not a feature

    category: Category
    priority: Priority
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=300)
