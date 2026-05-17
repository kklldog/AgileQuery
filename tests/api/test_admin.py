from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.dependencies import get_catalog_repository
from app.domain.models import TableMeta
from app.main import app
from app.repositories.catalog import InMemoryCatalogRepository

client = TestClient(app)


def override_catalog_dependency() -> None:
    app.dependency_overrides[get_catalog_repository] = InMemoryCatalogRepository.with_demo_data


def clear_dependency_overrides() -> None:
    app.dependency_overrides.clear()


def test_sync_schema_success(monkeypatch):
    override_catalog_dependency()
    mock_connector = MagicMock()
    mock_connector.introspect_tables.return_value = [
        TableMeta(name="mock_table", business_name="mock_table", description="", alias="mt", columns=[])
    ]

    monkeypatch.setattr(
        "app.api.routes.admin.build_connector_registry_from_json",
        lambda _: {"demo_sqlite": mock_connector},
    )

    response = client.post("/admin/databases/demo/spaces/sales/sync?schema=public")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["tables_synced"] == 1
    assert response.json()["table_names"] == ["mock_table"]
    clear_dependency_overrides()

def test_sync_schema_database_not_found():
    override_catalog_dependency()
    response = client.post("/admin/databases/unknown/spaces/sales/sync")
    assert response.status_code == 400
    assert "Unknown database: unknown" in response.json()["detail"]
    clear_dependency_overrides()

def test_sync_schema_connector_not_found(monkeypatch):
    override_catalog_dependency()
    monkeypatch.setattr(
        "app.api.routes.admin.build_connector_registry_from_json",
        lambda _: {},
    )
    response = client.post("/admin/databases/demo/spaces/sales/sync")
    assert response.status_code == 400
    assert "No connector found for demo_sqlite" in response.json()["detail"]
    clear_dependency_overrides()


def test_create_space_success():
    repository = InMemoryCatalogRepository.with_demo_data()
    app.dependency_overrides[get_catalog_repository] = lambda: repository

    response = client.post(
        "/admin/databases/demo/spaces",
        json={"id": "finance_ops", "name": "Finance Ops", "description": "财务运营域"},
    )

    assert response.status_code == 201
    assert response.json()["space"] == {
        "id": "finance_ops",
        "name": "Finance Ops",
        "description": "财务运营域",
        "sample_questions": [],
        "tables": [],
        "join_rules": [],
        "metric_rules": [],
    }
    assert repository.get_space("demo", "finance_ops").name == "Finance Ops"
    clear_dependency_overrides()


def test_create_space_duplicate_id():
    override_catalog_dependency()

    response = client.post(
        "/admin/databases/demo/spaces",
        json={"id": "sales", "name": "Sales Copy", "description": "重复空间"},
    )

    assert response.status_code == 409
    assert "Space already exists: sales" in response.json()["detail"]
    clear_dependency_overrides()


def test_create_space_unknown_database():
    override_catalog_dependency()

    response = client.post(
        "/admin/databases/unknown/spaces",
        json={"id": "finance", "name": "Finance", "description": "财务域"},
    )

    assert response.status_code == 404
    assert "Unknown database: unknown" in response.json()["detail"]
    clear_dependency_overrides()


def test_create_space_rejects_invalid_id():
    override_catalog_dependency()

    response = client.post(
        "/admin/databases/demo/spaces",
        json={"id": "Finance Ops", "name": "Finance Ops", "description": "非法 ID"},
    )

    assert response.status_code == 422
    clear_dependency_overrides()


def test_get_space_success():
    override_catalog_dependency()

    response = client.get("/admin/databases/demo/spaces/sales")

    assert response.status_code == 200
    space = response.json()["space"]
    assert space["id"] == "sales"
    assert space["name"] == "Sales"
    clear_dependency_overrides()


def test_get_space_unknown_space():
    override_catalog_dependency()

    response = client.get("/admin/databases/demo/spaces/unknown")

    assert response.status_code == 404
    assert "Unknown space" in response.json()["detail"]
    clear_dependency_overrides()


def test_update_space_success():
    repository = InMemoryCatalogRepository.with_demo_data()
    app.dependency_overrides[get_catalog_repository] = lambda: repository

    response = client.patch(
        "/admin/databases/demo/spaces/sales",
        json={"name": "Sales Renamed", "description": "新的描述"},
    )

    assert response.status_code == 200
    space = response.json()["space"]
    assert space["name"] == "Sales Renamed"
    assert space["description"] == "新的描述"
    assert len(space["tables"]) == 2
    assert len(space["join_rules"]) == 1
    assert repository.get_space("demo", "sales").name == "Sales Renamed"
    clear_dependency_overrides()


def test_update_space_partial_only_name():
    repository = InMemoryCatalogRepository.with_demo_data()
    app.dependency_overrides[get_catalog_repository] = lambda: repository

    response = client.patch(
        "/admin/databases/demo/spaces/sales",
        json={"name": "Only Name"},
    )

    assert response.status_code == 200
    space = response.json()["space"]
    assert space["name"] == "Only Name"
    assert space["description"] == "销售业务域"
    clear_dependency_overrides()


def test_update_space_empty_payload_returns_422():
    override_catalog_dependency()

    response = client.patch(
        "/admin/databases/demo/spaces/sales",
        json={},
    )

    assert response.status_code == 422
    clear_dependency_overrides()


def test_update_space_unknown_space_returns_404():
    override_catalog_dependency()

    response = client.patch(
        "/admin/databases/demo/spaces/unknown",
        json={"name": "X"},
    )

    assert response.status_code == 404
    assert "Unknown space" in response.json()["detail"]
    clear_dependency_overrides()
