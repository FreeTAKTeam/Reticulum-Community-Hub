<template>
  <AppShell>
    <ErrorBoundary>
      <RouterView />
    </ErrorBoundary>
  </AppShell>
  <BaseToast />
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { RouterView } from "vue-router";
import AppShell from "./components/AppShell.vue";
import BaseToast from "./components/BaseToast.vue";
import ErrorBoundary from "./components/ErrorBoundary.vue";
import { useAppStore } from "./stores/app";

const appStore = useAppStore();

onMounted(() => {
  appStore.fetchAppInfo();
});
</script>
