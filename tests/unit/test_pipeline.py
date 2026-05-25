from unittest.mock import MagicMock

from app.core.dependencies import get_catalog_repository
from app.domain.errors import QueryValidationError
from app.domain.models import ExecutionResult
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


def test_pipeline_retries_on_db_error() -> None:
    good_result = ExecutionResult(
        sql="SELECT COUNT(*) FROM orders",
        columns=["cnt"],
        rows=[[42]],
        row_count=1,
        is_truncated=False,
        status="scalar",
        diagnostics=[],
    )

    execution_service = MagicMock()
    execution_service.execute.side_effect = [
        QueryValidationError("no such table: orders"),
        good_result,
    ]

    sql_service = MagicMock()
    sql_service.generate_sql_raw.return_value = ("SELECT bad FROM orders", [], "prompt", "SELECT bad FROM orders")
    sql_service.safety_check.return_value = None
    sql_service.build_sql_prompt.return_value = "prompt"
    sql_service.correct_sql.return_value = ("SELECT COUNT(*) FROM orders", "correction_prompt", "SELECT COUNT(*) FROM orders")

    insight_service = MagicMock()
    insight_service.build_insight.return_value = (MagicMock(summary="42", table_markdown="", diagnostics=[]), "insight_prompt", "42")

    retrieval_service = MagicMock()
    retrieval_service.retrieve.return_value = MagicMock(
        space=MagicMock(id="sales"),
        diagnostics=[],
        llm_keyword_prompt="",
        llm_keyword_response="",
    )

    pipeline = QueryPipeline(
        retrieval_service=retrieval_service,
        sql_service=sql_service,
        execution_service=execution_service,
        insight_service=insight_service,
        default_max_rows=50,
    )

    response = pipeline.run(QueryRequest(database_id="demo", question="多少订单？"))

    assert execution_service.execute.call_count == 2
    assert sql_service.correct_sql.call_count == 1
    assert "sql_correction_attempt=1" in response.diagnostics


def test_pipeline_raises_after_max_corrections() -> None:
    execution_service = MagicMock()
    execution_service.execute.side_effect = QueryValidationError("persistent db error")

    sql_service = MagicMock()
    sql_service.generate_sql_raw.return_value = ("SELECT bad", [], "prompt", "SELECT bad")
    sql_service.safety_check.return_value = None
    sql_service.build_sql_prompt.return_value = "prompt"
    sql_service.correct_sql.return_value = ("SELECT still_bad", "correction_prompt", "SELECT still_bad")

    retrieval_service = MagicMock()
    retrieval_service.retrieve.return_value = MagicMock(space=MagicMock(id="sales"), diagnostics=[], llm_keyword_prompt="", llm_keyword_response="")

    pipeline = QueryPipeline(
        retrieval_service=retrieval_service,
        sql_service=sql_service,
        execution_service=execution_service,
        insight_service=MagicMock(),
        default_max_rows=50,
    )

    try:
        pipeline.run(QueryRequest(database_id="demo", question="bad question"))
    except QueryValidationError:
        pass
    else:
        raise AssertionError("Expected QueryValidationError after max correction attempts")
