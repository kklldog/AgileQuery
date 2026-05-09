import pytest
from fastapi.testclient import TestClient

from app.domain.models import TableMeta, ColumnMeta
from app.main import app

client = TestClient(app)

def test_sync_schema_success(mocker):
    # Mock the registry to return a fake connector
    mock_connector = mocker.MagicMock()
    mock_connector.introspect_tables.return_value = [
        TableMeta(name="mock_table", business_name="mock_table", description="", alias="mt", columns=[])
    ]
    
    mocker.patch(
        "app.api.routes.admin.build_connector_registry_from_json",
        return_value={"demo_sqlite": mock_connector}
    )
    
    response = client.post("/admin/databases/demo/spaces/sales/sync?schema=public")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["tables_synced"] == 1
    assert response.json()["table_names"] == ["mock_table"]

def test_sync_schema_database_not_found():
    response = client.post("/admin/databases/unknown/spaces/sales/sync")
    assert response.status_code == 400
    assert "Unknown database: unknown" in response.json()["detail"]

def test_sync_schema_connector_not_found(mocker):
    mocker.patch(
        "app.api.routes.admin.build_connector_registry_from_json",
        return_value={}
    )
    response = client.post("/admin/databases/demo/spaces/sales/sync")
    assert response.status_code == 400
    assert "No connector found for demo_sqlite" in response.json()["detail"]
