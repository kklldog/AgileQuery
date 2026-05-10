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
