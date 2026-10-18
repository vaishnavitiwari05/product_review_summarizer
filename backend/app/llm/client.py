"""API-based LLM clients (Anthropic + OpenAI-compatible) built on httpx.

Each client turns (system, user) into text, retrying transient failures.
Errors are converted to DataValidationError with user-safe messages (API keys are never echoed)."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import httpx

from app.utils.errors import DataValidationError

log = logging.getLogger(__name__)
DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5"}
DEFAULT_URLS = {"anthropic": "https://api.anthropic.com", "openai": "https://api.openai.com/v1"}
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


class LLMClient(ABC):
    provider = "base"

    def __init__(self, api_key: str, model: str, base_url: str = "", timeout: float = 60.0,
                 max_retries: int = 2, backoff: float = 1.0, transport: httpx.BaseTransport | None = None):
        self.api_key, self.model = api_key, model
        self.base_url = (base_url or DEFAULT_URLS[self.provider]).rstrip("/")
        self.max_retries, self.backoff = max_retries, backoff
        self._http = httpx.Client(timeout=timeout, transport=transport)

    @abstractmethod
    def _request(self, system: str, messages: list[dict]) -> httpx.Response: ...
    @abstractmethod
    def _extract(self, data: dict) -> str: ...

    def complete(self, system: str, messages: list[dict]) -> str:
        last = "unknown error"
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._request(system, messages)
            except httpx.TimeoutException:
                last = "the request timed out"
            except httpx.HTTPError as exc:
                last = f"network error ({type(exc).__name__})"
            else:
                if resp.status_code in (401, 403):
                    raise DataValidationError(
                        "llm_auth_failed",
                        "The LLM provider rejected the API key. Check LLM_API_KEY in your .env file.",
                        status_code=502)
                if resp.status_code == 404:
                    raise DataValidationError(
                        "llm_model_not_found",
                        f"The LLM provider does not know the model '{self.model}'. Check LLM_MODEL.",
                        status_code=502)
                if resp.status_code in RETRY_STATUS:
                    last = f"provider returned HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    raise DataValidationError("llm_request_rejected",
                                              f"The LLM provider rejected the request (HTTP {resp.status_code}).",
                                              status_code=502, details={"body": resp.text[:200]})
                else:
                    try:
                        return self._extract(resp.json())
                    except (ValueError, KeyError, IndexError, TypeError):
                        last = "the provider response had an unexpected format"
            if attempt < self.max_retries:
                time.sleep(self.backoff * (2 ** attempt))
        raise DataValidationError(
            "llm_unavailable",
            f"The LLM service could not be reached after {self.max_retries + 1} attempts ({last}). "
            "Try again shortly, or set USE_MOCK_LLM=true for the offline demo mode.",
            status_code=503)


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def _request(self, system, messages):
        return self._http.post(
            f"{self.base_url}/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": self.model, "max_tokens": 1200, "temperature": 0.2,
                  "system": system, "messages": messages})

    def _extract(self, data):
        return "".join(b["text"] for b in data["content"] if b.get("type") == "text")


class OpenAIClient(LLMClient):
    provider = "openai"

    def _request(self, system, messages):
        return self._http.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"},
            json={"model": self.model, "temperature": 0.2, "max_tokens": 1200,
                  "messages": [{"role": "system", "content": system}, *messages]})

    def _extract(self, data):
        return data["choices"][0]["message"]["content"]


def build_client(provider: str, api_key: str, model: str, base_url: str = "", timeout: float = 60.0,
                 max_retries: int = 2, backoff: float = 1.0, transport=None) -> LLMClient:
    provider = provider.lower()
    if provider not in ("anthropic", "openai"):
        raise DataValidationError("llm_provider_unsupported",
                                  f"Unknown LLM_PROVIDER '{provider}'. Use 'anthropic' or 'openai'.", status_code=500)
    model = model or DEFAULT_MODELS.get(provider, "")
    if not model:
        raise DataValidationError("llm_model_missing",
                                  "LLM_MODEL is not set. Add a model name to your .env file.", status_code=500)
    cls = AnthropicClient if provider == "anthropic" else OpenAIClient
    return cls(api_key, model, base_url, timeout, max_retries, backoff, transport)
