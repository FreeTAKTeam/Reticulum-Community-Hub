<template>
  <BaseModal :open="open" title="Link Checklist to Mission" @close="emit('close')">
    <div class="template-modal">
      <p class="template-modal-hint">Associate this checklist with a mission or leave it unscoped.</p>
      <BaseSelect
        :model-value="selectionUid"
        label="Mission"
        :options="selectOptions"
        @update:model-value="emit('update:selection-uid', $event)"
      />
      <div class="template-modal-actions">
        <BaseButton variant="ghost" icon-left="undo" :disabled="submitting" @click="emit('close')">
          Cancel
        </BaseButton>
        <BaseButton icon-left="link" :disabled="submitting || !canSubmit" @click="emit('submit')">
          {{ submitting ? "Saving..." : actionLabel }}
        </BaseButton>
      </div>
    </div>
  </BaseModal>
</template>

<script setup lang="ts">
import BaseButton from "../../components/BaseButton.vue";
import BaseModal from "../../components/BaseModal.vue";
import BaseSelect from "../../components/BaseSelect.vue";

interface SelectOption {
  value: string;
  label: string;
}

defineProps<{
  open: boolean;
  selectionUid: string;
  selectOptions: SelectOption[];
  submitting: boolean;
  canSubmit: boolean;
  actionLabel: string;
}>();

const emit = defineEmits<{
  (event: "close"): void;
  (event: "update:selection-uid", value: string): void;
  (event: "submit"): void;
}>();
</script>

<style scoped src="./MissionModals.css"></style>
