import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.domain.errors import QueryValidationError
from app.domain.models import RetrievedContext, ValidatedSql
from app.integrations.llm_client import LLMClient, StubLLMClient
from app.repositories.prompt_config import PROMPT_SQL_CORRECTION, PromptConfig
from app.services.prompt_builder import PromptBuilder
from app.services.sql_dialect import apply_limit


class SqlGenerationService:
    def __init__(self, prompt_builder: PromptBuilder | None = None, llm_client: LLMClient | None = None, prompt_config: PromptConfig | None = None) -> None:
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._llm_client = llm_client or StubLLMClient()
        self._cfg = prompt_config or PromptConfig()

    def generate_and_validate(self, question: str, context: RetrievedContext, prompt_config: PromptConfig | None = None) -> ValidatedSql:
        base_prompt = self._prompt_builder.build_sql_prompt(question, context, prompt_config=prompt_config)
        diagnostics = ["sql_prompt_built=true"]

        llm_sql = self._llm_client.complete(base_prompt).strip()
        sql = llm_sql or self._generate_sql(question, context)
        generator = "llm_client" if llm_sql else "deterministic_stub"
        diagnostics.append(f"sql_generated={generator}")

        self._safety_check(sql)
        diagnostics.append("sql_validated=safety_check_passed")
        return ValidatedSql(sql=sql, diagnostics=diagnostics)

    def generate_sql_raw(self, question: str, context: RetrievedContext, prompt_config: PromptConfig | None = None) -> tuple[str, list[str], str, str]:
        base_prompt = self._prompt_builder.build_sql_prompt(question, context, prompt_config=prompt_config)
        diagnostics = ["sql_prompt_built=true"]
        llm_response = self._llm_client.complete(base_prompt).strip()
        sql = llm_response or self._generate_sql(question, context)
        generator = "llm_client" if llm_response else "deterministic_stub"
        diagnostics.append(f"sql_generated={generator}")
        return sql, diagnostics, base_prompt, llm_response

    def correct_sql(self, original_prompt: str, sql: str, db_error: str, prompt_config: PromptConfig | None = None) -> tuple[str, str, str]:
        cfg = prompt_config or self._cfg
        template = cfg.get(PROMPT_SQL_CORRECTION)
        correction_prompt = template.replace("{original_prompt}", original_prompt).replace("{sql}", sql).replace("{db_error}", db_error)
        llm_response = self._llm_client.complete(correction_prompt).strip()
        return llm_response, correction_prompt, llm_response

    def build_sql_prompt(self, question: str, context: RetrievedContext) -> str:
        return self._prompt_builder.build_sql_prompt(question, context)

    def safety_check(self, sql: str) -> None:
        stripped = sql.strip().rstrip(";")
        if ";" in stripped:
            raise QueryValidationError("Multiple SQL statements are not allowed")
        try:
            expression = sqlglot.parse_one(sql)
        except ParseError as exc:
            raise QueryValidationError(f"SQL parse failed: {exc}") from exc
        if not isinstance(expression, exp.Select):
            raise QueryValidationError("Only SELECT statements are allowed")

    def _safety_check(self, sql: str) -> None:
        self.safety_check(sql)

    def _generate_sql(self, question: str, context: RetrievedContext) -> str:
        join_sql = self._generate_join_sql(question, context)
        if join_sql:
            return join_sql

        metric_sql = self._generate_metric_sql(question, context)
        if metric_sql:
            return metric_sql

        table = context.tables[0]
        available_columns = [column.name for column in table.columns]
        lowered = question.lower()
        asks_for_sales_metric = "销售额" in question or "营收" in question or "收入" in question
        asks_for_amount_detail = "列出" in question and "金额" in question
        if "count" in lowered or "数量" in question or ("多少" in question and not asks_for_sales_metric):
            return f"SELECT COUNT(1) AS total_count FROM {table.name} AS {table.alias}"
        if ("sum" in lowered or asks_for_sales_metric) and not asks_for_amount_detail and "amount" in available_columns:
            return f"SELECT SUM({table.alias}.amount) AS total_amount FROM {table.name} AS {table.alias}"
        projected_columns = available_columns[: min(4, len(available_columns))]
        if not projected_columns:
            raise QueryValidationError(f"No queryable columns found for table: {table.name}")
        projection = ", ".join([f"{table.alias}.{column_name}" for column_name in projected_columns])
        return apply_limit(f"SELECT {projection} FROM {table.name} AS {table.alias}", context.database.dialect, 10)

    def _generate_metric_sql(self, question: str, context: RetrievedContext) -> str | None:
        if not context.metric_rules:
            return None

        question_text = question.lower()
        table_lookup = {table.name: table for table in context.tables}
        for metric_rule in context.metric_rules:
            metric_terms = [metric_rule.name, metric_rule.id, *metric_rule.synonyms]
            if not any(term and term.lower() in question_text for term in metric_terms):
                continue
            source_table = table_lookup.get(metric_rule.source_table)
            if source_table is None:
                continue
            return (
                f"SELECT {metric_rule.expression} AS {metric_rule.output_alias} "
                f"FROM {source_table.name} AS {source_table.alias}"
        )
        return None

    def _generate_join_sql(self, question: str, context: RetrievedContext) -> str | None:
        if not context.join_rules:
            return None

        question_markers = ["客户", "等级", "关联", "join"]
        if not any(marker in question.lower() for marker in question_markers):
            return None

        table_lookup = {table.name: table for table in context.tables}
        for join_rule in context.join_rules:
            left_table = table_lookup.get(join_rule.left_table)
            right_table = table_lookup.get(join_rule.right_table)
            if left_table is None or right_table is None:
                continue

            left_column = left_table.columns[0].name
            right_column = right_table.columns[0].name
            if len(left_table.columns) > 1:
                left_column = left_table.columns[1].name
            if len(right_table.columns) > 1:
                right_column = right_table.columns[1].name

            return (
                apply_limit(
                    f"SELECT {left_table.alias}.{left_column}, {right_table.alias}.{right_column} "
                    f"FROM {left_table.name} AS {left_table.alias} "
                    f"JOIN {right_table.name} AS {right_table.alias} ON {join_rule.condition}",
                    context.database.dialect,
                    10,
                )
            )
        return None



