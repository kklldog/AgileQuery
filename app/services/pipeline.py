from app.schemas.query import QueryRequest, QueryResponse
from app.services.phase1_retrieval import RetrievalService
from app.services.phase2_sql import SqlGenerationService
from app.services.phase3_execution import QueryExecutionService
from app.services.phase4_insight import InsightService


class QueryPipeline:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        sql_service: SqlGenerationService,
        execution_service: QueryExecutionService,
        insight_service: InsightService,
        default_max_rows: int,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._sql_service = sql_service
        self._execution_service = execution_service
        self._insight_service = insight_service
        self._default_max_rows = default_max_rows

    def run(self, request: QueryRequest) -> QueryResponse:
        retrieval = self._retrieval_service.retrieve(
            database_id=request.database_id,
            question=request.question,
            space_id=request.space_id,
        )
        validated_sql = self._sql_service.generate_and_validate(request.question, retrieval)
        execution = self._execution_service.execute(
            validated_sql.sql,
            database_id=request.database_id,
            max_rows=request.max_rows or self._default_max_rows,
        )
        insight = self._insight_service.build_insight(execution)
        diagnostics = retrieval.diagnostics + validated_sql.diagnostics + execution.diagnostics + insight.diagnostics
        return QueryResponse(
            database_id=request.database_id,
            space_id=retrieval.space.id,
            sql=validated_sql.sql,
            status=execution.status,
            summary=insight.summary,
            table_markdown=insight.table_markdown,
            row_count=execution.row_count,
            is_truncated=execution.is_truncated,
            diagnostics=diagnostics,
        )
