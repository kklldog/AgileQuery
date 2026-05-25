import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.core.dependencies import (
    build_merged_connector_registry_json,
    build_llm_client,
    get_catalog_repository,
    get_connections_repository,
    get_llm_config_repository,
    get_pipeline,
    get_prompt_config_repository,
    get_settings,
)
from app.domain.errors import CatalogLookupError, QueryValidationError
from app.domain.models import ColumnMeta, DatabaseMeta, JoinRuleMeta, MetricRuleMeta, SpaceMeta, TableMeta
from app.integrations.database_connectors import (
    PostgresConnector,
    SqlServerConnector,
    build_connector_registry_from_json,
)
from app.repositories.catalog import InMemoryCatalogRepository
from app.repositories.connections import ConnectionConfig, ConnectionsFileRepository
from app.repositories.llm_config import LlmConfig, LlmConfigFileRepository
from app.repositories.prompt_config import (
    ALL_PROMPT_KEYS,
    DEFAULT_PROMPTS,
    PROMPT_DESCRIPTIONS,
    PROMPT_LABELS,
    PromptConfig,
    PromptConfigFileRepository,
)

router = APIRouter(prefix="/admin", tags=["admin"])
SPACE_ID_PATTERN = re.compile(r"^[a-z0-9_-]+$")


class TestConnectionRequest(BaseModel):
    dialect: str
    dsn: str
    connect_timeout_seconds: int = Field(default=10, ge=1, le=120)


@router.post("/test-connection")
def test_connection(request: TestConnectionRequest):
    dialect = request.dialect.lower()
    try:
        if dialect in ("postgresql", "postgres"):
            connector = PostgresConnector(
                dsn=request.dsn,
                connection_ref="__test__",
                connect_timeout_seconds=request.connect_timeout_seconds,
            )
            conn = connector._connect()
            conn.close()
        elif dialect in ("sqlserver", "mssql", "tsql"):
            connector = SqlServerConnector(
                dsn=request.dsn,
                connection_ref="__test__",
                connect_timeout_seconds=request.connect_timeout_seconds,
            )
            conn = connector._connect()
            conn.close()
        else:
            raise HTTPException(status_code=422, detail=f"不支持测试该数据库类型: {dialect}")
    except QueryValidationError as exc:
        return {"ok": False, "message": str(exc)}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": "连接成功"}


class AiFillColumnRequest(BaseModel):
    name: str
    data_type: str = ""


class AiFillTableMetaRequest(BaseModel):
    table_name: str
    columns: list[AiFillColumnRequest] = []
    database_id: str = ""


@router.post("/ai/fill-table-meta")
def ai_fill_table_meta(
    request: AiFillTableMetaRequest,
    settings=Depends(get_settings),
):
    cols_desc = "\n".join(
        f"  - {c.name} ({c.data_type})" if c.data_type else f"  - {c.name}"
        for c in request.columns
    )
    if request.database_id:
        prompt_template = get_prompt_config_repository(request.database_id).get().get("ai_fill_table")
    else:
        from app.repositories.prompt_config import DEFAULT_PROMPTS
        prompt_template = DEFAULT_PROMPTS["ai_fill_table"]
    prompt = prompt_template.replace("{table_name}", request.table_name).replace("{cols_desc}", cols_desc)

    try:
        llm = build_llm_client(settings)
        raw = llm.complete(prompt)
        raw = raw.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("LLM did not return JSON")
        result = json.loads(raw[start:end])
        return {"ok": True, "data": result}
    except Exception as exc:
        return {"ok": False, "message": str(exc), "data": None}


class _TableSummary(BaseModel):
    name: str
    columns: list[AiFillColumnRequest] = []


class AiFillJoinsRequest(BaseModel):
    tables: list[_TableSummary] = []
    database_id: str = ""


class AiFillMetricsRequest(BaseModel):
    tables: list[_TableSummary] = []
    database_id: str = ""


@router.post("/ai/fill-joins")
def ai_fill_joins(
    request: AiFillJoinsRequest,
    settings=Depends(get_settings),
):
    tables_desc = "\n".join(
        f"- {t.name}({', '.join(c.name + (':' + c.data_type if c.data_type else '') for c in t.columns)})"
        for t in request.tables
    )
    if request.database_id:
        prompt = get_prompt_config_repository(request.database_id).get().get("ai_fill_joins").replace("{tables_desc}", tables_desc)
    else:
        from app.repositories.prompt_config import DEFAULT_PROMPTS
        prompt = DEFAULT_PROMPTS["ai_fill_joins"].replace("{tables_desc}", tables_desc)

    try:
        llm = build_llm_client(settings)
        text = llm.complete(prompt).strip()
        return {"ok": True, "text": text}
    except Exception as exc:
        return {"ok": False, "message": str(exc), "text": ""}


@router.post("/ai/fill-metrics")
def ai_fill_metrics(
    request: AiFillMetricsRequest,
    settings=Depends(get_settings),
):
    tables_desc = "\n".join(
        f"- {t.name}({', '.join(c.name + (':' + c.data_type if c.data_type else '') for c in t.columns)})"
        for t in request.tables
    )
    if request.database_id:
        prompt = get_prompt_config_repository(request.database_id).get().get("ai_fill_metrics").replace("{tables_desc}", tables_desc)
    else:
        from app.repositories.prompt_config import DEFAULT_PROMPTS
        prompt = DEFAULT_PROMPTS["ai_fill_metrics"].replace("{tables_desc}", tables_desc)

    try:
        llm = build_llm_client(settings)
        text = llm.complete(prompt).strip()
        return {"ok": True, "text": text}
    except Exception as exc:
        return {"ok": False, "message": str(exc), "text": ""}


class ColumnMetaRequest(BaseModel):
    name: str
    data_type: str = ""
    description: str = ""


class TableMetaRequest(BaseModel):
    name: str
    business_name: str = ""
    description: str = ""
    alias: str = ""
    columns: list[ColumnMetaRequest] = []


class JoinRuleMetaRequest(BaseModel):
    id: str
    description: str = ""
    left_table: str = ""
    right_table: str = ""
    condition: str = ""
    guidance: str = ""
    examples: list[str] = []


class MetricRuleMetaRequest(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    expression: str = ""
    source_table: str = ""
    output_alias: str = ""
    synonyms: list[str] = []


# ---------------------------------------------------------------------------
# Space request models
# ---------------------------------------------------------------------------

class CreateSpaceRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    tables: list[TableMetaRequest] = []
    join_rules: list[JoinRuleMetaRequest] = []
    metric_rules: list[MetricRuleMetaRequest] = []
    joins_text: str = ""
    metrics_text: str = ""

    @field_validator("id")
    @classmethod
    def validate_space_id(cls, value: str) -> str:
        if not SPACE_ID_PATTERN.fullmatch(value):
            raise ValueError("Space id must use lowercase letters, numbers, hyphens, or underscores")
        return value


class UpdateSpaceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    tables: list[TableMetaRequest] | None = None
    join_rules: list[JoinRuleMetaRequest] | None = None
    metric_rules: list[MetricRuleMetaRequest] | None = None
    joins_text: str | None = None
    metrics_text: str | None = None


class CreateDatabaseRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    dialect: str = Field(min_length=1, max_length=32)
    description: str = ""
    dsn: str = ""
    connect_timeout_seconds: int = Field(default=10, ge=1, le=120)
    statement_timeout_ms: int = Field(default=30000, ge=1000, le=300000)

    @field_validator("id")
    @classmethod
    def validate_database_id(cls, value: str) -> str:
        if not SPACE_ID_PATTERN.fullmatch(value):
            raise ValueError("Database id must use lowercase letters, numbers, hyphens, or underscores")
        return value

    @field_validator("dialect")
    @classmethod
    def validate_dialect(cls, value: str) -> str:
        allowed = {"sqlite", "sqlite-demo", "postgresql", "postgres", "mysql", "sqlserver", "mssql", "tsql"}
        if value.lower() not in allowed:
            raise ValueError(f"Unsupported dialect: {value}. Allowed: {', '.join(sorted(allowed))}")
        return value.lower()


class UpdateDatabaseRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    dialect: str | None = Field(default=None, min_length=1, max_length=32)
    description: str | None = None
    dsn: str | None = None
    connect_timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    statement_timeout_ms: int | None = Field(default=None, ge=1000, le=300000)

    @field_validator("dialect")
    @classmethod
    def validate_dialect(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {"sqlite", "sqlite-demo", "postgresql", "postgres", "mysql", "sqlserver", "mssql", "tsql"}
        if value.lower() not in allowed:
            raise ValueError(f"Unsupported dialect: {value}. Allowed: {', '.join(sorted(allowed))}")
        return value.lower()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_table_meta(t: TableMetaRequest) -> TableMeta:
    return TableMeta(
        name=t.name,
        business_name=t.business_name,
        description=t.description,
        alias=t.alias,
        columns=[ColumnMeta(name=c.name, data_type=c.data_type, description=c.description) for c in t.columns],
    )


def _to_join_rule(j: JoinRuleMetaRequest) -> JoinRuleMeta:
    return JoinRuleMeta(
        id=j.id,
        description=j.description,
        left_table=j.left_table,
        right_table=j.right_table,
        condition=j.condition,
        guidance=j.guidance,
        examples=list(j.examples),
    )


def _to_metric_rule(m: MetricRuleMetaRequest) -> MetricRuleMeta:
    return MetricRuleMeta(
        id=m.id,
        name=m.name,
        description=m.description,
        expression=m.expression,
        source_table=m.source_table,
        output_alias=m.output_alias,
        synonyms=list(m.synonyms),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/databases/{database_id}/introspect")
def introspect_database(
    database_id: str,
    schema: str = "public",
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
):
    try:
        database = catalog.get_database(database_id)
        settings = get_settings()
        registry = build_connector_registry_from_json(build_merged_connector_registry_json(settings))

        if database.connection_ref not in registry:
            raise QueryValidationError(f"No connector found for {database.connection_ref}")
        connector = registry[database.connection_ref]
        if not hasattr(connector, "introspect_objects"):
            raise QueryValidationError(f"Connector for {database.connection_ref} does not support introspection")
        objects = connector.introspect_objects(schema=schema)
        return {"schema": schema, "objects": objects}
    except (CatalogLookupError, QueryValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/databases/{database_id}/spaces/{space_id}/sync")
def sync_schema(
    database_id: str,
    space_id: str,
    schema: str = "public",
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
):
    try:
        database = catalog.get_database(database_id)
        settings = get_settings()
        registry = build_connector_registry_from_json(settings.database_connections_json)

        if database.connection_ref not in registry:
            raise QueryValidationError(f"No connector found for {database.connection_ref}")

        connector = registry[database.connection_ref]

        if not hasattr(connector, "introspect_tables"):
            raise QueryValidationError(f"Connector for {database.connection_ref} does not support introspection")

        tables = connector.introspect_tables(schema=schema)
        catalog.update_space_tables(database_id, space_id, tables)

        get_pipeline.cache_clear()

        return {"status": "success", "tables_synced": len(tables), "table_names": [t.name for t in tables]}

    except (CatalogLookupError, QueryValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/databases")
def list_databases(catalog: InMemoryCatalogRepository = Depends(get_catalog_repository)):
    try:
        databases = [catalog.get_database(db_id) for db_id in catalog.database_ids()]
        return {"databases": databases}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/databases", status_code=201)
def create_database(
    request: CreateDatabaseRequest,
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
    connections: ConnectionsFileRepository = Depends(get_connections_repository),
):
    try:
        connection_ref = request.id
        if request.dialect in {"postgresql", "postgres", "mysql"}:
            dialect_norm = request.dialect
        elif request.dialect in {"sqlserver", "mssql", "tsql"}:
            dialect_norm = "tsql"
        else:
            dialect_norm = "sqlite-demo"

        needs_dsn = dialect_norm in {"postgresql", "postgres", "tsql"}
        if needs_dsn:
            if not request.dsn.strip():
                raise HTTPException(status_code=422, detail=f"dsn is required for {dialect_norm} dialect")
            persisted_dialect = request.dialect if dialect_norm == "tsql" else dialect_norm
            connections.upsert(ConnectionConfig(
                connection_ref=connection_ref,
                dialect=persisted_dialect,
                dsn=request.dsn.strip(),
                connect_timeout_seconds=request.connect_timeout_seconds,
                statement_timeout_ms=request.statement_timeout_ms,
            ))

        database = DatabaseMeta(
            id=request.id,
            name=request.name,
            dialect=dialect_norm,
            description=request.description,
            connection_ref=connection_ref,
        )
        catalog.add_database(database)
        get_pipeline.cache_clear()
        return {"database": database}
    except HTTPException:
        raise
    except CatalogLookupError as exc:
        message = str(exc)
        if message.startswith("Database already exists"):
            raise HTTPException(status_code=409, detail=message)
        raise HTTPException(status_code=400, detail=message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/databases/{database_id}", status_code=204)
def delete_database(
    database_id: str,
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
    connections: ConnectionsFileRepository = Depends(get_connections_repository),
):
    try:
        database = catalog.get_database(database_id)
        catalog.delete_database(database_id)
        connections.delete(database.connection_ref)
        get_pipeline.cache_clear()
    except CatalogLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _normalize_dialect(dialect: str) -> str:
    if dialect in {"postgresql", "postgres", "mysql"}:
        return dialect
    if dialect in {"sqlserver", "mssql", "tsql"}:
        return "tsql"
    return "sqlite-demo"


@router.get("/databases/{database_id}/connection")
def get_database_connection(
    database_id: str,
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
    connections: ConnectionsFileRepository = Depends(get_connections_repository),
):
    try:
        database = catalog.get_database(database_id)
        config = connections.get(database.connection_ref)
        if config is None:
            return {"connection": None}
        return {
            "connection": {
                "connection_ref": config.connection_ref,
                "dialect": config.dialect,
                "dsn": config.dsn,
                "connect_timeout_seconds": config.connect_timeout_seconds,
                "statement_timeout_ms": config.statement_timeout_ms,
            }
        }
    except CatalogLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/databases/{database_id}")
def update_database(
    database_id: str,
    request: UpdateDatabaseRequest,
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
    connections: ConnectionsFileRepository = Depends(get_connections_repository),
):
    if (
        request.name is None
        and request.dialect is None
        and request.description is None
        and request.dsn is None
        and request.connect_timeout_seconds is None
        and request.statement_timeout_ms is None
    ):
        raise HTTPException(status_code=422, detail="At least one field must be provided")
    try:
        existing = catalog.get_database(database_id)
        new_dialect_norm = _normalize_dialect(request.dialect) if request.dialect is not None else existing.dialect

        needs_dsn = new_dialect_norm in {"postgresql", "postgres", "tsql"}
        if needs_dsn:
            current_cfg = connections.get(existing.connection_ref)
            new_dsn = request.dsn.strip() if request.dsn is not None and request.dsn.strip() else (current_cfg.dsn if current_cfg else "")
            if not new_dsn:
                raise HTTPException(status_code=422, detail=f"dsn is required for {new_dialect_norm} dialect")
            persisted_dialect = request.dialect if request.dialect is not None else (current_cfg.dialect if current_cfg else new_dialect_norm)
            if new_dialect_norm == "tsql" and persisted_dialect not in {"sqlserver", "mssql", "tsql"}:
                persisted_dialect = "sqlserver"
            connections.upsert(ConnectionConfig(
                connection_ref=existing.connection_ref,
                dialect=persisted_dialect,
                dsn=new_dsn,
                connect_timeout_seconds=request.connect_timeout_seconds if request.connect_timeout_seconds is not None else (current_cfg.connect_timeout_seconds if current_cfg else 10),
                statement_timeout_ms=request.statement_timeout_ms if request.statement_timeout_ms is not None else (current_cfg.statement_timeout_ms if current_cfg else 30000),
            ))
        else:
            if connections.get(existing.connection_ref) is not None:
                connections.delete(existing.connection_ref)

        updated = catalog.update_database(
            database_id,
            name=request.name,
            description=request.description,
            dialect=new_dialect_norm if request.dialect is not None else None,
        )
        get_pipeline.cache_clear()
        return {"database": updated}
    except HTTPException:
        raise
    except CatalogLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/databases/{database_id}/spaces", status_code=201)
def create_space(
    database_id: str,
    request: CreateSpaceRequest,
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
):
    try:
        space = SpaceMeta(
            id=request.id,
            name=request.name,
            description=request.description,
            tables=[_to_table_meta(t) for t in request.tables],
            join_rules=[_to_join_rule(j) for j in request.join_rules],
            metric_rules=[_to_metric_rule(m) for m in request.metric_rules],
            joins_text=request.joins_text,
            metrics_text=request.metrics_text,
        )
        catalog.add_space(database_id, space)
        return {"space": space}
    except CatalogLookupError as exc:
        message = str(exc)
        if message.startswith("Unknown database"):
            raise HTTPException(status_code=404, detail=message)
        if message.startswith("Space already exists"):
            raise HTTPException(status_code=409, detail=message)
        raise HTTPException(status_code=400, detail=message)


@router.get("/databases/{database_id}/spaces")
def list_spaces(database_id: str, catalog: InMemoryCatalogRepository = Depends(get_catalog_repository)):
    try:
        spaces = catalog.list_spaces(database_id)
        return {"spaces": spaces}
    except CatalogLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/databases/{database_id}/spaces/{space_id}")
def get_space(
    database_id: str,
    space_id: str,
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
):
    try:
        space = catalog.get_space(database_id, space_id)
        return {"space": space}
    except CatalogLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/databases/{database_id}/spaces/{space_id}")
def update_space(
    database_id: str,
    space_id: str,
    request: UpdateSpaceRequest,
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
):
    if (
        request.name is None
        and request.description is None
        and request.tables is None
        and request.join_rules is None
        and request.metric_rules is None
        and request.joins_text is None
        and request.metrics_text is None
    ):
        raise HTTPException(status_code=422, detail="At least one field must be provided")
    try:
        space = catalog.update_space(
            database_id,
            space_id,
            name=request.name,
            description=request.description,
            tables=[_to_table_meta(t) for t in request.tables] if request.tables is not None else None,
            join_rules=[_to_join_rule(j) for j in request.join_rules] if request.join_rules is not None else None,
            metric_rules=[_to_metric_rule(m) for m in request.metric_rules] if request.metric_rules is not None else None,
            joins_text=request.joins_text,
            metrics_text=request.metrics_text,
        )
        return {"space": space}
    except CatalogLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/databases/{database_id}/spaces/{space_id}", status_code=204)
def delete_space(
    database_id: str,
    space_id: str,
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
):
    try:
        catalog.delete_space(database_id, space_id)
    except CatalogLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class UpdateLlmConfigRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: float = Field(default=30.0, gt=0)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        allowed = {"stub", "openai", "openai-compatible", "deepseek"}
        if value.lower() not in allowed:
            raise ValueError(f"Unsupported provider: {value}. Allowed: {', '.join(sorted(allowed))}")
        return value.lower()


@router.get("/llm-config")
def get_llm_config(
    llm_repo: LlmConfigFileRepository = Depends(get_llm_config_repository),
):
    cfg = llm_repo.get()
    return {
        "provider": cfg.provider,
        "base_url": cfg.base_url,
        "api_key_set": bool(cfg.api_key),
        "model": cfg.model,
        "timeout_seconds": cfg.timeout_seconds,
    }


@router.put("/llm-config")
def update_llm_config(
    request: UpdateLlmConfigRequest,
    llm_repo: LlmConfigFileRepository = Depends(get_llm_config_repository),
):
    try:
        if request.provider in {"openai", "openai-compatible"}:
            if not request.base_url.strip():
                raise HTTPException(status_code=422, detail="base_url is required for openai-compatible provider")
            if not request.model.strip():
                raise HTTPException(status_code=422, detail="model is required for openai-compatible provider")
        llm_repo.update(LlmConfig(
            provider=request.provider,
            base_url=request.base_url.strip(),
            api_key=request.api_key,
            model=request.model.strip(),
            timeout_seconds=request.timeout_seconds,
        ))
        get_pipeline.cache_clear()
        cfg = llm_repo.get()
        return {
            "provider": cfg.provider,
            "base_url": cfg.base_url,
            "api_key_set": bool(cfg.api_key),
            "model": cfg.model,
            "timeout_seconds": cfg.timeout_seconds,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/databases/{database_id}/prompts")
def get_database_prompts(database_id: str):
    repo = get_prompt_config_repository(database_id)
    cfg = repo.get()
    return {
        key: {
            "value": cfg.get(key),
            "label": PROMPT_LABELS[key],
            "description": PROMPT_DESCRIPTIONS[key],
            "is_default": key not in cfg.prompts,
        }
        for key in ALL_PROMPT_KEYS
    }


class UpdatePromptsRequest(BaseModel):
    prompts: dict[str, str]


@router.put("/databases/{database_id}/prompts")
def update_database_prompts(database_id: str, request: UpdatePromptsRequest):
    try:
        repo = get_prompt_config_repository(database_id)
        repo.update(request.prompts)
        get_pipeline.cache_clear()
        cfg = repo.get()
        return {
            key: {
                "value": cfg.get(key),
                "label": PROMPT_LABELS[key],
                "description": PROMPT_DESCRIPTIONS[key],
                "is_default": key not in cfg.prompts,
            }
            for key in ALL_PROMPT_KEYS
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
