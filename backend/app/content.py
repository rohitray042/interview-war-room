import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from app.contracts import StrictModel


class Rubric(StrictModel):
    id: str
    version: int = Field(ge=1)
    dimensions: dict[str, dict[str, str]]
    weights: dict[str, int]


class Question(StrictModel):
    id: str
    version: int = Field(ge=1)
    topic: str
    difficulty: Literal["Easy", "Medium", "Hard", "Expert"]
    type: Literal["Conceptual", "Coding", "Scenario", "Production", "Architecture", "Behavioral"]
    prompt: str = Field(min_length=1)
    rubric_id: str
    expected_concepts: list[str] = Field(min_length=1)


class ContentCatalog:
    def __init__(self, root: Path):
        self.rubrics = self._load(root / "rubrics", Rubric)
        self.questions = self._load(root / "questions", Question)
        for rubric in self.rubrics.values():
            expected = {"accuracy", "depth", "reasoning", "clarity"}
            if set(rubric.weights) != expected or sum(rubric.weights.values()) != 100:
                raise ValueError("Rubric weights must contain four dimensions totaling 100")
            if set(rubric.dimensions) != expected:
                raise ValueError("Rubric dimensions are incomplete")
            for anchors in rubric.dimensions.values():
                if set(anchors) != {"0", "1", "2", "3", "4"}:
                    raise ValueError("Each rubric dimension needs anchors 0 through 4")
        for question in self.questions.values():
            if question.rubric_id not in self.rubrics:
                raise ValueError(f"Unknown rubric for {question.id}")

    @staticmethod
    def _load(directory, schema):
        values = {}
        for path in sorted(directory.glob("*.json")):
            value = schema.model_validate(json.loads(path.read_text()))
            if value.id in values:
                raise ValueError(f"Duplicate content ID: {value.id}")
            values[value.id] = value
        if not values:
            raise ValueError(f"No content found in {directory.name}")
        return values
