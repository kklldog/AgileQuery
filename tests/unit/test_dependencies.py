from app.core.config import Settings
from app.core.dependencies import build_llm_client
from app.domain.errors import QueryValidationError
from app.integrations.llm_client import OpenAICompatibleLLMClient, StubLLMClient


def test_build_llm_client_defaults_to_stub() -> None:
    client = build_llm_client(Settings())

    assert isinstance(client, StubLLMClient)


def test_build_llm_client_supports_openai_compatible_provider() -> None:
    client = build_llm_client(
        Settings(
            llm_provider="openai-compatible",
            llm_base_url="https://llm.example/v1",
            llm_api_key="secret",
            llm_model="demo-model",
        )
    )

    assert isinstance(client, OpenAICompatibleLLMClient)


def test_build_llm_client_rejects_unknown_provider() -> None:
    try:
        build_llm_client(Settings(llm_provider="unknown"))
    except QueryValidationError as exc:
        assert str(exc) == "Unsupported LLM provider: unknown"
    else:
        raise AssertionError("Expected unsupported provider to fail")
