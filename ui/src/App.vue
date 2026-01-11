<template>
  <AppShell>
    <RouterView />
  </AppShell>
  <BaseToast />
</template>

<script setup lang="ts">
import { RouterView } from "vue-router";
import AppShell from "./components/AppShell.vue";
import BaseToast from "./components/BaseToast.vue";
</script>
