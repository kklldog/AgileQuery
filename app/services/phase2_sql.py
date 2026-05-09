import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.domain.errors import QueryValidationError
from app.domain.models import RetrievedContext, ValidatedSql
from app.integrations.llm_client import LLMClient, StubLLMClient
from app.services.prompt_builder import PromptBuilder
from app.services.sql_dialect import apply_limit, resolve_sqlglot_dialect


class SqlGenerationService:
    def __init__(self, prompt_builder: PromptBuilder | None = None, llm_client: LLMClient | None = None) -> None:
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._llm_client = llm_client or StubLLMClient()

    def generate_and_validate(self, question: str, context: RetrievedContext) -> ValidatedSql:
        base_prompt = self._prompt_builder.build_sql_prompt(question, context)
        diagnostics = ["sql_prompt_built=true"]

        last_error = None
        for attempt in range(3):
            if attempt > 0 and last_error:
                correction_prompt = (
                    f"{base_prompt}\n\n[Self-Correction]\n"
                    f"Your previous SQL failed validation with this error:\n{last_error}\n"
                    f"Please fix the SQL and return ONLY the corrected SQL statement."
                )
                llm_sql = self._llm_client.complete(correction_prompt).strip()
            else:
                llm_sql = self._llm_client.complete(base_prompt).strip()

            sql = llm_sql or self._generate_sql(question, context)

            try:
                self.validate_sql(sql, context)
                generator = "llm_client" if llm_sql else "deterministic_stub"
                diagnostics.append(f"sql_generated={generator}")
                if attempt > 0:
                    diagnostics.append(f"self_correction_attempts={attempt}")
                diagnostics.append("sql_validated=parseable_select")
                return ValidatedSql(sql=sql, diagnostics=diagnostics)
            except QueryValidationError as exc:
                last_error = str(exc)
                if not llm_sql:
                    raise

        raise QueryValidationError(f"Failed to generate valid SQL after 3 attempts. Last error: {last_error}")

    def validate_sql(self, sql: str, context: RetrievedContext) -> None:
        if ";" in sql.strip().rstrip(";"):
            raise QueryValidationError("Multiple SQL statements are not allowed")

        sqlglot_dialect = resolve_sqlglot_dialect(context.database.dialect)
        try:
            expression = sqlglot.parse_one(sql, read=sqlglot_dialect)
        except ParseError as exc:
            raise QueryValidationError(f"SQL parse failed: {exc}") from exc

        if not isinstance(expression, exp.Select):
            raise QueryValidationError("Only SELECT statements are allowed")

        if list(expression.find_all(exp.Star)):
            raise QueryValidationError("Star projections are not allowed")

        allowed_tables = {table.name: table for table in context.tables}
        alias_to_table: dict[str, str] = {}
        for table_ref in expression.find_all(exp.Table):
            table_name = table_ref.name
            if table_name not in allowed_tables:
                raise QueryValidationError(f"Unknown table in SQL: {table_name}")
            alias = table_ref.alias_or_name
            alias_to_table[alias] = table_name

        if not alias_to_table:
            raise QueryValidationError("SQL must reference at least one table")

        multi_table_scope = len(alias_to_table) > 1 or len(context.tables) > 1
        allowed_columns_by_table = {
            table.name: {column.name for column in table.columns}
            for table in context.tables
        }

        for column in expression.find_all(exp.Column):
            column_name = column.name
            qualifier = column.table

            if qualifier:
                if qualifier not in alias_to_table:
                    raise QueryValidationError(f"Unknown table alias in SQL: {qualifier}")
                table_name = alias_to_table[qualifier]
                if column_name not in allowed_columns_by_table[table_name]:
                    raise QueryValidationError(f"Unknown column in SQL: {qualifier}.{column_name}")
                continue

            if multi_table_scope:
                raise QueryValidationError(f"Unqualified column is not allowed in multi-table scope: {column_name}")

            single_table_name = next(iter(alias_to_table.values()))
            if column_name not in allowed_columns_by_table[single_table_name]:
                raise QueryValidationError(f"Unknown column in SQL: {column_name}")

        self._validate_join_conditions(expression, context, alias_to_table)

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
        if "count" in lowered or "数量" in question or "多少" in question:
            return f"SELECT COUNT(1) AS total_count FROM {table.name} AS {table.alias}"
        if ("sum" in lowered or "销售额" in question or "金额" in question) and "amount" in available_columns:
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

    def _validate_join_conditions(
        self,
        expression: exp.Select,
        context: RetrievedContext,
        alias_to_table: dict[str, str],
    ) -> None:
        joins = list(expression.find_all(exp.Join))
        if len(alias_to_table) <= 1 and not joins:
            return

        for join in joins:
            join_condition = join.args.get("on")
            if join_condition is None:
                raise QueryValidationError("JOIN must include an allowed ON condition")
            condition_aliases = {
                column.table
                for column in join_condition.find_all(exp.Column)
                if column.table
            }
            if len(condition_aliases) < 2:
                raise QueryValidationError("JOIN condition must reference at least two table aliases")
            unknown_aliases = condition_aliases - set(alias_to_table.keys())
            if unknown_aliases:
                unknown_alias = sorted(unknown_aliases)[0]
                raise QueryValidationError(f"Unknown table alias in JOIN condition: {unknown_alias}")
