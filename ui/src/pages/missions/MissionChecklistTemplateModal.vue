<template>
  <BaseModal :open="open" title="Create Checklist from Template" @close="emit('close')">
    <div class="template-modal">
      <label class="field-control full">
        <span>Checklist Name</span>
        <input
          :value="checklistNameDraft"
          type="text"
          placeholder="Mission Checklist"
          @input="emit('update:checklist-name-draft', readInputValue($event))"
        />
      </label>

      <div v-if="templateOptions.length" class="template-modal-list">
        <BaseSelect
          :model-value="selectionUid"
          label="Template"
          :options="selectOptions"
          @update:model-value="emit('update:selection-uid', $event)"
        />
        <p v-if="selectedTemplateOption" class="template-modal-hint">
          {{ selectedTemplateOption.columns }} columns
          <span v-if="selectedTemplateOption.task_rows > 0"> | {{ selectedTemplateOption.task_rows }} tasks </span>
          <span v-if="selectedTemplateOption.source_type === 'csv_import'"> | sourced from CSV import</span>
        </p>
      </div>
      <p v-else class="template-modal-empty">No checklist templates available.</p>

      <div class="template-modal-actions">
        <BaseButton variant="ghost" icon-left="undo" @click="emit('close')">Cancel</BaseButton>
        <BaseButton icon-left="plus" :disabled="submitting || !selectionUid" @click="emit('submit')">
          {{ submitting ? "Creating..." : "Create" }}
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

interface TemplateOption {
  uid: string;
  columns: number;
  task_rows: number;
  source_type: "template" | "csv_import";
}

defineProps<{
  open: boolean;
  checklistNameDraft: string;
  selectionUid: string;
  submitting: boolean;
  templateOptions: TemplateOption[];
  selectOptions: SelectOption[];
  selectedTemplateOption: TemplateOption | undefined;
}>();

const emit = defineEmits<{
  (event: "close"): void;
  (event: "update:checklist-name-draft", value: string): void;
  (event: "update:selection-uid", value: string): void;
  (event: "submit"): void;
}>();

const readInputValue = (event: Event): string => {
  const target = event.target as HTMLInputElement | null;
  return String(target?.value ?? "");
};
</script>

<style scoped src="./MissionModals.css"></style>
