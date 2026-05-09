from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_pipeline
from app.domain.errors import CatalogLookupError, QueryValidationError
from app.schemas.query import QueryRequest, QueryResponse
from app.services.pipeline import QueryPipeline

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def run_query(request: QueryRequest, pipeline: QueryPipeline = Depends(get_pipeline)) -> QueryResponse:
    try:
        return pipeline.run(request)
    except CatalogLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
