from typing import Literal
from uuid import uuid4

from pydantic import Field, field_validator

from app.contracts import Evidence, StrictModel

Category = Literal[
    "name",
    "summary",
    "years_experience",
    "skills",
    "technologies",
    "cloud_platforms",
    "databases",
    "programming_languages",
    "projects",
    "work_experience",
    "responsibilities",
    "achievements",
    "certifications",
    "education",
    "experience_requirements",
    "domain_knowledge",
    "behavioral_requirements",
]
Requirement = Literal["must_have", "good_to_have", "nice_to_have", "unspecified"]


class Claim(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()), max_length=80)
    category: Category
    value: str = Field(min_length=1, max_length=3000)
    origin: Literal["extracted", "user", "ai_inferred"] = "extracted"
    reviewed: bool = False
    uncertain: bool = False
    requirement: Requirement = "unspecified"
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)

    @field_validator("value")
    @classmethod
    def nonempty_value(cls, value):
        if not value.strip():
            raise ValueError("Value cannot be blank")
        return value


class AIExtraction(StrictModel):
    claims: list[Claim] = Field(max_length=250)


class TextDocument(StrictModel):
    kind: Literal["resume", "jd"]
    text: str = Field(min_length=1, max_length=100000)
    filename: str = Field(default="Pasted text", min_length=1, max_length=200)


class ReviewInput(StrictModel):
    revision: int = Field(ge=1)
    claims: list[Claim] = Field(max_length=250)


class RevisionInput(StrictModel):
    revision: int = Field(ge=1)


class TargetInput(StrictModel):
    resume_id: str
    jd_id: str
