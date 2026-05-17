import type { DatabaseMeta, QueryResponse, SpaceMeta } from './types'

export const API_BASE_URL = 'http://localhost:8000'
export const SPACE_ID_PATTERN = /^[a-z0-9_-]+$/

function getErrorMessage(value: unknown): string {
  return value instanceof Error ? value.message : 'Unexpected error'
}

async function parseError(response: Response, fallback: string): Promise<Error> {
  const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null
  const detail = payload?.detail
  if (typeof detail === 'string') {
    return new Error(detail)
  }
  return new Error(fallback)
}

async function request<T>(path: string, init?: RequestInit, fallback = 'Request failed'): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    throw await parseError(response, fallback)
  }
  return (await response.json()) as T
}

export interface CreateDatabasePayload {
  id: string
  name: string
  dialect: string
  description?: string
  dsn?: string
  connect_timeout_seconds?: number
  statement_timeout_ms?: number
}

export async function testConnection(payload: {
  dialect: string
  dsn: string
  connect_timeout_seconds?: number
}): Promise<{ ok: boolean; message: string }> {
  return request(
    '/admin/test-connection',
    { method: 'POST', body: JSON.stringify(payload) },
    'Test connection failed',
  )
}

export interface AiFillTableMetaResult {
  business_name: string
  description: string
  columns: { name: string; description: string }[]
}

export async function aiFillTableMeta(payload: {
  table_name: string
  columns: { name: string; data_type: string }[]
}): Promise<{ ok: boolean; message?: string; data: AiFillTableMetaResult | null }> {
  return request(
    '/admin/ai/fill-table-meta',
    { method: 'POST', body: JSON.stringify(payload) },
    'AI fill failed',
  )
}

export interface AiTableSummary {
  name: string
  columns: { name: string; data_type: string }[]
}

export async function aiFillJoins(
  tables: AiTableSummary[],
): Promise<{ ok: boolean; message?: string; text: string }> {
  return request(
    '/admin/ai/fill-joins',
    { method: 'POST', body: JSON.stringify({ tables }) },
    'AI fill joins failed',
  )
}

export async function aiFillMetrics(
  tables: AiTableSummary[],
): Promise<{ ok: boolean; message?: string; text: string }> {
  return request(
    '/admin/ai/fill-metrics',
    { method: 'POST', body: JSON.stringify({ tables }) },
    'AI fill metrics failed',
  )
}

export async function createDatabase(payload: CreateDatabasePayload): Promise<DatabaseMeta> {
  const data = await request<{ database: DatabaseMeta }>(
    '/admin/databases',
    { method: 'POST', body: JSON.stringify(payload) },
    'Failed to create database',
  )
  return data.database
}

export async function deleteDatabase(databaseId: string): Promise<void> {
  await request<void>(
    `/admin/databases/${databaseId}`,
    { method: 'DELETE' },
    'Failed to delete database',
  )
}

export interface UpdateDatabasePayload {
  name?: string
  dialect?: string
  description?: string
  dsn?: string
  connect_timeout_seconds?: number
  statement_timeout_ms?: number
}

export async function updateDatabase(
  databaseId: string,
  payload: UpdateDatabasePayload,
): Promise<DatabaseMeta> {
  const data = await request<{ database: DatabaseMeta }>(
    `/admin/databases/${databaseId}`,
    { method: 'PUT', body: JSON.stringify(payload) },
    'Failed to update database',
  )
  return data.database
}

export interface DatabaseConnection {
  connection_ref: string
  dialect: string
  dsn: string
  connect_timeout_seconds: number
  statement_timeout_ms: number
}

export async function getDatabaseConnection(databaseId: string): Promise<DatabaseConnection | null> {
  const data = await request<{ connection: DatabaseConnection | null }>(
    `/admin/databases/${databaseId}/connection`,
    undefined,
    'Failed to fetch database connection',
  )
  return data.connection
}

export async function listDatabases(): Promise<DatabaseMeta[]> {
  const data = await request<{ databases: DatabaseMeta[] }>('/admin/databases', undefined, 'Failed to fetch databases')
  return data.databases
}

export async function getSpace(databaseId: string, spaceId: string): Promise<SpaceMeta> {
  const data = await request<{ space: SpaceMeta }>(
    `/admin/databases/${databaseId}/spaces/${spaceId}`,
    undefined,
    'Failed to fetch space',
  )
  return data.space
}

export async function createSpace(
  databaseId: string,
  payload: Pick<SpaceMeta, 'id' | 'name' | 'description' | 'tables' | 'join_rules' | 'metric_rules'>,
): Promise<SpaceMeta> {
  const data = await request<{ space: SpaceMeta }>(
    `/admin/databases/${databaseId}/spaces`,
    { method: 'POST', body: JSON.stringify(payload) },
    'Failed to create space',
  )
  return data.space
}

export async function updateSpace(
  databaseId: string,
  spaceId: string,
  payload: Partial<Pick<SpaceMeta, 'name' | 'description' | 'tables' | 'join_rules' | 'metric_rules' | 'sample_questions'>>,
): Promise<SpaceMeta> {
  const data = await request<{ space: SpaceMeta }>(
    `/admin/databases/${databaseId}/spaces/${spaceId}`,
    { method: 'PATCH', body: JSON.stringify(payload) },
    'Failed to update space',
  )
  return data.space
}

export async function deleteSpace(databaseId: string, spaceId: string): Promise<void> {
  await request<void>(
    `/admin/databases/${databaseId}/spaces/${spaceId}`,
    { method: 'DELETE' },
    'Failed to delete space',
  )
}

export async function syncSpaceSchema(
  databaseId: string,
  spaceId: string,
  schema = 'public',
): Promise<{ tables_synced: number; table_names: string[] }> {
  return request(
    `/admin/databases/${databaseId}/spaces/${spaceId}/sync?schema=${encodeURIComponent(schema)}`,
    { method: 'POST' },
    'Sync failed',
  )
}

export interface IntrospectedColumn {
  name: string
  data_type: string
  description: string
}

export interface IntrospectedObject {
  name: string
  kind: 'table' | 'view'
  columns: IntrospectedColumn[]
}

export async function introspectDatabase(
  databaseId: string,
  schema = 'public',
): Promise<{ schema: string; objects: IntrospectedObject[] }> {
  return request(
    `/admin/databases/${databaseId}/introspect?schema=${encodeURIComponent(schema)}`,
    { method: 'GET' },
    'Introspect failed',
  )
}

export async function submitQuery(databaseId: string, question: string): Promise<QueryResponse> {
  return request<QueryResponse>(
    '/query',
    { method: 'POST', body: JSON.stringify({ database_id: databaseId, question }) },
    'Query failed',
  )
}

export interface LlmConfig {
  provider: string
  base_url: string
  api_key_set: boolean
  model: string
  timeout_seconds: number
}

export interface UpdateLlmConfigPayload {
  provider: string
  base_url: string
  api_key: string
  model: string
  timeout_seconds: number
}

export async function getLlmConfig(): Promise<LlmConfig> {
  return request<LlmConfig>('/admin/llm-config', undefined, 'Failed to fetch LLM config')
}

export async function updateLlmConfig(payload: UpdateLlmConfigPayload): Promise<LlmConfig> {
  return request<LlmConfig>(
    '/admin/llm-config',
    { method: 'PUT', body: JSON.stringify(payload) },
    'Failed to update LLM config',
  )
}

export { getErrorMessage }
