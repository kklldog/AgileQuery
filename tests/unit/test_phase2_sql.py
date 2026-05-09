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


def test_validate_sql_accepts_simple_qualified_select() -> None:
    service = SqlGenerationService()

    service.validate_sql(
        "SELECT so.order_id, so.amount FROM sales_orders AS so LIMIT 10",
        build_single_table_context(),
    )


def test_validate_sql_rejects_multiple_statements() -> None:
    service = SqlGenerationService()

    try:
        service.validate_sql("SELECT so.order_id FROM sales_orders AS so; DELETE FROM sales_orders", build_single_table_context())
    except QueryValidationError as exc:
        assert str(exc) == "Multiple SQL statements are not allowed"
    else:
        raise AssertionError("Expected multi-statement SQL to fail")


def test_validate_sql_rejects_unknown_table() -> None:
    service = SqlGenerationService()

    try:
        service.validate_sql("SELECT x.order_id FROM unknown_table AS x", build_single_table_context())
    except QueryValidationError as exc:
        assert str(exc) == "Unknown table in SQL: unknown_table"
    else:
        raise AssertionError("Expected unknown table to fail")


def test_validate_sql_rejects_unknown_column() -> None:
    service = SqlGenerationService()

    try:
        service.validate_sql("SELECT so.unknown_metric FROM sales_orders AS so", build_single_table_context())
    except QueryValidationError as exc:
        assert str(exc) == "Unknown column in SQL: so.unknown_metric"
    else:
        raise AssertionError("Expected unknown column to fail")


def test_validate_sql_rejects_star_projection() -> None:
    service = SqlGenerationService()

    try:
        service.validate_sql("SELECT * FROM sales_orders AS so", build_single_table_context())
    except QueryValidationError as exc:
        assert str(exc) == "Star projections are not allowed"
    else:
        raise AssertionError("Expected star projection to fail")


def test_validate_sql_rejects_unqualified_column_in_multi_table_scope() -> None:
    service = SqlGenerationService()

    try:
        service.validate_sql(
            "SELECT order_id FROM sales_orders AS so JOIN sales_customers AS sc ON so.order_id = sc.customer_name",
            build_context(),
        )
    except QueryValidationError as exc:
        assert str(exc) == "Unqualified column is not allowed in multi-table scope: order_id"
    else:
        raise AssertionError("Expected bare column to fail in multi-table scope")


def test_validate_sql_accepts_join_condition_from_join_rule() -> None:
    service = SqlGenerationService()

    service.validate_sql(
        "SELECT so.amount, sc.customer_tier FROM sales_orders AS so JOIN sales_customers AS sc ON so.customer_name = sc.customer_name",
        build_context(),
    )


def test_validate_sql_accepts_structurally_safe_join_not_in_join_rule() -> None:
    service = SqlGenerationService()

    service.validate_sql(
        "SELECT so.amount, sc.customer_tier FROM sales_orders AS so JOIN sales_customers AS sc ON so.order_id = sc.customer_name",
        build_context(),
    )


def test_validate_sql_accepts_join_without_join_rule_when_structurally_safe() -> None:
    service = SqlGenerationService()
    context = build_context()
    context_without_join_rule = RetrievedContext(
        database=context.database,
        space=context.space,
        tables=context.tables,
        keywords=context.keywords,
    )

    service.validate_sql(
        "SELECT so.amount, sc.customer_tier FROM sales_orders AS so JOIN sales_customers AS sc ON so.customer_name = sc.customer_name",
        context_without_join_rule,
    )


def test_validate_sql_rejects_join_without_on_condition() -> None:
    service = SqlGenerationService()

    try:
        service.validate_sql("SELECT so.amount, sc.customer_tier FROM sales_orders AS so JOIN sales_customers AS sc", build_context())
    except QueryValidationError as exc:
        assert str(exc) == "JOIN must include an allowed ON condition"
    else:
        raise AssertionError("Expected JOIN without ON to fail")


def test_validate_sql_rejects_join_condition_that_does_not_connect_tables() -> None:
    service = SqlGenerationService()

    try:
        service.validate_sql(
            "SELECT so.amount, sc.customer_tier FROM sales_orders AS so JOIN sales_customers AS sc ON so.amount > 100",
            build_context(),
        )
    except QueryValidationError as exc:
        assert str(exc) == "JOIN condition must reference at least two table aliases"
    else:
        raise AssertionError("Expected non-connecting JOIN condition to fail")


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


def test_validate_sql_uses_context_database_dialect() -> None:
    service = SqlGenerationService()

    service.validate_sql('SELECT so.amount FROM "sales_orders" AS so LIMIT 10', build_postgres_context())


def test_generate_sql_uses_dialect_limit_renderer() -> None:
    service = SqlGenerationService()

    validated = service.generate_and_validate("列出订单金额", build_postgres_context())

    assert validated.sql.endswith("LIMIT 10")


def test_validate_sql_rejects_unsupported_database_dialect() -> None:
    service = SqlGenerationService()
    context = build_single_table_context()
    unsupported_context = RetrievedContext(
        database=DatabaseMeta(id="oracle_demo", name="Oracle Demo", dialect="oracle", description="Oracle", spaces=[]),
        space=context.space,
        tables=context.tables,
        keywords=context.keywords,
    )

    try:
        service.validate_sql("SELECT so.amount FROM sales_orders AS so", unsupported_context)
    except QueryValidationError as exc:
        assert str(exc) == "Unsupported SQL dialect: oracle"
    else:
        raise AssertionError("Expected unsupported dialect to fail")
