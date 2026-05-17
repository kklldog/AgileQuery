from app.domain.errors import QueryValidationError


SQLGLOT_DIALECT_ALIASES = {
    "sqlite": "sqlite",
    "postgres": "postgres",
    "postgresql": "postgres",
    "mysql": "mysql",
    "tsql": "tsql",
    "mssql": "tsql",
    "sqlserver": "tsql",
}


def resolve_sqlglot_dialect(database_dialect: str) -> str:
    normalized = database_dialect.strip().lower()
    if normalized in SQLGLOT_DIALECT_ALIASES:
        return SQLGLOT_DIALECT_ALIASES[normalized]
    raise QueryValidationError(f"Unsupported SQL dialect: {database_dialect}")


def apply_limit(sql: str, database_dialect: str, limit: int) -> str:
    dialect = resolve_sqlglot_dialect(database_dialect)
    if dialect in {"sqlite", "postgres", "mysql"}:
        return f"{sql} LIMIT {limit}"
    if dialect == "tsql":
        return _apply_tsql_top(sql, limit)
    raise QueryValidationError(f"LIMIT rendering is not implemented for SQL dialect: {database_dialect}")


def _apply_tsql_top(sql: str, limit: int) -> str:
    stripped = sql.lstrip()
    upper = stripped.upper()
    if upper.startswith("SELECT DISTINCT"):
        prefix_len = len("SELECT DISTINCT")
        rest = stripped[prefix_len:]
        return f"SELECT DISTINCT TOP {limit}{rest}"
    if upper.startswith("SELECT"):
        rest = stripped[len("SELECT"):]
        return f"SELECT TOP {limit}{rest}"
    raise QueryValidationError("T-SQL TOP rendering only supports SELECT statements")
