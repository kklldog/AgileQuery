export interface ColumnMeta {
  name: string
  data_type: string
  description: string
  nullable?: boolean
  null_check?: string
}

export interface TableMeta {
  name: string
  business_name: string
  description: string
  alias: string
  columns: ColumnMeta[]
}

export interface JoinRuleMeta {
  id: string
  description: string
  left_table: string
  right_table: string
  condition: string
  guidance: string
  examples: string[]
}

export interface MetricRuleMeta {
  id: string
  name: string
  description: string
  expression: string
  source_table: string
  output_alias: string
  synonyms: string[]
}

export interface SpaceMeta {
  id: string
  name: string
  description: string
  sample_questions: string[]
  tables: TableMeta[]
  join_rules: JoinRuleMeta[]
  metric_rules: MetricRuleMeta[]
  joins_text: string
  metrics_text: string
}

export interface DatabaseMeta {
  id: string
  name: string
  dialect: string
  description: string
  connection_ref: string
  spaces: SpaceMeta[]
}

export interface LLMTrace {
  stage: string
  prompt: string
  response: string
}

export interface QueryResponse {
  database_id: string
  space_id: string
  sql: string
  status: string
  summary: string
  table_markdown: string
  row_count: number
  is_truncated: boolean
  diagnostics: string[]
  llm_traces: LLMTrace[]
}

export interface PromptEntry {
  value: string
  label: string
  description: string
  is_default: boolean
}

export type PromptsConfig = Record<string, PromptEntry>
