from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.contracts import StrictModel
from app.question_schemas import Difficulty, Label, QuestionType

InterviewType = Literal[
    "technical",
    "sql",
    "data_engineering",
    "system_design",
    "behavioral",
    "project_deep_dive",
    "mixed",
]
SessionStatus = Literal["not_started", "active", "paused", "completed", "abandoned"]
EvaluationState = Literal["unsubmitted", "pending", "evaluating", "succeeded", "failed", "deferred"]
Token = Annotated[str, StringConstraints(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]


class InterviewInput(StrictModel):
    request_id: Token
    target_id: Label | None = None
    interview_type: InterviewType = "technical"
    category: Label | None = None
    difficulty: Difficulty | None = None
    question_type: QuestionType | None = None
    number_of_questions: int = Field(default=5, ge=1, le=20)
    source: Literal["curated", "personalized", "ai_generated", "mixed"] = "curated"
    allow_external_processing: bool = False
    focus_id: Label | None = None


class ActionInput(StrictModel):
    revision: int = Field(ge=1)
    action: Literal["start", "pause", "resume", "next", "finish", "abandon", "defer_evaluation"]


class AnswerInput(StrictModel):
    revision: int = Field(ge=1)
    submission_id: Token
    answer_text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)
    ]


class EvaluateInput(StrictModel):
    allow_external_processing: bool = False


class AnswerEvidence(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Evidence range must be ordered")
        return self


class RubricRating(StrictModel):
    dimension: Label
    score: int = Field(ge=0, le=4)
    evidence: list[AnswerEvidence] = Field(max_length=5)


class TopicRating(StrictModel):
    topic: Label
    status: Literal["demonstrated", "partial", "not_demonstrated", "incorrect"]
    evidence: list[AnswerEvidence] = Field(max_length=5)


class InterviewEvaluation(StrictModel):
    dimensions: list[RubricRating] = Field(min_length=1, max_length=8)
    topics: list[TopicRating] = Field(min_length=1, max_length=15)
    follow_up_topic: Label | None


class EvaluationView(StrictModel):
    id: str
    score: float
    strengths: list[str]
    weaknesses: list[str]
    missing_points: list[str]
    feedback: str
    rubric_results: list[RubricRating]
    topics: list[TopicRating]
    follow_up_required: bool
    follow_up_reason: str | None
    follow_up_topic: str | None
    rubric_id: str
    rubric_version: int


class TurnView(StrictModel):
    id: str
    primary_number: int
    follow_up_depth: int
    parent_turn_id: str | None
    question_text: str
    question_type: str
    category: str
    difficulty: str
    asked_at: datetime | None
    answered_at: datetime | None
    answer_text: str | None
    evaluation_state: EvaluationState
    evaluation_error: str | None
    retryable: bool
    evaluation: EvaluationView | None


class SessionCard(StrictModel):
    id: str
    status: SessionStatus
    revision: int
    configuration: dict
    total_questions: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class SessionView(SessionCard):
    current_turn: TurnView | None
    answered_turns: int
    resolved_primary_questions: int
    next_action: Literal[
        "start", "answer", "evaluate", "wait", "follow_up", "next", "finish", "resume", "none"
    ]


class WeaknessEvidence(StrictModel):
    session_id: str
    turn_id: str
    evaluation_id: str
    primary_number: int
    follow_up_depth: int
    assessment: str
    evidence: list[AnswerEvidence]


class WeaknessView(StrictModel):
    skill: str
    topic: str
    count: int
    occurrences: list[WeaknessEvidence]


class SummaryView(StrictModel):
    session: SessionCard
    primary_questions: int
    primary_answered: int
    answers_submitted: int
    evaluations_completed: int
    unscored_answers: int
    average_score: float | None
    primary_average_score: float | None
    follow_ups: int
    strong_areas: list[str]
    weak_areas: list[WeaknessView]
    suggested_practice: list[str]
    review_turn_ids: list[str]
    turns: list[TurnView]
