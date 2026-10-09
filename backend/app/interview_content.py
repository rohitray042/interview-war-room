"""Reuse the rubric contract with question-type-specific versioned content."""

import json
from string import Formatter
from typing import get_args

from pydantic import Field

from app.content import Rubric
from app.contracts import StrictModel
from app.interview_schemas import InterviewType


class TypePolicy(StrictModel):
    excluded_types: list[str]
    category: str | None
    question_type: str | None


class InterviewContent(StrictModel):
    version: int = Field(ge=1)
    rubrics: dict[str, Rubric]
    follow_up_templates: list[str] = Field(min_length=2, max_length=2)
    types: dict[str, TypePolicy]

    @classmethod
    def load(cls, root):
        content = cls.model_validate(json.loads((root / "interview-policy.json").read_text()))
        if set(content.types) != set(get_args(InterviewType)):
            raise ValueError("Interview type policies are incomplete")
        if set(content.rubrics) != {"technical", "sql", "system_design", "behavioral"}:
            raise ValueError("Interview rubrics are incomplete")
        for rubric in content.rubrics.values():
            if set(rubric.weights) != set(rubric.dimensions) or sum(rubric.weights.values()) != 100:
                raise ValueError("Rubric weights must match dimensions and total 100")
            if any(w <= 0 for w in rubric.weights.values()):
                raise ValueError("Rubric weights must be positive")
            if any(set(a) != {"0", "1", "2", "3", "4"} for a in rubric.dimensions.values()):
                raise ValueError("Rubric anchors must cover 0 through 4")
        for template in content.follow_up_templates:
            fields = {name for _, name, _, _ in Formatter().parse(template) if name}
            if fields != {"skill", "topic"}:
                raise ValueError("Follow-ups must refer only to skill and topic")
        return content

    def rubric_for(self, question):
        kind = "sql" if question["category"] == "SQL" else question["question_type"]
        return self.rubrics.get(kind, self.rubrics["technical"]).model_dump()
