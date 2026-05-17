<script setup lang="ts">
import { useDatabasesStore } from '@/stores/databases'

const store = useDatabasesStore()
</script>

<template>
  <v-container class="pa-8" style="max-width: 720px">
    <v-card rounded="xl" elevation="0" border>
      <v-card-item>
        <v-card-title>Welcome to AgileQuery</v-card-title>
        <v-card-subtitle>Select a database from the left sidebar to start.</v-card-subtitle>
      </v-card-item>
      <v-card-text>
        <v-alert v-if="!store.isLoading.value && store.databases.value.length === 0" type="info" variant="tonal">
          No databases configured yet.
        </v-alert>
        <v-list v-else lines="two">
          <v-list-item
            v-for="db in store.databases.value"
            :key="db.id"
            :to="{ name: 'database-chat', params: { databaseId: db.id } }"
            prepend-icon="mdi-database"
            :title="db.name"
            :subtitle="db.description || db.id"
          />
        </v-list>
      </v-card-text>
    </v-card>
  </v-container>
</template>
