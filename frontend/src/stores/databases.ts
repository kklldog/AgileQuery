import { ref, computed } from 'vue'
import type { DatabaseMeta } from '@/api/types'
import { listDatabases, getErrorMessage } from '@/api/client'

const databases = ref<DatabaseMeta[]>([])
const isLoading = ref(false)
const error = ref('')

export function useDatabasesStore() {
  async function refresh() {
    isLoading.value = true
    error.value = ''
    try {
      databases.value = await listDatabases()
    } catch (err: unknown) {
      error.value = getErrorMessage(err)
    } finally {
      isLoading.value = false
    }
  }

  function findDatabase(databaseId: string): DatabaseMeta | undefined {
    return databases.value.find((db) => db.id === databaseId)
  }

  return {
    databases,
    isLoading,
    error,
    refresh,
    findDatabase,
    hasDatabases: computed(() => databases.value.length > 0),
  }
}
