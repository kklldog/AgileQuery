import json
import os
from dataclasses import asdict

from app.domain.errors import CatalogLookupError
from app.domain.models import ColumnMeta, DatabaseMeta, JoinRuleMeta, MetricRuleMeta, SpaceMeta, TableMeta


class InMemoryCatalogRepository:
    def __init__(self, databases: list[DatabaseMeta]) -> None:
        self._databases = {database.id: database for database in databases}

    def database_ids(self) -> list[str]:
        return list(self._databases.keys())

    @classmethod
    def with_demo_data(cls) -> "InMemoryCatalogRepository":
        sales_orders = TableMeta(
            name="sales_orders",
            business_name="销售订单",
            description="记录订单明细与销售金额。",
            alias="so",
            columns=[
                ColumnMeta(name="order_id", data_type="INTEGER", description="订单主键"),
                ColumnMeta(name="customer_name", data_type="TEXT", description="客户名称"),
                ColumnMeta(name="region", data_type="TEXT", description="销售区域"),
                ColumnMeta(name="amount", data_type="REAL", description="订单金额"),
            ],
        )
        sales_customers = TableMeta(
            name="sales_customers",
            business_name="销售客户",
            description="记录客户名称与客户等级。",
            alias="sc",
            columns=[
                ColumnMeta(name="customer_name", data_type="TEXT", description="客户名称"),
                ColumnMeta(name="customer_tier", data_type="TEXT", description="客户等级"),
            ],
        )
        order_customer_join = JoinRuleMeta(
            id="orders_to_customers",
            description="订单和客户可通过客户名称关联。也可以参考用户维护的常见 join 示例生成 SQL。",
            left_table="sales_orders",
            right_table="sales_customers",
            condition="so.customer_name = sc.customer_name",
            guidance="优先使用客户名称连接订单和客户维表；若用户描述同名字段可连接，也可以作为 LLM 生成 SQL 的参考。",
            examples=[
                "SELECT so.amount, sc.customer_tier FROM sales_orders AS so JOIN sales_customers AS sc ON so.customer_name = sc.customer_name"
            ],
        )
        total_sales_amount = MetricRuleMeta(
            id="total_sales_amount",
            name="销售额",
            description="销售额口径为订单金额 amount 的求和。",
            expression="SUM(so.amount)",
            source_table="sales_orders",
            output_alias="total_amount",
            synonyms=["营收", "收入", "订单金额"],
        )
        sales_space = SpaceMeta(
            id="sales",
            name="Sales",
            description="销售业务域",
            sample_questions=["华东区销售额是多少？", "客户等级对应的订单金额是多少？"],
            tables=[sales_orders, sales_customers],
            join_rules=[order_customer_join],
            metric_rules=[total_sales_amount],
        )
        demo_database = DatabaseMeta(
            id="demo",
            name="Demo Database",
            dialect="sqlite",
            description="内置演示数据库",
            connection_ref="demo_sqlite",
            spaces=[sales_space],
        )
        return cls([demo_database])

    def add_database(self, database: DatabaseMeta) -> None:
        if database.id in self._databases:
            raise CatalogLookupError(f"Database already exists: {database.id}")
        self._databases[database.id] = database

    def delete_database(self, database_id: str) -> None:
        if database_id not in self._databases:
            raise CatalogLookupError(f"Unknown database: {database_id}")
        del self._databases[database_id]

    def get_database(self, database_id: str) -> DatabaseMeta:
        if database_id not in self._databases:
            raise CatalogLookupError(f"Unknown database: {database_id}")
        return self._databases[database_id]

    def update_database(
        self,
        database_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        dialect: str | None = None,
    ) -> DatabaseMeta:
        existing = self.get_database(database_id)
        updated = DatabaseMeta(
            id=existing.id,
            name=name if name is not None else existing.name,
            dialect=dialect if dialect is not None else existing.dialect,
            description=description if description is not None else existing.description,
            connection_ref=existing.connection_ref,
            spaces=list(existing.spaces),
        )
        self._databases[database_id] = updated
        return updated

    def get_space(self, database_id: str, space_id: str) -> SpaceMeta:
        database = self.get_database(database_id)
        for space in database.spaces:
            if space.id == space_id:
                return space
        raise CatalogLookupError(f"Unknown space: {space_id}")

    def list_spaces(self, database_id: str) -> list[SpaceMeta]:
        return list(self.get_database(database_id).spaces)

    def list_tables(self, database_id: str, space_id: str) -> list[TableMeta]:
        return list(self.get_space(database_id, space_id).tables)

    def delete_space(self, database_id: str, space_id: str) -> None:
        database = self.get_database(database_id)
        if not any(space.id == space_id for space in database.spaces):
            raise CatalogLookupError(f"Unknown space: {space_id}")
        self._databases[database_id] = DatabaseMeta(
            id=database.id,
            name=database.name,
            dialect=database.dialect,
            description=database.description,
            connection_ref=database.connection_ref,
            spaces=[s for s in database.spaces if s.id != space_id],
        )

    def add_space(self, database_id: str, space: SpaceMeta) -> None:
        database = self.get_database(database_id)
        if any(existing_space.id == space.id for existing_space in database.spaces):
            raise CatalogLookupError(f"Space already exists: {space.id}")
        self._databases[database_id] = DatabaseMeta(
            id=database.id,
            name=database.name,
            dialect=database.dialect,
            description=database.description,
            connection_ref=database.connection_ref,
            spaces=[*database.spaces, space],
        )

    def list_join_rules(self, database_id: str, space_id: str) -> list[JoinRuleMeta]:
        return list(self.get_space(database_id, space_id).join_rules)

    def list_metric_rules(self, database_id: str, space_id: str) -> list[MetricRuleMeta]:
        return list(self.get_space(database_id, space_id).metric_rules)

    def update_space(
        self,
        database_id: str,
        space_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        tables: list[TableMeta] | None = None,
        join_rules: list[JoinRuleMeta] | None = None,
        metric_rules: list[MetricRuleMeta] | None = None,
    ) -> SpaceMeta:
        database = self.get_database(database_id)
        if not any(space.id == space_id for space in database.spaces):
            raise CatalogLookupError(f"Unknown space: {space_id}")

        updated_spaces: list[SpaceMeta] = []
        updated: SpaceMeta | None = None
        for space in database.spaces:
            if space.id == space_id:
                updated = SpaceMeta(
                    id=space.id,
                    name=name if name is not None else space.name,
                    description=description if description is not None else space.description,
                    sample_questions=list(space.sample_questions),
                    tables=tables if tables is not None else list(space.tables),
                    join_rules=join_rules if join_rules is not None else list(space.join_rules),
                    metric_rules=metric_rules if metric_rules is not None else list(space.metric_rules),
                )
                updated_spaces.append(updated)
            else:
                updated_spaces.append(space)

        self._databases[database_id] = DatabaseMeta(
            id=database.id,
            name=database.name,
            dialect=database.dialect,
            description=database.description,
            connection_ref=database.connection_ref,
            spaces=updated_spaces,
        )
        assert updated is not None
        return updated

    def update_space_tables(self, database_id: str, space_id: str, tables: list[TableMeta]) -> None:
        database = self.get_database(database_id)
        updated_spaces = [
            SpaceMeta(
                id=space.id,
                name=space.name,
                description=space.description,
                sample_questions=list(space.sample_questions),
                tables=tables if space.id == space_id else list(space.tables),
                join_rules=list(space.join_rules),
                metric_rules=list(space.metric_rules),
            )
            for space in database.spaces
        ]
        if not any(space.id == space_id for space in database.spaces):
            raise CatalogLookupError(f"Unknown space: {space_id}")
        self._databases[database_id] = DatabaseMeta(
            id=database.id,
            name=database.name,
            dialect=database.dialect,
            description=database.description,
            connection_ref=database.connection_ref,
            spaces=updated_spaces,
        )

    def export_documents(self, database_id: str, space_id: str) -> list[dict]:
        return [
            *[asdict(table) for table in self.list_tables(database_id, space_id)],
            *[asdict(join_rule) for join_rule in self.list_join_rules(database_id, space_id)],
            *[asdict(metric_rule) for metric_rule in self.list_metric_rules(database_id, space_id)],
        ]

class JsonFileCatalogRepository(InMemoryCatalogRepository):
    def __init__(self, file_path: str) -> None:
        self._file_path = file_path
        databases = self._load_from_file()
        super().__init__(databases)

    def _load_from_file(self) -> list[DatabaseMeta]:
        if not os.path.exists(self._file_path):
            demo_repo = InMemoryCatalogRepository.with_demo_data()
            databases = [demo_repo.get_database(db_id) for db_id in demo_repo.database_ids()]
            self._save_to_file(databases)
            return databases

        with open(self._file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        return [self._parse_database(db_data) for db_data in data]

    def _save_to_file(self, databases: list[DatabaseMeta] | None = None) -> None:
        if databases is None:
            databases = [self.get_database(db_id) for db_id in self.database_ids()]
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump([asdict(db) for db in databases], f, ensure_ascii=False, indent=2)

    def update_space_tables(self, database_id: str, space_id: str, tables: list[TableMeta]) -> None:
        super().update_space_tables(database_id, space_id, tables)
        self._save_to_file()

    def add_database(self, database: DatabaseMeta) -> None:
        super().add_database(database)
        self._save_to_file()

    def delete_database(self, database_id: str) -> None:
        super().delete_database(database_id)
        self._save_to_file()

    def add_space(self, database_id: str, space: SpaceMeta) -> None:
        super().add_space(database_id, space)
        self._save_to_file()

    def delete_space(self, database_id: str, space_id: str) -> None:
        super().delete_space(database_id, space_id)
        self._save_to_file()

    def update_space(
        self,
        database_id: str,
        space_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        tables: list[TableMeta] | None = None,
        join_rules: list[JoinRuleMeta] | None = None,
        metric_rules: list[MetricRuleMeta] | None = None,
    ) -> SpaceMeta:
        updated = super().update_space(
            database_id,
            space_id,
            name=name,
            description=description,
            tables=tables,
            join_rules=join_rules,
            metric_rules=metric_rules,
        )
        self._save_to_file()
        return updated

    def _parse_database(self, data: dict) -> DatabaseMeta:
        return DatabaseMeta(
            id=data["id"],
            name=data["name"],
            dialect=data["dialect"],
            description=data["description"],
            connection_ref=data.get("connection_ref", ""),
            spaces=[self._parse_space(s) for s in data.get("spaces", [])]
        )

    def _parse_space(self, data: dict) -> SpaceMeta:
        return SpaceMeta(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            sample_questions=data.get("sample_questions", []),
            tables=[self._parse_table(t) for t in data.get("tables", [])],
            join_rules=[self._parse_join_rule(j) for j in data.get("join_rules", [])],
            metric_rules=[self._parse_metric_rule(m) for m in data.get("metric_rules", [])]
        )

    def _parse_table(self, data: dict) -> TableMeta:
        return TableMeta(
            name=data["name"],
            business_name=data["business_name"],
            description=data["description"],
            alias=data["alias"],
            columns=[ColumnMeta(**c) for c in data.get("columns", [])]
        )

    def _parse_join_rule(self, data: dict) -> JoinRuleMeta:
        return JoinRuleMeta(**data)

    def _parse_metric_rule(self, data: dict) -> MetricRuleMeta:
        return MetricRuleMeta(**data)
