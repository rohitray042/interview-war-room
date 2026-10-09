from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(StrictModel):
    document_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)

    def verify(self, document_id: str, text: str) -> bool:
        return (
            self.document_id == document_id
            and self.end <= len(text)
            and text[self.start : self.end] == self.quote
        )

    @model_validator(mode="after")
    def valid_range(self):
        if self.end <= self.start:
            raise ValueError("Evidence end must be after start")
        return self


class SupportedClaim(StrictModel):
    claim: str = Field(min_length=1)
    source_kind: Literal["resume", "jd"]
    evidence: list[Evidence] = Field(min_length=1)


class Dimension(StrictModel):
    score: int = Field(ge=0, le=4)
    rationale: str = Field(min_length=1)


class Mistake(StrictModel):
    answer_quote: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class Evaluation(StrictModel):
    accuracy: Dimension
    depth: Dimension
    reasoning: Dimension
    clarity: Dimension
    missing_concepts: list[str]
    mistakes: list[Mistake]
    feedback: str = Field(min_length=1)
    follow_up_recommended: bool


class InterviewPolicy(StrictModel):
    max_follow_ups: int = Field(default=2, ge=0, le=3)


class LLMRequest(StrictModel):
    task: Literal[
        "resume_analysis", "jd_analysis", "question_generation", "evaluation", "follow_up"
    ]
    instructions: str
    context: str
    output_schema: dict


class LLMResult(StrictModel):
    data: dict
    provider: str
    model: str
    request_id: str


class LLMProvider(Protocol):
    async def generate_structured(self, request: LLMRequest) -> LLMResult: ...


class ProviderUnavailable(Exception):
    pass


class DisabledProvider:
    async def generate_structured(self, request: LLMRequest) -> LLMResult:
        raise ProviderUnavailable("No live LLM provider is configured")
