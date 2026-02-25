<template>
  <article class="stage-card">
    <h4>{{ isCreate ? "Mission Create" : "Mission Edit" }}</h4>
    <div class="field-grid">
      <label class="field-control">
        <span>Mission UID</span>
        <input :value="missionDraftUidLabel" type="text" readonly />
      </label>
      <label class="field-control">
        <span>
          Name
          <span class="required-marker" aria-hidden="true">*</span>
        </span>
        <input
          :value="missionDraftName"
          type="text"
          placeholder="Mission Name"
          required
          aria-required="true"
          @input="emit('update:mission-draft-name', readInputValue($event))"
        />
      </label>
      <label v-if="!isCreate" class="field-control">
        <span>Expiration</span>
        <input
          :value="missionDraftExpiration"
          type="datetime-local"
          @input="emit('update:mission-draft-expiration', readInputValue($event))"
        />
      </label>
      <label v-if="!isCreate" class="field-control full">
        <span>Description</span>
        <textarea
          :value="missionDraftDescription"
          rows="4"
          placeholder="Mission objective and constraints..."
          @input="emit('update:mission-draft-description', readInputValue($event))"
        ></textarea>
      </label>
      <label class="field-control">
        <span>Topic Scope</span>
        <div class="field-inline-control">
          <select :value="missionDraftTopic" @change="emit('update:mission-draft-topic', readSelectValue($event))">
            <option v-for="option in missionTopicOptions" :key="`mission-topic-${option.value}`" :value="option.value">
              {{ option.label }}
            </option>
          </select>
          <BaseButton size="sm" variant="secondary" icon-left="plus" @click="emit('open-topic-create')">New</BaseButton>
        </div>
      </label>
      <label class="field-control">
        <span>Status</span>
        <select :value="missionDraftStatus" @change="emit('update:mission-draft-status', readSelectValue($event))">
          <option v-for="status in missionStatusOptions" :key="status" :value="status">
            {{ missionStatusLabel(status) }}
          </option>
        </select>
      </label>
      <label class="field-control">
        <span>Parent Mission</span>
        <select :value="missionDraftParentUid" @change="emit('update:mission-draft-parent-uid', readSelectValue($event))">
          <option v-for="option in missionParentOptions" :key="`mission-parent-${option.value}`" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <label class="field-control">
        <span>Reference Team</span>
        <select :value="missionDraftTeamUid" @change="emit('update:mission-draft-team-uid', readSelectValue($event))">
          <option v-for="option in missionReferenceTeamOptions" :key="`mission-team-${option.value}`" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <details
        class="mission-advanced-properties full"
        :open="missionAdvancedPropertiesOpen"
        @toggle="handleMissionAdvancedPropertiesToggle"
      >
        <summary class="mission-advanced-properties__summary">
          <span class="mission-advanced-properties__title">Advanced Properties</span>
          <span class="mission-advanced-properties__meta">
            {{ missionAdvancedPropertiesOpen ? "Expanded" : "Folded" }}
          </span>
        </summary>
        <div class="field-grid mission-advanced-properties__grid">
          <label class="field-control">
            <span>Path</span>
            <input
              :value="missionDraftPath"
              type="text"
              placeholder="ops.region.path"
              @input="emit('update:mission-draft-path', readInputValue($event))"
            />
          </label>
          <label class="field-control">
            <span>Classification</span>
            <input
              :value="missionDraftClassification"
              type="text"
              placeholder="UNCLASSIFIED"
              @input="emit('update:mission-draft-classification', readInputValue($event))"
            />
          </label>
          <label class="field-control">
            <span>Tool</span>
            <input
              :value="missionDraftTool"
              type="text"
              placeholder="ATAK"
              @input="emit('update:mission-draft-tool', readInputValue($event))"
            />
          </label>
          <label class="field-control">
            <span>Keywords (comma separated)</span>
            <input
              :value="missionDraftKeywords"
              type="text"
              placeholder="winter,storm,rescue"
              @input="emit('update:mission-draft-keywords', readInputValue($event))"
            />
          </label>
          <label class="field-control">
            <span>Default Role</span>
            <input
              :value="missionDraftDefaultRole"
              type="text"
              placeholder="TEAM_MEMBER"
              @input="emit('update:mission-draft-default-role', readInputValue($event))"
            />
          </label>
          <label class="field-control">
            <span>Owner Role</span>
            <input
              :value="missionDraftOwnerRole"
              type="text"
              placeholder="TEAM_LEAD"
              @input="emit('update:mission-draft-owner-role', readInputValue($event))"
            />
          </label>
          <label class="field-control">
            <span>Mission Priority</span>
            <input
              :value="missionDraftPriority"
              type="number"
              min="0"
              step="1"
              placeholder="1"
              @input="emit('update:mission-draft-priority', readInputValue($event))"
            />
          </label>
          <label class="field-control">
            <span>Mission RDE Role</span>
            <input
              :value="missionDraftMissionRdeRole"
              type="text"
              placeholder="observer"
              @input="emit('update:mission-draft-mission-rde-role', readInputValue($event))"
            />
          </label>
          <label class="field-control">
            <span>Token</span>
            <input
              :value="missionDraftToken"
              type="text"
              placeholder="optional token"
              @input="emit('update:mission-draft-token', readInputValue($event))"
            />
          </label>
          <label class="field-control">
            <span>Feeds (comma separated)</span>
            <input
              :value="missionDraftFeeds"
              type="text"
              placeholder="feed-alpha,feed-bravo"
              @input="emit('update:mission-draft-feeds', readInputValue($event))"
            />
          </label>
          <label v-if="isCreate" class="field-control">
            <span>Expiration</span>
            <input
              :value="missionDraftExpiration"
              type="datetime-local"
              @input="emit('update:mission-draft-expiration', readInputValue($event))"
            />
          </label>
          <label class="field-control">
            <span>Invite Only</span>
            <select :value="String(missionDraftInviteOnly)" @change="emit('update:mission-draft-invite-only', readBooleanValue($event))">
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </label>
        </div>
      </details>
      <label class="field-control full">
        <span>Reference Zones</span>
        <select class="field-control-multi" multiple :value="missionDraftZoneUids" @change="onZoneSelectionChange">
          <option v-for="option in missionReferenceZoneOptions" :key="`mission-zone-${option.value}`" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <small class="field-note">Use Ctrl/Cmd + click to select multiple zones.</small>
      </label>
      <label class="field-control full">
        <span>Reference Assets</span>
        <select class="field-control-multi" multiple :value="missionDraftAssetUids" @change="onAssetSelectionChange">
          <option v-for="option in missionReferenceAssetOptions" :key="`mission-asset-${option.value}`" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <small class="field-note">Preferred assets can be finalized in Assign Assets once tasks and members exist.</small>
      </label>
      <label v-if="isCreate" class="field-control full">
        <span>Description</span>
        <textarea
          :value="missionDraftDescription"
          rows="4"
          placeholder="Mission objective and constraints..."
          @input="emit('update:mission-draft-description', readInputValue($event))"
        ></textarea>
      </label>
    </div>
  </article>

  <article class="stage-card">
    <h4>{{ isCreate ? "Create Preview" : "Edit Preview" }}</h4>
    <ul class="stack-list">
      <li><strong>Name</strong><span>{{ missionDraftName || "-" }}</span></li>
      <li><strong>UID</strong><span>{{ missionDraftUidLabel }}</span></li>
      <li><strong>Topic</strong><span>{{ missionDraftTopic || "-" }}</span></li>
      <li>
        <strong>Status</strong>
        <span class="mission-status-chip" :class="missionStatusChipClass(missionDraftStatus)">
          {{ missionStatusLabel(missionDraftStatus) }}
        </span>
      </li>
      <li><strong>Parent Mission</strong><span>{{ missionDraftParentLabel }}</span></li>
      <li><strong>Reference Team</strong><span>{{ missionDraftTeamLabel }}</span></li>
      <li><strong>Reference Zones</strong><span>{{ missionDraftZoneLabel }}</span></li>
      <li><strong>Reference Assets</strong><span>{{ missionDraftAssetLabel }}</span></li>
      <li><strong>Invite Only</strong><span>{{ missionDraftInviteOnly ? "YES" : "NO" }}</span></li>
      <li><strong>Description</strong><span>{{ missionDraftDescription || "-" }}</span></li>
    </ul>
  </article>
</template>

<script setup lang="ts">
import BaseButton from "../../components/BaseButton.vue";
import { getMissionStatusLabel } from "./mission-status";
import { getMissionStatusTone } from "./mission-status";

interface SelectOption {
  value: string;
  label: string;
}

defineProps<{
  isCreate: boolean;
  missionDraftUidLabel: string;
  missionDraftName: string;
  missionDraftTopic: string;
  missionDraftStatus: string;
  missionDraftDescription: string;
  missionDraftParentUid: string;
  missionDraftTeamUid: string;
  missionDraftPath: string;
  missionDraftClassification: string;
  missionDraftTool: string;
  missionDraftKeywords: string;
  missionDraftDefaultRole: string;
  missionDraftOwnerRole: string;
  missionDraftPriority: string;
  missionDraftMissionRdeRole: string;
  missionDraftToken: string;
  missionDraftFeeds: string;
  missionDraftExpiration: string;
  missionDraftInviteOnly: boolean;
  missionDraftZoneUids: string[];
  missionDraftAssetUids: string[];
  missionStatusOptions: string[];
  missionTopicOptions: SelectOption[];
  missionParentOptions: SelectOption[];
  missionReferenceTeamOptions: SelectOption[];
  missionReferenceZoneOptions: SelectOption[];
  missionReferenceAssetOptions: SelectOption[];
  missionDraftParentLabel: string;
  missionDraftTeamLabel: string;
  missionDraftZoneLabel: string;
  missionDraftAssetLabel: string;
  missionAdvancedPropertiesOpen: boolean;
}>();

const emit = defineEmits<{
  (event: "open-topic-create"): void;
  (event: "toggle-mission-advanced-properties", open: boolean): void;
  (event: "update:mission-draft-name", value: string): void;
  (event: "update:mission-draft-topic", value: string): void;
  (event: "update:mission-draft-status", value: string): void;
  (event: "update:mission-draft-description", value: string): void;
  (event: "update:mission-draft-parent-uid", value: string): void;
  (event: "update:mission-draft-team-uid", value: string): void;
  (event: "update:mission-draft-path", value: string): void;
  (event: "update:mission-draft-classification", value: string): void;
  (event: "update:mission-draft-tool", value: string): void;
  (event: "update:mission-draft-keywords", value: string): void;
  (event: "update:mission-draft-default-role", value: string): void;
  (event: "update:mission-draft-owner-role", value: string): void;
  (event: "update:mission-draft-priority", value: string): void;
  (event: "update:mission-draft-mission-rde-role", value: string): void;
  (event: "update:mission-draft-token", value: string): void;
  (event: "update:mission-draft-feeds", value: string): void;
  (event: "update:mission-draft-expiration", value: string): void;
  (event: "update:mission-draft-invite-only", value: boolean): void;
  (event: "update:mission-draft-zone-uids", value: string[]): void;
  (event: "update:mission-draft-asset-uids", value: string[]): void;
}>();

const readInputValue = (event: Event): string => {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement | null;
  return String(target?.value ?? "");
};

const readSelectValue = (event: Event): string => {
  const target = event.target as HTMLSelectElement | null;
  return String(target?.value ?? "");
};

const readBooleanValue = (event: Event): boolean => readSelectValue(event) === "true";

const readMultiSelectValues = (event: Event): string[] => {
  const target = event.target as HTMLSelectElement | null;
  if (!target) {
    return [];
  }
  return Array.from(target.selectedOptions)
    .map((entry) => entry.value.trim())
    .filter((entry) => entry.length > 0);
};

const handleMissionAdvancedPropertiesToggle = (event: Event) => {
  const target = event.currentTarget as HTMLDetailsElement | null;
  emit("toggle-mission-advanced-properties", Boolean(target?.open));
};

const onZoneSelectionChange = (event: Event) => {
  emit("update:mission-draft-zone-uids", readMultiSelectValues(event));
};

const onAssetSelectionChange = (event: Event) => {
  emit("update:mission-draft-asset-uids", readMultiSelectValues(event));
};

const missionStatusLabel = (value?: string | null): string => getMissionStatusLabel(value);

const missionStatusChipClass = (value?: string | null): string => {
  return `mission-status-chip--${getMissionStatusTone(value)}`;
};
</script>

<style scoped>
.stack-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.stack-list li {
  border: 1px solid rgba(55, 242, 255, 0.2);
  border-radius: 8px;
  background: rgba(7, 18, 28, 0.72);
  padding: 8px;
  display: grid;
  gap: 4px;
}

.stack-list li strong {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.stack-list li span {
  font-size: 11px;
  color: rgba(204, 248, 255, 0.8);
}

.mission-status-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgb(var(--CosmicUI-Secondary-rgb) / 45%);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  background: var(--cui-mission-status-chip-background);
  color: rgb(var(--CosmicUI-Secondary-rgb) / 92%);
}

.mission-status-chip--active {
  border-color: var(--cui-mission-status-active);
  color: var(--cui-mission-status-active-text);
  box-shadow: 0 0 12px var(--cui-mission-status-active-glow);
}

.mission-status-chip--pending {
  border-color: var(--cui-mission-status-pending);
  color: var(--cui-mission-status-pending-text);
  box-shadow: 0 0 12px var(--cui-mission-status-pending-glow);
}

.mission-status-chip--success {
  border-color: var(--cui-mission-status-success);
  color: var(--cui-mission-status-success-text);
  box-shadow: 0 0 12px var(--cui-mission-status-success-glow);
}

.mission-status-chip--failed {
  border-color: var(--cui-mission-status-failed);
  color: var(--cui-mission-status-failed-text);
  box-shadow: 0 0 12px var(--cui-mission-status-failed-glow);
}

.mission-status-chip--deleted {
  border-color: var(--cui-mission-status-deleted);
  color: var(--cui-mission-status-deleted-text);
  box-shadow: 0 0 12px var(--cui-mission-status-deleted-glow);
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.mission-advanced-properties {
  grid-column: 1 / -1;
  border: 1px solid rgba(55, 242, 255, 0.34);
  border-radius: 10px;
  background: rgba(5, 14, 22, 0.62);
  overflow: hidden;
}

.mission-advanced-properties__summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  list-style: none;
  border-bottom: 1px solid rgba(55, 242, 255, 0.2);
  background: linear-gradient(180deg, rgba(9, 24, 36, 0.92), rgba(7, 17, 27, 0.95));
}

.mission-advanced-properties__summary::-webkit-details-marker {
  display: none;
}

.mission-advanced-properties__title {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(211, 250, 255, 0.9);
}

.mission-advanced-properties__meta {
  margin-left: auto;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(191, 246, 255, 0.72);
}

.mission-advanced-properties__summary::after {
  content: "v";
  font-size: 12px;
  line-height: 1;
  color: rgba(191, 246, 255, 0.82);
  transform: rotate(-90deg);
  transition: transform 150ms ease;
}

.mission-advanced-properties[open] .mission-advanced-properties__summary::after {
  transform: rotate(0deg);
}

.mission-advanced-properties__grid {
  padding: 12px;
}

.field-inline-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.field-inline-control select {
  flex: 1;
}

.field-control-multi {
  min-height: 108px;
}

.field-note {
  margin: 0;
  font-size: 10px;
  letter-spacing: 0.08em;
  color: rgba(191, 246, 255, 0.72);
}

.required-marker {
  color: rgba(255, 179, 92, 0.95);
  margin-left: 4px;
}

@media (max-width: 800px) {
  .field-grid {
    grid-template-columns: 1fr;
  }
}
</style>
