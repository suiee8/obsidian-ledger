"""The JSON a model must return. Anything else is rejected and retried once."""

from __future__ import annotations

import json
import re
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Section = Literal["verdict", "leaks", "strengths", "risk", "next_step"]
FINDING_ID = r"^(seg~[a-z_]+~.{1,80}|beh~[a-z_]+)$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SummaryParagraph(Strict):
    section: Section
    text: str = Field(min_length=1, max_length=900)


class Summary(Strict):
    headline: str = Field(min_length=1, max_length=200)
    paragraphs: list[SummaryParagraph] = Field(min_length=1, max_length=5)

    @field_validator("paragraphs")
    @classmethod
    def one_per_section(cls, value: list[SummaryParagraph]) -> list[SummaryParagraph]:
        sections = [paragraph.section for paragraph in value]
        if len(sections) != len(set(sections)):
            raise ValueError("each section may appear once")
        return value


class AnswerParagraph(Strict):
    text: str = Field(min_length=1, max_length=900)
    finding_ids: list[str] = Field(default_factory=list[str], max_length=5)
    trade_ids: list[str] = Field(default_factory=list[str], max_length=10)


class Answer(Strict):
    paragraphs: list[AnswerParagraph] = Field(min_length=1, max_length=6)


SUMMARY_SHAPE = (
    '{"headline": "one sentence", "paragraphs": [{"section": "verdict", "text": "..."}, '
    '{"section": "leaks", "text": "..."}, {"section": "strengths", "text": "..."}, '
    '{"section": "risk", "text": "..."}, {"section": "next_step", "text": "..."}]}'
)
ANSWER_SHAPE = (
    '{"paragraphs": [{"text": "...", "finding_ids": ["beh~revenge"], "trade_ids": ["T000042"]}]}'
)

Model = TypeVar("Model", bound=BaseModel)
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class InvalidOutput(ValueError):
    pass


def parse[Model: BaseModel](content: str | None, model: type[Model]) -> Model:
    """Parse a model reply as JSON for the schema. Tolerates a surrounding code fence only."""
    if not content or not content.strip():
        raise InvalidOutput("The reply was empty.")
    text = FENCE.sub("", content.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidOutput(f"The reply is not valid JSON ({exc.msg}).") from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "the reply"
        raise InvalidOutput(
            f"The reply does not match the schema at {where}: {first['msg']}."
        ) from exc
