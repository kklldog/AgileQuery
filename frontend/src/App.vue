<script setup lang="ts">
import { ref } from 'vue'
import Chat from './views/Chat.vue'
import Metadata from './views/Metadata.vue'

const currentView = ref('chat')
</script>

<template>
  <div class="app-layout">
    <nav class="sidebar">
      <h2>AgileQuery</h2>
      <ul>
        <li :class="{ active: currentView === 'chat' }">
          <a href="#" @click.prevent="currentView = 'chat'">Ask (Chat)</a>
        </li>
        <li :class="{ active: currentView === 'metadata' }">
          <a href="#" @click.prevent="currentView = 'metadata'">Metadata Admin</a>
        </li>
      </ul>
    </nav>
    <main class="content">
      <Chat v-if="currentView === 'chat'" />
      <Metadata v-if="currentView === 'metadata'" />
    </main>
  </div>
</template>

<style>
body {
  margin: 0;
  padding: 0;
  font-family: system-ui, -apple-system, sans-serif;
  background: #f0f2f5;
}
.app-layout {
  display: flex;
  height: 100vh;
}
.sidebar {
  width: 250px;
  background: #2c3e50;
  color: white;
  padding: 1.5rem;
}
.sidebar h2 {
  margin-top: 0;
  margin-bottom: 2rem;
}
.sidebar ul {
  list-style: none;
  padding: 0;
}
.sidebar li {
  margin-bottom: 0.5rem;
}
.sidebar a {
  color: #ecf0f1;
  text-decoration: none;
  display: block;
  padding: 0.5rem;
  border-radius: 4px;
}
.sidebar a:hover {
  background: #34495e;
}
.sidebar li.active a {
  background: #3498db;
  font-weight: bold;
}
.content {
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
}
</style>
