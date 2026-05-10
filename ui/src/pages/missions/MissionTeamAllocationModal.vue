<template>
  <BaseModal :open="open" title="Mission Team Allocation" @close="emit('close')">
    <div class="template-modal mission-allocation-modal">
      <p class="template-modal-hint">
        Link an existing team to this mission or create a new mission team.
      </p>
      <div class="allocation-grid">
        <section class="allocation-card">
          <h4>Assign Existing Team</h4>
          <BaseSelect
            :model-value="existingTeamUid"
            label="Existing Team"
            :options="existingTeamOptions"
            @update:model-value="emit('update:existing-team-uid', $event)"
          />
          <p v-if="existingTeamOptions.length <= 1" class="template-modal-empty">
            No unassigned teams are currently available.
          </p>
          <div class="allocation-card-actions">
            <BaseButton
              icon-left="link"
              :disabled="submitting || !canAssignExistingTeam"
              @click="emit('assign-existing-team')"
            >
              {{ submitting ? "Assigning..." : "Assign Team" }}
            </BaseButton>
          </div>
        </section>

        <section class="allocation-card">
          <h4>Create New Team</h4>
          <label class="field-control full">
            <span>Team Name</span>
            <input
              :value="newTeamName"
              type="text"
              maxlength="96"
              placeholder="Mission Team"
              @input="emit('update:new-team-name', readInputValue($event))"
            />
          </label>
          <label class="field-control full">
            <span>Description</span>
            <textarea
              :value="newTeamDescription"
              rows="3"
              maxlength="512"
              placeholder="Operational role and purpose"
              @input="emit('update:new-team-description', readTextareaValue($event))"
            ></textarea>
          </label>
          <div class="allocation-card-actions">
            <BaseButton icon-left="plus" :disabled="submitting || !canCreateMissionTeam" @click="emit('create-team')">
              {{ submitting ? "Creating..." : "Create Team" }}
            </BaseButton>
          </div>
        </section>
      </div>

      <div class="template-modal-actions">
        <BaseButton variant="ghost" icon-left="undo" :disabled="submitting" @click="emit('close')">
          Cancel
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
  submitting: boolean;
  existingTeamUid: string;
  existingTeamOptions: SelectOption[];
  canAssignExistingTeam: boolean;
  newTeamName: string;
  newTeamDescription: string;
  canCreateMissionTeam: boolean;
}>();

const emit = defineEmits<{
  (event: "close"): void;
  (event: "update:existing-team-uid", value: string): void;
  (event: "update:new-team-name", value: string): void;
  (event: "update:new-team-description", value: string): void;
  (event: "assign-existing-team"): void;
  (event: "create-team"): void;
}>();

const readInputValue = (event: Event): string => {
  const target = event.target as HTMLInputElement | null;
  return String(target?.value ?? "");
};

const readTextareaValue = (event: Event): string => {
  const target = event.target as HTMLTextAreaElement | null;
  return String(target?.value ?? "");
};
</script>

<style scoped src="./MissionModals.css"></style>
