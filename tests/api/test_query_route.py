from fastapi.testclient import TestClient

from app.core.dependencies import get_pipeline
from app.domain.errors import QueryValidationError
from app.main import app


def test_query_route_returns_structured_response() -> None:
    client = TestClient(app)

    response = client.post(
        "/query",
        json={"database_id": "demo", "question": "销售额是多少？", "max_rows": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["database_id"] == "demo"
    assert payload["space_id"] == "sales"
    assert payload["sql"].startswith("SELECT")
    assert payload["status"] in {"scalar", "table", "empty"}
    assert isinstance(payload["summary"], str)
    assert isinstance(payload["table_markdown"], str)
    assert isinstance(payload["row_count"], int)
    assert isinstance(payload["is_truncated"], bool)
    assert isinstance(payload["diagnostics"], list)


def test_query_route_returns_404_for_unknown_database() -> None:
    client = TestClient(app)

    response = client.post(
        "/query",
        json={"database_id": "missing", "question": "销售额是多少？", "max_rows": 5},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown database: missing"


def test_query_route_returns_422_for_query_validation_error() -> None:
    class FakePipeline:
        def run(self, request):
            raise QueryValidationError("forced validation failure")

    app.dependency_overrides[get_pipeline] = lambda: FakePipeline()
    client = TestClient(app)

    response = client.post(
        "/query",
        json={"database_id": "demo", "question": "销售额是多少？", "max_rows": 5},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "forced validation failure"
    app.dependency_overrides.clear()
