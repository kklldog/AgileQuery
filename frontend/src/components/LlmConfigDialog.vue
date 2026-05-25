<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { LlmConfig, UpdateLlmConfigPayload } from '@/api/client'

const props = defineProps<{
  modelValue: boolean
  isSubmitting?: boolean
  errorMessage?: string
  current?: LlmConfig | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: UpdateLlmConfigPayload]
}>()

const isOpen = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const providerValue = ref('openai-compatible')
const baseUrlValue = ref('')
const apiKeyValue = ref('')
const modelValue = ref('')
const timeoutValue = ref(30)
const showKey = ref(false)

const isOpenAI = computed(() =>
  ['openai', 'openai-compatible', 'deepseek'].includes(providerValue.value),
)

const baseUrlPlaceholder = computed(() => {
  if (providerValue.value === 'deepseek') return 'https://api.deepseek.com/v1'
  return 'https://api.openai.com/v1'
})

const modelPlaceholder = computed(() => {
  if (providerValue.value === 'deepseek') return 'deepseek-chat'
  return 'gpt-4o'
})

watch(providerValue, (val) => {
  if (val === 'deepseek' && !baseUrlValue.value) {
    baseUrlValue.value = 'https://api.deepseek.com/v1'
  }
})

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    showKey.value = false
    const c = props.current
    providerValue.value = c?.provider && c.provider !== 'stub' ? c.provider : 'openai-compatible'
    baseUrlValue.value = c?.base_url ?? ''
    apiKeyValue.value = ''
    modelValue.value = c?.model ?? ''
    timeoutValue.value = c?.timeout_seconds ?? 30
  },
)

const canSubmit = computed(() => {
  if (providerValue.value === 'stub') return true
  if (!baseUrlValue.value.trim()) return false
  if (!modelValue.value.trim()) return false
  return true
})

function handleSubmit() {
  if (!canSubmit.value) return
  emit('submit', {
    provider: providerValue.value,
    base_url: baseUrlValue.value.trim(),
    api_key: apiKeyValue.value,
    model: modelValue.value.trim(),
    timeout_seconds: timeoutValue.value,
  })
}
</script>

<template>
  <v-dialog v-model="isOpen" max-width="520" :persistent="isSubmitting" scrollable>
    <v-card rounded="xl">
      <v-card-title class="llm-dialog-title">
        <v-icon icon="mdi-robot-outline" color="primary" class="mr-2" />
        LLM 配置
      </v-card-title>

      <v-divider />

      <v-card-text class="llm-dialog-body">
        <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-4" rounded="lg">
          {{ errorMessage }}
        </v-alert>

        <v-alert
          v-if="current?.provider && current.provider !== 'stub'"
          type="success"
          variant="tonal"
          class="mb-4"
          rounded="lg"
          density="compact"
        >
          当前已配置：{{ current.provider }} · {{ current.model }}
          <template v-if="current.api_key_set">（API Key 已设置）</template>
        </v-alert>

        <v-select
          v-model="providerValue"
          label="Provider"
          variant="outlined"
          density="comfortable"
          prepend-inner-icon="mdi-cloud-outline"
          :items="[
            { title: 'OpenAI Compatible（推荐）', value: 'openai-compatible' },
            { title: 'DeepSeek', value: 'deepseek' },
            { title: 'OpenAI', value: 'openai' },
            { title: 'Stub（禁用 LLM）', value: 'stub' },
          ]"
          class="mb-3"
        />

        <template v-if="isOpenAI">
          <v-text-field
            v-model="baseUrlValue"
            label="Base URL"
            :placeholder="baseUrlPlaceholder"
            variant="outlined"
            density="comfortable"
            prepend-inner-icon="mdi-link"
            class="mb-3"
          />

          <v-text-field
            v-model="apiKeyValue"
            label="API Key"
            :placeholder="current?.api_key_set ? '（留空保留原 Key）' : 'sk-...'"
            :type="showKey ? 'text' : 'password'"
            variant="outlined"
            density="comfortable"
            prepend-inner-icon="mdi-key-outline"
            :append-inner-icon="showKey ? 'mdi-eye-off' : 'mdi-eye'"
            class="mb-3"
            @click:append-inner="showKey = !showKey"
          />

          <v-text-field
            v-model="modelValue"
            label="模型名称"
            :placeholder="modelPlaceholder"
            variant="outlined"
            density="comfortable"
            prepend-inner-icon="mdi-chip"
            class="mb-3"
          />

          <v-text-field
            v-model.number="timeoutValue"
            label="超时（秒）"
            type="number"
            variant="outlined"
            density="comfortable"
            hide-details
          />
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
          保存
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.llm-dialog-title {
  display: flex;
  align-items: center;
  font-size: 17px;
  font-weight: 700;
  padding: 20px 24px 16px;
}

.llm-dialog-body {
  padding: 20px 24px;
  max-height: 70vh;
}
</style>
