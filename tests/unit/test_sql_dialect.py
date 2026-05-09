from app.domain.errors import QueryValidationError
from app.services.sql_dialect import apply_limit, resolve_sqlglot_dialect


def test_resolve_sqlglot_dialect_normalizes_common_names() -> None:
    assert resolve_sqlglot_dialect("sqlite") == "sqlite"
    assert resolve_sqlglot_dialect("postgresql") == "postgres"
    assert resolve_sqlglot_dialect("postgres") == "postgres"
    assert resolve_sqlglot_dialect("mysql") == "mysql"


def test_apply_limit_renders_common_dialects() -> None:
    assert apply_limit("SELECT 1", "sqlite", 10) == "SELECT 1 LIMIT 10"
    assert apply_limit("SELECT 1", "postgres", 10) == "SELECT 1 LIMIT 10"
    assert apply_limit("SELECT 1", "mysql", 10) == "SELECT 1 LIMIT 10"


def test_resolve_sqlglot_dialect_rejects_unsupported_name() -> None:
    try:
        resolve_sqlglot_dialect("oracle")
    except QueryValidationError as exc:
        assert str(exc) == "Unsupported SQL dialect: oracle"
    else:
        raise AssertionError("Expected unsupported dialect to fail")
