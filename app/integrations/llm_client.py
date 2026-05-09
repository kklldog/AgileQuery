import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Protocol

from app.domain.errors import QueryValidationError


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        """Return a completion for the given prompt."""


class StubLLMClient:
    """Deterministic no-op client used until a real provider is configured."""

    def complete(self, prompt: str) -> str:
        return ""


class FixedResponseLLMClient:
    """Test helper client that always returns the configured response."""

    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, prompt: str) -> str:
        return self.response


class OpenAICompatibleLLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        if not self.base_url:
            raise ValueError("OpenAI-compatible LLM base_url is required")
        if not self.api_key:
            raise ValueError("OpenAI-compatible LLM api_key is required")
        if not self.model:
            raise ValueError("OpenAI-compatible LLM model is required")

    def complete(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        request = Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8")
            raise QueryValidationError(f"LLM provider HTTP error: {exc.code} {detail}") from exc
        except URLError as exc:
            raise QueryValidationError(f"LLM provider request failed: {exc.reason}") from exc

        try:
            parsed = json.loads(response_body)
            return parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise QueryValidationError("LLM provider returned an invalid response shape") from exc
