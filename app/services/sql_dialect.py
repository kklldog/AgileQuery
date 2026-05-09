from app.domain.errors import QueryValidationError


SQLGLOT_DIALECT_ALIASES = {
    "sqlite": "sqlite",
    "postgres": "postgres",
    "postgresql": "postgres",
    "mysql": "mysql",
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
    raise QueryValidationError(f"LIMIT rendering is not implemented for SQL dialect: {database_dialect}")
