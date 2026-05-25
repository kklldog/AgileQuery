from app.domain.errors import QueryValidationError
from app.repositories.prompt_config import PromptConfig, PromptConfigFileRepository
from app.schemas.query import LLMTrace, QueryRequest, QueryResponse
from app.services.phase1_retrieval import RetrievalService
from app.services.phase2_sql import SqlGenerationService
from app.services.phase3_execution import QueryExecutionService
from app.services.phase4_insight import InsightService

_MAX_CORRECTION_ATTEMPTS = 2


class QueryPipeline:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        sql_service: SqlGenerationService,
        execution_service: QueryExecutionService,
        insight_service: InsightService,
        default_max_rows: int,
        prompts_data_dir: str = "data",
    ) -> None:
        self._retrieval_service = retrieval_service
        self._sql_service = sql_service
        self._execution_service = execution_service
        self._insight_service = insight_service
        self._default_max_rows = default_max_rows
        self._prompts_data_dir = prompts_data_dir

    def _load_prompt_config(self, database_id: str) -> PromptConfig:
        try:
            return PromptConfigFileRepository(self._prompts_data_dir, database_id).get()
        except Exception:
            return PromptConfig()

    def run(self, request: QueryRequest) -> QueryResponse:
        llm_traces: list[LLMTrace] = []
        prompt_config = self._load_prompt_config(request.database_id)

        retrieval = self._retrieval_service.retrieve(
            database_id=request.database_id,
            question=request.question,
            space_id=request.space_id,
            prompt_config=prompt_config,
        )
        if retrieval.llm_keyword_prompt:
            llm_traces.append(LLMTrace(stage="keyword_expansion", prompt=retrieval.llm_keyword_prompt, response=retrieval.llm_keyword_response))
        sql, sql_diagnostics, sql_prompt, sql_response = self._sql_service.generate_sql_raw(request.question, retrieval, prompt_config=prompt_config)
        llm_traces.append(LLMTrace(stage="sql_generation", prompt=sql_prompt, response=sql_response))

        try:
            self._sql_service.safety_check(sql)
            sql_diagnostics.append("sql_validated=safety_check_passed")
        except QueryValidationError as exc:
            corrected, correction_prompt, correction_response = self._sql_service.correct_sql(sql_prompt, sql, str(exc), prompt_config=prompt_config)
            llm_traces.append(LLMTrace(stage="sql_correction_safety", prompt=correction_prompt, response=correction_response))
            if not corrected:
                raise
            sql = corrected
            sql_diagnostics.append("sql_correction_attempt=0_safety_check")

        last_db_error: str | None = None

        for attempt in range(_MAX_CORRECTION_ATTEMPTS + 1):
            try:
                execution = self._execution_service.execute(
                    sql,
                    database_id=request.database_id,
                    max_rows=request.max_rows or self._default_max_rows,
                )
                break
            except QueryValidationError as exc:
                last_db_error = str(exc)
                if attempt >= _MAX_CORRECTION_ATTEMPTS:
                    raise
                corrected, correction_prompt, correction_response = self._sql_service.correct_sql(sql_prompt, sql, last_db_error, prompt_config=prompt_config)
                llm_traces.append(LLMTrace(stage=f"sql_correction_{attempt + 1}", prompt=correction_prompt, response=correction_response))
                if not corrected:
                    raise
                sql = corrected
                sql_diagnostics.append(f"sql_correction_attempt={attempt + 1}")

        insight, insight_prompt, insight_response = self._insight_service.build_insight(execution, prompt_config=prompt_config)
        llm_traces.append(LLMTrace(stage="insight", prompt=insight_prompt, response=insight_response))

        diagnostics = retrieval.diagnostics + sql_diagnostics + execution.diagnostics + insight.diagnostics
        return QueryResponse(
            database_id=request.database_id,
            space_id=retrieval.space.id,
            sql=sql,
            status=execution.status,
            summary=insight.summary,
            table_markdown=insight.table_markdown,
            row_count=execution.row_count,
            is_truncated=execution.is_truncated,
            diagnostics=diagnostics,
            llm_traces=llm_traces,
        )
