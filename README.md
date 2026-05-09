# AgileQuery MVP

这是基于 `design.md` 搭建的 Python 后端 MVP 骨架（附带 Vue 3 前端），目标是先跑通一个可验证的四阶段链路：

1. Retrieval：路由 Space 并召回表上下文
2. Text-to-SQL：生成并校验 SQL
3. Execution：只读执行与结果保护
4. Insight：输出摘要和 Markdown 表格

## 当前能力

- FastAPI 服务骨架
- `Database -> Space -> Table` 领域模型
- `JoinRule` / `MetricRule` 元数据骨架
- 内存元数据仓库
- SQLite FTS5 索引服务骨架，支持 table / metric_rule 文档；JoinRule 作为 Space 级常驻上下文
- FTS5 已接入基础 MATCH 检索流程，支持文档侧/查询侧对齐的轻量中文 token 发射
- 确定性 SQL 生成与 `sqlglot` AST 校验
- 可插拔 `LLMClient` 抽象，默认使用 `StubLLMClient` 保持 deterministic 行为
- OpenAI-compatible LLM adapter（默认关闭）
- SQL / Insight PromptBuilder 合同
- SQL 生成与校验会基于 `DatabaseMeta.dialect` 选择 SQL 方言（当前支持 sqlite/postgres/mysql）
- 执行层通过 `DatabaseConnector` 抽象接入数据库，当前内置 SQLite demo connector
- SQL 生成会优先使用召回到的 MetricRule 指标口径
- SQL 生成支持参考 Space 常驻 JoinRule 生成最小 JOIN 示例
- SQLite 查询执行器，支持空结果、标量结果、结果截断
- 查询 API：`POST /query`
- 健康检查 API：`GET /health`

## 运行方式

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

如需启用 PostgreSQL 执行 connector，额外安装：

```bash
pip install -e .[postgres]
```

## 测试

```bash
pytest
```

## 可选 LLM Provider 配置

默认不启用真实模型，系统使用 `StubLLMClient`。如需启用 OpenAI-compatible Provider，可设置：

```bash
export AGILEQUERY_LLM_PROVIDER=openai-compatible
export AGILEQUERY_LLM_BASE_URL=https://your-provider.example/v1
export AGILEQUERY_LLM_API_KEY=your-api-key
export AGILEQUERY_LLM_MODEL=your-model
export AGILEQUERY_LLM_TIMEOUT_SECONDS=30
```

## 可选数据库连接配置

默认注册内置 `demo_sqlite` connector。可以通过 JSON 环境变量增加连接引用：

```bash
export AGILEQUERY_DATABASE_CONNECTIONS_JSON='[
  {"connection_ref":"local_demo","dialect":"sqlite-demo"},
  {
    "connection_ref":"pg_sales",
    "dialect":"postgresql",
    "dsn":"postgresql://readonly_user:password@localhost:5432/sales",
    "connect_timeout_seconds":10,
    "statement_timeout_ms":30000
  },
  {"connection_ref":"mysql_sales","dialect":"mysql"}
]'
```

当前 `postgresql` connector 基于可选依赖 `psycopg`；`mysql` connector 仍是占位，会返回清晰的“运行时驱动未配置”错误。

PostgreSQL connector 还支持读取 schema 元数据：通过 `information_schema.columns` 将表/列转换为 `TableMeta` / `ColumnMeta`，用于后续元数据导入和 FTS5 重建流程。

## 当前边界

- OpenAI-compatible Provider 已有 adapter，但默认关闭；真实调用仍需配置环境变量
- FTS5 目前只实现了轻量 Top-N 知识检索；JoinRule 不走召回，而是作为 Space 级 SQL 生成参考资料常驻上下文
- SQL 生成目前是确定性占位实现，用来稳定打通主链路
- 多数据库方言目前已接入 SQL 生成/校验层；执行层已有 connector registry，PostgreSQL 支持可选 `psycopg` connector 和 schema introspection，MySQL 仍是占位实现
- SQL 校验目前已覆盖只读 SELECT、禁用 `SELECT *`、基础表/列/别名白名单和 JOIN 结构校验；JoinRule 是高置信提示而不是穷举白名单
- 默认使用 SQLite 演示执行器，后续可替换成真实业务库只读连接
