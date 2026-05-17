<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { SPACE_ID_PATTERN, aiFillTableMeta, aiFillJoins, aiFillMetrics } from '@/api/client'
import type { SpaceMeta, TableMeta, ColumnMeta, JoinRuleMeta, MetricRuleMeta } from '@/api/types'
import type { IntrospectedObject } from '@/api/client'
import ImportTablesDialog from '@/components/ImportTablesDialog.vue'
import { getErrorMessage } from '@/api/client'

type Mode = 'create' | 'edit'

const props = defineProps<{
  modelValue: boolean
  mode: Mode
  databaseName: string
  databaseId?: string
  databaseDialect?: string
  initial?: SpaceMeta | null
  isSubmitting?: boolean
  errorMessage?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: SpaceMeta]
}>()

const isOpen = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const activeTab = ref('info')
const idValue = ref('')
const nameValue = ref('')
const descriptionValue = ref('')

type EditableColumn = { name: string; data_type: string; description: string; nullable: boolean; null_check: string }
type EditableTable = {
  name: string
  business_name: string
  description: string
  alias: string
  columns: EditableColumn[]
}

const tablesValue = ref<EditableTable[]>([])
const tableCollapsed = ref<boolean[]>([])
const tableAiLoading = ref<boolean[]>([])
const sampleQuestionsText = ref('')
const joinsText = ref('')
const metricsText = ref('')
const joinsAiLoading = ref(false)
const metricsAiLoading = ref(false)
const aiErrorSnackbar = ref(false)
const aiErrorMessage = ref('')

watch(
  () => [props.modelValue, props.initial, props.mode] as const,
  ([open, initial]) => {
    if (!open) return
    activeTab.value = 'info'
    idValue.value = initial?.id ?? ''
    nameValue.value = initial?.name ?? ''
    descriptionValue.value = initial?.description ?? ''
    sampleQuestionsText.value = (initial?.sample_questions ?? []).join('\n')
    tablesValue.value = (initial?.tables ?? []).map(t => ({
      name: t.name,
      business_name: t.business_name,
      description: t.description,
      alias: t.alias,
      columns: t.columns.map(c => ({ name: c.name, data_type: c.data_type, description: c.description, nullable: c.nullable ?? true, null_check: c.null_check ?? '' })),
    }))
    tableCollapsed.value = tablesValue.value.map(() => false)
    tableAiLoading.value = tablesValue.value.map(() => false)
    joinsText.value = (initial?.join_rules ?? []).length
      ? JSON.stringify(initial!.join_rules, null, 2)
      : ''
    metricsText.value = (initial?.metric_rules ?? []).length
      ? JSON.stringify(initial!.metric_rules, null, 2)
      : ''
  },
  { immediate: true },
)

const idError = computed(() =>
  idValue.value && !SPACE_ID_PATTERN.test(idValue.value.trim())
    ? 'Use lowercase letters, numbers, hyphens, or underscores.'
    : '',
)

const canSubmit = computed(() => {
  if (!nameValue.value.trim()) return false
  if (props.mode === 'create' && (!idValue.value.trim() || idError.value)) return false
  return true
})

function addTable() {
  tablesValue.value.push({ name: '', business_name: '', description: '', alias: '', columns: [] })
  tableCollapsed.value.push(false)
  tableAiLoading.value.push(false)
}

const importDialogOpen = ref(false)

function openImportDialog() {
  if (!props.databaseId) return
  importDialogOpen.value = true
}

function handleImported(objects: IntrospectedObject[]) {
  const existingNames = new Set(tablesValue.value.map(t => t.name.trim()).filter(Boolean))
  for (const obj of objects) {
    if (existingNames.has(obj.name)) continue
    tablesValue.value.push({
        name: obj.name,
        business_name: obj.name,
        description: obj.kind === 'view' ? `View ${obj.name}` : '',
        alias: makeAlias(obj.name),
        columns: obj.columns.map(c => ({
          name: c.name,
          data_type: c.data_type,
          description: c.description,
          nullable: true,
          null_check: '',
        })),
      })
      tableCollapsed.value.push(false)
      tableAiLoading.value.push(false)
      existingNames.add(obj.name)
  }
  activeTab.value = 'tables'
}

function makeAlias(tableName: string): string {
  const parts = tableName.split('_').filter(Boolean)
  if (parts.length === 1) return parts[0].slice(0, 2).toLowerCase()
  return parts.map(p => p[0]).join('').toLowerCase()
}

function removeTable(idx: number) {
  tablesValue.value.splice(idx, 1)
  tableCollapsed.value.splice(idx, 1)
  tableAiLoading.value.splice(idx, 1)
}

function addColumn(tableIdx: number) {
  tablesValue.value[tableIdx].columns.push({ name: '', data_type: '', description: '', nullable: true, null_check: '' })
}

function removeColumn(tableIdx: number, colIdx: number) {
  tablesValue.value[tableIdx].columns.splice(colIdx, 1)
}

function tryParseJson<T>(src: string): T[] {
  const s = src.trim()
  if (!s || s === '[]') return []
  try {
    const parsed = JSON.parse(s) as unknown
    return Array.isArray(parsed) ? (parsed as T[]) : []
  } catch {
    return []
  }
}

async function aiFillTable(ti: number) {
  const table = tablesValue.value[ti]
  tableAiLoading.value[ti] = true
  try {
    const result = await aiFillTableMeta({
      table_name: table.name,
      columns: table.columns.map(c => ({ name: c.name, data_type: c.data_type })),
    })
    if (result.ok && result.data) {
      table.business_name = result.data.business_name || table.business_name
      table.description = result.data.description || table.description
      for (const col of table.columns) {
        const match = result.data.columns.find(c => c.name === col.name)
        if (match?.description) col.description = match.description
      }
      tableCollapsed.value[ti] = false
    }
  } finally {
    tableAiLoading.value[ti] = false
  }
}

async function aiFillJoinsText() {
  joinsAiLoading.value = true
  try {
    const tables = tablesValue.value
      .filter(t => t.name.trim())
      .map(t => ({ name: t.name, columns: t.columns.map(c => ({ name: c.name, data_type: c.data_type })) }))
    const result = await aiFillJoins(tables)
    if (result.ok && result.text) {
      joinsText.value = result.text
    } else if (!result.ok) {
      aiErrorMessage.value = result.message ?? 'AI 生成失败'
      aiErrorSnackbar.value = true
    }
  } catch (e) {
    aiErrorMessage.value = getErrorMessage(e)
    aiErrorSnackbar.value = true
  } finally {
    joinsAiLoading.value = false
  }
}

async function aiFillMetricsText() {
  metricsAiLoading.value = true
  try {
    const tables = tablesValue.value
      .filter(t => t.name.trim())
      .map(t => ({ name: t.name, columns: t.columns.map(c => ({ name: c.name, data_type: c.data_type })) }))
    const result = await aiFillMetrics(tables)
    if (result.ok && result.text) {
      metricsText.value = result.text
    } else if (!result.ok) {
      aiErrorMessage.value = result.message ?? 'AI 生成失败'
      aiErrorSnackbar.value = true
    }
  } catch (e) {
    aiErrorMessage.value = getErrorMessage(e)
    aiErrorSnackbar.value = true
  } finally {
    metricsAiLoading.value = false
  }
}

function handleSubmit() {
  if (!canSubmit.value) return

  const joinsList = tryParseJson<JoinRuleMeta>(joinsText.value)
  const metricsList = tryParseJson<MetricRuleMeta>(metricsText.value)

  const tables: TableMeta[] = tablesValue.value
    .filter(t => t.name.trim())
    .map(t => ({
      name: t.name.trim(),
      business_name: t.business_name.trim(),
      description: t.description.trim(),
      alias: t.alias.trim(),
      columns: t.columns.filter(c => c.name.trim()).map<ColumnMeta>(c => ({
        name: c.name.trim(),
        data_type: c.data_type.trim(),
        description: c.description.trim(),
        nullable: c.nullable,
        null_check: c.null_check.trim(),
      })),
    }))

  emit('submit', {
    id: idValue.value.trim(),
    name: nameValue.value.trim(),
    description: descriptionValue.value.trim(),
    sample_questions: sampleQuestionsText.value.split('\n').map(s => s.trim()).filter(Boolean),
    tables,
    join_rules: joinsList,
    metric_rules: metricsList,
  })
}
</script>

<template>
  <v-dialog v-model="isOpen" max-width="1060" :persistent="isSubmitting" scrollable>
    <v-card rounded="xl">
      <v-card-title class="dialog-title">
        <v-icon :icon="mode === 'create' ? 'mdi-folder-plus' : 'mdi-folder-edit'" color="primary" class="mr-2" />
        {{ mode === 'create' ? 'New Space' : 'Edit Space' }}
        <v-chip class="ml-2" size="small" variant="tonal">{{ databaseName }}</v-chip>
      </v-card-title>

      <v-tabs v-model="activeTab" color="primary" density="compact" class="px-4">
        <v-tab value="info" prepend-icon="mdi-information">Info</v-tab>
        <v-tab value="tables" prepend-icon="mdi-table">Tables ({{ tablesValue.length }})</v-tab>
        <v-tab value="joins" prepend-icon="mdi-link-variant">Joins</v-tab>
        <v-tab value="metrics" prepend-icon="mdi-chart-line">Metrics</v-tab>
      </v-tabs>

      <v-divider />

      <v-card-text class="dialog-body">
        <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-4" rounded="lg">
          {{ errorMessage }}
        </v-alert>

        <v-window v-model="activeTab">
          <v-window-item value="info">
            <v-text-field
              v-model="idValue"
              :disabled="mode === 'edit'"
              label="Space ID"
              hint="lowercase letters, numbers, hyphens, underscores"
              persistent-hint
              variant="outlined"
              density="comfortable"
              prepend-inner-icon="mdi-identifier"
              :error-messages="idError"
              class="mb-4"
            />
            <v-text-field
              v-model="nameValue"
              label="Display Name"
              variant="outlined"
              density="comfortable"
              prepend-inner-icon="mdi-folder"
              class="mb-4"
            />
            <v-textarea
              v-model="descriptionValue"
              label="Description"
              variant="outlined"
              density="comfortable"
              rows="3"
              prepend-inner-icon="mdi-text-box-outline"
              class="mb-4"
            />
            <v-textarea
              v-model="sampleQuestionsText"
              label="Sample Questions"
              hint="每行一个示例问题，用于辅助问题路由到此 Space"
              persistent-hint
              variant="outlined"
              density="comfortable"
              rows="4"
              prepend-inner-icon="mdi-comment-question-outline"
              placeholder="华东区上季度销售额是多少？&#10;哪个客户的订单量最多？&#10;本月各产品的退货率如何？"
            />
          </v-window-item>

          <v-window-item value="tables">
            <div class="d-flex align-center mb-3">
              <p class="text-body-2 text-medium-emphasis flex-grow-1">Define physical tables and their columns.</p>
              <v-btn
                v-if="databaseId"
                color="primary"
                variant="outlined"
                size="small"
                prepend-icon="mdi-database-import"
                rounded="lg"
                class="mr-2"
                @click="openImportDialog"
              >
                从数据库导入
              </v-btn>
              <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-plus" rounded="lg" @click="addTable">
                Add Table
              </v-btn>
            </div>

            <div v-if="tablesValue.length === 0" class="empty-tables">
              <v-icon icon="mdi-table-plus" size="36" color="grey-lighten-1" />
              <p class="text-body-2 text-medium-emphasis mt-2">No tables. Click "Add Table" to start.</p>
            </div>

            <div v-for="(table, ti) in tablesValue" :key="ti" class="table-block mb-4">
              <div class="table-block-header" @click="tableCollapsed[ti] = !tableCollapsed[ti]">
                <v-icon icon="mdi-table" size="16" color="primary" />
                <span class="table-block-title">Table {{ ti + 1 }}{{ table.name ? ': ' + table.name : '' }}</span>
                <v-btn
                  :icon="tableAiLoading[ti] ? 'mdi-loading' : 'mdi-auto-fix'"
                  variant="text"
                  size="small"
                  density="compact"
                  color="primary"
                  :loading="tableAiLoading[ti]"
                  :disabled="!table.name"
                  class="ml-auto"
                  title="AI 辅助填写"
                  @click.stop="aiFillTable(ti)"
                />
                <v-btn
                  icon="mdi-delete"
                  variant="text"
                  size="small"
                  density="compact"
                  color="error"
                  @click.stop="removeTable(ti)"
                />
                <v-icon
                  :icon="tableCollapsed[ti] ? 'mdi-chevron-down' : 'mdi-chevron-up'"
                  size="18"
                  color="grey"
                />
              </div>
              <v-expand-transition>
                <div v-show="!tableCollapsed[ti]" class="table-block-body">
                <v-row dense>
                  <v-col cols="6">
                    <v-text-field v-model="table.name" label="Table name" density="compact" variant="outlined" hide-details />
                  </v-col>
                  <v-col cols="6">
                    <v-text-field v-model="table.alias" label="Alias" density="compact" variant="outlined" hide-details />
                  </v-col>
                  <v-col cols="6">
                    <v-text-field v-model="table.business_name" label="Business name" density="compact" variant="outlined" hide-details />
                  </v-col>
                  <v-col cols="6">
                    <v-text-field v-model="table.description" label="Description" density="compact" variant="outlined" hide-details />
                  </v-col>
                </v-row>

                <div class="columns-area mt-3">
                  <div class="d-flex align-center mb-2">
                    <p class="text-caption text-medium-emphasis flex-grow-1">Columns</p>
                    <v-btn variant="text" size="x-small" prepend-icon="mdi-plus" color="primary" @click="addColumn(ti)">Add</v-btn>
                  </div>
                  <div v-for="(col, ci) in table.columns" :key="ci" class="column-block mb-2">
                    <div class="column-row-top">
                      <v-text-field v-model="col.name" label="Name" density="compact" variant="outlined" hide-details class="col-field" />
                      <v-text-field v-model="col.data_type" label="Type" density="compact" variant="outlined" hide-details class="col-field" />
                      <v-text-field v-model="col.description" label="Description" density="compact" variant="outlined" hide-details class="col-field-wide" />
                      <v-checkbox
                        v-model="col.nullable"
                        label="可空"
                        density="compact"
                        hide-details
                        color="primary"
                        class="col-nullable"
                      />
                    </div>
                    <div class="column-row-bottom">
                      <v-text-field
                        v-model="col.null_check"
                        label="空值判定"
                        placeholder="e.g. IS NULL  /  = ''  /  = 0  /  IS NULL OR = ''"
                        density="compact"
                        variant="outlined"
                        hide-details
                        class="null-check-field"
                        prepend-inner-icon="mdi-null"
                      />
                    </div>
                    <div class="column-row-actions">
                      <v-btn variant="text" size="x-small" color="error" prepend-icon="mdi-delete-outline" @click="removeColumn(ti, ci)">删除</v-btn>
                    </div>
                  </div>
                  <p v-if="table.columns.length === 0" class="text-caption text-medium-emphasis">No columns yet.</p>
                </div>
              </div>
              </v-expand-transition>
            </div>
          </v-window-item>

          <v-window-item value="joins">
            <div class="d-flex align-center mb-3">
              <p class="text-body-2 text-medium-emphasis flex-grow-1">
                描述表之间的关联关系，供 AI 生成 SQL 时参考。可自由书写，例如："orders 表通过 customer_id 关联 customers 表"。
              </p>
              <v-btn
                color="primary"
                variant="tonal"
                size="small"
                prepend-icon="mdi-auto-fix"
                rounded="lg"
                :loading="joinsAiLoading"
                :disabled="tablesValue.filter(t => t.name.trim()).length === 0"
                @click="aiFillJoinsText"
              >
                AI 辅助生成
              </v-btn>
            </div>
            <v-textarea
              v-model="joinsText"
              variant="outlined"
              rows="14"
              class="mono-textarea"
              placeholder="orders 通过 customer_id 关联 customers&#10;order_items 通过 order_id 关联 orders&#10;..."
            />
          </v-window-item>

          <v-window-item value="metrics">
            <div class="d-flex align-center mb-3">
              <p class="text-body-2 text-medium-emphasis flex-grow-1">
                描述业务指标的计算口径，供 AI 生成 SQL 时参考。可自由书写，例如："总销售额 = SUM(amount)，仅统计 status='paid' 的订单"。
              </p>
              <v-btn
                color="primary"
                variant="tonal"
                size="small"
                prepend-icon="mdi-auto-fix"
                rounded="lg"
                :loading="metricsAiLoading"
                :disabled="tablesValue.filter(t => t.name.trim()).length === 0"
                @click="aiFillMetricsText"
              >
                AI 辅助生成
              </v-btn>
            </div>
            <v-textarea
              v-model="metricsText"
              variant="outlined"
              rows="14"
              class="mono-textarea"
              placeholder="总销售额 = SUM(amount)，仅统计 status='paid' 的订单&#10;客单价 = 总销售额 / 下单客户数&#10;..."
            />
          </v-window-item>
        </v-window>
      </v-card-text>

      <v-divider />

      <v-card-actions class="px-6 py-4">
        <v-btn variant="text" @click="isOpen = false">Cancel</v-btn>
        <v-spacer />
        <v-btn color="primary" rounded="lg" :disabled="!canSubmit" :loading="isSubmitting" @click="handleSubmit">
          {{ mode === 'create' ? 'Create Space' : 'Save Changes' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <ImportTablesDialog
    v-if="databaseId"
    v-model="importDialogOpen"
    :database-id="databaseId"
    :database-dialect="databaseDialect ?? ''"
    :existing-table-names="tablesValue.map(t => t.name).filter(Boolean)"
    @import="handleImported"
  />

  <v-snackbar v-model="aiErrorSnackbar" color="error" timeout="4000" location="top">
    {{ aiErrorMessage }}
    <template #actions>
      <v-btn variant="text" @click="aiErrorSnackbar = false">关闭</v-btn>
    </template>
  </v-snackbar>
</template>

<style scoped>
.dialog-title {
  display: flex;
  align-items: center;
  font-size: 17px;
  font-weight: 700;
  padding: 20px 24px 12px;
}

.dialog-body {
  padding: 20px 24px;
  max-height: 60vh;
}

.empty-tables {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px;
  border: 1px dashed rgba(0,0,0,0.15);
  border-radius: 12px;
  text-align: center;
}

.table-block {
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 12px;
  overflow: hidden;
}

.table-block-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(var(--v-theme-primary), 0.04);
  border-bottom: 1px solid rgba(0,0,0,0.07);
  cursor: pointer;
  user-select: none;
}

.table-block-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.table-block-body {
  padding: 14px;
}

.columns-area {
  background: #f9fafb;
  border-radius: 8px;
  padding: 10px;
}

.column-block {
  border: 1px solid rgba(0,0,0,0.07);
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.column-row-top {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px 6px 8px;
}

.column-row-bottom {
  padding: 0 8px 6px 8px;
}

.column-row-actions {
  display: flex;
  justify-content: flex-end;
  padding: 0 6px 4px 8px;
  border-top: 1px solid rgba(0,0,0,0.05);
}

.col-field { flex: 1; }
.col-field-wide { flex: 2; }
.col-nullable { flex: 0 0 auto; }
.null-check-field { width: 100%; }

.mono-textarea :deep(textarea) {
  font-family: 'Fira Code', 'JetBrains Mono', monospace;
  font-size: 13px;
  line-height: 1.6;
}
</style>
