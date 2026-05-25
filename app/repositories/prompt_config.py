import json
import os
from dataclasses import dataclass, field


PROMPT_KEYWORD_EXPANSION = "keyword_expansion"
PROMPT_SQL_GENERATION = "sql_generation"
PROMPT_SQL_CORRECTION = "sql_correction"
PROMPT_INSIGHT = "insight"
PROMPT_AI_FILL_TABLE = "ai_fill_table"
PROMPT_AI_FILL_JOINS = "ai_fill_joins"
PROMPT_AI_FILL_METRICS = "ai_fill_metrics"

ALL_PROMPT_KEYS = [
    PROMPT_KEYWORD_EXPANSION,
    PROMPT_SQL_GENERATION,
    PROMPT_SQL_CORRECTION,
    PROMPT_INSIGHT,
    PROMPT_AI_FILL_TABLE,
    PROMPT_AI_FILL_JOINS,
    PROMPT_AI_FILL_METRICS,
]

PROMPT_LABELS = {
    PROMPT_KEYWORD_EXPANSION: "关键词扩展",
    PROMPT_SQL_GENERATION: "SQL 生成（系统指令）",
    PROMPT_SQL_CORRECTION: "SQL 修正",
    PROMPT_INSIGHT: "Insight 摘要（系统指令）",
    PROMPT_AI_FILL_TABLE: "AI 补全表元数据",
    PROMPT_AI_FILL_JOINS: "AI 补全 Joins",
    PROMPT_AI_FILL_METRICS: "AI 补全 Metrics",
}

PROMPT_DESCRIPTIONS = {
    PROMPT_KEYWORD_EXPANSION: "用于从自然语言问题中提取业务关键词并扩展同义词。占位符：{question}",
    PROMPT_SQL_GENERATION: "SQL 生成的系统指令前缀（Rules 部分）。动态上下文（表结构、问题）由系统自动追加，无需手动填写。",
    PROMPT_SQL_CORRECTION: "SQL 执行出错后的修正提示前缀。占位符：{original_prompt}、{sql}、{db_error}",
    PROMPT_INSIGHT: "Insight 摘要的系统指令前缀。动态数据（查询结果表格）由系统自动追加。",
    PROMPT_AI_FILL_TABLE: "AI 补全表元数据的提示。占位符：{table_name}、{cols_desc}",
    PROMPT_AI_FILL_JOINS: "AI 补全 Joins 关联关系的提示。占位符：{tables_desc}",
    PROMPT_AI_FILL_METRICS: "AI 补全业务指标的提示。占位符：{tables_desc}",
}

DEFAULT_PROMPTS: dict[str, str] = {
    PROMPT_KEYWORD_EXPANSION: (
        "从以下问题中提取核心业务关键词，并为每个关键词联想2-3个同义词或相关词，用于数据库文档检索。"
        "只返回一个 JSON 数组，包含所有关键词和同义词，不要输出其他内容。\n\n"
        "示例：\n问题: \"25年一共多少订单量\"\n"
        "输出: [\"订单\", \"订单量\", \"order\", \"订单数\", \"订单总量\", \"单量\"]\n\n"
        "问题: \"{question}\"\n输出:"
    ),
    PROMPT_SQL_GENERATION: (
        "You are generating read-only SQL for AgileQuery.\n"
        "Rules:\n"
        "- Return only one SELECT statement.\n"
        "- Do not use SELECT *.\n"
        "- Use only tables, aliases, and columns from the provided context.\n"
        "- Treat JoinRules as always-available Space-level guidance, not as exhaustive join permissions.\n"
        "- Prefer MetricRules when the question asks for a known metric."
    ),
    PROMPT_SQL_CORRECTION: (
        "{original_prompt}\n\n"
        "[Self-Correction]\n"
        "The following SQL failed when executed against the database:\n"
        "```sql\n{sql}\n```\n"
        "Database error: {db_error}\n\n"
        "Please fix the SQL and return ONLY the corrected SQL statement, no explanation."
    ),
    PROMPT_INSIGHT: (
        "You are summarizing a SQL result for AgileQuery.\n"
        "Rules:\n"
        "- Use only the returned data.\n"
        "- Do not introduce external knowledge.\n"
        "- Do not perform new arithmetic beyond values already returned.\n"
        "- Keep the answer to 1-2 sentences."
    ),
    PROMPT_AI_FILL_TABLE: (
        "你是数据库元数据专家。根据以下表名和列信息，用中文生成业务友好的元数据描述，以 JSON 格式输出。\n\n"
        "表名: {table_name}\n"
        "列信息:\n{cols_desc}\n\n"
        "请以以下 JSON 格式输出（不要输出任何其他内容）：\n"
        "{{\n"
        "  \"business_name\": \"表的中文业务名称\",\n"
        "  \"description\": \"表的业务用途描述（1-2句话）\",\n"
        "  \"columns\": [\n"
        "    {{\"name\": \"列名\", \"description\": \"列的业务含义描述\"}}\n"
        "  ]\n"
        "}}"
    ),
    PROMPT_AI_FILL_JOINS: (
        "你是数据库设计专家。根据以下表结构，用自然语言描述这些表之间可能的关联关系（JOIN 关系），供 AI 生成 SQL 时参考。\n"
        "每行描述一个关联关系，语言简洁、清晰。只输出文本内容，不要输出 JSON 或 Markdown。\n\n"
        "表结构:\n{tables_desc}\n\n"
        "示例输出格式:\n"
        "orders 通过 customer_id 关联 customers\n"
        "order_items 通过 order_id 关联 orders\n\n"
        "请直接输出关联关系描述:"
    ),
    PROMPT_AI_FILL_METRICS: (
        "你是业务数据分析专家。根据以下表结构，用自然语言描述常见业务指标的计算口径，供 AI 生成 SQL 时参考。\n"
        "每行描述一个业务指标，语言简洁、清晰。只输出文本内容，不要输出 JSON 或 Markdown。\n\n"
        "表结构:\n{tables_desc}\n\n"
        "示例输出格式:\n"
        "总销售额 = SUM(amount)，仅统计 status='paid' 的订单\n"
        "客单价 = 总销售额 / 下单客户数\n\n"
        "请直接输出业务指标描述:"
    ),
}


@dataclass
class PromptConfig:
    prompts: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str:
        return self.prompts.get(key) or DEFAULT_PROMPTS.get(key, "")

    def to_dict(self) -> dict[str, str]:
        return dict(self.prompts)


class PromptConfigFileRepository:
    def __init__(self, data_dir: str, database_id: str) -> None:
        self._file_path = os.path.join(data_dir, f"prompts_{database_id}.json")
        self._config = PromptConfig()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._file_path):
            return
        with open(self._file_path, "r", encoding="utf-8") as f:
            data: dict = json.load(f)
        self._config = PromptConfig(prompts={k: v for k, v in data.items() if isinstance(v, str)})

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._file_path) or ".", exist_ok=True)
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(self._config.to_dict(), f, ensure_ascii=False, indent=2)

    def get(self) -> PromptConfig:
        return self._config

    def update(self, prompts: dict[str, str]) -> PromptConfig:
        self._config = PromptConfig(prompts={k: v for k, v in prompts.items() if k in ALL_PROMPT_KEYS})
        self._save()
        return self._config
