<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { introspectDatabase, getErrorMessage } from '@/api/client'
import type { IntrospectedObject } from '@/api/client'

const props = defineProps<{
  modelValue: boolean
  databaseId: string
  databaseDialect: string
  existingTableNames: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  import: [objects: IntrospectedObject[]]
}>()

const isOpen = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

function defaultSchemaFor(dialect: string): string {
  const d = (dialect || '').toLowerCase()
  if (d === 'tsql' || d === 'sqlserver' || d === 'mssql') return 'dbo'
  if (d === 'mysql') return ''
  return 'public'
}

const schemaValue = ref(defaultSchemaFor(props.databaseDialect))
const isLoading = ref(false)
const errorMessage = ref('')
const objects = ref<IntrospectedObject[]>([])
const selectedNames = ref<Set<string>>(new Set())
const searchQuery = ref('')
const kindFilter = ref<'all' | 'table' | 'view'>('all')

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    schemaValue.value = defaultSchemaFor(props.databaseDialect)
    selectedNames.value = new Set()
    searchQuery.value = ''
    kindFilter.value = 'all'
    objects.value = []
    errorMessage.value = ''
    await loadObjects()
  },
)

async function loadObjects() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const result = await introspectDatabase(props.databaseId, schemaValue.value)
    objects.value = result.objects
    selectedNames.value = new Set()
  } catch (err: unknown) {
    errorMessage.value = getErrorMessage(err)
    objects.value = []
  } finally {
    isLoading.value = false
  }
}

const filteredObjects = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  return objects.value.filter(o => {
    if (kindFilter.value !== 'all' && o.kind !== kindFilter.value) return false
    if (q && !o.name.toLowerCase().includes(q)) return false
    return true
  })
})

const existingSet = computed(() => new Set(props.existingTableNames))

function isAlreadyAdded(name: string): boolean {
  return existingSet.value.has(name)
}

function toggle(name: string) {
  const s = new Set(selectedNames.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  selectedNames.value = s
}

function toggleAll() {
  const importable = filteredObjects.value.filter(o => !isAlreadyAdded(o.name))
  if (importable.every(o => selectedNames.value.has(o.name))) {
    const s = new Set(selectedNames.value)
    importable.forEach(o => s.delete(o.name))
    selectedNames.value = s
  } else {
    const s = new Set(selectedNames.value)
    importable.forEach(o => s.add(o.name))
    selectedNames.value = s
  }
}

const allFilteredSelected = computed(() => {
  const importable = filteredObjects.value.filter(o => !isAlreadyAdded(o.name))
  return importable.length > 0 && importable.every(o => selectedNames.value.has(o.name))
})

function handleImport() {
  const picked = objects.value.filter(o => selectedNames.value.has(o.name))
  if (picked.length === 0) return
  emit('import', picked)
  isOpen.value = false
}
</script>

<template>
  <v-dialog v-model="isOpen" max-width="780" scrollable>
    <v-card rounded="xl">
      <v-card-title class="import-title">
        <v-icon icon="mdi-database-import" color="primary" class="mr-2" />
        从数据库导入表/视图
      </v-card-title>

      <v-divider />

      <v-card-text class="import-body">
        <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-3" rounded="lg">
          {{ errorMessage }}
        </v-alert>

        <div class="d-flex align-center gap-2 mb-3">
          <v-text-field
            v-model="schemaValue"
            label="Schema"
            density="compact"
            variant="outlined"
            hide-details
            style="max-width: 200px"
            prepend-inner-icon="mdi-folder-outline"
          />
          <v-btn
            color="primary"
            variant="tonal"
            rounded="lg"
            :loading="isLoading"
            prepend-icon="mdi-refresh"
            @click="loadObjects"
          >
            加载
          </v-btn>
          <v-spacer />
          <v-btn-toggle v-model="kindFilter" density="comfortable" mandatory variant="outlined" divided>
            <v-btn value="all" size="small">全部</v-btn>
            <v-btn value="table" size="small">表</v-btn>
            <v-btn value="view" size="small">视图</v-btn>
          </v-btn-toggle>
        </div>

        <v-text-field
          v-model="searchQuery"
          placeholder="搜索表/视图名…"
          density="compact"
          variant="outlined"
          hide-details
          prepend-inner-icon="mdi-magnify"
          clearable
          class="mb-3"
        />

        <div v-if="isLoading" class="loading-state">
          <v-progress-circular indeterminate color="primary" size="32" />
          <p class="text-body-2 text-medium-emphasis mt-3">正在读取数据库结构…</p>
        </div>

        <div v-else-if="filteredObjects.length === 0" class="empty-state">
          <v-icon icon="mdi-database-off" size="36" color="grey-lighten-1" />
          <p class="text-body-2 text-medium-emphasis mt-2">没有匹配的对象</p>
        </div>

        <div v-else class="object-list">
          <div class="object-list-header">
            <v-checkbox
              :model-value="allFilteredSelected"
              density="compact"
              hide-details
              color="primary"
              @update:model-value="toggleAll"
            />
            <span class="text-caption text-medium-emphasis">
              已选 {{ selectedNames.size }} / {{ filteredObjects.length }}
            </span>
          </div>

          <div
            v-for="obj in filteredObjects"
            :key="obj.name"
            class="object-row"
            :class="{ 'is-existing': isAlreadyAdded(obj.name) }"
            @click="!isAlreadyAdded(obj.name) && toggle(obj.name)"
          >
            <v-checkbox
              :model-value="selectedNames.has(obj.name)"
              :disabled="isAlreadyAdded(obj.name)"
              density="compact"
              hide-details
              color="primary"
              @click.stop
              @update:model-value="toggle(obj.name)"
            />
            <v-icon
              :icon="obj.kind === 'view' ? 'mdi-eye-outline' : 'mdi-table'"
              size="18"
              :color="obj.kind === 'view' ? 'purple' : 'primary'"
              class="mr-2"
            />
            <div class="object-name">
              {{ obj.name }}
              <v-chip
                v-if="isAlreadyAdded(obj.name)"
                size="x-small"
                variant="tonal"
                color="grey"
                class="ml-2"
              >
                已添加
              </v-chip>
            </div>
            <v-chip size="x-small" variant="outlined" class="ml-2">
              {{ obj.columns.length }} cols
            </v-chip>
          </div>
        </div>
      </v-card-text>

      <v-divider />

      <v-card-actions class="px-6 py-4">
        <v-btn variant="text" @click="isOpen = false">取消</v-btn>
        <v-spacer />
        <v-btn
          color="primary"
          rounded="lg"
          :disabled="selectedNames.size === 0"
          @click="handleImport"
        >
          导入 {{ selectedNames.size }} 项
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.import-title {
  display: flex;
  align-items: center;
  font-size: 17px;
  font-weight: 700;
  padding: 20px 24px 16px;
}

.import-body {
  padding: 20px 24px;
  max-height: 70vh;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px;
  border: 1px dashed rgba(0, 0, 0, 0.12);
  border-radius: 12px;
}

.object-list {
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  overflow: hidden;
}

.object-list-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(0, 0, 0, 0.03);
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
}

.object-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  cursor: pointer;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  transition: background 0.12s;
}

.object-row:last-child {
  border-bottom: none;
}

.object-row:hover:not(.is-existing) {
  background: rgba(var(--v-theme-primary), 0.04);
}

.object-row.is-existing {
  cursor: not-allowed;
  opacity: 0.55;
}

.object-name {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
}
</style>
