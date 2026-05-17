import json
import sqlite3
from dataclasses import dataclass
from typing import Protocol, Any

from app.domain.errors import QueryValidationError
from app.domain.models import ColumnMeta, TableMeta

try:
    import psycopg
except ImportError:  # pragma: no cover - exercised by explicit runtime branch
    psycopg = None

try:
    import pyodbc  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised by explicit runtime branch
    pyodbc = None


@dataclass(frozen=True)
class ConnectorQueryResult:
    columns: list[str]
    rows: list[list[Any]]
    is_truncated: bool
    diagnostics: list[str]


class DatabaseConnector(Protocol):
    dialect: str

    def execute(self, sql: str, max_rows: int) -> ConnectorQueryResult:
        """Execute read-only SQL and return a bounded result set."""


class SQLiteDemoConnector:
    dialect = "sqlite"

    def execute(self, sql: str, max_rows: int) -> ConnectorQueryResult:
        connection = self._build_connection()
        try:
            cursor = connection.execute(sql)
            fetched_rows = cursor.fetchmany(max_rows + 1)
            is_truncated = len(fetched_rows) > max_rows
            rows = fetched_rows[:max_rows]
            columns = [description[0] for description in cursor.description or []]
            diagnostics = [f"row_limit={max_rows}"]
            if is_truncated:
                diagnostics.append("result_truncated=true")
            return ConnectorQueryResult(
                columns=columns,
                rows=[list(row) for row in rows],
                is_truncated=is_truncated,
                diagnostics=diagnostics,
            )
        except sqlite3.Error as exc:
            raise QueryValidationError(f"SQL execution failed: {exc}") from exc
        finally:
            connection.close()

    def _build_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE sales_orders (order_id INTEGER PRIMARY KEY, customer_name TEXT, region TEXT, amount REAL)"
        )
        connection.execute(
            "CREATE TABLE sales_customers (customer_name TEXT PRIMARY KEY, customer_tier TEXT)"
        )
        connection.executemany(
            "INSERT INTO sales_orders (order_id, customer_name, region, amount) VALUES (?, ?, ?, ?)",
            [
                (1, "Acme", "East", 120.5),
                (2, "Globex", "West", 90.0),
                (3, "Initech", "East", 210.0),
            ],
        )
        connection.executemany(
            "INSERT INTO sales_customers (customer_name, customer_tier) VALUES (?, ?)",
            [
                ("Acme", "Gold"),
                ("Globex", "Silver"),
                ("Initech", "Gold"),
            ],
        )
        connection.commit()
        connection.execute("PRAGMA query_only = ON")
        return connection


class DriverBackedConnectorPlaceholder:
    def __init__(self, dialect: str, connection_ref: str) -> None:
        self.dialect = dialect
        self.connection_ref = connection_ref

    def execute(self, sql: str, max_rows: int) -> ConnectorQueryResult:
        raise QueryValidationError(
            f"No runtime driver is configured for {self.dialect} connector: {self.connection_ref}"
        )


class PostgresConnector:
    dialect = "postgresql"

    def __init__(
        self,
        dsn: str,
        connection_ref: str,
        connect_timeout_seconds: int = 10,
        statement_timeout_ms: int = 30000,
    ) -> None:
        self.dsn = dsn
        self.connection_ref = connection_ref
        self.connect_timeout_seconds = connect_timeout_seconds
        self.statement_timeout_ms = statement_timeout_ms
        if not self.dsn:
            raise QueryValidationError(f"PostgreSQL connector is missing dsn: {connection_ref}")

    def execute(self, sql: str, max_rows: int) -> ConnectorQueryResult:
        connection = self._connect()
        try:
            return self._execute_with_connection(connection, sql, max_rows)
        finally:
            connection.close()

    def introspect_tables(self, schema: str = "public") -> list[TableMeta]:
        connection = self._connect()
        try:
            query = """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
            """
            with connection.transaction():
                cursor = connection.execute(query, (schema,))
                rows = cursor.fetchall()
            return self._rows_to_table_meta(rows)
        except Exception as exc:
            raise QueryValidationError(f"PostgreSQL schema introspection failed: {exc}") from exc
        finally:
            connection.close()

    def introspect_objects(self, schema: str = "public") -> list[dict]:
        connection = self._connect()
        try:
            with connection.transaction():
                kinds_cursor = connection.execute(
                    """
                    SELECT table_name, table_type
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    ORDER BY table_name
                    """,
                    (schema,),
                )
                kinds_rows = kinds_cursor.fetchall()
                cols_cursor = connection.execute(
                    """
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = %s
                    ORDER BY table_name, ordinal_position
                    """,
                    (schema,),
                )
                cols_rows = cols_cursor.fetchall()
            return _assemble_objects(kinds_rows, cols_rows, "PostgreSQL")
        except Exception as exc:
            raise QueryValidationError(f"PostgreSQL schema introspection failed: {exc}") from exc
        finally:
            connection.close()

    def _connect(self):
        if psycopg is None:
            raise QueryValidationError(
                "psycopg is required for PostgreSQL execution. Install with: pip install -e .[postgres]"
            )

        try:
            connection = psycopg.connect(
                self.dsn,
                autocommit=False,
                connect_timeout=self.connect_timeout_seconds,
                options=f"-c statement_timeout={self.statement_timeout_ms}",
            )
        except Exception as exc:
            raise QueryValidationError(f"PostgreSQL connection failed: {exc}") from exc

        connection.set_read_only(True)
        return connection

    def _execute_with_connection(self, connection, sql: str, max_rows: int) -> ConnectorQueryResult:
        try:
            with connection.transaction():
                cursor = connection.execute(sql)
                fetched_rows = cursor.fetchmany(max_rows + 1)
                is_truncated = len(fetched_rows) > max_rows
                rows = fetched_rows[:max_rows]
                columns = [description[0] for description in cursor.description or []]
                diagnostics = [
                    f"row_limit={max_rows}",
                    f"statement_timeout_ms={self.statement_timeout_ms}",
                    "read_only=true",
                ]
                if is_truncated:
                    diagnostics.append("result_truncated=true")
                return ConnectorQueryResult(
                    columns=columns,
                    rows=[list(row) for row in rows],
                    is_truncated=is_truncated,
                    diagnostics=diagnostics,
                )
        except Exception as exc:
            raise QueryValidationError(f"PostgreSQL execution failed: {exc}") from exc

    def _rows_to_table_meta(self, rows) -> list[TableMeta]:
        tables: dict[str, list[ColumnMeta]] = {}
        for table_name, column_name, data_type in rows:
            tables.setdefault(table_name, []).append(
                ColumnMeta(
                    name=column_name,
                    data_type=data_type,
                    description=f"PostgreSQL column {table_name}.{column_name}",
                )
            )
        return [
            TableMeta(
                name=table_name,
                business_name=table_name,
                description=f"PostgreSQL table {table_name}",
                alias=self._make_alias(table_name),
                columns=columns,
            )
            for table_name, columns in tables.items()
        ]

    def _make_alias(self, table_name: str) -> str:
        parts = [part for part in table_name.split("_") if part]
        if len(parts) == 1:
            return parts[0][:2].lower()
        return "".join(part[0] for part in parts).lower()


class SqlServerConnector:
    dialect = "tsql"

    def __init__(
        self,
        dsn: str,
        connection_ref: str,
        connect_timeout_seconds: int = 10,
        statement_timeout_ms: int = 30000,
    ) -> None:
        self.dsn = dsn
        self.connection_ref = connection_ref
        self.connect_timeout_seconds = connect_timeout_seconds
        self.statement_timeout_ms = statement_timeout_ms
        if not self.dsn:
            raise QueryValidationError(f"SQL Server connector is missing dsn: {connection_ref}")

    def execute(self, sql: str, max_rows: int) -> ConnectorQueryResult:
        connection = self._connect()
        try:
            return self._execute_with_connection(connection, sql, max_rows)
        finally:
            connection.close()

    def introspect_tables(self, schema: str = "dbo") -> list[TableMeta]:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = ?
                ORDER BY table_name, ordinal_position
                """,
                schema,
            )
            rows = cursor.fetchall()
            return self._rows_to_table_meta(rows)
        except Exception as exc:
            raise QueryValidationError(f"SQL Server schema introspection failed: {exc}") from exc
        finally:
            connection.close()

    def introspect_objects(self, schema: str = "dbo") -> list[dict]:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = ?
                ORDER BY table_name
                """,
                schema,
            )
            kinds_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = ?
                ORDER BY table_name, ordinal_position
                """,
                schema,
            )
            cols_rows = cursor.fetchall()
            return _assemble_objects(kinds_rows, cols_rows, "SQL Server")
        except Exception as exc:
            raise QueryValidationError(f"SQL Server schema introspection failed: {exc}") from exc
        finally:
            connection.close()

    def _connect(self):
        if pyodbc is None:
            raise QueryValidationError(
                "pyodbc is required for SQL Server execution. Install with: pip install -e .[sqlserver]"
            )
        try:
            connection = pyodbc.connect(
                self.dsn,
                timeout=self.connect_timeout_seconds,
                readonly=True,
                autocommit=False,
            )
        except Exception as exc:
            raise QueryValidationError(f"SQL Server connection failed: {exc}") from exc

        try:
            connection.timeout = int(self.statement_timeout_ms / 1000) or 1
        except Exception:  # pragma: no cover - driver-specific
            pass
        return connection

    def _execute_with_connection(self, connection, sql: str, max_rows: int) -> ConnectorQueryResult:
        try:
            cursor = connection.cursor()
            cursor.execute(sql)
            fetched_rows = cursor.fetchmany(max_rows + 1)
            is_truncated = len(fetched_rows) > max_rows
            rows = fetched_rows[:max_rows]
            columns = [description[0] for description in cursor.description or []]
            diagnostics = [
                f"row_limit={max_rows}",
                f"statement_timeout_ms={self.statement_timeout_ms}",
                "read_only=true",
            ]
            if is_truncated:
                diagnostics.append("result_truncated=true")
            return ConnectorQueryResult(
                columns=columns,
                rows=[list(row) for row in rows],
                is_truncated=is_truncated,
                diagnostics=diagnostics,
            )
        except Exception as exc:
            raise QueryValidationError(f"SQL Server execution failed: {exc}") from exc

    def _rows_to_table_meta(self, rows) -> list[TableMeta]:
        tables: dict[str, list[ColumnMeta]] = {}
        for table_name, column_name, data_type in rows:
            tables.setdefault(table_name, []).append(
                ColumnMeta(
                    name=column_name,
                    data_type=data_type,
                    description=f"SQL Server column {table_name}.{column_name}",
                )
            )
        return [
            TableMeta(
                name=table_name,
                business_name=table_name,
                description=f"SQL Server table {table_name}",
                alias=self._make_alias(table_name),
                columns=columns,
            )
            for table_name, columns in tables.items()
        ]

    def _make_alias(self, table_name: str) -> str:
        parts = [part for part in table_name.split("_") if part]
        if len(parts) == 1:
            return parts[0][:2].lower()
        return "".join(part[0] for part in parts).lower()


def _assemble_objects(kinds_rows, cols_rows, source_label: str) -> list[dict]:
    columns_by_table: dict[str, list[dict]] = {}
    for table_name, column_name, data_type in cols_rows:
        columns_by_table.setdefault(table_name, []).append({
            "name": column_name,
            "data_type": data_type,
            "description": f"{source_label} column {table_name}.{column_name}",
        })
    objects: list[dict] = []
    for table_name, table_type in kinds_rows:
        kind = "view" if str(table_type).upper().endswith("VIEW") else "table"
        objects.append({
            "name": table_name,
            "kind": kind,
            "columns": columns_by_table.get(table_name, []),
        })
    return objects


def build_default_connector_registry() -> dict[str, DatabaseConnector]:
    return {"demo_sqlite": SQLiteDemoConnector()}


def build_connector_registry_from_json(config_json: str) -> dict[str, DatabaseConnector]:
    registry = build_default_connector_registry()
    if not config_json.strip():
        return registry

    try:
        entries = json.loads(config_json)
    except json.JSONDecodeError as exc:
        raise QueryValidationError("Database connector configuration is not valid JSON") from exc

    if not isinstance(entries, list):
        raise QueryValidationError("Database connector configuration must be a JSON array")

    for entry in entries:
        if not isinstance(entry, dict):
            raise QueryValidationError("Each database connector configuration entry must be an object")
        connection_ref = str(entry.get("connection_ref", "")).strip()
        dialect = str(entry.get("dialect", "")).strip().lower()
        if not connection_ref:
            raise QueryValidationError("Database connector entry is missing connection_ref")
        if dialect == "sqlite-demo":
            registry[connection_ref] = SQLiteDemoConnector()
            continue
        if dialect in {"postgres", "postgresql"}:
            registry[connection_ref] = PostgresConnector(
                dsn=str(entry.get("dsn", "")),
                connection_ref=connection_ref,
                connect_timeout_seconds=int(entry.get("connect_timeout_seconds", 10)),
                statement_timeout_ms=int(entry.get("statement_timeout_ms", 30000)),
            )
            continue
        if dialect in {"sqlserver", "mssql", "tsql"}:
            registry[connection_ref] = SqlServerConnector(
                dsn=str(entry.get("dsn", "")),
                connection_ref=connection_ref,
                connect_timeout_seconds=int(entry.get("connect_timeout_seconds", 10)),
                statement_timeout_ms=int(entry.get("statement_timeout_ms", 30000)),
            )
            continue
        if dialect == "mysql":
            registry[connection_ref] = DriverBackedConnectorPlaceholder(dialect=dialect, connection_ref=connection_ref)
            continue
        raise QueryValidationError(f"Unsupported database connector dialect: {dialect}")

    return registry
