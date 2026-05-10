<template>
  <div class="panel-header">
    <div>
      <div class="panel-title"><slot name="title">{{ title }}</slot></div>
      <div v-if="subtitle || $slots.subtitle" class="panel-subtitle"><slot name="subtitle">{{ subtitle }}</slot></div>
    </div>
    <div v-if="$slots.default || chip" class="panel-chip">
      <slot>{{ chip }}</slot>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    subtitle?: string;
    chip?: string;
  }>(),
  {
    title: "",
    subtitle: "",
    chip: ""
  }
);
</script>
