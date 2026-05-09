from unittest.mock import MagicMock, patch

from app.domain.errors import QueryValidationError
from app.integrations.database_connectors import (
    DriverBackedConnectorPlaceholder,
    PostgresConnector,
    SQLiteDemoConnector,
    build_connector_registry_from_json,
)


def test_build_connector_registry_defaults_to_demo_sqlite() -> None:
    registry = build_connector_registry_from_json("")

    assert isinstance(registry["demo_sqlite"], SQLiteDemoConnector)


def test_build_connector_registry_adds_sqlite_demo_alias() -> None:
    registry = build_connector_registry_from_json(
        '[{"connection_ref":"local_demo","dialect":"sqlite-demo"}]'
    )

    assert isinstance(registry["local_demo"], SQLiteDemoConnector)


def test_build_connector_registry_adds_postgres_connector() -> None:
    registry = build_connector_registry_from_json(
        '[{"connection_ref":"pg_sales","dialect":"postgresql","dsn":"postgresql://user:pass@localhost/db"}]'
    )

    assert isinstance(registry["pg_sales"], PostgresConnector)


def test_build_connector_registry_adds_mysql_placeholder() -> None:
    registry = build_connector_registry_from_json(
        '[{"connection_ref":"mysql_sales","dialect":"mysql"}]'
    )

    assert isinstance(registry["mysql_sales"], DriverBackedConnectorPlaceholder)


def test_driver_placeholder_returns_clear_error() -> None:
    connector = DriverBackedConnectorPlaceholder(dialect="postgresql", connection_ref="pg_sales")

    try:
        connector.execute("SELECT 1", max_rows=10)
    except QueryValidationError as exc:
        assert str(exc) == "No runtime driver is configured for postgresql connector: pg_sales"
    else:
        raise AssertionError("Expected placeholder connector to fail clearly")


def test_build_connector_registry_rejects_invalid_json() -> None:
    try:
        build_connector_registry_from_json("not-json")
    except QueryValidationError as exc:
        assert str(exc) == "Database connector configuration is not valid JSON"
    else:
        raise AssertionError("Expected invalid connector JSON to fail")


def test_postgres_connector_requires_dsn() -> None:
    try:
        PostgresConnector(dsn="", connection_ref="pg_sales")
    except QueryValidationError as exc:
        assert str(exc) == "PostgreSQL connector is missing dsn: pg_sales"
    else:
        raise AssertionError("Expected missing Postgres DSN to fail")


def test_postgres_connector_introspects_information_schema_columns() -> None:
    connector = PostgresConnector(dsn="postgresql://user:pass@localhost/db", connection_ref="pg_sales")
    connection = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        ("sales_orders", "order_id", "integer"),
        ("sales_orders", "amount", "numeric"),
        ("sales_customers", "customer_name", "text"),
    ]
    connection.execute.return_value = cursor
    transaction = MagicMock()
    connection.transaction.return_value = transaction

    with patch("app.integrations.database_connectors.psycopg") as mocked_psycopg:
        mocked_psycopg.connect.return_value = connection
        tables = connector.introspect_tables(schema="public")

    assert [table.name for table in tables] == ["sales_orders", "sales_customers"]
    assert tables[0].alias == "so"
    assert tables[0].columns[1].name == "amount"
    connection.set_read_only.assert_called_once_with(True)
    connection.close.assert_called_once()
