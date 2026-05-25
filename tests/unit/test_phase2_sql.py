from app.domain.errors import QueryValidationError
from app.domain.models import ColumnMeta, DatabaseMeta, JoinRuleMeta, MetricRuleMeta, RetrievedContext, SpaceMeta, TableMeta
from app.integrations.llm_client import FixedResponseLLMClient
from app.services.phase2_sql import SqlGenerationService

def build_context() -> RetrievedContext:
    sales_orders = TableMeta(
        name="sales_orders",
        business_name="销售订单",
        description="订单金额与销售区域明细",
        alias="so",
        columns=[
            ColumnMeta(name="order_id", data_type="INTEGER", description="订单编号"),
            ColumnMeta(name="amount", data_type="REAL", description="销售金额"),
            ColumnMeta(name="region", data_type="TEXT", description="销售区域"),
        ],
    )
    sales_customers = TableMeta(
        name="sales_customers",
        business_name="销售客户",
        description="销售客户信息",
        alias="sc",
        columns=[
            ColumnMeta(name="customer_name", data_type="TEXT", description="客户名称"),
            ColumnMeta(name="customer_tier", data_type="TEXT", description="客户等级"),
        ],
    )
    order_customer_join = JoinRuleMeta(
        id="orders_to_customers",
        left_table="sales_orders",
        right_table="sales_customers",
        condition="so.customer_name = sc.customer_name",
        description="订单和客户可通过客户名称关联。",
    )
    sales_space = SpaceMeta(
        id="sales",
        name="Sales",
        description="销售分析",
        sample_questions=["销售额是多少？"],
        tables=[sales_orders, sales_customers],
        join_rules=[order_customer_join],
    )
    database = DatabaseMeta(
        id="demo",
        name="Demo",
        dialect="sqlite",
        description="演示库",
        spaces=[sales_space],
    )
    return RetrievedContext(
        database=database,
        space=sales_space,
        tables=[sales_orders, sales_customers],
        keywords=["销售额"],
        join_rules=[order_customer_join],
    )


def build_single_table_context() -> RetrievedContext:
    context = build_context()
    return RetrievedContext(
        database=context.database,
        space=context.space,
        tables=[context.tables[0]],
        keywords=context.keywords,
    )


def build_postgres_context() -> RetrievedContext:
    context = build_single_table_context()
    database = DatabaseMeta(
        id="pg_demo",
        name="Postgres Demo",
        dialect="postgresql",
        description="Postgres 演示库",
        spaces=context.database.spaces,
    )
    return RetrievedContext(
        database=database,
        space=context.space,
        tables=context.tables,
        keywords=context.keywords,
    )


def test_safety_check_rejects_multiple_statements() -> None:
    service = SqlGenerationService()

    try:
        service._safety_check("SELECT order_id FROM sales_orders; DELETE FROM sales_orders")
    except QueryValidationError as exc:
        assert "Multiple SQL statements" in str(exc)
    else:
        raise AssertionError("Expected multi-statement SQL to fail")


def test_safety_check_rejects_non_select() -> None:
    service = SqlGenerationService()

    try:
        service._safety_check("DELETE FROM sales_orders")
    except QueryValidationError as exc:
        assert "Only SELECT" in str(exc)
    else:
        raise AssertionError("Expected DELETE to fail safety check")


def test_correct_sql_builds_prompt_with_error() -> None:
    captured: list[str] = []

    class CapturingLLMClient:
        def complete(self, prompt: str) -> str:
            captured.append(prompt)
            return "SELECT COUNT(*) FROM sales_orders"

    service = SqlGenerationService(llm_client=CapturingLLMClient())
    result = service.correct_sql("original prompt", "SELECT bad FROM x", "no such table: x")

    assert "original prompt" in captured[0]
    assert "no such table: x" in captured[0]
    corrected_sql, _, _ = result
    assert corrected_sql == "SELECT COUNT(*) FROM sales_orders"


def test_generate_sql_uses_available_columns_for_default_projection() -> None:
    service = SqlGenerationService()

    validated = service.generate_and_validate("列出订单信息", build_single_table_context())

    assert "so.order_id" in validated.sql
    assert "so.region" in validated.sql


def test_generate_sql_only_uses_amount_when_column_exists() -> None:
    service = SqlGenerationService()
    single_table_context = build_single_table_context()
    customer_only_table = TableMeta(
        name="sales_customers",
        business_name="销售客户",
        description="客户表",
        alias="sc",
        columns=[ColumnMeta(name="customer_name", data_type="TEXT", description="客户名称")],
    )
    customer_context = RetrievedContext(
        database=single_table_context.database,
        space=single_table_context.space,
        tables=[customer_only_table],
        keywords=["销售额"],
    )

    validated = service.generate_and_validate("销售额是多少？", customer_context)

    assert "SUM" not in validated.sql
    assert "sc.customer_name" in validated.sql


def test_generate_sql_prefers_metric_rule_expression() -> None:
    service = SqlGenerationService()
    context = build_single_table_context()
    metric_context = RetrievedContext(
        database=context.database,
        space=context.space,
        tables=context.tables,
        keywords=context.keywords,
        metric_rules=[
            MetricRuleMeta(
                id="total_sales_amount",
                name="销售额",
                description="销售额为订单金额求和。",
                expression="SUM(so.amount)",
                source_table="sales_orders",
                output_alias="total_amount",
                synonyms=["营收", "收入"],
            )
        ],
    )

    validated = service.generate_and_validate("营收是多少？", metric_context)

    assert validated.sql == "SELECT SUM(so.amount) AS total_amount FROM sales_orders AS so"


def test_generate_sql_uses_retrieved_join_rule_for_customer_question() -> None:
    service = SqlGenerationService()

    validated = service.generate_and_validate("客户等级对应的订单金额是多少？", build_context())

    assert "JOIN sales_customers AS sc ON so.customer_name = sc.customer_name" in validated.sql
    assert "so.amount" in validated.sql
    assert "sc.customer_tier" in validated.sql


def test_generate_sql_accepts_valid_llm_client_response() -> None:
    service = SqlGenerationService(
        llm_client=FixedResponseLLMClient("SELECT so.amount FROM sales_orders AS so LIMIT 10")
    )

    validated = service.generate_and_validate("列出订单金额", build_single_table_context())

    assert validated.sql == "SELECT so.amount FROM sales_orders AS so LIMIT 10"
    assert "sql_generated=llm_client" in validated.diagnostics


def test_generate_sql_uses_dialect_limit_renderer() -> None:
    service = SqlGenerationService()

    validated = service.generate_and_validate("列出订单金额", build_postgres_context())

    assert validated.sql.endswith("LIMIT 10")


def test_safety_check_accepts_valid_select() -> None:
    service = SqlGenerationService()
    service._safety_check("SELECT so.amount FROM sales_orders AS so LIMIT 10")
