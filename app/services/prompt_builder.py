from app.domain.models import ExecutionResult, RetrievedContext


class PromptBuilder:
    def build_sql_prompt(self, question: str, context: RetrievedContext) -> str:
        tables = "\n".join(
            [
                f"- {table.name} AS {table.alias}: {table.description}; columns: "
                + ", ".join([f"{column.name} ({column.data_type}) - {column.description}" for column in table.columns])
                for table in context.tables
            ]
        )
        metrics = "\n".join(
            [
                f"- {metric.name} ({metric.id}): {metric.description}; expression: {metric.expression} AS {metric.output_alias}; synonyms: {', '.join(metric.synonyms)}"
                for metric in context.metric_rules
            ]
        ) or "- none"
        join_guidance = "\n".join(
            [
                f"- {rule.id}: {rule.description}; guidance: {rule.guidance or 'none'}; condition example: {rule.condition or 'not specified'}; examples: {' | '.join(rule.examples) if rule.examples else 'none'}"
                for rule in context.join_rules
            ]
        ) or "- none"

        return "\n".join(
            [
                "You are generating read-only SQL for AgileQuery.",
                "Rules:",
                "- Return only one SELECT statement.",
                "- Do not use SELECT *.",
                "- Use only tables, aliases, and columns from the provided context.",
                "- Treat JoinRules as always-available Space-level guidance, not as exhaustive join permissions.",
                "- Prefer MetricRules when the question asks for a known metric.",
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

    def build_insight_prompt(self, execution_result: ExecutionResult) -> str:
        table_markdown = self._to_markdown(execution_result)
        truncation_notice = (
            f"Result is truncated to {execution_result.row_count} rows. You must mention this."
            if execution_result.is_truncated
            else "Result is not truncated."
        )
        return "\n".join(
            [
                "You are summarizing a SQL result for AgileQuery.",
                "Rules:",
                "- Use only the returned data.",
                "- Do not introduce external knowledge.",
                "- Do not perform new arithmetic beyond values already returned.",
                "- Keep the answer to 1-2 sentences.",
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
