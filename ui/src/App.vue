<template>
  <AppShell>
    <ErrorBoundary>
      <RouterView />
    </ErrorBoundary>
  </AppShell>
  <BaseToast />
</template>

<script setup lang="ts">
import { RouterView } from "vue-router";
import AppShell from "./components/AppShell.vue";
import BaseToast from "./components/BaseToast.vue";
import ErrorBoundary from "./components/ErrorBoundary.vue";
</script>
