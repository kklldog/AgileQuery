<script setup lang="ts">
import { ref, watch } from 'vue'
import { getDatabasePrompts, updateDatabasePrompts, getErrorMessage } from '@/api/client'
import type { PromptsConfig } from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  databaseId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const activeTab = ref('query')
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const config = ref<PromptsConfig>({})
const edited = ref<Record<string, string>>({})

const QUERY_KEYS = ['keyword_expansion', 'sql_generation', 'sql_correction', 'insight']
const ADMIN_KEYS = ['ai_fill_table', 'ai_fill_joins', 'ai_fill_metrics']

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    activeTab.value = 'query'
    errorMessage.value = ''
    edited.value = {}
    if (!props.databaseId) return
    loading.value = true
    try {
      config.value = await getDatabasePrompts(props.databaseId)
      for (const key of Object.keys(config.value)) {
        edited.value[key] = config.value[key].value
      }
    } catch (err) {
      errorMessage.value = getErrorMessage(err)
    } finally {
      loading.value = false
    }
  },
)

function resetToDefault(key: string) {
  edited.value[key] = ''
}

async function handleSave() {
  saving.value = true
  errorMessage.value = ''
  try {
    config.value = await updateDatabasePrompts(props.databaseId, edited.value)
    for (const key of Object.keys(config.value)) {
      edited.value[key] = config.value[key].value
    }
    emit('update:modelValue', false)
  } catch (err) {
    errorMessage.value = getErrorMessage(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-dialog :model-value="modelValue" max-width="800" scrollable :persistent="saving" @update:model-value="emit('update:modelValue', $event)">
    <v-card rounded="xl">
      <v-card-title class="prompt-dialog-title">
        <v-icon icon="mdi-text-box-edit-outline" color="primary" class="mr-2" />
        Prompt 配置
        <span v-if="databaseId" class="text-caption text-medium-emphasis ml-2">· {{ databaseId }}</span>
      </v-card-title>

      <v-divider />

      <v-card-text class="prompt-dialog-body">
        <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-4" rounded="lg">
          {{ errorMessage }}
        </v-alert>

        <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

        <v-tabs v-model="activeTab" color="primary" class="mb-4">
          <v-tab value="query">查询类</v-tab>
          <v-tab value="admin">管理类</v-tab>
        </v-tabs>

        <v-window v-model="activeTab">
          <v-window-item value="query">
            <div v-for="key in QUERY_KEYS" :key="key" class="mb-5">
              <div class="d-flex align-center mb-1">
                <span class="text-body-2 font-weight-medium">{{ config[key]?.label ?? key }}</span>
                <v-chip v-if="config[key]?.is_default && !edited[key]" size="x-small" color="secondary" class="ml-2">默认</v-chip>
                <v-spacer />
                <v-btn size="x-small" variant="text" color="secondary" @click="resetToDefault(key)">重置为默认</v-btn>
              </div>
              <div class="text-caption text-medium-emphasis mb-1">{{ config[key]?.description }}</div>
              <v-textarea
                v-model="edited[key]"
                :placeholder="config[key]?.value ?? ''"
                variant="outlined"
                density="compact"
                rows="4"
                auto-grow
                hide-details
              />
            </div>
          </v-window-item>

          <v-window-item value="admin">
            <div v-for="key in ADMIN_KEYS" :key="key" class="mb-5">
              <div class="d-flex align-center mb-1">
                <span class="text-body-2 font-weight-medium">{{ config[key]?.label ?? key }}</span>
                <v-chip v-if="config[key]?.is_default && !edited[key]" size="x-small" color="secondary" class="ml-2">默认</v-chip>
                <v-spacer />
                <v-btn size="x-small" variant="text" color="secondary" @click="resetToDefault(key)">重置为默认</v-btn>
              </div>
              <div class="text-caption text-medium-emphasis mb-1">{{ config[key]?.description }}</div>
              <v-textarea
                v-model="edited[key]"
                :placeholder="config[key]?.value ?? ''"
                variant="outlined"
                density="compact"
                rows="4"
                auto-grow
                hide-details
              />
            </div>
          </v-window-item>
        </v-window>
      </v-card-text>

      <v-divider />

      <v-card-actions class="px-6 py-4">
        <v-btn variant="text" @click="emit('update:modelValue', false)">取消</v-btn>
        <v-spacer />
        <v-btn color="primary" rounded="lg" :loading="saving" :disabled="loading" @click="handleSave">保存</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.prompt-dialog-title {
  display: flex;
  align-items: center;
  font-size: 17px;
  font-weight: 700;
  padding: 20px 24px 16px;
}

.prompt-dialog-body {
  padding: 20px 24px;
  max-height: 70vh;
}
</style>
