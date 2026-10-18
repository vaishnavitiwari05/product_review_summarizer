"""Phase 7 entry point: structured payload -> validated LLMSummary (live or mock)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.llm.client import LLMClient, build_client
from app.llm.mock import mock_summary
from app.llm.prompts import REPAIR_TEMPLATE, SYSTEM_PROMPT, USER_TEMPLATE
from app.llm.schemas import LLMOutputError, LLMSummary, parse_summary
from app.utils.config import Settings, settings as default_settings
from app.utils.errors import DataValidationError


@dataclass
class SummaryResult:
    summary: LLMSummary
    mode: str                       # "live" | "mock"
    model: str
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "model": self.model, "warnings": self.warnings,
                "summary": self.summary.model_dump()}


def generate_summary(payload: dict, cfg: Settings | None = None, client: LLMClient | None = None) -> SummaryResult:
    cfg = cfg or default_settings

    if cfg.use_mock_llm and client is None:
        return SummaryResult(mock_summary(payload), "mock", "mock-summarizer",
                             ["Demo mode: this summary was generated offline from the statistics "
                              "(set USE_MOCK_LLM=false and add LLM_API_KEY for the real LLM)."])

    if client is None:
        if not cfg.llm_api_key:
            raise DataValidationError(
                "llm_api_key_missing",
                "No LLM API key configured. Set LLM_API_KEY in backend/.env, "
                "or set USE_MOCK_LLM=true to use the offline demo mode.",
                status_code=400)
        client = build_client(cfg.llm_provider, cfg.llm_api_key, cfg.llm_model, cfg.llm_base_url,
                              cfg.llm_timeout, cfg.llm_max_retries)

    messages = [{"role": "user", "content": USER_TEMPLATE.format(payload=json.dumps(payload, indent=2))}]
    text = client.complete(SYSTEM_PROMPT, messages)
    try:
        summary = parse_summary(text)
    except LLMOutputError as first:                 # one repair attempt
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": REPAIR_TEMPLATE.format(reason=str(first)[:150])}]
        try:
            summary = parse_summary(client.complete(SYSTEM_PROMPT, messages))
        except LLMOutputError as second:
            raise DataValidationError(
                "llm_bad_output",
                "The LLM did not return a usable summary. Please try again.",
                status_code=502, details={"reason": str(second)[:200]})
    return SummaryResult(summary, "live", client.model)
