<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDatabasesStore } from '@/stores/databases'
import { submitQuery, createSpace, updateSpace, deleteSpace, getErrorMessage } from '@/api/client'
import type { SpaceMeta, QueryResponse } from '@/api/types'
import SpaceFormDialog from '@/components/SpaceFormDialog.vue'

const props = defineProps<{ databaseId: string }>()

const store = useDatabasesStore()

const question = ref('')
const queryLoading = ref(false)
const queryResult = ref<QueryResponse | null>(null)
const queryError = ref('')
const dialogOpen = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const dialogInitial = ref<SpaceMeta | null>(null)
const dialogSubmitting = ref(false)
const dialogError = ref('')
const spaceSuccess = ref('')

const deleteConfirmId = ref<string | null>(null)
const deleteConfirmName = ref('')
const deleteConfirmOpen = computed({
  get: () => deleteConfirmId.value !== null,
  set: (v: boolean) => { if (!v) deleteConfirmId.value = null },
})
const deleteLoading = ref(false)
const deleteError = ref('')

const currentDatabase = computed(() => store.findDatabase(props.databaseId))
const spaces = computed(() => currentDatabase.value?.spaces ?? [])

watch(() => props.databaseId, () => {
  queryResult.value = null
  queryError.value = ''
  spaceSuccess.value = ''
})

async function onSubmitQuery() {
  if (!question.value.trim()) return
  queryLoading.value = true
  queryError.value = ''
  queryResult.value = null
  try {
    queryResult.value = await submitQuery(props.databaseId, question.value)
  } catch (e: unknown) {
    queryError.value = getErrorMessage(e)
  } finally {
    queryLoading.value = false
  }
}

function openCreate() {
  dialogMode.value = 'create'
  dialogInitial.value = null
  dialogError.value = ''
  dialogOpen.value = true
}

function openEdit(space: SpaceMeta) {
  dialogMode.value = 'edit'
  dialogInitial.value = space
  dialogError.value = ''
  dialogOpen.value = true
}

async function onDialogSubmit(payload: {
  id: string
  name: string
  description: string
  tables: SpaceMeta['tables']
  join_rules: SpaceMeta['join_rules']
  metric_rules: SpaceMeta['metric_rules']
}) {
  dialogSubmitting.value = true
  dialogError.value = ''
  try {
    if (dialogMode.value === 'create') {
      await createSpace(props.databaseId, payload)
      spaceSuccess.value = `Space "${payload.name}" 已创建。`
    } else {
      await updateSpace(props.databaseId, payload.id, {
        name: payload.name,
        description: payload.description,
        tables: payload.tables,
        join_rules: payload.join_rules,
        metric_rules: payload.metric_rules,
      })
      spaceSuccess.value = `Space "${payload.name}" 已更新。`
    }
    await store.refresh()
    dialogOpen.value = false
  } catch (e: unknown) {
    dialogError.value = getErrorMessage(e)
  } finally {
    dialogSubmitting.value = false
  }
}

function goToSpace(space: SpaceMeta) {
  openEdit(space)
}

function openDeleteConfirm(space: SpaceMeta) {
  deleteConfirmId.value = space.id
  deleteConfirmName.value = space.name
  deleteError.value = ''
}

async function onDeleteSpace() {
  if (!deleteConfirmId.value) return
  deleteLoading.value = true
  deleteError.value = ''
  try {
    await deleteSpace(props.databaseId, deleteConfirmId.value)
    spaceSuccess.value = `Space "${deleteConfirmName.value}" 已删除。`
    await store.refresh()
    deleteConfirmId.value = null
  } catch (e: unknown) {
    deleteError.value = getErrorMessage(e)
  } finally {
    deleteLoading.value = false
  }
}

const FALLBACK_PROMPTS = [
  '上季度华东区销售额是多少？',
  '各产品线的销售额排名如何？',
  '最近30天新增用户数是多少？',
]

function fillPromptIdea() {
  const allQuestions = spaces.value.flatMap(s => s.sample_questions).filter(Boolean)
  const pool = allQuestions.length > 0 ? allQuestions : FALLBACK_PROMPTS
  const pick = pool[Math.floor(Math.random() * pool.length)]
  question.value = pick
}
</script>

<template>
  <div class="page">
    <!-- Query Card -->
    <div class="chat-card">
      <div class="card-header">
        <div class="header-icon">
          <v-icon icon="mdi-database" color="primary" size="22" />
        </div>
        <div class="header-text">
          <h1 class="card-title">{{ currentDatabase?.name ?? databaseId }}</h1>
          <p class="card-sub">Ask anything about this database</p>
        </div>
      </div>

      <div class="textarea-wrap">
        <v-textarea
          v-model="question"
          placeholder="例如：请提供上季度华东区销售数据的详细趋势分析。"
          rows="3"
          variant="outlined"
          hide-details
          rounded="lg"
          bg-color="white"
          @keydown.ctrl.enter="onSubmitQuery"
        />
        <v-btn
          size="small"
          variant="tonal"
          rounded="lg"
          class="prompt-ideas-btn"
          prepend-icon="mdi-lightbulb-outline"
          @click="fillPromptIdea"
        >
          Prompt Ideas
        </v-btn>
      </div>

      <div class="submit-row">
        <span class="hint">Ctrl + Enter</span>
        <v-btn
          color="primary"
          rounded="lg"
          :loading="queryLoading"
          :disabled="!question.trim()"
          prepend-icon="mdi-send"
          elevation="0"
          @click="onSubmitQuery"
        >
          Generate
        </v-btn>
      </div>

      <v-alert v-if="queryError" type="error" variant="tonal" closable rounded="lg" class="mt-1" @click:close="queryError = ''">
        {{ queryError }}
      </v-alert>

      <template v-if="queryResult">
        <div class="result-block">
          <p class="result-summary">{{ queryResult.summary }}</p>
          <pre v-if="queryResult.table_markdown" class="result-table">{{ queryResult.table_markdown }}</pre>
          <v-expansion-panels variant="accordion" class="mt-3" rounded="lg">
            <v-expansion-panel title="SQL & Diagnostics">
              <v-expansion-panel-text>
                <p class="text-caption mb-1">
                  <strong>Space:</strong> {{ queryResult.space_id }} &nbsp;·&nbsp;
                  <strong>{{ queryResult.row_count }}</strong> rows
                </p>
                <pre class="sql-block">{{ queryResult.sql }}</pre>
                <p v-for="d in queryResult.diagnostics" :key="d" class="text-caption text-medium-emphasis mt-1">· {{ d }}</p>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </div>
      </template>
    </div>

    <!-- Data Spaces Section -->
    <div class="spaces-section">
      <div class="spaces-header">
        <div>
          <h2 class="spaces-title">Data Spaces</h2>
          <p class="spaces-sub">Define tables, joins and metrics for AI queries</p>
        </div>
        <v-btn color="primary" rounded="lg" prepend-icon="mdi-plus" elevation="0" @click="openCreate">
          New Space
        </v-btn>
      </div>

      <v-alert v-if="spaceSuccess" type="success" variant="tonal" closable rounded="lg" class="mb-4" @click:close="spaceSuccess = ''">
        {{ spaceSuccess }}
      </v-alert>

      <div v-if="spaces.length > 0" class="space-grid">
        <div v-for="space in spaces" :key="space.id" class="space-card" @click="goToSpace(space)">
          <div class="space-top">
            <div class="space-icon">
              <v-icon icon="mdi-folder-table" size="18" color="primary" />
            </div>
            <div class="space-info">
              <p class="space-name">{{ space.name }}</p>
              <p class="space-id-text">{{ space.id }}</p>
            </div>
            <v-btn
              icon="mdi-pencil-outline"
              variant="text"
              size="small"
              density="compact"
              class="edit-btn"
              @click.stop="openEdit(space)"
            />
            <v-btn
              icon="mdi-delete-outline"
              variant="text"
              size="small"
              density="compact"
              color="error"
              class="edit-btn"
              @click.stop="openDeleteConfirm(space)"
            />
          </div>

          <p class="space-desc">{{ space.description || 'No description.' }}</p>

          <div class="chips">
            <span class="chip chip-blue">
              <v-icon size="11" icon="mdi-table" class="chip-icon" />
              {{ space.tables.length }} tables
            </span>
            <span class="chip chip-amber">
              <v-icon size="11" icon="mdi-relation-many-to-many" class="chip-icon" />
              {{ space.join_rules.length }} joins
            </span>
            <span class="chip chip-green">
              <v-icon size="11" icon="mdi-chart-bar" class="chip-icon" />
              {{ space.metric_rules.length }} metrics
            </span>
          </div>

          <div v-if="space.tables.length > 0" class="table-tags">
            <span v-for="t in space.tables.slice(0, 4)" :key="t.name" class="table-tag">
              <v-icon size="10" icon="mdi-table-outline" class="mr-1" />{{ t.name }}
            </span>
            <span v-if="space.tables.length > 4" class="table-tag table-tag-more">
              +{{ space.tables.length - 4 }}
            </span>
            <span class="data-connection-badge">
              <span class="dot" />
              data connection
            </span>
          </div>
        </div>
      </div>

      <div v-else class="empty-state">
        <v-icon icon="mdi-folder-plus-outline" size="48" color="grey-lighten-1" />
        <p class="empty-title">No spaces yet</p>
        <p class="empty-sub">Create a space to organise tables and metrics for AI queries.</p>
        <v-btn color="primary" rounded="lg" prepend-icon="mdi-plus" class="mt-4" elevation="0" @click="openCreate">
          New Space
        </v-btn>
      </div>
    </div>

    <SpaceFormDialog
      v-model="dialogOpen"
      :mode="dialogMode"
      :database-name="currentDatabase?.name ?? databaseId"
      :database-id="databaseId"
      :database-dialect="currentDatabase?.dialect ?? ''"
      :initial="dialogInitial"
      :is-submitting="dialogSubmitting"
      :error-message="dialogError"
      @submit="onDialogSubmit"
    />

    <v-dialog v-model="deleteConfirmOpen" max-width="360">
      <v-card rounded="xl">
        <v-card-title class="pt-5 px-6 text-body-1 font-weight-bold">删除 Space</v-card-title>
        <v-card-text class="px-6">
          确认删除 Space <strong>{{ deleteConfirmName }}</strong>？此操作不可撤销，相关表和规则数据也会一并删除。
          <v-alert v-if="deleteError" type="error" variant="tonal" density="compact" class="mt-3" rounded="lg">
            {{ deleteError }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-btn variant="text" @click="deleteConfirmId = null">取消</v-btn>
          <v-spacer />
          <v-btn color="error" rounded="lg" :loading="deleteLoading" @click="onDeleteSpace">删除</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  padding: 28px 32px;
  gap: 28px;
  box-sizing: border-box;
  background: #f4f6fb;
}

/* Query Card */
.chat-card {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.07);
  border-radius: 18px;
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}

.card-header { display: flex; align-items: flex-start; gap: 14px; }
.header-icon {
  width: 42px; height: 42px; border-radius: 10px;
  background: rgba(var(--v-theme-primary), 0.1);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.header-text { display: flex; flex-direction: column; gap: 2px; }
.card-title { font-size: 18px; font-weight: 700; color: #111827; margin: 0; }
.card-sub { font-size: 13px; color: #6b7280; margin: 0; }

.textarea-wrap { position: relative; }
.prompt-ideas-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  font-size: 12px !important;
  height: 28px !important;
}

.submit-row { display: flex; align-items: center; justify-content: space-between; }
.hint { font-size: 12px; color: #9ca3af; }

.result-block { border-top: 1px solid rgba(0, 0, 0, 0.07); padding-top: 18px; }
.result-summary { font-size: 15px; color: #1f2937; line-height: 1.7; margin: 0 0 14px; }
.result-table {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
  background: #f8f9fc;
  border: 1px solid rgba(0, 0, 0, 0.07);
  border-radius: 10px;
  padding: 14px 18px;
  overflow-x: auto;
  white-space: pre;
}
.sql-block {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
  background: #f0f2f8;
  border-radius: 8px;
  padding: 10px 14px;
  overflow-x: auto;
  white-space: pre-wrap;
  margin: 6px 0 0;
}

/* Data Spaces */
.spaces-section { flex: 1; }
.spaces-header {
  display: flex; align-items: flex-end; justify-content: space-between;
  margin-bottom: 20px;
}
.spaces-title { font-size: 20px; font-weight: 700; color: #111827; margin: 0; }
.spaces-sub { font-size: 13px; color: #6b7280; margin: 3px 0 0; }

.space-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 18px;
}

.space-card {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.07);
  border-radius: 14px;
  padding: 20px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.space-card:hover {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 6px 24px rgba(37, 99, 235, 0.12);
  transform: translateY(-2px);
}
.space-card:hover .edit-btn { opacity: 1; }

.space-top { display: flex; align-items: center; gap: 10px; }
.space-icon {
  width: 36px; height: 36px; border-radius: 9px;
  background: rgba(var(--v-theme-primary), 0.09);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.space-info { flex: 1; min-width: 0; }
.space-name { font-size: 15px; font-weight: 700; color: #111827; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.space-id-text { font-size: 11px; color: #9ca3af; margin: 2px 0 0; }
.edit-btn { opacity: 0; transition: opacity 0.15s; }

.space-desc {
  font-size: 13px; color: #6b7280; margin: 0; line-height: 1.55;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.chips { display: flex; flex-wrap: wrap; gap: 7px; }
.chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; font-weight: 600;
  padding: 3px 9px; border-radius: 999px;
}
.chip-icon { opacity: 0.85; }
.chip-blue   { background: rgba(59,  130, 246, 0.1); color: #2563eb; }
.chip-amber  { background: rgba(245, 158,  11, 0.1); color: #d97706; }
.chip-green  { background: rgba(16,  185, 129, 0.1); color: #059669; }

.table-tags {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
  padding-top: 10px;
  margin-top: 2px;
}
.table-tag {
  display: inline-flex; align-items: center;
  font-size: 11px; color: #374151; font-weight: 500;
  background: #f3f4f6; border-radius: 6px;
  padding: 2px 7px;
}
.table-tag-more { color: #6b7280; background: #f3f4f6; }
.data-connection-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; color: #059669; font-weight: 500;
  margin-left: auto;
}
.dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #10b981;
  flex-shrink: 0;
}

/* Empty state */
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  padding: 64px 24px; text-align: center;
  background: #fff; border: 1.5px dashed rgba(0, 0, 0, 0.12);
  border-radius: 18px;
}
.empty-title { font-size: 16px; font-weight: 600; color: #374151; margin: 14px 0 4px; }
.empty-sub { font-size: 13px; color: #9ca3af; margin: 0; max-width: 300px; }
</style>
