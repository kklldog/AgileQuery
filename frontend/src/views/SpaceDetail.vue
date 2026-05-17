<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDatabasesStore } from '@/stores/databases'
import { getSpace, updateSpace, syncSpaceSchema, getErrorMessage } from '@/api/client'
import type { SpaceMeta } from '@/api/types'
import SpaceFormDialog from '@/components/SpaceFormDialog.vue'

const props = defineProps<{ databaseId: string; spaceId: string }>()
const store = useDatabasesStore()

const space = ref<SpaceMeta | null>(null)
const loading = ref(false)
const error = ref('')
const syncing = ref(false)
const successMessage = ref('')
const dialogOpen = ref(false)
const dialogSubmitting = ref(false)
const dialogError = ref('')
const tab = ref<'tables' | 'joins' | 'metrics'>('tables')

async function loadSpace() {
  loading.value = true
  error.value = ''
  try {
    space.value = await getSpace(props.databaseId, props.spaceId)
  } catch (e: unknown) {
    error.value = getErrorMessage(e)
  } finally {
    loading.value = false
  }
}

async function onSync() {
  syncing.value = true
  successMessage.value = ''
  error.value = ''
  try {
    const result = await syncSpaceSchema(props.databaseId, props.spaceId)
    successMessage.value = `Synced ${result.tables_synced} tables.`
    space.value = await getSpace(props.databaseId, props.spaceId)
    await store.refresh()
  } catch (e: unknown) {
    error.value = getErrorMessage(e)
  } finally {
    syncing.value = false
  }
}

async function onEditSubmit(payload: SpaceMeta) {
  dialogSubmitting.value = true
  dialogError.value = ''
  try {
    await updateSpace(props.databaseId, props.spaceId, payload)
    space.value = await getSpace(props.databaseId, props.spaceId)
    await store.refresh()
    dialogOpen.value = false
    successMessage.value = 'Space updated.'
  } catch (e: unknown) {
    dialogError.value = getErrorMessage(e)
  } finally {
    dialogSubmitting.value = false
  }
}

watch(
  () => [props.databaseId, props.spaceId] as const,
  () => { tab.value = 'tables'; successMessage.value = ''; error.value = ''; void loadSpace() },
  { immediate: true },
)
</script>

<template>
  <div class="page-layout">
    <div class="page-header">
      <v-btn
        variant="text"
        prepend-icon="mdi-arrow-left"
        size="small"
        color="primary"
        :to="{ name: 'database-chat', params: { databaseId } }"
        class="mb-3"
      >
        Back to {{ databaseId }}
      </v-btn>

      <v-skeleton-loader v-if="loading" type="heading, sentences" />

      <template v-if="space && !loading">
        <div class="d-flex align-start ga-4 flex-wrap">
          <div class="space-icon">
            <v-icon icon="mdi-folder-table" color="primary" size="22" />
          </div>
          <div class="flex-grow-1">
            <h1 class="space-title">{{ space.name }}</h1>
            <p class="space-id-text">{{ space.id }}</p>
            <p class="space-description">{{ space.description || 'No description.' }}</p>
          </div>
          <div class="d-flex ga-2 flex-wrap">
            <v-btn variant="tonal" color="success" prepend-icon="mdi-database-sync" :loading="syncing" rounded="lg" size="small" @click="onSync">
              Sync Schema
            </v-btn>
            <v-btn variant="tonal" prepend-icon="mdi-pencil" rounded="lg" size="small" @click="dialogOpen = true">
              Edit Space
            </v-btn>
          </div>
        </div>
      </template>
    </div>

    <v-alert v-if="successMessage" type="success" variant="tonal" closable rounded="lg" class="mx-6 mb-2" @click:close="successMessage = ''">
      {{ successMessage }}
    </v-alert>
    <v-alert v-if="error" type="error" variant="tonal" closable rounded="lg" class="mx-6 mb-2" @click:close="error = ''">
      {{ error }}
    </v-alert>

    <template v-if="space && !loading">
      <div class="tabs-wrap">
        <v-tabs v-model="tab" color="primary">
          <v-tab value="tables" prepend-icon="mdi-table">Tables <v-chip class="ml-2" size="x-small" variant="tonal">{{ space.tables.length }}</v-chip></v-tab>
          <v-tab value="joins" prepend-icon="mdi-link-variant">Joins <v-chip class="ml-2" size="x-small" variant="tonal">{{ space.join_rules.length }}</v-chip></v-tab>
          <v-tab value="metrics" prepend-icon="mdi-chart-line">Metrics <v-chip class="ml-2" size="x-small" variant="tonal">{{ space.metric_rules.length }}</v-chip></v-tab>
        </v-tabs>
      </div>

      <div class="tab-content">
        <v-window v-model="tab">
          <v-window-item value="tables">
            <v-empty-state v-if="space.tables.length === 0" icon="mdi-table-off" title="No tables" text="Use Sync Schema to pull table metadata." />
            <v-expansion-panels v-else variant="accordion" class="tables-list">
              <v-expansion-panel v-for="table in space.tables" :key="table.name">
                <v-expansion-panel-title>
                  <div class="d-flex align-center ga-3 flex-wrap w-100">
                    <v-icon icon="mdi-table" color="primary" size="16" />
                    <strong class="text-body-2">{{ table.business_name || table.name }}</strong>
                    <span class="text-caption text-medium-emphasis">{{ table.name }}</span>
                    <v-chip size="x-small" variant="tonal">alias: {{ table.alias }}</v-chip>
                    <v-chip size="x-small" variant="tonal" color="primary" class="ml-auto mr-1">{{ table.columns.length }} cols</v-chip>
                  </div>
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <p v-if="table.description" class="text-caption text-medium-emphasis mb-3">{{ table.description }}</p>
                  <div class="cols-table">
                    <div class="cols-header">
                      <span>Name</span><span>Type</span><span>Description</span>
                    </div>
                    <div v-for="col in table.columns" :key="col.name" class="cols-row">
                      <span class="col-name">{{ col.name }}</span>
                      <v-chip size="x-small" variant="outlined" label>{{ col.data_type }}</v-chip>
                      <span class="text-caption text-medium-emphasis">{{ col.description }}</span>
                    </div>
                  </div>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </v-window-item>

          <v-window-item value="joins">
            <v-empty-state v-if="space.join_rules.length === 0" icon="mdi-link-variant-off" title="No join rules" text="Define join rules when editing this space." />
            <v-row v-else dense>
              <v-col v-for="jr in space.join_rules" :key="jr.id" cols="12" md="6">
                <v-card rounded="xl" elevation="0" border>
                  <v-card-item>
                    <template #prepend>
                      <v-avatar color="primary" variant="tonal" size="32" rounded="lg">
                        <v-icon icon="mdi-link-variant" size="16" />
                      </v-avatar>
                    </template>
                    <v-card-title class="text-body-2 font-weight-semibold">{{ jr.id }}</v-card-title>
                    <v-card-subtitle class="text-caption">{{ jr.left_table }} → {{ jr.right_table }}</v-card-subtitle>
                  </v-card-item>
                  <v-card-text class="pt-0">
                    <p v-if="jr.description" class="text-caption mb-2">{{ jr.description }}</p>
                    <code class="condition-code">{{ jr.condition }}</code>
                    <p v-if="jr.guidance" class="text-caption text-medium-emphasis mt-2">{{ jr.guidance }}</p>
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>
          </v-window-item>

          <v-window-item value="metrics">
            <v-empty-state v-if="space.metric_rules.length === 0" icon="mdi-chart-line-variant" title="No metric rules" text="Define metrics when editing this space." />
            <v-row v-else dense>
              <v-col v-for="mr in space.metric_rules" :key="mr.id" cols="12" md="6">
                <v-card rounded="xl" elevation="0" border>
                  <v-card-item>
                    <template #prepend>
                      <v-avatar color="success" variant="tonal" size="32" rounded="lg">
                        <v-icon icon="mdi-chart-line" size="16" />
                      </v-avatar>
                    </template>
                    <v-card-title class="text-body-2 font-weight-semibold">{{ mr.name }}</v-card-title>
                    <v-card-subtitle class="text-caption">{{ mr.id }}</v-card-subtitle>
                  </v-card-item>
                  <v-card-text class="pt-0">
                    <p v-if="mr.description" class="text-caption mb-2">{{ mr.description }}</p>
                    <code class="condition-code">{{ mr.expression }}</code>
                    <div class="d-flex flex-wrap ga-1 mt-2">
                      <v-chip v-for="s in mr.synonyms" :key="s" size="x-small" variant="tonal">{{ s }}</v-chip>
                    </div>
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>
          </v-window-item>
        </v-window>
      </div>
    </template>

    <v-alert v-else-if="!loading && !space" type="warning" variant="tonal" class="ma-6">
      Space not found.
    </v-alert>

    <SpaceFormDialog
      v-model="dialogOpen"
      mode="edit"
      :database-name="databaseId"
      :database-id="databaseId"
      :database-dialect="store.findDatabase(databaseId)?.dialect ?? ''"
      :initial="space"
      :is-submitting="dialogSubmitting"
      :error-message="dialogError"
      @submit="onEditSubmit"
    />
  </div>
</template>

<style scoped>
.page-layout {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.page-header {
  padding: 24px 32px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.07);
  background: #fff;
}

.space-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: rgba(var(--v-theme-primary), 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.space-title {
  font-size: 20px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0;
}

.space-id-text {
  font-size: 12px;
  color: #9ca3af;
  margin: 2px 0 4px;
}

.space-description {
  font-size: 14px;
  color: #6b7280;
  margin: 0;
}

.tabs-wrap {
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid rgba(0, 0, 0, 0.07);
}

.tab-content {
  padding: 24px 32px;
  flex: 1;
}

.tables-list {
  border-radius: 12px;
}

.cols-table {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cols-header {
  display: grid;
  grid-template-columns: 1.5fr 1fr 3fr;
  gap: 12px;
  font-size: 11px;
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 0 4px 4px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.cols-row {
  display: grid;
  grid-template-columns: 1.5fr 1fr 3fr;
  gap: 12px;
  align-items: center;
  padding: 4px 4px;
}

.col-name {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
  font-family: monospace;
}

.condition-code {
  font-family: monospace;
  font-size: 12px;
  background: #f1f5f9;
  padding: 4px 8px;
  border-radius: 6px;
  display: block;
  overflow-x: auto;
}
</style>
