from app.domain.models import ExecutionResult, InsightResult
from app.integrations.llm_client import LLMClient, StubLLMClient
from app.services.prompt_builder import PromptBuilder


class InsightService:
    def __init__(self, prompt_builder: PromptBuilder | None = None, llm_client: LLMClient | None = None) -> None:
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._llm_client = llm_client or StubLLMClient()

    def build_insight(self, execution_result: ExecutionResult) -> InsightResult:
        prompt = self._prompt_builder.build_insight_prompt(execution_result)
        llm_summary = self._llm_client.complete(prompt).strip()
        summary = llm_summary or self._build_summary(execution_result)
        table_markdown = self._to_markdown(execution_result)
        diagnostics = ["insight_prompt_built=true"]
        diagnostics.append("insight_generated=llm_client" if llm_summary else "insight_generated=deterministic_stub")
        return InsightResult(summary=summary, table_markdown=table_markdown, diagnostics=diagnostics)

    def _build_summary(self, result: ExecutionResult) -> str:
        if result.status == "empty":
            return "未找到符合条件的数据。"
        if result.status == "scalar":
            scalar_value = result.rows[0][0]
            return f"查询返回了 1 个标量结果，结果值为 {scalar_value}。"
        summary = f"当前展示了 {result.row_count} 行数据。"
        if result.is_truncated:
            summary += f" 因数据量较大，此处仅展示前 {result.row_count} 条，建议增加过滤条件。"
        return summary

    def _to_markdown(self, result: ExecutionResult) -> str:
        if not result.columns:
            return ""
        header = "| " + " | ".join(result.columns) + " |"
        divider = "| " + " | ".join(["---"] * len(result.columns)) + " |"
        body = ["| " + " | ".join(map(str, row)) + " |" for row in result.rows]
        return "\n".join([header, divider, *body])
