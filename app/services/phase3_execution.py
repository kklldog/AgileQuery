import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.domain.errors import CatalogLookupError, QueryValidationError
from app.domain.models import DatabaseMeta, ExecutionResult
from app.integrations.database_connectors import DatabaseConnector, build_default_connector_registry
from app.repositories.catalog import InMemoryCatalogRepository
from app.services.sql_dialect import resolve_sqlglot_dialect


class QueryExecutionService:
    def __init__(
        self,
        default_max_rows: int = 50,
        catalog: InMemoryCatalogRepository | None = None,
        connectors: dict[str, DatabaseConnector] | None = None,
    ) -> None:
        self._default_max_rows = default_max_rows
        self._catalog = catalog
        self._connectors = connectors or build_default_connector_registry()

    def execute(self, sql: str, database_id: str, max_rows: int | None = None) -> ExecutionResult:
        effective_max_rows = max_rows or self._default_max_rows
        database = self._resolve_database(database_id)
        self._validate_executable_sql(sql, database)

        connector = self._resolve_connector(database)
        connector_result = connector.execute(sql, effective_max_rows)
        status = self._resolve_status(connector_result.rows, connector_result.columns)
        return ExecutionResult(
            sql=sql,
            columns=connector_result.columns,
            rows=connector_result.rows,
            row_count=len(connector_result.rows),
            is_truncated=connector_result.is_truncated,
            status=status,
            diagnostics=[f"connector={database.connection_ref or database.id}", *connector_result.diagnostics],
        )

    def _resolve_status(self, rows: list[list], columns: list[str]) -> str:
        if not rows:
            return "empty"
        if len(rows) == 1 and len(columns) == 1:
            return "scalar"
        return "table"

    def _resolve_database(self, database_id: str) -> DatabaseMeta:
        if self._catalog is not None:
            return self._catalog.get_database(database_id)
        if database_id == "demo":
            return DatabaseMeta(
                id="demo",
                name="Demo Database",
                dialect="sqlite",
                description="内置演示数据库",
                connection_ref="demo_sqlite",
            )
        raise CatalogLookupError(f"Unknown database: {database_id}")

    def _resolve_connector(self, database: DatabaseMeta) -> DatabaseConnector:
        connector_key = database.connection_ref or database.id
        if connector_key not in self._connectors:
            raise CatalogLookupError(f"No execution connector configured for database: {database.id}")
        return self._connectors[connector_key]

    def _validate_executable_sql(self, sql: str, database: DatabaseMeta) -> None:
        try:
            expression = sqlglot.parse_one(sql, read=resolve_sqlglot_dialect(database.dialect))
        except ParseError as exc:
            raise QueryValidationError(f"SQL parse failed: {exc}") from exc

        if not isinstance(expression, exp.Select):
            raise QueryValidationError("Only SELECT statements are allowed for execution")
