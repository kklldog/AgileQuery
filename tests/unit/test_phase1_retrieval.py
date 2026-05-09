from app.domain.errors import QueryValidationError
from app.domain.models import ColumnMeta, DatabaseMeta, JoinRuleMeta, MetricRuleMeta, SpaceMeta, TableMeta
from app.repositories.catalog import InMemoryCatalogRepository
from app.services.phase1_retrieval import RetrievalService


def build_multi_space_repository() -> InMemoryCatalogRepository:
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
        description="销售客户信息与等级",
        alias="sc",
        columns=[ColumnMeta(name="customer_name", data_type="TEXT", description="客户名称")],
    )
    sales_customer_join = JoinRuleMeta(
        id="orders_to_customers",
        description="订单和客户可通过客户名称关联。",
        left_table="sales_orders",
        right_table="sales_customers",
        condition="so.customer_name = sc.customer_name",
        guidance="同名客户字段通常可以作为 join 参考。",
        examples=["SELECT ... FROM sales_orders AS so JOIN sales_customers AS sc ON so.customer_name = sc.customer_name"],
    )
    total_sales_metric = MetricRuleMeta(
        id="total_sales_amount",
        name="销售额",
        description="销售额为订单金额求和。",
        expression="SUM(so.amount)",
        source_table="sales_orders",
        output_alias="total_amount",
        synonyms=["营收", "收入", "订单金额"],
    )
    finance_ledger = TableMeta(
        name="finance_ledger",
        business_name="财务总账",
        description="净利润与成本记录",
        alias="fl",
        columns=[
            ColumnMeta(name="entry_id", data_type="INTEGER", description="分录编号"),
            ColumnMeta(name="profit", data_type="REAL", description="净利润"),
        ],
    )
    sales_space = SpaceMeta(
        id="sales",
        name="Sales",
        description="销售分析和订单报表",
        sample_questions=["华东销售额是多少？", "订单金额最高的是谁？"],
        tables=[sales_orders, sales_customers],
        join_rules=[sales_customer_join],
        metric_rules=[total_sales_metric],
    )
    finance_space = SpaceMeta(
        id="finance",
        name="Finance",
        description="财务利润分析和成本报表",
        sample_questions=["本月净利润是多少？"],
        tables=[finance_ledger],
    )
    database = DatabaseMeta(
        id="demo",
        name="Demo",
        dialect="sqlite",
        description="演示库",
        spaces=[sales_space, finance_space],
    )
    return InMemoryCatalogRepository([database])


def test_retrieve_uses_explicit_space_id_over_scoring() -> None:
    service = RetrievalService(build_multi_space_repository())

    context = service.retrieve("demo", "净利润是多少？", space_id="sales")

    assert context.space.id == "sales"
    assert any(item == "routing_strategy=explicit" for item in context.diagnostics)


def test_retrieve_routes_space_from_sample_question_overlap() -> None:
    service = RetrievalService(build_multi_space_repository())

    context = service.retrieve("demo", "华东销售额是多少？")

    assert context.space.id == "sales"
    assert context.tables[0].name == "sales_orders"
    assert context.metric_rules[0].id == "total_sales_amount"
    assert any(item.startswith("routing_scores=") for item in context.diagnostics)


def test_retrieve_always_returns_space_join_rules_as_context() -> None:
    service = RetrievalService(build_multi_space_repository())

    context = service.retrieve("demo", "华东销售额是多少？", space_id="sales")

    assert context.tables
    assert context.join_rules[0].id == "orders_to_customers"
    assert any(item == "context_join_rules=orders_to_customers" for item in context.diagnostics)


def test_retrieve_returns_metric_rules_when_metric_matches() -> None:
    service = RetrievalService(build_multi_space_repository())

    context = service.retrieve("demo", "营收是多少？", space_id="sales")

    assert context.tables[0].name == "sales_orders"
    assert context.metric_rules[0].name == "销售额"


def test_retrieve_raises_for_ambiguous_multi_space_question() -> None:
    service = RetrievalService(build_multi_space_repository())

    try:
        service.retrieve("demo", "分析一下情况")
    except QueryValidationError as exc:
        assert str(exc) == "Unable to resolve target space from the question"
    else:
        raise AssertionError("Expected ambiguous question to fail closed")


def test_retrieve_raises_when_no_tables_match_in_resolved_space() -> None:
    service = RetrievalService(build_multi_space_repository())

    try:
        service.retrieve("demo", "Finance 的税务发票是什么？", space_id="finance")
    except QueryValidationError as exc:
        assert str(exc) == "No relevant tables matched the question in the resolved space"
    else:
        raise AssertionError("Expected zero-hit retrieval to fail closed")


def test_retrieve_handles_quotes_without_fts_failure() -> None:
    service = RetrievalService(build_multi_space_repository())

    context = service.retrieve("demo", '"华东" 销售额是多少？')

    assert context.space.id == "sales"
    assert context.tables
