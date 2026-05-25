from app.domain.models import ExecutionResult, RetrievedContext
from app.repositories.prompt_config import (
    PROMPT_INSIGHT,
    PROMPT_SQL_GENERATION,
    PromptConfig,
)


class PromptBuilder:
    def __init__(self, prompt_config: PromptConfig | None = None) -> None:
        self._cfg = prompt_config or PromptConfig()

    def build_sql_prompt(self, question: str, context: RetrievedContext, prompt_config: PromptConfig | None = None) -> str:
        cfg = prompt_config or self._cfg
        tables = "\n".join(
            [
                f"- {table.name} AS {table.alias}: {table.description}; columns: "
                + ", ".join([f"{column.name} ({column.data_type}) - {column.description}" for column in table.columns])
                for table in context.tables
            ]
        )
        join_guidance = "\n".join(
            [
                f"- {rule.id}: {rule.description}; guidance: {rule.guidance or 'none'}; condition example: {rule.condition or 'not specified'}; examples: {' | '.join(rule.examples) if rule.examples else 'none'}"
                for rule in context.join_rules
            ]
        )
        if context.space.joins_text:
            if join_guidance:
                join_guidance = context.space.joins_text + "\n" + join_guidance
            else:
                join_guidance = context.space.joins_text
        join_guidance = join_guidance or "- none"

        metrics_structured = "\n".join(
            [
                f"- {metric.name} ({metric.id}): {metric.description}; expression: {metric.expression} AS {metric.output_alias}; synonyms: {', '.join(metric.synonyms)}"
                for metric in context.metric_rules
            ]
        )
        if context.space.metrics_text:
            if metrics_structured:
                metrics = context.space.metrics_text + "\n" + metrics_structured
            else:
                metrics = context.space.metrics_text
        else:
            metrics = metrics_structured or "- none"

        system_instruction = cfg.get(PROMPT_SQL_GENERATION)

        return "\n".join(
            [
                system_instruction,
                "",
                f"Database: {context.database.id} ({context.database.dialect})",
                f"Space: {context.space.id} - {context.space.description}",
                "",
                "Tables:",
                tables,
                "",
                "MetricRules:",
                metrics,
                "",
                "JoinRules / SQL guidance:",
                join_guidance,
                "",
                f"Question: {question}",
            ]
        )

    def build_insight_prompt(self, execution_result: ExecutionResult, prompt_config: PromptConfig | None = None) -> str:
        cfg = prompt_config or self._cfg
        table_markdown = self._to_markdown(execution_result)
        truncation_notice = (
            f"Result is truncated to {execution_result.row_count} rows. You must mention this."
            if execution_result.is_truncated
            else "Result is not truncated."
        )
        system_instruction = cfg.get(PROMPT_INSIGHT)
        return "\n".join(
            [
                system_instruction,
                truncation_notice,
                "",
                "Data:",
                table_markdown,
            ]
        )

    def _to_markdown(self, result: ExecutionResult) -> str:
        if not result.columns:
            return ""
        header = "| " + " | ".join(result.columns) + " |"
        divider = "| " + " | ".join(["---"] * len(result.columns)) + " |"
        body = ["| " + " | ".join(map(str, row)) + " |" for row in result.rows]
        return "\n".join([header, divider, *body])
