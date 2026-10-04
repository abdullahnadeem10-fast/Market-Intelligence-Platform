"""LLM abstraction.

`LLMService` is the only place that talks to a language model. The default implementation speaks
the OpenAI-compatible Chat Completions protocol, so any compatible provider (OpenAI, Azure OpenAI
proxy, OpenRouter, Together, Groq, a local Ollama/vLLM server, ...) works by changing
LLM_BASE_URL / LLM_MODEL / LLM_API_KEY. The key is read from the backend environment only.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    tokens_estimated: bool
    latency_ms: int
    model: str


class LLMError(Exception):
    """A user-presentable LLM failure (message never includes secrets or raw provider bodies)."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def estimate_tokens(text: str) -> int:
    # ~4 characters per token for English text; used only when the provider omits usage.
    return max(1, len(text) // 4)


class LLMService(ABC):
    provider: str
    model: str

    @abstractmethod
    def complete_json(self, system: str, user: str, max_output_tokens: int) -> LLMResponse:
        """Return a completion whose content is expected to be a JSON object."""


class OpenAICompatibleLLM(LLMService):
    provider = "openai-compatible"
    max_attempts = 3

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        if not settings.llm_api_key:
            raise LLMError("AI analysis is not configured: set LLM_API_KEY in the backend .env", status_code=503)
        self.model = settings.llm_model
        self._url = settings.llm_base_url.rstrip("/") + "/chat/completions"
        self._client = httpx.Client(
            timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=10.0),
            headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
            transport=transport,
        )

    def complete_json(self, system: str, user: str, max_output_tokens: int) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        started = time.perf_counter()
        last_error: LLMError | None = None
        for attempt in range(self.max_attempts):
            try:
                resp = self._client.post(self._url, json=payload)
            except httpx.TimeoutException:
                last_error = LLMError("The AI provider timed out. Please try again.", 504)
            except httpx.HTTPError as exc:
                logger.warning("LLM network error: %s", exc.__class__.__name__)
                last_error = LLMError("Could not reach the AI provider.", 502)
            else:
                if resp.status_code == 200:
                    return self._parse(resp, started, system + user)
                if resp.status_code in (401, 403):
                    raise LLMError("The AI provider rejected the API key (check LLM_API_KEY).", 502)
                if resp.status_code == 400 and "response_format" in resp.text and "response_format" in payload:
                    payload.pop("response_format")  # some compatible servers don't support JSON mode
                    continue
                if resp.status_code == 429:
                    last_error = LLMError("The AI provider is rate limiting requests. Please wait and retry.", 429)
                    retry_after = resp.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else 2.0 * (attempt + 1)
                    if attempt < self.max_attempts - 1:
                        time.sleep(min(delay, 10.0))
                    continue
                if resp.status_code >= 500:
                    last_error = LLMError(f"The AI provider returned an error (HTTP {resp.status_code}).", 502)
                else:
                    logger.warning("LLM request rejected: HTTP %s", resp.status_code)
                    raise LLMError(f"The AI provider rejected the request (HTTP {resp.status_code}).", 502)
            if attempt < self.max_attempts - 1:
                time.sleep(1.0 * (attempt + 1))
        assert last_error is not None
        raise last_error

    def _parse(self, resp: httpx.Response, started: float, prompt_text: str) -> LLMResponse:
        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError("The AI provider returned an invalid response.", 502)
        usage = data.get("usage") or {}
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        estimated = not (isinstance(input_tokens, int) and isinstance(output_tokens, int))
        return LLMResponse(
            content=content,
            input_tokens=input_tokens if isinstance(input_tokens, int) else estimate_tokens(prompt_text),
            output_tokens=output_tokens if isinstance(output_tokens, int) else estimate_tokens(content),
            tokens_estimated=estimated,
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=data.get("model") or self.model,
        )


def get_llm_service(settings: Settings | None = None) -> LLMService | None:
    """Return the configured LLM, or None for the offline 'extractive' mode."""
    settings = settings or get_settings()
    provider = settings.llm_provider.lower()
    if provider in ("extractive", "none", "offline"):
        return None
    if provider in ("openai", "openai-compatible"):
        return OpenAICompatibleLLM(settings)
    raise LLMError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'", status_code=503)
