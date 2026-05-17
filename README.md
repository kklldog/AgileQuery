# AgileQuery

AgileQuery 是一个基于自然语言的数据查询平台，允许用户通过 AI 对话直接查询数据库，无需编写 SQL。

## 功能截图

### 数据库管理

管理多个数据库连接（SQLite / PostgreSQL / MySQL），支持连接测试与元数据导入。

![数据库管理](docs/screenshots/01_databases.png)

### LLM 配置

在设置面板中配置 OpenAI-compatible LLM Provider，支持自定义 Base URL、API Key、模型名称与超时时间。

![LLM 配置](docs/screenshots/02_llm_config.png)

### 添加数据库

通过表单添加新数据库，支持方言选择（SQLite / PostgreSQL / MySQL / MSSQL）和连接字符串配置。

![添加数据库](docs/screenshots/03_add_database.png)

### 智能对话查询

选择 Space 后即可用自然语言提问，AI 自动生成 SQL 并返回结构化结果与洞察摘要。

![智能对话](docs/screenshots/04_spaces_chat.png)

### Space 基本信息

编辑 Space 的 ID、名称、描述和示例问题，用于辅助 AI 路由。

![Space 信息](docs/screenshots/06_space_edit_info.png)

### Tables 管理

以结构化表格形式管理 Space 内的表，支持字段描述编辑，支持从数据库批量选入表/视图，支持 AI 一键生成表元数据。

![Space Tables](docs/screenshots/07_space_tables.png)

### Joins 配置

以纯文本形式描述表间关联关系，支持 AI 一键辅助生成 JOIN 规则。

![Space Joins](docs/screenshots/08_space_joins.png)

### Metrics 配置

以纯文本形式定义业务指标口径，支持 AI 一键辅助生成 Metric 规则。

![Space Metrics](docs/screenshots/09_space_metrics.png)

---

## 架构

系统基于四阶段 RAG 链路：

1. **Retrieval** — 路由 Space，召回表/指标上下文；支持 LLM 关键词扩展（强 AND → LLM-OR → bigram-OR 三级降级）
2. **Text-to-SQL** — 基于召回上下文生成 SQL，使用 `sqlglot` AST 校验
3. **Execution** — 只读执行，支持结果截断保护
4. **Insight** — LLM 生成摘要与 Markdown 表格

## 技术栈

- **后端**: Python / FastAPI / SQLite FTS5 / sqlglot
- **前端**: Vue 3 / TypeScript / Vuetify 3 / Vite
- **LLM**: 可插拔 `LLMClient`，默认 Stub；支持 OpenAI-compatible Provider

## 当前能力

- `Database -> Space -> Table` 领域模型，支持 `JoinRule` / `MetricRule`
- SQLite FTS5 全文检索，支持中文 token 发射 + LLM 关键词扩展
- SQL 生成与 `sqlglot` AST 校验（只读 SELECT、列/表白名单、JOIN 结构）
- 多方言支持（sqlite / postgresql / mysql），SQL 方言自动切换
- PostgreSQL schema introspection，批量导入表元数据
- AI 辅助生成：表描述、JOIN 规则、Metric 规则
- 查询 API：`POST /query`；健康检查：`GET /health`

## 运行方式

```bash
# 后端
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev
```

如需启用 PostgreSQL connector：

```bash
pip install -e .[postgres]
```

## 测试

```bash
pytest
```

## LLM 配置

默认不启用真实模型，系统使用 `StubLLMClient`。如需启用 OpenAI-compatible Provider：

```bash
export AGILEQUERY_LLM_PROVIDER=openai-compatible
export AGILEQUERY_LLM_BASE_URL=https://your-provider.example/v1
export AGILEQUERY_LLM_API_KEY=your-api-key
export AGILEQUERY_LLM_MODEL=your-model
export AGILEQUERY_LLM_TIMEOUT_SECONDS=30
```

## 数据库连接配置

默认注册内置 `demo_sqlite` connector。可以通过 JSON 环境变量增加连接引用：

```bash
export AGILEQUERY_DATABASE_CONNECTIONS_JSON='[
  {
    "connection_ref": "pg_sales",
    "dialect": "postgresql",
    "dsn": "postgresql://readonly_user:password@localhost:5432/sales",
    "connect_timeout_seconds": 10,
    "statement_timeout_ms": 30000
  }
]'
```
