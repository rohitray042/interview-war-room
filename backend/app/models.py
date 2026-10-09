from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class Profile(SQLModel, table=True):
    __tablename__ = "profiles"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    singleton_key: int = Field(default=1, unique=True, index=True)
    name: str = ""
    background: str = ""
    target_role: str = "Data Engineer"
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    learning_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    daily_study_minutes: int = 60
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Document(SQLModel, table=True):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("kind", "content_hash", name="uq_document_content"),)
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    kind: str
    filename: str
    text: str
    content_hash: str
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now)


class Analysis(SQLModel, table=True):
    __tablename__ = "analyses"
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    document_id: str = Field(foreign_key="documents.id", index=True)
    status: str = "draft"
    revision: int = 1
    claims: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    method: str = "local-v1"
    created_at: datetime = Field(default_factory=utc_now)
    confirmed_at: datetime | None = None


class Target(SQLModel, table=True):
    __tablename__ = "targets"
    __table_args__ = (UniqueConstraint("resume_id", "jd_id", name="uq_target_pair"),)
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    resume_id: str = Field(foreign_key="analyses.id")
    jd_id: str = Field(foreign_key="analyses.id")
    result: dict = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now)


class BankQuestion(SQLModel, table=True):
    __tablename__ = "bank_questions"
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    normalized_text: str = Field(unique=True)
    content: dict = Field(sa_column=Column(JSON, nullable=False))
    source: str
    source_reference: dict = Field(sa_column=Column(JSON, nullable=False))
    version: int = 1
    rationale: str
    status: str = "new"
    bookmarked: bool = False
    active: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class QuestionTarget(SQLModel, table=True):
    __tablename__ = "question_targets"
    question_id: str = Field(foreign_key="bank_questions.id", primary_key=True)
    target_id: str = Field(foreign_key="targets.id", primary_key=True)
    evidence: dict = Field(sa_column=Column(JSON, nullable=False))


class InterviewSession(SQLModel, table=True):
    __tablename__ = "interview_sessions"
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    request_id: str = Field(unique=True)
    target_id: str | None = Field(default=None, foreign_key="targets.id")
    configuration: dict = Field(sa_column=Column(JSON, nullable=False))
    status: str = "not_started"
    revision: int = 1
    current_turn_id: str | None = None
    total_questions: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class InterviewTurn(SQLModel, table=True):
    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "primary_number", "follow_up_depth", name="uq_turn_position"
        ),
        UniqueConstraint("session_id", "submission_id", name="uq_answer_submission"),
    )
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="interview_sessions.id", index=True)
    question_id: str
    primary_number: int
    follow_up_depth: int = 0
    parent_turn_id: str | None = Field(default=None, foreign_key="interview_turns.id")
    snapshot: dict = Field(sa_column=Column(JSON, nullable=False))
    asked_at: datetime | None = None
    answered_at: datetime | None = None
    answer_text: str | None = None
    submission_id: str | None = None
    evaluation_state: str = "unsubmitted"
    evaluation_error: str | None = None
    lease_token: str | None = None
    lease_until: datetime | None = None


class TurnEvaluation(SQLModel, table=True):
    __tablename__ = "turn_evaluations"
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    turn_id: str = Field(foreign_key="interview_turns.id", unique=True)
    score: float
    result: dict = Field(sa_column=Column(JSON, nullable=False))
    provider: str
    model: str
    created_at: datetime = Field(default_factory=utc_now)


class LearningTopic(SQLModel, table=True):
    __tablename__ = "learning_topics"
    id: str = Field(primary_key=True)
    skill: str
    topic: str
    category: str
    practicing: bool = False
    revision: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class LearningEvidence(SQLModel, table=True):
    __tablename__ = "learning_evidence"
    __table_args__ = (UniqueConstraint("topic_id", "evaluation_id", name="uq_learning_evidence"),)
    id: str = Field(primary_key=True)
    topic_id: str = Field(foreign_key="learning_topics.id", index=True)
    evaluation_id: str = Field(foreign_key="turn_evaluations.id")
    raw_topics: list[str] = Field(sa_column=Column(JSON, nullable=False))
    assessment: str
    strong: bool
    observed_at: datetime
