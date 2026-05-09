from app.domain.errors import QueryValidationError
from app.integrations.database_connectors import PostgresConnector, SQLiteDemoConnector
from app.domain.models import DatabaseMeta
from app.repositories.catalog import InMemoryCatalogRepository
from app.services.phase3_execution import QueryExecutionService


def test_execution_service_detects_scalar_result() -> None:
    service = QueryExecutionService(default_max_rows=2)
    result = service.execute("SELECT COUNT(*) AS total_count FROM sales_orders", database_id="demo")

    assert result.status == "scalar"
    assert result.row_count == 1
    assert result.is_truncated is False


def test_execution_service_detects_truncation() -> None:
    service = QueryExecutionService(default_max_rows=1)
    result = service.execute("SELECT order_id, customer_name FROM sales_orders ORDER BY order_id", database_id="demo")

    assert result.status == "table"
    assert result.row_count == 1
    assert result.is_truncated is True


def test_execution_service_rejects_unknown_database() -> None:
    service = QueryExecutionService(default_max_rows=1)

    try:
        service.execute("SELECT 1", database_id="unknown")
    except Exception as exc:
        assert str(exc) == "Unknown database: unknown"
    else:
        raise AssertionError("Expected unknown database execution to fail")


def test_execution_service_rejects_non_select_sql() -> None:
    service = QueryExecutionService(default_max_rows=1)

    try:
        service.execute("DELETE FROM sales_orders", database_id="demo")
    except QueryValidationError as exc:
        assert str(exc) == "Only SELECT statements are allowed for execution"
    else:
        raise AssertionError("Expected non-select SQL to fail")


def test_execution_service_maps_sqlite_error_to_query_validation_error() -> None:
    service = QueryExecutionService(default_max_rows=1)

    try:
        service.execute("SELECT missing_column FROM sales_orders", database_id="demo")
    except QueryValidationError as exc:
        assert str(exc).startswith("SQL execution failed:")
    else:
        raise AssertionError("Expected SQLite runtime error to be normalized")


def test_execution_service_executes_demo_join_query() -> None:
    service = QueryExecutionService(default_max_rows=5)

    result = service.execute(
        "SELECT so.amount, sc.customer_tier FROM sales_orders AS so JOIN sales_customers AS sc ON so.customer_name = sc.customer_name ORDER BY so.order_id",
        database_id="demo",
    )

    assert result.status == "table"
    assert result.row_count == 3
    assert result.columns == ["amount", "customer_tier"]


def test_execution_service_reports_connector_diagnostics() -> None:
    service = QueryExecutionService(default_max_rows=2)

    result = service.execute("SELECT COUNT(*) AS total_count FROM sales_orders", database_id="demo")

    assert "connector=demo_sqlite" in result.diagnostics


def test_sqlite_demo_connector_executes_bounded_query() -> None:
    result = SQLiteDemoConnector().execute("SELECT order_id FROM sales_orders ORDER BY order_id", max_rows=2)

    assert result.columns == ["order_id"]
    assert result.rows == [[1], [2]]
    assert result.is_truncated is True


def test_execution_service_uses_configured_connector_placeholder_error() -> None:
    database = DatabaseMeta(
        id="pg_demo",
        name="Postgres Demo",
        dialect="postgresql",
        description="Postgres demo",
        connection_ref="pg_sales",
    )
    service = QueryExecutionService(
        default_max_rows=5,
        catalog=InMemoryCatalogRepository([database]),
        connectors={"pg_sales": PostgresConnector(dsn="postgresql://user:pass@localhost/db", connection_ref="pg_sales")},
    )

    try:
        service.execute("SELECT 1", database_id="pg_demo")
    except QueryValidationError as exc:
        assert str(exc).startswith("psycopg is required for PostgreSQL execution") or str(exc).startswith("PostgreSQL connection failed:")
    else:
        raise AssertionError("Expected PostgreSQL connector failure without configured runtime")
