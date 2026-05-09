from app.domain.models import (
    ColumnMeta,
    DatabaseMeta,
    ExecutionResult,
    JoinRuleMeta,
    MetricRuleMeta,
    RetrievedContext,
    SpaceMeta,
    TableMeta,
)
from app.services.prompt_builder import PromptBuilder


def build_prompt_context() -> RetrievedContext:
    sales_orders = TableMeta(
        name="sales_orders",
        business_name="销售订单",
        description="订单金额与区域",
        alias="so",
        columns=[ColumnMeta(name="amount", data_type="REAL", description="订单金额")],
    )
    join_rule = JoinRuleMeta(
        id="same_name_join",
        description="A 表跟 B 表中相同 column name 的字段可以作为 join 参考。",
        guidance="同名字段可以作为 LLM 生成 SQL 的 join 候选。",
    )
    metric_rule = MetricRuleMeta(
        id="total_sales_amount",
        name="销售额",
        description="销售额为订单金额求和。",
        expression="SUM(so.amount)",
        source_table="sales_orders",
        output_alias="total_amount",
        synonyms=["营收"],
    )
    space = SpaceMeta(
        id="sales",
        name="Sales",
        description="销售业务域",
        tables=[sales_orders],
        join_rules=[join_rule],
        metric_rules=[metric_rule],
    )
    database = DatabaseMeta(id="demo", name="Demo", dialect="sqlite", description="演示库", spaces=[space])
    return RetrievedContext(
        database=database,
        space=space,
        tables=[sales_orders],
        keywords=["销售额"],
        join_rules=[join_rule],
        metric_rules=[metric_rule],
    )


def test_sql_prompt_includes_join_rules_as_space_guidance() -> None:
    prompt = PromptBuilder().build_sql_prompt("销售额是多少？", build_prompt_context())

    assert "JoinRules / SQL guidance" in prompt
    assert "same_name_join" in prompt
    assert "相同 column name" in prompt
    assert "MetricRules" in prompt
    assert "SUM(so.amount)" in prompt


def test_insight_prompt_includes_anti_hallucination_rules() -> None:
    result = ExecutionResult(
        sql="SELECT SUM(amount) AS total_amount FROM sales_orders",
        columns=["total_amount"],
        rows=[[420.5]],
        row_count=1,
        is_truncated=False,
        status="scalar",
    )

    prompt = PromptBuilder().build_insight_prompt(result)

    assert "Use only the returned data" in prompt
    assert "Do not perform new arithmetic" in prompt
    assert "| total_amount |" in prompt
