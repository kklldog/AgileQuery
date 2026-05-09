from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_catalog_repository, get_settings
from app.domain.errors import CatalogLookupError, QueryValidationError
from app.integrations.database_connectors import build_connector_registry_from_json
from app.repositories.catalog import InMemoryCatalogRepository

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/databases/{database_id}/spaces/{space_id}/sync")
def sync_schema(
    database_id: str,
    space_id: str,
    schema: str = "public",
    catalog: InMemoryCatalogRepository = Depends(get_catalog_repository),
):
    try:
        database = catalog.get_database(database_id)
        settings = get_settings()
        registry = build_connector_registry_from_json(settings.database_connections_json)
        
        if database.connection_ref not in registry:
            raise QueryValidationError(f"No connector found for {database.connection_ref}")
            
        connector = registry[database.connection_ref]
        
        if not hasattr(connector, "introspect_tables"):
            raise QueryValidationError(f"Connector for {database.connection_ref} does not support introspection")
            
        tables = connector.introspect_tables(schema=schema)
        catalog.update_space_tables(database_id, space_id, tables)
        
        from app.core.dependencies import get_pipeline
        get_pipeline.cache_clear()
        
        return {"status": "success", "tables_synced": len(tables), "table_names": [t.name for t in tables]}
        
    except (CatalogLookupError, QueryValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/databases")
def list_databases(catalog: InMemoryCatalogRepository = Depends(get_catalog_repository)):
    try:
        databases = [catalog.get_database(db_id) for db_id in catalog.database_ids()]
        return {"databases": databases}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/databases/{database_id}/spaces")
def list_spaces(database_id: str, catalog: InMemoryCatalogRepository = Depends(get_catalog_repository)):
    try:
        spaces = catalog.list_spaces(database_id)
        return {"spaces": spaces}
    except CatalogLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
