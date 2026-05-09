from app.domain.models import ColumnMeta, DatabaseMeta, MetricRuleMeta, SpaceMeta, TableMeta


def test_database_space_table_hierarchy() -> None:
    table = TableMeta(
        name="sales_orders",
        business_name="销售订单",
        description="订单表",
        alias="so",
        columns=[ColumnMeta(name="order_id", data_type="INTEGER", description="订单编号")],
    )
    metric_rule = MetricRuleMeta(
        id="total_sales_amount",
        name="销售额",
        description="销售额为订单金额求和。",
        expression="SUM(so.amount)",
        source_table="sales_orders",
        output_alias="total_amount",
    )
    space = SpaceMeta(id="sales", name="Sales", description="销售域", tables=[table], metric_rules=[metric_rule])
    database = DatabaseMeta(id="demo", name="Demo", dialect="sqlite", description="演示库", spaces=[space])

    assert database.spaces[0].tables[0].alias == "so"
    assert database.spaces[0].metric_rules[0].output_alias == "total_amount"
