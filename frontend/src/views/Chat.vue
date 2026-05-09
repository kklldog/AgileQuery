<script setup lang="ts">
import { ref } from 'vue'

const databaseId = ref('demo')
const question = ref('')
const isLoading = ref(false)
const error = ref('')

interface QueryResponse {
  database_id: string
  space_id: string
  sql: string
  status: string
  summary: string
  table_markdown: string
  row_count: number
  is_truncated: boolean
  diagnostics: string[]
}

const result = ref<QueryResponse | null>(null)

async function submitQuery() {
  if (!question.value.trim()) return
  
  isLoading.value = true
  error.value = ''
  result.value = null
  
  try {
    const res = await fetch('http://localhost:8000/query', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        database_id: databaseId.value,
        question: question.value,
      }),
    })
    
    if (!res.ok) {
      const errorData = await res.json()
      throw new Error(errorData.detail || 'Query failed')
    }
    
    result.value = await res.json()
  } catch (err: any) {
    error.value = err.message
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="container">
    <header>
      <h1>AgileQuery Data Agent</h1>
      <p>Text-to-Insight System</p>
    </header>

    <main>
      <div class="query-box">
        <div class="input-group">
          <label for="db">Database ID:</label>
          <input id="db" v-model="databaseId" type="text" />
        </div>
        
        <div class="input-group">
          <label for="q">Ask a question:</label>
          <textarea 
            id="q" 
            v-model="question" 
            placeholder="e.g. 华东区销售额是多少？"
            @keyup.enter.ctrl="submitQuery"
          ></textarea>
        </div>
        
        <button @click="submitQuery" :disabled="isLoading">
          {{ isLoading ? 'Thinking...' : 'Generate Insight' }}
        </button>
      </div>

      <div v-if="error" class="error">
        {{ error }}
      </div>

      <div v-if="result" class="result-box">
        <div class="summary">
          <h3>Summary</h3>
          <p>{{ result.summary }}</p>
        </div>
        
        <div class="data-table" v-if="result.table_markdown">
          <h3>Data</h3>
          <pre class="markdown">{{ result.table_markdown }}</pre>
        </div>
        
        <div class="metadata">
          <details>
            <summary>Execution Details (SQL & Diagnostics)</summary>
            <div class="details-content">
              <strong>Space:</strong> {{ result.space_id }}<br/>
              <strong>Status:</strong> {{ result.status }} ({{ result.row_count }} rows)<br/>
              <strong>SQL:</strong>
              <pre><code>{{ result.sql }}</code></pre>
              <strong>Diagnostics:</strong>
              <ul>
                <li v-for="diag in result.diagnostics" :key="diag">{{ diag }}</li>
              </ul>
            </div>
          </details>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.container {
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem;
  font-family: system-ui, -apple-system, sans-serif;
}

header {
  text-align: center;
  margin-bottom: 2rem;
}

.query-box {
  background: #f8f9fa;
  padding: 1.5rem;
  border-radius: 8px;
  margin-bottom: 2rem;
}

.input-group {
  margin-bottom: 1rem;
}

label {
  display: block;
  font-weight: bold;
  margin-bottom: 0.5rem;
}

input, textarea {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #ccc;
  border-radius: 4px;
}

textarea {
  min-height: 80px;
  resize: vertical;
}

button {
  background: #0066cc;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

button:disabled {
  background: #cccccc;
}

.error {
  background: #ffebee;
  color: #cc0000;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 2rem;
}

.result-box {
  border: 1px solid #eee;
  border-radius: 8px;
  overflow: hidden;
}

.summary {
  background: #e8f4f8;
  padding: 1rem;
  border-bottom: 1px solid #eee;
}

.data-table {
  padding: 1rem;
  border-bottom: 1px solid #eee;
}

.markdown {
  background: #f5f5f5;
  padding: 1rem;
  border-radius: 4px;
  overflow-x: auto;
}

.metadata {
  padding: 1rem;
  background: #fafafa;
}

.details-content {
  margin-top: 1rem;
  font-size: 0.9em;
}

pre {
  margin: 0.5rem 0;
}
</style>
