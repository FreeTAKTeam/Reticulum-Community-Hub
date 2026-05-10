<template>
  <section class="cui-form-section" :class="{ 'cui-form-section--advanced': advanced }">
    <header v-if="title || description" class="cui-form-section__head">
      <h4 v-if="title" class="cui-form-section__title">{{ title }}</h4>
      <p v-if="description" class="cui-form-section__description">{{ description }}</p>
    </header>
    <div :class="gridClass">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    title?: string;
    description?: string;
    columns?: 1 | 2 | 3;
    advanced?: boolean;
  }>(),
  {
    title: "",
    description: "",
    columns: 1,
    advanced: false
  }
);

const gridClass = computed(() => {
  if (props.columns === 2) {
    return "cui-form-grid--2";
  }
  if (props.columns === 3) {
    return "cui-form-grid--3";
  }
  return "cui-form-grid--1";
});
</script>
