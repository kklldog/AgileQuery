from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ColumnMeta:
    name: str
    data_type: str
    description: str


@dataclass(frozen=True)
class TableMeta:
    name: str
    business_name: str
    description: str
    alias: str
    columns: list[ColumnMeta] = field(default_factory=list)


@dataclass(frozen=True)
class JoinRuleMeta:
    id: str
    description: str
    left_table: str = ""
    right_table: str = ""
    condition: str = ""
    guidance: str = ""
    examples: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MetricRuleMeta:
    id: str
    name: str
    description: str
    expression: str
    source_table: str
    output_alias: str
    synonyms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SpaceMeta:
    id: str
    name: str
    description: str
    sample_questions: list[str] = field(default_factory=list)
    tables: list[TableMeta] = field(default_factory=list)
    join_rules: list[JoinRuleMeta] = field(default_factory=list)
    metric_rules: list[MetricRuleMeta] = field(default_factory=list)


@dataclass(frozen=True)
class DatabaseMeta:
    id: str
    name: str
    dialect: str
    description: str
    connection_ref: str = ""
    spaces: list[SpaceMeta] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievedContext:
    database: DatabaseMeta
    space: SpaceMeta
    tables: list[TableMeta]
    keywords: list[str]
    join_rules: list[JoinRuleMeta] = field(default_factory=list)
    metric_rules: list[MetricRuleMeta] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidatedSql:
    sql: str
    diagnostics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionResult:
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    is_truncated: bool
    status: str
    diagnostics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InsightResult:
    summary: str
    table_markdown: str
    diagnostics: list[str] = field(default_factory=list)
