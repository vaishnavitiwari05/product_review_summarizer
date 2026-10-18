"""Structured LLM output + tolerant JSON parsing."""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, ValidationError


class AspectNote(BaseModel):
    aspect: str
    note: str


class LLMSummary(BaseModel):
    overall_summary: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    recurring_issues: list[str] = Field(default_factory=list)
    important_aspects: list[AspectNote] = Field(default_factory=list)
    sentiment_explanation: str = ""


class LLMOutputError(ValueError):
    """The model answered, but not with usable JSON."""


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def parse_summary(text: str) -> LLMSummary:
    t = _FENCE.sub("", text.strip()).strip()
    if not t.startswith("{"):                       # tolerate chatter around the JSON
        a, b = t.find("{"), t.rfind("}")
        if a == -1 or b <= a:
            raise LLMOutputError("no JSON object found in the model output")
        t = t[a:b + 1]
    try:
        data = json.loads(t)
    except json.JSONDecodeError as exc:
        raise LLMOutputError(f"invalid JSON: {exc}") from exc
    # accept plain strings for important_aspects
    aspects = data.get("important_aspects", [])
    if isinstance(aspects, list):
        data["important_aspects"] = [a if isinstance(a, dict) else {"aspect": str(a), "note": ""} for a in aspects]
    try:
        return LLMSummary(**data)
    except (ValidationError, TypeError) as exc:
        raise LLMOutputError(f"JSON does not match the expected structure: {str(exc)[:200]}") from exc
