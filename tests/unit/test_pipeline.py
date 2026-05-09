from app.core.dependencies import get_catalog_repository
from app.schemas.query import QueryRequest
from app.services.phase1_retrieval import RetrievalService
from app.services.phase2_sql import SqlGenerationService
from app.services.phase3_execution import QueryExecutionService
from app.services.phase4_insight import InsightService
from app.services.pipeline import QueryPipeline


def test_pipeline_runs_full_chain() -> None:
    pipeline = QueryPipeline(
        retrieval_service=RetrievalService(get_catalog_repository()),
        sql_service=SqlGenerationService(),
        execution_service=QueryExecutionService(default_max_rows=5),
        insight_service=InsightService(),
        default_max_rows=5,
    )

    response = pipeline.run(QueryRequest(database_id="demo", question="销售额是多少？"))

    assert response.database_id == "demo"
    assert response.space_id == "sales"
    assert response.sql.startswith("SELECT")
    assert response.status == "scalar"
    assert response.diagnostics
    assert "结果值为" in response.summary
