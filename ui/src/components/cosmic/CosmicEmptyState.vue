<template>
  <div class="panel-empty">
    <slot>{{ message }}</slot>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    message?: string;
  }>(),
  {
    message: "No records available."
  }
);
</script>
