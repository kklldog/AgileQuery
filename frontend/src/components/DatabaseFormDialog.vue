<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { SPACE_ID_PATTERN, testConnection } from '@/api/client'
import type { CreateDatabasePayload, DatabaseConnection, UpdateDatabasePayload } from '@/api/client'
import type { DatabaseMeta } from '@/api/types'

type Mode = 'create' | 'edit'

const props = defineProps<{
  modelValue: boolean
  mode?: Mode
  isSubmitting?: boolean
  errorMessage?: string
  initialDatabase?: DatabaseMeta | null
  initialConnection?: DatabaseConnection | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: CreateDatabasePayload]
  update: [databaseId: string, payload: UpdateDatabasePayload]
}>()

const isOpen = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const mode = computed<Mode>(() => props.mode ?? 'create')
const isEdit = computed(() => mode.value === 'edit')

const idValue = ref('')
const nameValue = ref('')
const dialectValue = ref('postgresql')
const descriptionValue = ref('')
const hostValue = ref('')
const portValue = ref('5432')
const dbNameValue = ref('')
const userValue = ref('')
const passwordValue = ref('')
const connectTimeoutValue = ref(10)
const statementTimeoutValue = ref(30000)

const DEFAULT_PORT: Record<string, string> = {
  postgresql: '5432',
  sqlserver: '1433',
}

function parsePostgresDsn(dsn: string) {
  const match = /^postgres(?:ql)?:\/\/(?:([^:@/]+)(?::([^@/]*))?@)?([^:/]+)(?::(\d+))?\/([^?]+)/.exec(dsn)
  if (!match) return null
  return {
    user: decodeURIComponent(match[1] ?? ''),
    password: decodeURIComponent(match[2] ?? ''),
    host: match[3] ?? '',
    port: match[4] ?? '5432',
    database: match[5] ?? '',
  }
}

function parseOdbcDsn(dsn: string) {
  const parts = dsn.split(';').map(p => p.trim()).filter(Boolean)
  const map: Record<string, string> = {}
  for (const p of parts) {
    const eq = p.indexOf('=')
    if (eq <= 0) continue
    map[p.slice(0, eq).trim().toUpperCase()] = p.slice(eq + 1).trim()
  }
  const server = map.SERVER ?? ''
  const [host, port] = server.includes(',') ? server.split(',') : [server, '1433']
  return {
    user: map.UID ?? '',
    password: map.PWD ?? '',
    host: host ?? '',
    port: port ?? '1433',
    database: map.DATABASE ?? '',
  }
}

function resetToCreateDefaults() {
  idValue.value = ''
  nameValue.value = ''
  dialectValue.value = 'postgresql'
  descriptionValue.value = ''
  hostValue.value = ''
  portValue.value = '5432'
  dbNameValue.value = ''
  userValue.value = ''
  passwordValue.value = ''
  connectTimeoutValue.value = 10
  statementTimeoutValue.value = 30000
}

function applyEditDefaults() {
  const db = props.initialDatabase
  const conn = props.initialConnection
  idValue.value = db?.id ?? ''
  nameValue.value = db?.name ?? ''
  dialectValue.value = db?.dialect === 'tsql' ? 'sqlserver' : (db?.dialect ?? 'postgresql')
  descriptionValue.value = db?.description ?? ''
  connectTimeoutValue.value = conn?.connect_timeout_seconds ?? 10
  statementTimeoutValue.value = conn?.statement_timeout_ms ?? 30000

  if (!conn?.dsn) {
    hostValue.value = ''
    portValue.value = DEFAULT_PORT[dialectValue.value] ?? ''
    dbNameValue.value = ''
    userValue.value = ''
    passwordValue.value = ''
    return
  }

  const parsed = dialectValue.value === 'sqlserver'
    ? parseOdbcDsn(conn.dsn)
    : parsePostgresDsn(conn.dsn)
  if (parsed) {
    hostValue.value = parsed.host
    portValue.value = parsed.port
    dbNameValue.value = parsed.database
    userValue.value = parsed.user
    passwordValue.value = parsed.password
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    if (isEdit.value) {
      applyEditDefaults()
    } else {
      resetToCreateDefaults()
    }
  },
)

watch(dialectValue, (next) => {
  if (isEdit.value) return
  const dp = DEFAULT_PORT[next]
  if (dp) portValue.value = dp
})

const idError = computed(() =>
  idValue.value && !SPACE_ID_PATTERN.test(idValue.value.trim())
    ? '只允许小写字母、数字、连字符、下划线'
    : '',
)

const isPostgres = computed(() =>
  dialectValue.value === 'postgresql' || dialectValue.value === 'postgres',
)

const isSqlServer = computed(() => dialectValue.value === 'sqlserver')

const needsConnection = computed(() => isPostgres.value || isSqlServer.value)

const builtDsn = computed(() => {
  if (!needsConnection.value) return ''
  const h = hostValue.value.trim() || 'localhost'
  const p = portValue.value.trim() || (isSqlServer.value ? '1433' : '5432')
  const db = dbNameValue.value.trim()
  const u = userValue.value.trim()
  const pw = passwordValue.value
  if (!u || !db) return ''
  if (isSqlServer.value) {
    return [
      'DRIVER={ODBC Driver 18 for SQL Server}',
      `SERVER=${h},${p}`,
      `DATABASE=${db}`,
      `UID=${u}`,
      `PWD=${pw}`,
      'TrustServerCertificate=yes',
    ].join(';')
  }
  const auth = pw ? `${encodeURIComponent(u)}:${encodeURIComponent(pw)}` : encodeURIComponent(u)
  return `postgresql://${auth}@${h}:${p}/${db}`
})

const maskedDsn = computed(() => {
  if (!builtDsn.value) return ''
  if (isSqlServer.value) return builtDsn.value.replace(/PWD=[^;]*/i, 'PWD=****')
  return builtDsn.value.replace(/:([^:@]+)@/, ':****@')
})

const canSubmit = computed(() => {
  if (!isEdit.value && (!idValue.value.trim() || idError.value)) return false
  if (!nameValue.value.trim()) return false
  if (needsConnection.value && !builtDsn.value) return false
  return true
})

const title = computed(() => (isEdit.value ? '编辑数据库' : '添加数据库'))
const submitLabel = computed(() => (isEdit.value ? '保存修改' : '创建数据库'))
const titleIcon = computed(() => (isEdit.value ? 'mdi-database-edit' : 'mdi-database-plus'))

const testLoading = ref(false)
const testResult = ref<{ ok: boolean; message: string } | null>(null)

watch([hostValue, portValue, dbNameValue, userValue, passwordValue, dialectValue], () => {
  testResult.value = null
})

async function handleTestConnection() {
  if (!builtDsn.value) return
  testLoading.value = true
  testResult.value = null
  try {
    testResult.value = await testConnection({
      dialect: dialectValue.value,
      dsn: builtDsn.value,
      connect_timeout_seconds: connectTimeoutValue.value,
    })
  } catch {
    testResult.value = { ok: false, message: '请求失败，请检查服务端是否正常' }
  } finally {
    testLoading.value = false
  }
}

function handleSubmit() {
  if (!canSubmit.value) return
  if (isEdit.value) {
    const payload: UpdateDatabasePayload = {
      name: nameValue.value.trim(),
      dialect: dialectValue.value,
      description: descriptionValue.value.trim(),
    }
    if (needsConnection.value) {
      payload.dsn = builtDsn.value
      payload.connect_timeout_seconds = connectTimeoutValue.value
      payload.statement_timeout_ms = statementTimeoutValue.value
    }
    emit('update', idValue.value.trim(), payload)
  } else {
    const payload: CreateDatabasePayload = {
      id: idValue.value.trim(),
      name: nameValue.value.trim(),
      dialect: dialectValue.value,
      description: descriptionValue.value.trim(),
    }
    if (needsConnection.value) {
      payload.dsn = builtDsn.value
      payload.connect_timeout_seconds = connectTimeoutValue.value
      payload.statement_timeout_ms = statementTimeoutValue.value
    }
    emit('submit', payload)
  }
}
</script>

<template>
  <v-dialog v-model="isOpen" max-width="580" :persistent="isSubmitting" scrollable>
    <v-card rounded="xl">
      <v-card-title class="db-dialog-title">
        <v-icon :icon="titleIcon" color="primary" class="mr-2" />
        {{ title }}
      </v-card-title>

      <v-divider />

      <v-card-text class="db-dialog-body">
        <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-4" rounded="lg">
          {{ errorMessage }}
        </v-alert>

        <v-text-field
          v-model="idValue"
          label="数据库 ID"
          hint="小写字母、数字、连字符、下划线"
          persistent-hint
          variant="outlined"
          density="comfortable"
          prepend-inner-icon="mdi-identifier"
          :error-messages="idError"
          :disabled="isEdit"
          class="mb-3"
        />

        <v-text-field
          v-model="nameValue"
          label="显示名称"
          variant="outlined"
          density="comfortable"
          prepend-inner-icon="mdi-database"
          class="mb-3"
        />

        <v-select
          v-model="dialectValue"
          label="数据库类型"
          variant="outlined"
          density="comfortable"
          prepend-inner-icon="mdi-database-cog"
          :items="[
            { title: 'PostgreSQL', value: 'postgresql' },
            { title: 'SQL Server', value: 'sqlserver' },
            { title: 'SQLite Demo（内置演示）', value: 'sqlite-demo' },
          ]"
          class="mb-3"
        />

        <v-textarea
          v-model="descriptionValue"
          label="描述（可选）"
          variant="outlined"
          density="comfortable"
          rows="2"
          class="mb-4"
        />

        <template v-if="needsConnection">
          <v-divider class="mb-4">
            <span class="text-caption text-medium-emphasis px-2">连接信息</span>
          </v-divider>

          <v-row dense class="mb-1">
            <v-col cols="8">
              <v-text-field
                v-model="hostValue"
                label="Host"
                placeholder="localhost"
                variant="outlined"
                density="comfortable"
                prepend-inner-icon="mdi-server"
                hide-details
              />
            </v-col>
            <v-col cols="4">
              <v-text-field
                v-model="portValue"
                label="Port"
                :placeholder="isSqlServer ? '1433' : '5432'"
                variant="outlined"
                density="comfortable"
                hide-details
              />
            </v-col>
          </v-row>

          <v-text-field
            v-model="dbNameValue"
            label="数据库名"
            variant="outlined"
            density="comfortable"
            prepend-inner-icon="mdi-database-outline"
            class="mt-3"
            hide-details
          />

          <v-row dense class="mt-3 mb-1">
            <v-col cols="6">
              <v-text-field
                v-model="userValue"
                label="用户名"
                variant="outlined"
                density="comfortable"
                prepend-inner-icon="mdi-account"
                hide-details
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model="passwordValue"
                label="密码"
                type="password"
                variant="outlined"
                density="comfortable"
                prepend-inner-icon="mdi-lock"
                hide-details
              />
            </v-col>
          </v-row>

          <v-expand-transition>
            <div v-if="builtDsn" class="dsn-preview mt-3">
              <span class="text-caption text-medium-emphasis mr-1">DSN：</span>
              <code class="text-caption">{{ maskedDsn }}</code>
            </div>
          </v-expand-transition>

          <div class="mt-3 d-flex align-center gap-3">
            <v-btn
              variant="tonal"
              rounded="lg"
              density="comfortable"
              prepend-icon="mdi-connection"
              :loading="testLoading"
              :disabled="!builtDsn"
              @click="handleTestConnection"
            >
              测试连接
            </v-btn>
            <v-fade-transition>
              <span v-if="testResult" :class="testResult.ok ? 'test-ok' : 'test-fail'">
                <v-icon :icon="testResult.ok ? 'mdi-check-circle' : 'mdi-alert-circle'" size="16" class="mr-1" />
                {{ testResult.message }}
              </span>
            </v-fade-transition>
          </div>

          <v-row dense class="mt-3">
            <v-col cols="6">
              <v-text-field
                v-model.number="connectTimeoutValue"
                label="连接超时（秒）"
                type="number"
                variant="outlined"
                density="comfortable"
                hide-details
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="statementTimeoutValue"
                label="查询超时（毫秒）"
                type="number"
                variant="outlined"
                density="comfortable"
                hide-details
              />
            </v-col>
          </v-row>
        </template>
      </v-card-text>

      <v-divider />

      <v-card-actions class="px-6 py-4">
        <v-btn variant="text" @click="isOpen = false">取消</v-btn>
        <v-spacer />
        <v-btn
          color="primary"
          rounded="lg"
          :disabled="!canSubmit"
          :loading="isSubmitting"
          @click="handleSubmit"
        >
          {{ submitLabel }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.db-dialog-title {
  display: flex;
  align-items: center;
  font-size: 17px;
  font-weight: 700;
  padding: 20px 24px 16px;
}

.db-dialog-body {
  padding: 20px 24px;
  max-height: 70vh;
}

.dsn-preview {
  background: rgba(0, 0, 0, 0.04);
  border-radius: 8px;
  padding: 8px 12px;
  word-break: break-all;
}

.test-ok {
  display: inline-flex;
  align-items: center;
  font-size: 13px;
  font-weight: 500;
  color: #059669;
}

.test-fail {
  display: inline-flex;
  align-items: center;
  font-size: 13px;
  font-weight: 500;
  color: #dc2626;
}
</style>
