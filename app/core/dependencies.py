from functools import lru_cache

from app.core.config import Settings, get_settings
from app.domain.errors import QueryValidationError
from app.integrations.database_connectors import build_connector_registry_from_json
from app.integrations.llm_client import LLMClient, OpenAICompatibleLLMClient, StubLLMClient
from app.repositories.catalog import InMemoryCatalogRepository, JsonFileCatalogRepository
from app.repositories.connections import ConnectionsFileRepository
from app.repositories.llm_config import LlmConfig, LlmConfigFileRepository
from app.repositories.prompt_config import PromptConfigFileRepository
from app.services.phase1_retrieval import RetrievalService
from app.services.phase2_sql import SqlGenerationService
from app.services.phase3_execution import QueryExecutionService
from app.services.phase4_insight import InsightService
from app.services.pipeline import QueryPipeline
from app.services.prompt_builder import PromptBuilder


@lru_cache
def get_catalog_repository() -> InMemoryCatalogRepository:
    settings = get_settings()
    return JsonFileCatalogRepository(settings.catalog_file_path)


@lru_cache
def get_connections_repository() -> ConnectionsFileRepository:
    settings = get_settings()
    return ConnectionsFileRepository(settings.connections_file_path)


@lru_cache
def get_llm_config_repository() -> LlmConfigFileRepository:
    settings = get_settings()
    return LlmConfigFileRepository(settings.llm_config_file_path)


def _build_connector_registry_json(settings: Settings) -> str:
    return build_merged_connector_registry_json(settings)


def build_merged_connector_registry_json(settings: Settings) -> str:
    from_env = settings.database_connections_json.strip()
    connections_repo = get_connections_repository()
    file_json = connections_repo.to_registry_json()
    if not from_env or from_env == "[]":
        return file_json
    if not file_json or file_json == "[]":
        return from_env
    import json
    env_entries = json.loads(from_env)
    file_entries = json.loads(file_json)
    merged_refs = {e["connection_ref"] for e in env_entries}
    combined = env_entries + [e for e in file_entries if e["connection_ref"] not in merged_refs]
    return json.dumps(combined)


def _resolve_llm_config(settings: Settings) -> LlmConfig:
    if settings.llm_provider.lower() != "stub" or settings.llm_base_url:
        return LlmConfig(
            provider=settings.llm_provider,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return get_llm_config_repository().get()


def build_llm_client(settings: Settings) -> LLMClient:
    cfg = _resolve_llm_config(settings)
    provider = cfg.provider.lower()
    if provider == "stub":
        return StubLLMClient()
    if provider in {"openai", "openai-compatible", "deepseek"}:
        return OpenAICompatibleLLMClient(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model=cfg.model,
            timeout_seconds=cfg.timeout_seconds,
        )
    raise QueryValidationError(f"Unsupported LLM provider: {cfg.provider}")


def get_prompt_config_repository(database_id: str) -> PromptConfigFileRepository:
    return PromptConfigFileRepository(data_dir="data", database_id=database_id)


def get_pipeline() -> QueryPipeline:
    settings: Settings = get_settings()
    catalog = get_catalog_repository()
    prompt_builder = PromptBuilder()
    llm_client = build_llm_client(settings)
    return QueryPipeline(
        retrieval_service=RetrievalService(catalog, llm_client=llm_client),
        sql_service=SqlGenerationService(prompt_builder=prompt_builder, llm_client=llm_client),
        execution_service=QueryExecutionService(
            default_max_rows=settings.default_max_rows,
            catalog=catalog,
            connectors=build_connector_registry_from_json(_build_connector_registry_json(settings)),
        ),
        insight_service=InsightService(prompt_builder=prompt_builder, llm_client=llm_client),
        default_max_rows=settings.default_max_rows,
        prompts_data_dir="data",
    )
