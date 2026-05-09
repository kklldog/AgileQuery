from functools import lru_cache

from app.core.config import Settings, get_settings
from app.domain.errors import QueryValidationError
from app.integrations.database_connectors import build_connector_registry_from_json
from app.integrations.llm_client import LLMClient, OpenAICompatibleLLMClient, StubLLMClient
from app.repositories.catalog import InMemoryCatalogRepository, JsonFileCatalogRepository
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


def build_llm_client(settings: Settings) -> LLMClient:
    provider = settings.llm_provider.lower()
    if provider == "stub":
        return StubLLMClient()
    if provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleLLMClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise QueryValidationError(f"Unsupported LLM provider: {settings.llm_provider}")


@lru_cache
def get_pipeline() -> QueryPipeline:
    settings: Settings = get_settings()
    catalog = get_catalog_repository()
    prompt_builder = PromptBuilder()
    llm_client = build_llm_client(settings)
    return QueryPipeline(
        retrieval_service=RetrievalService(catalog),
        sql_service=SqlGenerationService(prompt_builder=prompt_builder, llm_client=llm_client),
        execution_service=QueryExecutionService(
            default_max_rows=settings.default_max_rows,
            catalog=catalog,
            connectors=build_connector_registry_from_json(settings.database_connections_json),
        ),
        insight_service=InsightService(prompt_builder=prompt_builder, llm_client=llm_client),
        default_max_rows=settings.default_max_rows,
    )
