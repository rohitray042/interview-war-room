from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.contracts import StrictModel

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Difficulty = Literal["easy", "medium", "hard"]
QuestionType = Literal[
    "conceptual",
    "coding",
    "debugging",
    "scenario",
    "system_design",
    "behavioral",
    "project_based",
    "follow_up",
]
Status = Literal["new", "in_progress", "practiced", "needs_review", "mastered"]


class QuestionContent(StrictModel):
    question_text: Text
    category: Label
    subcategory: Label
    skill: Label
    difficulty: Difficulty
    question_type: QuestionType
    tags: list[Label] = Field(min_length=1, max_length=15)
    expected_topics: list[Label] = Field(min_length=1, max_length=15)
    evaluation_focus: Text


class CuratedQuestion(QuestionContent):
    id: Label
    version: int = Field(ge=1)


class Catalog(StrictModel):
    version: int = Field(ge=1)
    questions: list[CuratedQuestion] = Field(min_length=1)


class GeneratedQuestion(QuestionContent):
    candidate_id: Label
    rationale: Text


class GeneratedSet(StrictModel):
    questions: list[GeneratedQuestion] = Field(min_length=1, max_length=20)


class GenerateInput(StrictModel):
    target_id: Label
    category: Label | None = None
    difficulty: Difficulty | None = None
    question_type: QuestionType | None = None
    number_of_questions: int = Field(default=5, ge=1, le=20)
    allow_external_processing: bool = False
    generation_mode: Literal["selection", "draft"] = "selection"


class DraftQuestion(StrictModel):
    candidate_id: Label
    question_text: Text


class DraftSet(StrictModel):
    questions: list[DraftQuestion] = Field(min_length=1, max_length=20)


class StateInput(StrictModel):
    status: Status
    bookmarked: bool


class QuestionView(QuestionContent):
    id: str
    source: Literal["curated", "generated"]
    source_reference: dict
    is_curated: bool
    version: int
    rationale: str
    status: Status
    bookmarked: bool
    created_at: datetime
    updated_at: datetime


class QuestionList(StrictModel):
    items: list[QuestionView]
    total: int


class GenerationResult(StrictModel):
    items: list[QuestionView]
    created: int
    reused: int


class Stats(StrictModel):
    total: int
    curated: int
    generated: int
    saved: int
    statuses: dict[str, int]


class GenerationPreview(StrictModel):
    available: int
    topics: list[str]
