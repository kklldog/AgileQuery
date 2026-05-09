import json
from unittest.mock import MagicMock, patch

from app.integrations.llm_client import FixedResponseLLMClient, OpenAICompatibleLLMClient, StubLLMClient


def test_stub_llm_client_returns_empty_completion() -> None:
    assert StubLLMClient().complete("prompt") == ""


def test_fixed_response_llm_client_returns_configured_response() -> None:
    assert FixedResponseLLMClient("SELECT 1").complete("prompt") == "SELECT 1"


def test_openai_compatible_client_parses_chat_completion_response() -> None:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {"choices": [{"message": {"content": "SELECT 1"}}]}
    ).encode("utf-8")

    with patch("app.integrations.llm_client.urlopen", return_value=response) as mocked_urlopen:
        client = OpenAICompatibleLLMClient(
            base_url="https://llm.example/v1",
            api_key="secret",
            model="demo-model",
        )

        result = client.complete("Generate SQL")

    assert result == "SELECT 1"
    request = mocked_urlopen.call_args.args[0]
    assert request.full_url == "https://llm.example/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer secret"
