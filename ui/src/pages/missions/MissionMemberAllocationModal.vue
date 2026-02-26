<template>
  <BaseModal :open="open" title="Mission Team Member Allocation" @close="emit('close')">
    <div class="template-modal mission-allocation-modal">
      <p class="template-modal-hint">
        Assign an existing team member to a mission team.
      </p>
      <div class="allocation-grid single-column">
        <section class="allocation-card">
          <BaseSelect
            :model-value="teamUid"
            label="Team"
            :options="teamOptions"
            @update:model-value="emit('update:team-uid', $event)"
          />
          <BaseSelect
            :model-value="memberUid"
            label="Existing Team Member"
            :options="existingMemberOptions"
            @update:model-value="emit('update:member-uid', $event)"
          />
          <p v-if="existingMemberOptions.length <= 1" class="template-modal-empty">
            No assignable team members found for this team.
          </p>
          <div class="allocation-card-actions">
            <BaseButton
              icon-left="link"
              :disabled="submitting || !canAssignExistingMember"
              @click="emit('assign-existing-member')"
            >
              {{ submitting ? "Assigning..." : "Assign Member" }}
            </BaseButton>
            <BaseButton
              variant="secondary"
              icon-left="plus"
              :disabled="submitting"
              @click="emit('open-member-create-workspace')"
            >
              Create New Member
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
  teamUid: string;
  teamOptions: SelectOption[];
  memberUid: string;
  existingMemberOptions: SelectOption[];
  canAssignExistingMember: boolean;
}>();

const emit = defineEmits<{
  (event: "close"): void;
  (event: "update:team-uid", value: string): void;
  (event: "update:member-uid", value: string): void;
  (event: "assign-existing-member"): void;
  (event: "open-member-create-workspace"): void;
}>();
</script>

<style scoped src="./MissionModals.css"></style>
