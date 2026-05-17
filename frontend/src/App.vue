<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { useDatabasesStore } from '@/stores/databases'
import {
  createDatabase,
  deleteDatabase,
  getDatabaseConnection,
  getErrorMessage,
  getLlmConfig,
  updateDatabase,
  updateLlmConfig,
} from '@/api/client'
import type {
  CreateDatabasePayload,
  DatabaseConnection,
  LlmConfig,
  UpdateDatabasePayload,
  UpdateLlmConfigPayload,
} from '@/api/client'
import type { DatabaseMeta } from '@/api/types'
import DatabaseFormDialog from '@/components/DatabaseFormDialog.vue'
import LlmConfigDialog from '@/components/LlmConfigDialog.vue'

const store = useDatabasesStore()
const route = useRoute()
const router = useRouter()

const dbDialogOpen = ref(false)
const dbDialogMode = ref<'create' | 'edit'>('create')
const dbSubmitting = ref(false)
const dbError = ref('')
const editingDatabase = ref<DatabaseMeta | null>(null)
const editingConnection = ref<DatabaseConnection | null>(null)
const deleteConfirmId = ref<string | null>(null)
const deleteConfirmOpen = computed({
  get: () => deleteConfirmId.value !== null,
  set: (v: boolean) => { if (!v) deleteConfirmId.value = null },
})
const deleteLoading = ref(false)

const llmDialogOpen = ref(false)
const llmSubmitting = ref(false)
const llmError = ref('')
const llmConfig = ref<LlmConfig | null>(null)

onMounted(async () => {
  await store.refresh()
  if (route.name === 'home' && store.databases.value.length > 0) {
    void router.replace({
      name: 'database-chat',
      params: { databaseId: store.databases.value[0].id },
    })
  }
  try {
    llmConfig.value = await getLlmConfig()
  } catch {
    // non-critical
  }
})

watch(
  () => store.databases.value,
  (list) => {
    if (route.name === 'home' && list.length > 0) {
      void router.replace({
        name: 'database-chat',
        params: { databaseId: list[0].id },
      })
    }
  },
)

async function onCreateDatabase(payload: CreateDatabasePayload) {
  dbSubmitting.value = true
  dbError.value = ''
  try {
    await createDatabase(payload)
    await store.refresh()
    dbDialogOpen.value = false
    void router.replace({ name: 'database-chat', params: { databaseId: payload.id } })
  } catch (e: unknown) {
    dbError.value = getErrorMessage(e)
  } finally {
    dbSubmitting.value = false
  }
}

async function openEditDialog(database: DatabaseMeta) {
  dbDialogMode.value = 'edit'
  editingDatabase.value = database
  editingConnection.value = null
  dbError.value = ''
  try {
    editingConnection.value = await getDatabaseConnection(database.id)
  } catch (e: unknown) {
    dbError.value = getErrorMessage(e)
  }
  dbDialogOpen.value = true
}

function openCreateDialog() {
  dbDialogMode.value = 'create'
  editingDatabase.value = null
  editingConnection.value = null
  dbError.value = ''
  dbDialogOpen.value = true
}

async function onUpdateDatabase(databaseId: string, payload: UpdateDatabasePayload) {
  dbSubmitting.value = true
  dbError.value = ''
  try {
    await updateDatabase(databaseId, payload)
    await store.refresh()
    dbDialogOpen.value = false
  } catch (e: unknown) {
    dbError.value = getErrorMessage(e)
  } finally {
    dbSubmitting.value = false
  }
}

async function openLlmDialog() {
  llmError.value = ''
  try {
    llmConfig.value = await getLlmConfig()
  } catch (e: unknown) {
    llmError.value = getErrorMessage(e)
  }
  llmDialogOpen.value = true
}

async function onSaveLlmConfig(payload: UpdateLlmConfigPayload) {
  llmSubmitting.value = true
  llmError.value = ''
  try {
    llmConfig.value = await updateLlmConfig(payload)
    llmDialogOpen.value = false
  } catch (e: unknown) {
    llmError.value = getErrorMessage(e)
  } finally {
    llmSubmitting.value = false
  }
}

async function onDeleteDatabase(databaseId: string) {
  deleteLoading.value = true
  try {
    await deleteDatabase(databaseId)
    await store.refresh()
    deleteConfirmId.value = null
    if (route.params.databaseId === databaseId) {
      const remaining = store.databases.value
      if (remaining.length > 0) {
        void router.replace({ name: 'database-chat', params: { databaseId: remaining[0].id } })
      } else {
        void router.replace({ name: 'home' })
      }
    }
  } catch (e: unknown) {
    console.error(getErrorMessage(e))
  } finally {
    deleteLoading.value = false
  }
}

function dialectIcon(dialect: string): string {
  if (dialect.startsWith('postgres')) return 'mdi-elephant'
  if (dialect.startsWith('mysql')) return 'mdi-dolphin'
  if (dialect === 'tsql' || dialect === 'sqlserver' || dialect === 'mssql') return 'mdi-microsoft'
  return 'mdi-database-outline'
}
</script>

<template>
  <v-app>
    <v-app-bar flat border="b" height="56">
      <div class="d-flex align-center pl-4 ga-2">
        <v-icon icon="mdi-lightning-bolt" color="primary" size="22" />
        <span class="text-h6 font-weight-bold">AgileQuery</span>
      </div>
      <v-spacer />
      <v-tooltip :text="llmConfig?.provider && llmConfig.provider !== 'stub' ? `LLM: ${llmConfig.model || llmConfig.provider}` : 'LLM 未配置'" location="bottom">
        <template #activator="{ props: tooltipProps }">
          <v-btn
            v-bind="tooltipProps"
            :icon="llmConfig?.provider && llmConfig.provider !== 'stub' ? 'mdi-robot' : 'mdi-robot-off'"
            :color="llmConfig?.provider && llmConfig.provider !== 'stub' ? 'success' : 'default'"
            variant="text"
            size="small"
            class="mr-1"
            @click="openLlmDialog"
          />
        </template>
      </v-tooltip>
      <v-btn
        icon="mdi-refresh"
        variant="text"
        size="small"
        class="mr-2"
        :loading="store.isLoading.value"
        @click="store.refresh()"
      />
    </v-app-bar>

    <v-navigation-drawer permanent width="256" border="r">
      <div class="px-3 pt-4 pb-1 d-flex align-center">
        <p class="text-overline text-medium-emphasis font-weight-medium flex-grow-1">Databases</p>
        <v-btn
          icon="mdi-plus"
          variant="text"
          size="x-small"
          color="primary"
          @click="openCreateDialog"
        />
      </div>

      <v-list nav density="comfortable" class="px-2">
        <v-list-item
          v-for="database in store.databases.value"
          :key="database.id"
          :to="{ name: 'database-chat', params: { databaseId: database.id } }"
          color="primary"
          rounded="lg"
          class="mb-1"
        >
          <template #prepend>
            <v-icon :icon="dialectIcon(database.dialect)" size="18" />
          </template>
          <v-list-item-title class="text-body-2 font-weight-medium">{{ database.name }}</v-list-item-title>
          <v-list-item-subtitle class="text-caption">{{ database.dialect }} · {{ database.spaces.length }} spaces</v-list-item-subtitle>
          <template #append>
            <v-btn
              icon="mdi-pencil-outline"
              variant="text"
              size="x-small"
              @click.prevent.stop="openEditDialog(database)"
            />
            <v-btn
              icon="mdi-delete-outline"
              variant="text"
              size="x-small"
              color="error"
              @click.prevent.stop="deleteConfirmId = database.id"
            />
          </template>
        </v-list-item>
      </v-list>

      <v-skeleton-loader v-if="store.isLoading.value" class="mx-3 mt-2" type="list-item-two-line@3" />

      <v-alert
        v-if="store.error.value"
        class="mx-3 mt-2"
        type="error"
        variant="tonal"
        density="compact"
      >{{ store.error.value }}</v-alert>
    </v-navigation-drawer>

    <v-main class="fill-height">
      <RouterView />
    </v-main>

    <DatabaseFormDialog
      v-model="dbDialogOpen"
      :mode="dbDialogMode"
      :is-submitting="dbSubmitting"
      :error-message="dbError"
      :initial-database="editingDatabase"
      :initial-connection="editingConnection"
      @submit="onCreateDatabase"
      @update="onUpdateDatabase"
    />

    <LlmConfigDialog
      v-model="llmDialogOpen"
      :is-submitting="llmSubmitting"
      :error-message="llmError"
      :current="llmConfig"
      @submit="onSaveLlmConfig"
    />

    <v-dialog v-model="deleteConfirmOpen" max-width="360">
      <v-card rounded="xl">
        <v-card-title class="pt-5 px-6 text-body-1 font-weight-bold">删除数据库</v-card-title>
        <v-card-text class="px-6">
          确认删除数据库 <strong>{{ deleteConfirmId }}</strong>？此操作不可撤销，相关 Space 数据也会一并删除。
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-btn variant="text" @click="deleteConfirmId = null">取消</v-btn>
          <v-spacer />
          <v-btn color="error" rounded="lg" :loading="deleteLoading" @click="onDeleteDatabase(deleteConfirmId!)">删除</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-app>
</template>

<style>
html, body, #app {
  height: 100%;
  width: 100%;
  margin: 0;
  padding: 0;
}

.v-application {
  width: 100% !important;
  min-height: 100% !important;
  background: #f8f9fc !important;
}

.v-application__wrap {
  width: 100% !important;
}
</style>
