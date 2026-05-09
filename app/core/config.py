from functools import lru_cache
from os import getenv

from pydantic import BaseModel, Field


class Settings(BaseModel):
    default_database_id: str = "demo"
    default_max_rows: int = Field(default=50, ge=1, le=1000)
    sqlite_uri: str = "file:agilequery_demo?mode=memory&cache=shared"
    catalog_file_path: str = "data/catalog.json"
    llm_provider: str = "stub"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    database_connections_json: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings(
        catalog_file_path=getenv("AGILEQUERY_CATALOG_FILE_PATH", "data/catalog.json"),
        llm_provider=getenv("AGILEQUERY_LLM_PROVIDER", "stub"),
        llm_base_url=getenv("AGILEQUERY_LLM_BASE_URL", ""),
        llm_api_key=getenv("AGILEQUERY_LLM_API_KEY", ""),
        llm_model=getenv("AGILEQUERY_LLM_MODEL", ""),
        llm_timeout_seconds=float(getenv("AGILEQUERY_LLM_TIMEOUT_SECONDS", "30")),
        database_connections_json=getenv("AGILEQUERY_DATABASE_CONNECTIONS_JSON", ""),
    )
