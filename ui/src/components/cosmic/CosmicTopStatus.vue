<template>
  <header class="registry-top">
    <div class="registry-title">
      <slot name="title">{{ title }}</slot>
    </div>
    <div class="registry-status">
      <slot>
        <OnlineHelpLauncher />
        <span class="cui-status-pill" :class="connectionClass">{{ connectionLabel }}</span>
        <span class="cui-status-pill" :class="wsClass">{{ wsLabel }}</span>
        <span class="status-url">{{ baseUrl }}</span>
      </slot>
    </div>
  </header>
</template>

<script setup lang="ts">
import OnlineHelpLauncher from "../OnlineHelpLauncher.vue";
import { useConnectionPills } from "../../composables/useConnectionPills";

withDefaults(
  defineProps<{
    title?: string;
  }>(),
  {
    title: ""
  }
);

const { baseUrl, connectionLabel, wsLabel, connectionClass, wsClass } = useConnectionPills();
</script>
