class CatalogLookupError(Exception):
    """Raised when a requested database or space cannot be resolved."""


class QueryValidationError(Exception):
    """Raised when generated SQL or query inputs fail validation."""
