<script setup lang="ts">
import { ref, onMounted } from 'vue'

const databases = ref<any[]>([])
const isLoading = ref(false)
const error = ref('')

async function fetchDatabases() {
  isLoading.value = true
  error.value = ''
  
  try {
    const res = await fetch('http://localhost:8000/admin/databases')
    if (!res.ok) throw new Error('Failed to fetch databases')
    
    const data = await res.json()
    databases.value = data.databases
  } catch (err: any) {
    error.value = err.message
  } finally {
    isLoading.value = false
  }
}

async function syncSchema(dbId: string, spaceId: string) {
  if (!confirm(`Are you sure you want to sync schema from database? This will overwrite current tables in space ${spaceId}.`)) return
  
  try {
    const res = await fetch(`http://localhost:8000/admin/databases/${dbId}/spaces/${spaceId}/sync?schema=public`, {
      method: 'POST'
    })
    
    if (!res.ok) {
      const errData = await res.json()
      throw new Error(errData.detail || 'Sync failed')
    }
    
    const result = await res.json()
    alert(`Successfully synced ${result.tables_synced} tables: ${result.table_names.join(', ')}`)
    await fetchDatabases()
  } catch (err: any) {
    alert(`Sync error: ${err.message}`)
  }
}

onMounted(() => {
  fetchDatabases()
})
</script>

<template>
  <div class="metadata-container">
    <header>
      <h2>Metadata Management</h2>
      <p>View and sync your spaces and tables</p>
    </header>

    <div v-if="error" class="error">
      {{ error }}
    </div>

    <div v-if="isLoading" class="loading">
      Loading...
    </div>

    <div v-else class="databases">
      <div v-for="db in databases" :key="db.id" class="database-card">
        <h3>Database: {{ db.name }} ({{ db.id }})</h3>
        <p>Dialect: {{ db.dialect }} | Ref: {{ db.connection_ref }}</p>
        
        <div class="spaces">
          <div v-for="space in db.spaces" :key="space.id" class="space-card">
            <h4>Space: {{ space.name }}</h4>
            <p>{{ space.description }}</p>
            
            <div class="actions">
              <button @click="syncSchema(db.id, space.id)" class="btn-sync">
                🔄 Sync Schema from DB
              </button>
            </div>
            
            <details>
              <summary>Tables ({{ space.tables.length }})</summary>
              <ul class="table-list">
                <li v-for="table in space.tables" :key="table.name">
                  <strong>{{ table.name }}</strong> ({{ table.alias }}) - {{ table.business_name }}
                  <ul class="column-list">
                    <li v-for="col in table.columns" :key="col.name">
                      <code>{{ col.name }}</code>: {{ col.data_type }}
                    </li>
                  </ul>
                </li>
              </ul>
            </details>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.metadata-container {
  max-width: 900px;
  margin: 0 auto;
  padding: 1rem;
}

.database-card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 2rem;
  background: #fff;
}

.space-card {
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 1rem;
  margin-top: 1rem;
  background: #fafafa;
}

.actions {
  margin: 1rem 0;
}

.btn-sync {
  background: #4caf50;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
}

.btn-sync:hover {
  background: #45a049;
}

.table-list, .column-list {
  margin-top: 0.5rem;
  font-size: 0.9em;
}

.column-list {
  color: #666;
  margin-bottom: 0.5rem;
}

.error {
  color: red;
  padding: 1rem;
  background: #ffebee;
  border-radius: 4px;
}
</style>
