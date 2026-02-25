<template>
  <div class="missions-workspace">
    <div class="registry-shell">
      <CosmicTopStatus :title="isChecklistPrimaryTab ? 'Checklist' : 'Mission Workspace'" />

      <section v-if="!isChecklistPrimaryTab" class="mission-kpis">
        <article class="kpi-card">
          <span class="kpi-label">Total Missions</span>
          <strong class="kpi-value">{{ missions.length }}</strong>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">Active</span>
          <strong class="kpi-value">{{ activeMissions }}</strong>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">Checklists</span>
          <strong class="kpi-value">{{ checklists.length }}</strong>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">Assets</span>
          <strong class="kpi-value">{{ assets.length }}</strong>
        </article>
      </section>

      <div class="registry-grid" :class="{ 'registry-grid-full': !showMissionDirectoryPanel }">
        <aside v-if="showMissionDirectoryPanel" class="panel registry-tree">
          <div class="panel-header">
            <div>
              <div class="panel-title">Mission Directory</div>
              <div class="panel-subtitle">Select Mission</div>
            </div>
            <div class="panel-chip">{{ missions.length }} records</div>
          </div>

          <div class="tree-list">
            <button
              v-for="mission in missions"
              :key="mission.uid"
              class="tree-item"
              :class="{ active: selectedMissionUid === mission.uid }"
              type="button"
              @click="selectMission(mission.uid)"
            >
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">{{ mission.mission_name }}</span>
              <span class="tree-count">{{ mission.status }}</span>
            </button>
          </div>
          <div class="mission-directory-actions">
            <button
              class="panel-tab mission-directory-create-button"
              :class="{ active: secondaryScreen === 'missionCreate' }"
              type="button"
              @click="setSecondaryScreen('missionCreate')"
            >
              Mission Create
            </button>
          </div>
        </aside>

        <section class="panel registry-main">
          <div v-if="!isChecklistPrimaryTab" class="panel-header panel-header-mission">
            <div class="panel-header-mission-main">
              <div class="panel-title">{{ workspacePanelTitle }}</div>
              <div class="panel-subtitle">{{ workspacePanelSubtitle }}</div>
            </div>
            <div class="mission-end-timer mission-end-timer--header" :class="{ 'mission-end-timer--inactive': !missionEndCountdown.hasEnd }">
              <div class="mission-end-timer__label">
                <span class="mission-end-timer__dot" aria-hidden="true"></span>
                Mission End
              </div>
              <div class="mission-end-timer__display mono">{{ missionEndCountdown.display }}</div>
              <div class="mission-end-timer__units">
                <span>Days</span>
                <span>Hrs</span>
                <span>Min</span>
              </div>
            </div>
          </div>

          <article class="screen-shell">
            <header v-if="showScreenHeader" class="screen-header">
              <h3>{{ currentScreen.title }}</h3>
              <p>{{ currentScreen.subtitle }}</p>
              <div class="screen-actions">
                <BaseButton
                  v-if="secondaryScreen === 'checklistImportCsv'"
                  variant="secondary"
                  size="sm"
                  icon-left="chevron-left"
                  @click="navigateToChecklistTemplateList"
                >
                  Template List
                </BaseButton>
                <BaseButton
                  v-for="action in screenActions"
                  :key="`${secondaryScreen}-${action}`"
                  variant="secondary"
                  size="sm"
                  :icon-left="iconForAction(action)"
                  @click="previewAction(action)"
                >
                  {{ action }}
                </BaseButton>
              </div>
            </header>

            <div v-if="secondaryScreen === 'missionDirectory'" class="screen-grid two-col">
              <article class="stage-card">
                <h4>Mission Registry</h4>
                <table class="mini-table">
                  <thead>
                    <tr>
                      <th>Mission</th>
                      <th>Status</th>
                      <th>Checklists</th>
                      <th>Open Tasks</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="mission in missions" :key="`registry-${mission.uid}`">
                      <td>{{ mission.mission_name }}</td>
                      <td>{{ mission.status }}</td>
                      <td>{{ missionChecklistCountByMission.get(mission.uid) ?? 0 }}</td>
                      <td>{{ missionOpenTaskCountByMission.get(mission.uid) ?? 0 }}</td>
                    </tr>
                  </tbody>
                </table>
              </article>

              <article class="stage-card">
                <h4>Selected Mission</h4>
                <ul class="stack-list">
                  <li><strong>Mission ID</strong><span>{{ selectedMission?.uid || "Not Selected" }}</span></li>
                  <li><strong>Topic Scope</strong><span>{{ selectedMission?.topic || "-" }}</span></li>
                  <li><strong>Status</strong><span>{{ selectedMission?.status || "-" }}</span></li>
                  <li><strong>Team Members</strong><span>{{ missionMembers.length }}</span></li>
                  <li><strong>Assigned Assets</strong><span>{{ missionAssets.length }}</span></li>
                </ul>
              </article>
            </div>

            <div v-else-if="isMissionFormScreen" class="screen-grid two-col">
              <MissionFormScreen
                :is-create="isMissionCreateScreen"
                :mission-draft-uid-label="missionDraftUidLabel"
                :mission-draft-name="missionDraftName"
                :mission-draft-topic="missionDraftTopic"
                :mission-draft-status="missionDraftStatus"
                :mission-draft-description="missionDraftDescription"
                :mission-draft-parent-uid="missionDraftParentUid"
                :mission-draft-team-uid="missionDraftTeamUid"
                :mission-draft-path="missionDraftPath"
                :mission-draft-classification="missionDraftClassification"
                :mission-draft-tool="missionDraftTool"
                :mission-draft-keywords="missionDraftKeywords"
                :mission-draft-default-role="missionDraftDefaultRole"
                :mission-draft-owner-role="missionDraftOwnerRole"
                :mission-draft-priority="missionDraftPriority"
                :mission-draft-mission-rde-role="missionDraftMissionRdeRole"
                :mission-draft-token="missionDraftToken"
                :mission-draft-feeds="missionDraftFeeds"
                :mission-draft-expiration="missionDraftExpiration"
                :mission-draft-invite-only="missionDraftInviteOnly"
                :mission-draft-zone-uids="missionDraftZoneUids"
                :mission-draft-asset-uids="missionDraftAssetUids"
                :mission-status-options="missionStatusOptions"
                :mission-topic-options="missionTopicOptions"
                :mission-parent-options="missionParentOptions"
                :mission-reference-team-options="missionReferenceTeamOptions"
                :mission-reference-zone-options="missionReferenceZoneOptions"
                :mission-reference-asset-options="missionReferenceAssetOptions"
                :mission-draft-parent-label="missionDraftParentLabel"
                :mission-draft-team-label="missionDraftTeamLabel"
                :mission-draft-zone-label="missionDraftZoneLabel"
                :mission-draft-asset-label="missionDraftAssetLabel"
                :mission-advanced-properties-open="missionAdvancedPropertiesOpen"
                @open-topic-create="openTopicCreatePage"
                @toggle-mission-advanced-properties="missionAdvancedPropertiesOpen = $event"
                @update:mission-draft-name="missionDraftName = $event"
                @update:mission-draft-topic="missionDraftTopic = $event"
                @update:mission-draft-status="missionDraftStatus = $event"
                @update:mission-draft-description="missionDraftDescription = $event"
                @update:mission-draft-parent-uid="missionDraftParentUid = $event"
                @update:mission-draft-team-uid="missionDraftTeamUid = $event"
                @update:mission-draft-path="missionDraftPath = $event"
                @update:mission-draft-classification="missionDraftClassification = $event"
                @update:mission-draft-tool="missionDraftTool = $event"
                @update:mission-draft-keywords="missionDraftKeywords = $event"
                @update:mission-draft-default-role="missionDraftDefaultRole = $event"
                @update:mission-draft-owner-role="missionDraftOwnerRole = $event"
                @update:mission-draft-priority="missionDraftPriority = $event"
                @update:mission-draft-mission-rde-role="missionDraftMissionRdeRole = $event"
                @update:mission-draft-token="missionDraftToken = $event"
                @update:mission-draft-feeds="missionDraftFeeds = $event"
                @update:mission-draft-expiration="missionDraftExpiration = $event"
                @update:mission-draft-invite-only="missionDraftInviteOnly = $event"
                @update:mission-draft-zone-uids="missionDraftZoneUids = $event"
                @update:mission-draft-asset-uids="missionDraftAssetUids = $event"
              />
            </div>

            <MissionOverviewScreen
              v-else-if="secondaryScreen === 'missionOverview'"
              :mission-status="selectedMission?.status || 'UNSCOPED'"
              :checklist-runs="missionChecklists.length"
              :open-tasks="missionOpenTaskTotal"
              :team-members="missionMembers.length"
              :assigned-assets="missionAssets.length"
              :assigned-zones="assignedZones.length"
              :mission-uid="selectedMission?.uid || ''"
              :mission-topic-name="selectedMissionTopicName"
              :mission-description="selectedMission?.description || ''"
              :mission-total-tasks="missionTotalTasks"
              :board-counts="boardCounts"
              :board-lane-tasks="boardLaneTasks"
              :mission-audit="missionAudit"
              @request-action="previewAction"
            />

            <div v-else-if="secondaryScreen === 'missionExcheckBoard'" class="screen-grid">
              <article class="stage-card">
                <h4>Mission Excheck Board</h4>
                <div class="board-lanes">
                  <div class="board-col board-lane board-lane-pending">
                    <h5>Pending</h5>
                    <span>{{ boardCounts.pending }}</span>
                    <ul class="lane-list">
                      <li v-for="task in boardLaneTasks.pending" :key="`pending-${task.id}`">
                        <strong>{{ task.name }}</strong>
                        <span>{{ task.meta }}</span>
                      </li>
                    </ul>
                  </div>
                  <div class="board-col board-lane board-lane-late">
                    <h5>Late</h5>
                    <span>{{ boardCounts.late }}</span>
                    <ul class="lane-list">
                      <li v-for="task in boardLaneTasks.late" :key="`late-${task.id}`">
                        <strong>{{ task.name }}</strong>
                        <span>{{ task.meta }}</span>
                      </li>
                    </ul>
                  </div>
                  <div class="board-col board-lane board-lane-complete">
                    <h5>Complete</h5>
                    <span>{{ boardCounts.complete }}</span>
                    <ul class="lane-list">
                      <li v-for="task in boardLaneTasks.complete" :key="`complete-${task.id}`">
                        <strong>{{ task.name }}</strong>
                        <span>{{ task.meta }}</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </article>
            </div>

            <div v-else-if="secondaryScreen === 'checklistImportCsv'" class="screen-grid two-col">
              <article class="stage-card">
                <h4>CSV Upload</h4>
                <div class="field-grid single-col">
                  <label class="field-control full">
                    <span>Select CSV File</span>
                    <input
                      ref="csvUploadInputRef"
                      class="csv-upload-native"
                      type="file"
                      accept=".csv,text/csv"
                      @change="handleCsvUpload"
                    />
                    <div class="csv-upload-picker">
                      <BaseButton size="sm" variant="secondary" icon-left="upload" @click="openCsvUploadPicker">
                        Choose File
                      </BaseButton>
                      <span class="csv-upload-filename">{{ csvImportFilename || "No file chosen" }}</span>
                    </div>
                  </label>
                </div>
                <ul class="stack-list csv-meta">
                  <li>
                    <strong>Selected File</strong>
                    <span>{{ csvImportFilename || "No file selected" }}</span>
                  </li>
                  <li>
                    <strong>Header Columns</strong>
                    <span>{{ csvImportHeaders.length }}</span>
                  </li>
                  <li>
                    <strong>Task Rows</strong>
                    <span>{{ csvImportRows.length }}</span>
                  </li>
                  <li>
                    <strong>Mission Scope</strong>
                    <span>{{ selectedMission?.mission_name || "Unscoped import" }}</span>
                  </li>
                </ul>
              </article>

              <article class="stage-card">
                <h4>CSV Task Preview</h4>
                <div v-if="csvImportHeaders.length && csvImportRows.length" class="csv-preview">
                  <table class="mini-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th v-for="(header, headerIndex) in csvImportHeaders" :key="`csv-header-${headerIndex}`">
                          {{ header }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, rowIndex) in csvImportPreviewRows" :key="`csv-row-${rowIndex}`">
                        <td>{{ rowIndex + 1 }}</td>
                        <td
                          v-for="(header, columnIndex) in csvImportHeaders"
                          :key="`csv-cell-${rowIndex}-${columnIndex}`"
                        >
                          {{ row[columnIndex] || "-" }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  <p v-if="csvImportRows.length > csvImportPreviewRows.length" class="csv-preview-note">
                    Showing first {{ csvImportPreviewRows.length }} of {{ csvImportRows.length }} task rows.
                  </p>
                </div>
                <div v-else class="builder-preview">
                  <p>Upload a CSV file to preview its header and task rows.</p>
                  <p>The first row becomes the checklist header and each remaining row becomes a task.</p>
                </div>
              </article>
            </div>
            <MissionChecklistWorkspaceScreen
              v-else-if="showChecklistArea"
              :checklist-search-query="checklistSearchQuery"
              :checklist-workspace-view="checklistWorkspaceView"
              :checklist-active-count="checklistActiveCount"
              :checklist-template-count="checklistTemplateCount"
              :checklist-detail-record="checklistDetailRecord"
              :can-create-from-detail-template="canCreateFromDetailTemplate"
              :checklist-link-mission-submitting="checklistLinkMissionSubmitting"
              :checklist-delete-busy="checklistDeleteBusy"
              :checklist-task-due-draft="checklistTaskDueDraft"
              :checklist-detail-columns="checklistDetailColumns"
              :checklist-detail-rows="checklistDetailRows"
              :checklist-task-status-busy-by-task-uid="checklistTaskStatusBusyByTaskUid"
              :filtered-checklist-cards="filteredChecklistCards"
              :filtered-checklist-templates="filteredChecklistTemplates"
              :checklist-template-editor-selection-uid="checklistTemplateEditorSelectionUid"
              :checklist-template-editor-selection-source-type="checklistTemplateEditorSelectionSourceType"
              :checklist-template-editor-title="checklistTemplateEditorTitle"
              :checklist-template-editor-subtitle="checklistTemplateEditorSubtitle"
              :can-add-checklist-template-column="canAddChecklistTemplateColumn"
              :can-save-checklist-template-draft="canSaveChecklistTemplateDraft"
              :can-save-checklist-template-draft-as-new="canSaveChecklistTemplateDraftAsNew"
              :can-clone-checklist-template-draft="canCloneChecklistTemplateDraft"
              :can-archive-checklist-template-draft="canArchiveChecklistTemplateDraft"
              :can-convert-checklist-template-draft="canConvertChecklistTemplateDraft"
              :can-delete-checklist-template-draft="canDeleteChecklistTemplateDraft"
              :checklist-template-draft-name="checklistTemplateDraftName"
              :checklist-template-draft-description="checklistTemplateDraftDescription"
              :is-checklist-template-draft-readonly="isChecklistTemplateDraftReadonly"
              :checklist-template-draft-columns="checklistTemplateDraftColumns"
              :checklist-template-column-type-options="checklistTemplateColumnTypeOptions"
              :checklist-template-editor-status-label="checklistTemplateEditorStatusLabel"
              :set-checklist-workspace-view="setChecklistWorkspaceView"
              :open-checklist-creation-modal="openChecklistCreationModal"
              :show-checklist-filter-notice="showChecklistFilterNotice"
              :open-template-builder-from-checklist="openTemplateBuilderFromChecklist"
              :open-checklist-import-from-checklist="openChecklistImportFromChecklist"
              :close-checklist-detail-view="closeChecklistDetailView"
              :checklist-description-label="checklistDescriptionLabel"
              :mode-chip-class="modeChipClass"
              :sync-chip-class="syncChipClass"
              :status-chip-class="statusChipClass"
              :checklist-origin-label="checklistOriginLabel"
              :checklist-mission-label="checklistMissionLabel"
              :create-checklist-from-detail-template="createChecklistFromDetailTemplate"
              :open-checklist-mission-link-modal="openChecklistMissionLinkModal"
              :delete-checklist-from-detail="deleteChecklistFromDetail"
              :progress-width="progressWidth"
              :add-checklist-task-from-detail="addChecklistTaskFromDetail"
              :toggle-checklist-task-done="toggleChecklistTaskDone"
              :open-checklist-detail-view="openChecklistDetailView"
              :format-checklist-date-time="formatChecklistDateTime"
              :select-checklist-template-for-editor="selectChecklistTemplateForEditor"
              :start-new-checklist-template-draft="startNewChecklistTemplateDraft"
              :add-checklist-template-column="addChecklistTemplateColumn"
              :save-checklist-template-draft="saveChecklistTemplateDraft"
              :save-checklist-template-draft-as-new="saveChecklistTemplateDraftAsNew"
              :clone-checklist-template-draft="cloneChecklistTemplateDraft"
              :archive-checklist-template-draft="archiveChecklistTemplateDraft"
              :convert-checklist-template-draft-to-server-template="convertChecklistTemplateDraftToServerTemplate"
              :delete-checklist-template-draft="deleteChecklistTemplateDraft"
              :is-checklist-template-due-column="isChecklistTemplateDueColumn"
              :set-checklist-template-column-name="setChecklistTemplateColumnName"
              :set-checklist-template-column-type="setChecklistTemplateColumnType"
              :set-checklist-template-column-editable="setChecklistTemplateColumnEditable"
              :checklist-template-column-color-value="checklistTemplateColumnColorValue"
              :set-checklist-template-column-background-color="setChecklistTemplateColumnBackgroundColor"
              :set-checklist-template-column-text-color="setChecklistTemplateColumnTextColor"
              :can-move-checklist-template-column-up="canMoveChecklistTemplateColumnUp"
              :move-checklist-template-column-up="moveChecklistTemplateColumnUp"
              :can-move-checklist-template-column-down="canMoveChecklistTemplateColumnDown"
              :move-checklist-template-column-down="moveChecklistTemplateColumnDown"
              :can-delete-checklist-template-column="canDeleteChecklistTemplateColumn"
              :delete-checklist-template-column="deleteChecklistTemplateColumn"
              @update:checklist-search-query="setChecklistSearchQuery"
              @update:checklist-task-due-draft="setChecklistTaskDueDraft"
              @update:checklist-template-draft-name="setChecklistTemplateDraftName"
              @update:checklist-template-draft-description="setChecklistTemplateDraftDescription"
            />

            <MissionOperationsScreen
              v-else
              :secondary-screen="secondaryScreen"
              :show-asset-area="showAssetArea"
              :mission-teams="missionTeams"
              :mission-members="missionMembers"
              :mission-assets="missionAssets"
              :mission-assignments="missionAssignments"
              :zones="zones"
              :assigned-zones="assignedZones"
              :zone-coverage-percent="zoneCoveragePercent"
              :selected-mission-topic="selectedMission?.topic || ''"
              :preview-action="previewAction"
              :toggle-zone="toggleZone"
            />
          </article>
        </section>
      </div>
    </div>

    <MissionTeamAllocationModal
      :open="teamAllocationModalOpen"
      :submitting="teamAllocationSubmitting"
      :existing-team-uid="teamAllocationExistingTeamUid"
      :existing-team-options="teamAllocationExistingTeamOptions"
      :can-assign-existing-team="canAssignExistingTeam"
      :new-team-name="teamAllocationNewTeamName"
      :new-team-description="teamAllocationNewTeamDescription"
      :can-create-mission-team="canCreateMissionTeam"
      @close="closeTeamAllocationModal"
      @update:existing-team-uid="teamAllocationExistingTeamUid = $event"
      @update:new-team-name="teamAllocationNewTeamName = $event"
      @update:new-team-description="teamAllocationNewTeamDescription = $event"
      @assign-existing-team="assignExistingTeamToMission"
      @create-team="createMissionTeamFromModal"
    />

    <MissionMemberAllocationModal
      :open="memberAllocationModalOpen"
      :submitting="memberAllocationSubmitting"
      :team-uid="memberAllocationTeamUid"
      :team-options="memberAllocationTeamOptions"
      :member-uid="memberAllocationMemberUid"
      :existing-member-options="memberAllocationExistingMemberOptions"
      :can-assign-existing-member="canAssignExistingMember"
      @close="closeMemberAllocationModal"
      @update:team-uid="memberAllocationTeamUid = $event"
      @update:member-uid="memberAllocationMemberUid = $event"
      @assign-existing-member="assignExistingMemberToTeam"
      @open-member-create-workspace="openTeamMemberCreateWorkspace"
    />

    <MissionChecklistTemplateModal
      :open="checklistTemplateModalOpen"
      :checklist-name-draft="checklistTemplateNameDraft"
      :selection-uid="checklistTemplateSelectionUid"
      :submitting="checklistTemplateSubmitting"
      :template-options="checklistTemplateOptions"
      :select-options="checklistTemplateSelectOptions"
      :selected-template-option="selectedChecklistTemplateOption"
      @close="closeChecklistTemplateModal"
      @update:checklist-name-draft="checklistTemplateNameDraft = $event"
      @update:selection-uid="checklistTemplateSelectionUid = $event"
      @submit="submitChecklistTemplateSelection"
    />

    <MissionChecklistMissionLinkModal
      :open="checklistLinkMissionModalOpen"
      :selection-uid="checklistLinkMissionSelectionUid"
      :select-options="checklistMissionLinkSelectOptions"
      :submitting="checklistLinkMissionSubmitting"
      :can-submit="canSubmitChecklistMissionLink"
      :action-label="checklistLinkMissionActionLabel"
      @close="closeChecklistMissionLinkModal"
      @update:selection-uid="checklistLinkMissionSelectionUid = $event"
      @submit="submitChecklistMissionLink"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { ApiError } from "../api/client";
import { del as deleteRequest, get, patch as patchRequest, post, put } from "../api/client";
import { endpoints } from "../api/endpoints";
import BaseButton from "../components/BaseButton.vue";
import CosmicTopStatus from "../components/cosmic/CosmicTopStatus.vue";
import MissionFormScreen from "./missions/MissionFormScreen.vue";
import MissionChecklistWorkspaceScreen from "./missions/MissionChecklistWorkspaceScreen.vue";
import MissionChecklistMissionLinkModal from "./missions/MissionChecklistMissionLinkModal.vue";
import MissionChecklistTemplateModal from "./missions/MissionChecklistTemplateModal.vue";
import MissionMemberAllocationModal from "./missions/MissionMemberAllocationModal.vue";
import MissionOperationsScreen from "./missions/MissionOperationsScreen.vue";
import MissionOverviewScreen from "./missions/MissionOverviewScreen.vue";
import MissionTeamAllocationModal from "./missions/MissionTeamAllocationModal.vue";
import { useChecklistTemplateDraft } from "../composables/useChecklistTemplateDraft";
import { useChecklistTemplateCrud } from "../composables/useChecklistTemplateCrud";
import { useToastStore } from "../stores/toasts";
import { loadJson, saveJson } from "../utils/storage";
import { resolveTeamMemberPrimaryLabel } from "../utils/team-members";

type PrimaryTab = "mission" | "checklists";

type ScreenId =
  | "missionDirectory"
  | "missionCreate"
  | "missionEdit"
  | "missionOverview"
  | "missionTeamMembers"
  | "assignAssets"
  | "assignZones"
  | "assetRegistry"
  | "checklistOverview"
  | "checklistDetails"
  | "checklistCreation"
  | "checklistRunDetail"
  | "taskAssignmentWorkspace"
  | "checklistImportCsv"
  | "checklistPublish"
  | "checklistProgress"
  | "missionExcheckBoard";

type ButtonIconName =
  | "refresh"
  | "plus"
  | "edit"
  | "trash"
  | "check"
  | "download"
  | "ban"
  | "unban"
  | "blackhole"
  | "filter"
  | "eye"
  | "save"
  | "link"
  | "upload"
  | "undo"
  | "send"
  | "route"
  | "users"
  | "help"
  | "list"
  | "chevron-left"
  | "chevron-right"
  | "layers"
  | "file"
  | "image"
  | "fingerprint"
  | "settings"
  | "tool";

interface Mission {
  uid: string;
  mission_name: string;
  description: string;
  topic: string;
  status: string;
  zone_ids: string[];
  path: string;
  classification: string;
  tool: string;
  keywords: string[];
  parent_uid: string;
  feeds: string[];
  default_role: string;
  mission_priority: number | null;
  owner_role: string;
  token: string;
  invite_only: boolean;
  expiration: string;
  mission_rde_role: string;
  asset_uids: string[];
}

interface Checklist {
  uid: string;
  mission_uid: string;
  name: string;
  description: string;
  created_at: string;
  mode: string;
  sync_state: string;
  origin_type: string;
  checklist_status: string;
  progress: number;
  pending_count: number;
  late_count: number;
  complete_count: number;
  tasks: Array<{
    id: string;
    number: number;
    name: string;
    description: string;
    status: string;
    assignee: string;
    due_dtg: string;
    due_relative_minutes: number | null;
    completed_at: string;
    cells: number;
  }>;
}

interface Team {
  uid: string;
  mission_uid: string;
  mission_uids: string[];
  name: string;
  description: string;
}

interface Member {
  uid: string;
  mission_uid: string;
  callsign: string;
  role: string;
  capabilities: string[];
}

interface Asset {
  uid: string;
  mission_uid: string;
  name: string;
  type: string;
  status: string;
}

interface Assignment {
  uid: string;
  mission_uid: string;
  task: string;
  member: string;
  assets: string[];
}

interface Zone {
  uid: string;
  mission_uid: string;
  name: string;
  assigned: boolean;
}

interface AuditEvent {
  uid: string;
  mission_uid: string;
  timestamp: string;
  time: string;
  type: string;
  message: string;
  details: Record<string, unknown> | null;
}

interface ChecklistTemplateOption {
  uid: string;
  name: string;
  columns: number;
  source_type: "template" | "csv_import";
  task_rows: number;
  description: string;
  created_at: string;
  owner: string;
}

type ChecklistTemplateSourceType = ChecklistTemplateOption["source_type"];
type ChecklistTemplateEditorMode = "create" | "edit" | "csv_readonly";
type ChecklistTemplateColumnType = "SHORT_STRING" | "LONG_STRING" | "INTEGER" | "ACTUAL_TIME" | "RELATIVE_TIME";

interface ChecklistTemplateDraftColumn {
  column_uid: string;
  column_name: string;
  display_order: number;
  column_type: ChecklistTemplateColumnType;
  column_editable: boolean;
  is_removable: boolean;
  system_key: string | null;
  background_color: string | null;
  text_color: string | null;
}

interface MissionRaw {
  uid?: string;
  mission_name?: string | null;
  description?: string | null;
  topic_id?: string | null;
  mission_status?: string | null;
  path?: string | null;
  classification?: string | null;
  tool?: string | null;
  keywords?: string[] | null;
  parent_uid?: string | null;
  feeds?: string[] | null;
  default_role?: string | null;
  mission_priority?: number | null;
  owner_role?: string | null;
  token?: string | null;
  invite_only?: boolean | null;
  expiration?: string | null;
  mission_rde_role?: string | null;
  asset_uids?: string[] | null;
  zones?: string[] | null;
}

interface TopicRaw {
  TopicID?: string | null;
  TopicName?: string | null;
  TopicPath?: string | null;
  TopicDescription?: string | null;
}

interface ChecklistCellRaw {
  column_uid?: string | null;
  value?: string | null;
}

interface ChecklistTaskRaw {
  task_uid?: string;
  number?: number;
  due_relative_minutes?: number | null;
  user_status?: string | null;
  task_status?: string | null;
  due_dtg?: string | null;
  completed_at?: string | null;
  is_late?: boolean | null;
  completed_by_team_member_rns_identity?: string | null;
  legacy_value?: string | null;
  cells?: ChecklistCellRaw[];
}

interface ChecklistColumnRaw {
  column_uid?: string;
  column_name?: string | null;
  column_type?: string | null;
  system_key?: string | null;
  column_editable?: boolean | null;
  display_order?: number | null;
  is_removable?: boolean | null;
  background_color?: string | null;
  text_color?: string | null;
}

interface ChecklistRaw {
  uid?: string;
  mission_id?: string | null;
  name?: string | null;
  description?: string | null;
  created_at?: string | null;
  created_by_team_member_rns_identity?: string | null;
  progress_percent?: number | null;
  origin_type?: string | null;
  checklist_status?: string | null;
  mode?: string | null;
  sync_state?: string | null;
  counts?: {
    pending_count?: number | null;
    late_count?: number | null;
    complete_count?: number | null;
  } | null;
  tasks?: ChecklistTaskRaw[];
  columns?: ChecklistColumnRaw[];
}

interface TeamRaw {
  uid?: string;
  mission_uid?: string | null;
  mission_uids?: string[];
  team_name?: string | null;
  team_description?: string | null;
}

interface TeamMemberRaw {
  uid?: string;
  team_uid?: string | null;
  rns_identity?: string | null;
  display_name?: string | null;
  role?: string | null;
  callsign?: string | null;
  client_identities?: string[];
}

interface AssetRaw {
  asset_uid?: string;
  team_member_uid?: string | null;
  name?: string | null;
  asset_type?: string | null;
  status?: string | null;
}

interface AssignmentRaw {
  assignment_uid?: string;
  mission_uid?: string | null;
  task_uid?: string | null;
  team_member_rns_identity?: string | null;
  status?: string | null;
  notes?: string | null;
  assets?: unknown;
}

interface DomainEventRaw {
  event_uid?: string;
  domain?: string | null;
  aggregate_type?: string | null;
  aggregate_uid?: string | null;
  event_type?: string | null;
  payload?: unknown;
  created_at?: string | null;
}

interface MissionChangeRaw {
  uid?: string;
  mission_uid?: string | null;
  name?: string | null;
  timestamp?: string | null;
  notes?: string | null;
  change_type?: string | null;
  hashes?: unknown;
}

interface LogEntryRaw {
  entry_uid?: string;
  mission_uid?: string | null;
  content?: string | null;
  server_time?: string | null;
  client_time?: string | null;
  content_hashes?: string[] | null;
  keywords?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface ZoneRaw {
  zone_id?: string;
  name?: string;
}

interface TemplateRaw {
  uid?: string;
  template_name?: string | null;
  description?: string | null;
  created_at?: string | null;
  created_by_team_member_rns_identity?: string | null;
  columns?: unknown;
}

interface SkillRaw {
  skill_uid?: string;
  name?: string | null;
}

interface TeamMemberSkillRaw {
  team_member_rns_identity?: string | null;
  skill_uid?: string | null;
  level?: number | null;
}

interface TaskSkillRequirementRaw {
  task_uid?: string | null;
}

const toastStore = useToastStore();
const route = useRoute();
const router = useRouter();

const DEFAULT_SOURCE_IDENTITY = "ui.operator";
const MISSION_SELECTION_STORAGE_KEY = "rth-ui-missions-selected-mission-uid";

const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);
const queryText = (value: unknown): string =>
  Array.isArray(value) ? String(value[0] ?? "").trim() : String(value ?? "").trim();

const asRecord = (value: unknown): Record<string, unknown> => {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
};

const toStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => String(item ?? "").trim())
    .filter((item) => item.length > 0);
};

const splitCommaSeparated = (value: string): string[] =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);

const joinCommaSeparated = (value: string[] | undefined): string => (value && value.length ? value.join(", ") : "");

const toOptionalInteger = (value: string): number | null => {
  const text = value.trim();
  if (!text) {
    return null;
  }
  const parsed = Number(text);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.trunc(parsed);
};

const toDatetimeLocalValue = (value?: string | null): string => {
  const text = String(value ?? "").trim();
  if (!text) {
    return "";
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  const timezoneOffsetMs = parsed.getTimezoneOffset() * 60_000;
  return new Date(parsed.getTime() - timezoneOffsetMs).toISOString().slice(0, 16);
};

const fromDatetimeLocalValue = (value: string): string | null => {
  const text = value.trim();
  if (!text) {
    return null;
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toISOString();
};

const toEpoch = (value?: string | null): number => {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return 0;
  }
  return parsed;
};

const formatCountdownSegment = (value: number): string => {
  const normalized = Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0;
  return String(normalized).padStart(2, "0");
};

const MISSION_STATUS_ENUM = [
  "MISSION_ACTIVE",
  "MISSION_PLANNED",
  "MISSION_STANDBY",
  "MISSION_COMPLETE",
  "MISSION_ARCHIVED"
] as const;

type MissionStatusEnum = (typeof MISSION_STATUS_ENUM)[number];

const MISSION_STATUS_ALIAS_MAP: Record<string, MissionStatusEnum> = {
  ACTIVE: "MISSION_ACTIVE",
  MISSION_ACTIVE: "MISSION_ACTIVE",
  PLANNED: "MISSION_PLANNED",
  MISSION_PLANNED: "MISSION_PLANNED",
  STANDBY: "MISSION_STANDBY",
  MISSION_STANDBY: "MISSION_STANDBY",
  COMPLETE: "MISSION_COMPLETE",
  COMPLETED: "MISSION_COMPLETE",
  IN_COMPLETE: "MISSION_COMPLETE",
  INCOMPLETE: "MISSION_COMPLETE",
  MISSION_COMPLETE: "MISSION_COMPLETE",
  MISSION_COMPLETED: "MISSION_COMPLETE",
  MISSION_IN_COMPLETE: "MISSION_COMPLETE",
  ARCHIVE: "MISSION_ARCHIVED",
  ARCHIVED: "MISSION_ARCHIVED",
  MISSION_ARCHIVE: "MISSION_ARCHIVED",
  MISSION_ARCHIVED: "MISSION_ARCHIVED"
};

const toMissionStatusEnum = (value?: string | null): MissionStatusEnum => {
  const token = String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");
  if (!token) {
    return "MISSION_ACTIVE";
  }

  const mapped = MISSION_STATUS_ALIAS_MAP[token];
  if (mapped) {
    return mapped;
  }

  if (token.startsWith("MISSION_")) {
    return MISSION_STATUS_ENUM.includes(token as MissionStatusEnum) ? (token as MissionStatusEnum) : "MISSION_ACTIVE";
  }

  const prefixed = `MISSION_${token}` as MissionStatusEnum;
  return MISSION_STATUS_ENUM.includes(prefixed) ? prefixed : "MISSION_ACTIVE";
};

const normalizeMissionStatus = (value?: string | null): string => {
  return toMissionStatusEnum(value).slice("MISSION_".length);
};

const toMissionStatusValue = (value?: string | null): string => {
  return toMissionStatusEnum(value);
};

const normalizeTaskStatus = (value?: string | null): string => {
  const text = String(value ?? "PENDING").trim().toUpperCase();
  return text || "PENDING";
};

const resolveTaskNameColumnUid = (checklist: ChecklistRaw): string | undefined => {
  const columns = toArray<ChecklistColumnRaw>(checklist.columns);
  const namedTask = columns.find((column) => String(column.column_name ?? "").trim().toUpperCase() === "TASK");
  if (namedTask?.column_uid) {
    return namedTask.column_uid;
  }
  const shortString = columns.find(
    (column) =>
      String(column.column_type ?? "").trim().toUpperCase() === "SHORT_STRING" &&
      String(column.system_key ?? "").trim().length === 0
  );
  if (shortString?.column_uid) {
    return shortString.column_uid;
  }
  return columns.find((column) => column.column_uid)?.column_uid;
};

const resolveChecklistTaskName = (
  checklist: ChecklistRaw,
  task: ChecklistTaskRaw,
  preferredColumnUid?: string
): string => {
  const cells = toArray<ChecklistCellRaw>(task.cells);
  const taskColumnUid = preferredColumnUid ?? resolveTaskNameColumnUid(checklist);
  if (taskColumnUid) {
    const preferredCell = cells.find((cell) => String(cell.column_uid ?? "").trim() === taskColumnUid);
    if (typeof preferredCell?.value === "string" && preferredCell.value.trim()) {
      return preferredCell.value.trim();
    }
  }
  const firstTextCell = cells.find((cell) => typeof cell.value === "string" && cell.value.trim().length > 0);
  if (typeof firstTextCell?.value === "string") {
    return firstTextCell.value.trim();
  }
  const legacyValue = String(task.legacy_value ?? "").trim();
  if (legacyValue) {
    return legacyValue;
  }
  if (typeof task.number === "number") {
    return `Task ${task.number}`;
  }
  const taskUid = String(task.task_uid ?? "").trim();
  if (taskUid) {
    return `Task ${taskUid.slice(0, 8)}`;
  }
  return "Task";
};

const resolveColumnUidByNames = (checklist: ChecklistRaw, candidateNames: string[]): string | undefined => {
  const normalizedCandidates = candidateNames.map((name) => name.trim().toUpperCase()).filter((name) => name.length > 0);
  if (!normalizedCandidates.length) {
    return undefined;
  }
  const columns = toArray<ChecklistColumnRaw>(checklist.columns);
  const exactMatch = columns.find((column) =>
    normalizedCandidates.includes(String(column.column_name ?? "").trim().toUpperCase())
  );
  if (exactMatch?.column_uid) {
    return exactMatch.column_uid;
  }
  return undefined;
};

const resolveTaskDescription = (
  checklist: ChecklistRaw,
  task: ChecklistTaskRaw,
  preferredDescriptionColumnUid?: string,
  preferredTaskColumnUid?: string
): string => {
  const cells = toArray<ChecklistCellRaw>(task.cells);
  if (preferredDescriptionColumnUid) {
    const descriptionCell = cells.find(
      (cell) => String(cell.column_uid ?? "").trim() === preferredDescriptionColumnUid
    );
    if (typeof descriptionCell?.value === "string" && descriptionCell.value.trim()) {
      return descriptionCell.value.trim();
    }
  }
  const fallback = cells.find((cell) => {
    const columnUid = String(cell.column_uid ?? "").trim();
    if (!columnUid || (preferredTaskColumnUid && columnUid === preferredTaskColumnUid)) {
      return false;
    }
    return typeof cell.value === "string" && cell.value.trim().length > 0;
  });
  if (typeof fallback?.value === "string") {
    return fallback.value.trim();
  }
  return "";
};

const extractErrorDetail = (error: ApiError): string | undefined => {
  if (typeof error.body === "string" && error.body.trim()) {
    return error.body.trim();
  }
  const payload = asRecord(error.body);
  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  return undefined;
};

const handleApiError = (error: unknown, fallback: string) => {
  const apiError = error as ApiError;
  if (apiError?.status === 401) {
    toastStore.push("Authentication required. Check your credentials.", "warning");
    return;
  }
  if (apiError?.status === 403) {
    toastStore.push("Forbidden. Your account lacks permission for this action.", "warning");
    return;
  }
  if (error instanceof Error && apiError?.status === undefined) {
    toastStore.push(`${fallback}: ${error.message}`, "warning");
    return;
  }
  const detail = extractErrorDetail(apiError);
  toastStore.push(detail ? `${fallback}: ${detail}` : fallback, "danger");
};

const formatAuditTime = (value?: string | null): string => {
  if (!value) {
    return "--:--:--";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleTimeString([], { hour12: false });
};

const toAuditTypeLabel = (value?: string | null): string => {
  const text = String(value ?? "").trim();
  if (!text) {
    return "ACTIVITY";
  }
  return text.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toUpperCase() || "ACTIVITY";
};

const formatChecklistDateTime = (value?: string | null): string => {
  if (!value) {
    return "--";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
};

const formatDueRelativeMinutesLabel = (value?: number | null): string => {
  const minutes = Number(value);
  if (!Number.isFinite(minutes)) {
    return "-";
  }
  const rounded = Math.trunc(minutes);
  const sign = rounded < 0 ? "-" : "+";
  const abs = Math.abs(rounded);
  const hours = String(Math.trunc(abs / 60)).padStart(2, "0");
  const mins = String(abs % 60).padStart(2, "0");
  return `T${sign}${hours}:${mins}`;
};

const formatDomainEventMessage = (event: DomainEventRaw): string => {
  const payload = asRecord(event.payload);
  const name = payload.name;
  if (typeof name === "string" && name.trim()) {
    return name.trim();
  }
  const notes = payload.notes;
  if (typeof notes === "string" && notes.trim()) {
    return notes.trim();
  }
  const checklistUid = payload.checklist_uid;
  if (typeof checklistUid === "string" && checklistUid.trim()) {
    return `Checklist ${checklistUid.trim()}`;
  }
  const missionUid = payload.mission_uid ?? payload.mission_id;
  if (typeof missionUid === "string" && missionUid.trim()) {
    return `Mission ${missionUid.trim()}`;
  }
  return String(event.event_type ?? "domain.event").trim() || "domain.event";
};

const buildTimestampTag = (): string => new Date().toISOString().replace(/[^0-9]/g, "").slice(0, 14);

const downloadJson = (filename: string, payload: unknown) => {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const downloadText = (filename: string, payload: string, contentType = "text/plain") => {
  const blob = new Blob([payload], { type: contentType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const parseCsvRows = (payload: string): string[][] => {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let inQuotes = false;
  for (let index = 0; index < payload.length; index += 1) {
    const char = payload[index];
    if (inQuotes) {
      if (char === "\"") {
        if (payload[index + 1] === "\"") {
          cell += "\"";
          index += 1;
        } else {
          inQuotes = false;
        }
      } else {
        cell += char;
      }
      continue;
    }
    if (char === "\"") {
      inQuotes = true;
      continue;
    }
    if (char === ",") {
      row.push(cell);
      cell = "";
      continue;
    }
    if (char === "\n" || char === "\r") {
      if (char === "\r" && payload[index + 1] === "\n") {
        index += 1;
      }
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
      continue;
    }
    cell += char;
  }
  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
};

const normalizeCsvRows = (rows: string[][]): string[][] => {
  return rows
    .map((row, rowIndex) =>
      row.map((cell, columnIndex) => {
        const cleanCell = rowIndex === 0 && columnIndex === 0 ? cell.replace(/^\uFEFF/, "") : cell;
        return cleanCell.trim();
      })
    )
    .filter((row) => row.some((cell) => cell.length > 0));
};

const uint8ArrayToBase64 = (bytes: Uint8Array): string => {
  const chunkSize = 0x8000;
  let binary = "";
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
};

const escapeCsvCell = (value: string): string => {
  if (/[",\r\n]/.test(value)) {
    return `"${value.replace(/"/g, "\"\"")}"`;
  }
  return value;
};

const csvImportFilename = ref("");
const csvImportBase64 = ref("");
const csvImportHeaders = ref<string[]>([]);
const csvImportRows = ref<string[][]>([]);
const csvUploadInputRef = ref<HTMLInputElement | null>(null);

const csvImportPreviewRows = computed(() => csvImportRows.value.slice(0, 12));

const clearCsvUpload = () => {
  csvImportFilename.value = "";
  csvImportBase64.value = "";
  csvImportHeaders.value = [];
  csvImportRows.value = [];
};

const openCsvUploadPicker = () => {
  csvUploadInputRef.value?.click();
};

const renderUploadedCsv = (): string => {
  const rows = [csvImportHeaders.value, ...csvImportRows.value];
  return rows.map((row) => row.map((cell) => escapeCsvCell(String(cell ?? ""))).join(",")).join("\n");
};

const handleCsvUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement | null;
  const file = target?.files?.[0];
  if (!file) {
    clearCsvUpload();
    return;
  }
  try {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      throw new Error("Select a file with .csv extension");
    }
    const bytes = new Uint8Array(await file.arrayBuffer());
    const text = new TextDecoder("utf-8").decode(bytes);
    const parsedRows = normalizeCsvRows(parseCsvRows(text));
    if (parsedRows.length < 2) {
      throw new Error("CSV must include a header row and at least one task row");
    }
    const headerRow = parsedRows[0];
    const taskRows = parsedRows.slice(1);
    const maxColumns = taskRows.reduce((max, row) => Math.max(max, row.length), headerRow.length);
    if (maxColumns <= 0) {
      throw new Error("CSV header row is empty");
    }
    const headers = Array.from({ length: maxColumns }, (_, index) => {
      const value = String(headerRow[index] ?? "").trim();
      return value || `Column ${index + 1}`;
    });
    const normalizedTaskRows = taskRows.map((row) =>
      headers.map((_, columnIndex) => String(row[columnIndex] ?? "").trim())
    );
    csvImportFilename.value = file.name;
    csvImportBase64.value = uint8ArrayToBase64(bytes);
    csvImportHeaders.value = headers;
    csvImportRows.value = normalizedTaskRows;
    toastStore.push(`Loaded ${file.name}: ${normalizedTaskRows.length} task rows`, "info");
  } catch (error) {
    clearCsvUpload();
    if (error instanceof Error) {
      toastStore.push(`CSV upload failed: ${error.message}`, "warning");
      return;
    }
    toastStore.push("CSV upload failed", "warning");
  }
};

const missions = ref<Mission[]>([]);
const topicRecords = ref<TopicRaw[]>([]);
const checklistRecords = ref<ChecklistRaw[]>([]);
const teamRecords = ref<TeamRaw[]>([]);
const memberRecords = ref<TeamMemberRaw[]>([]);
const assetRecords = ref<AssetRaw[]>([]);
const assignmentRecords = ref<AssignmentRaw[]>([]);
const eventRecords = ref<DomainEventRaw[]>([]);
const missionChanges = ref<MissionChangeRaw[]>([]);
const logEntryRecords = ref<LogEntryRaw[]>([]);
const zoneRecords = ref<ZoneRaw[]>([]);
const templateRecords = ref<TemplateRaw[]>([]);
const skillRecords = ref<SkillRaw[]>([]);
const teamMemberSkillRecords = ref<TeamMemberSkillRaw[]>([]);
const taskSkillRequirementRecords = ref<TaskSkillRequirementRaw[]>([]);

const loadingWorkspace = ref(false);
const zoneDraftByMission = ref<Record<string, string[]>>({});

const upsertChecklistRecord = (record: ChecklistRaw) => {
  const uid = String(record.uid ?? "").trim();
  if (!uid) {
    return;
  }
  const next = [...checklistRecords.value];
  const index = next.findIndex((entry) => String(entry.uid ?? "").trim() === uid);
  if (index >= 0) {
    next[index] = record;
  } else {
    next.push(record);
  }
  checklistRecords.value = next;
};

const hydrateChecklistRecord = async (checklistUid: string): Promise<ChecklistRaw | null> => {
  const uid = String(checklistUid ?? "").trim();
  if (!uid) {
    return null;
  }
  const detail = await get<ChecklistRaw>(`${endpoints.checklists}/${uid}`);
  upsertChecklistRecord(detail);
  return detail;
};

const checklists = computed<Checklist[]>(() => {
  return checklistRecords.value
    .map((entry) => {
      const checklistUid = String(entry.uid ?? "").trim();
      if (!checklistUid) {
        return null;
      }
      const preferredTaskColumnUid = resolveTaskNameColumnUid(entry);
      const preferredDescriptionColumnUid = resolveColumnUidByNames(entry, ["DESCRIPTION", "DETAILS", "NOTES"]);
      const tasks = toArray<ChecklistTaskRaw>(entry.tasks)
        .map((task) => {
          const taskUid = String(task.task_uid ?? "").trim();
          const taskStatus = normalizeTaskStatus(task.task_status ?? task.user_status);
          const taskName = resolveChecklistTaskName(entry, task, preferredTaskColumnUid);
          const taskDescription = resolveTaskDescription(
            entry,
            task,
            preferredDescriptionColumnUid,
            preferredTaskColumnUid
          );
          const assignee = String(task.completed_by_team_member_rns_identity ?? "").trim();
          return {
            id: taskUid || `${checklistUid}-task-${String(task.number ?? "0")}`,
            number: Number(task.number ?? 0),
            name: taskName,
            description: taskDescription,
            status: taskStatus,
            assignee: assignee || "-",
            due_dtg: String(task.due_dtg ?? ""),
            due_relative_minutes: Number.isFinite(Number(task.due_relative_minutes))
              ? Math.trunc(Number(task.due_relative_minutes))
              : null,
            completed_at: String(task.completed_at ?? ""),
            cells: toArray<ChecklistCellRaw>(task.cells).length
          };
        })
        .sort((left, right) => left.number - right.number);
      const missionUid = String(entry.mission_id ?? "").trim();
      const pendingCount = Number(entry.counts?.pending_count ?? NaN);
      const lateCount = Number(entry.counts?.late_count ?? NaN);
      const completeCount = Number(entry.counts?.complete_count ?? NaN);
      let computedPending = 0;
      let computedLate = 0;
      let computedComplete = 0;
      tasks.forEach((task) => {
        const status = normalizeTaskStatus(task.status);
        if (status.startsWith("COMPLETE")) {
          computedComplete += 1;
          return;
        }
        if (status === "LATE") {
          computedLate += 1;
          return;
        }
        computedPending += 1;
      });
      return {
        uid: checklistUid,
        mission_uid: missionUid,
        name: String(entry.name ?? checklistUid),
        description: String(entry.description ?? ""),
        created_at: String(entry.created_at ?? ""),
        mode: String(entry.mode ?? "UNKNOWN"),
        sync_state: String(entry.sync_state ?? "UNKNOWN"),
        origin_type: String(entry.origin_type ?? ""),
        checklist_status: normalizeTaskStatus(entry.checklist_status),
        progress: Number(entry.progress_percent ?? 0),
        pending_count: Number.isFinite(pendingCount) ? pendingCount : computedPending,
        late_count: Number.isFinite(lateCount) ? lateCount : computedLate,
        complete_count: Number.isFinite(completeCount) ? completeCount : computedComplete,
        tasks
      };
    })
    .filter((entry): entry is Checklist => entry !== null);
});

const teams = computed<Team[]>(() => {
  const collectTeamMissionUids = (entry: TeamRaw): string[] => {
    const values = [...toStringList(entry.mission_uids), String(entry.mission_uid ?? "").trim()].filter(
      (item) => item.length > 0
    );
    return [...new Set(values)];
  };

  return teamRecords.value
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) {
        return null;
      }
      const missionUids = collectTeamMissionUids(entry);
      return {
        uid,
        mission_uid: missionUids[0] ?? "",
        mission_uids: missionUids,
        name: String(entry.team_name ?? uid),
        description: String(entry.team_description ?? "")
      };
    })
    .filter((entry): entry is Team => entry !== null);
});

const hasPopulatedChecklistCells = (checklist: ChecklistRaw): boolean =>
  toArray<ChecklistTaskRaw>(checklist.tasks).some((task) =>
    toArray<ChecklistCellRaw>(task.cells).some((cell) => String(cell.value ?? "").trim().length > 0)
  );

const isRenderableCsvImportTemplate = (checklist: ChecklistRaw): boolean => {
  const nonDueColumns = toArray<ChecklistColumnRaw>(checklist.columns).filter(
    (column) => String(column.system_key ?? "").trim().toUpperCase() !== "DUE_RELATIVE_DTG"
  );
  if (nonDueColumns.length > 1) {
    return true;
  }
  return hasPopulatedChecklistCells(checklist);
};

const collectChecklistTemplateOptions = (): ChecklistTemplateOption[] => {
  const serverTemplates: ChecklistTemplateOption[] = [];
  templateRecords.value.forEach((entry) => {
    const uid = String(entry.uid ?? "").trim();
    if (!uid) {
      return;
    }
    serverTemplates.push({
      uid,
      name: String(entry.template_name ?? uid),
      columns: toArray<ChecklistColumnRaw>(entry.columns).length,
      source_type: "template",
      task_rows: 0,
      description: String(entry.description ?? "").trim(),
      created_at: String(entry.created_at ?? ""),
      owner: String(entry.created_by_team_member_rns_identity ?? "").trim()
    });
  });

  const csvImportedTemplates: ChecklistTemplateOption[] = [];
  checklistRecords.value.forEach((entry) => {
    const uid = String(entry.uid ?? "").trim();
    if (!uid) {
      return;
    }
    const originType = String(entry.origin_type ?? "").trim().toUpperCase();
    if (originType !== "CSV_IMPORT" || !isRenderableCsvImportTemplate(entry)) {
      return;
    }
    csvImportedTemplates.push({
      uid,
      name: String(entry.name ?? uid),
      columns: toArray<ChecklistColumnRaw>(entry.columns).length,
      source_type: "csv_import",
      task_rows: toArray<ChecklistTaskRaw>(entry.tasks).length,
      description: String(entry.description ?? "").trim(),
      created_at: String(entry.created_at ?? ""),
      owner: String(entry.created_by_team_member_rns_identity ?? "").trim()
    });
  });

  const seen = new Set<string>();
  return [...serverTemplates, ...csvImportedTemplates].filter((entry) => {
    if (seen.has(entry.uid)) {
      return false;
    }
    seen.add(entry.uid);
    return true;
  });
};

const checklistTemplateOptions = computed<ChecklistTemplateOption[]>(() => {
  return collectChecklistTemplateOptions().sort((left, right) => left.name.localeCompare(right.name));
});

const checklistTemplateSelectOptions = computed(() => {
  return checklistTemplateOptions.value.map((entry) => ({
    value: entry.uid,
    label:
      entry.source_type === "csv_import"
        ? `${entry.name} (${entry.columns} columns, CSV import)`
        : entry.name
  }));
});

const selectedChecklistTemplateOption = computed(() =>
  checklistTemplateOptions.value.find((entry) => entry.uid === checklistTemplateSelectionUid.value)
);

const skillNameByUid = computed(() => {
  const map = new Map<string, string>();
  skillRecords.value.forEach((entry) => {
    const uid = String(entry.skill_uid ?? "").trim();
    if (!uid) {
      return;
    }
    const name = String(entry.name ?? uid).trim() || uid;
    map.set(uid, name);
  });
  return map;
});

const normalizeIdentity = (value: string): string => String(value ?? "").trim().toLowerCase();

const resolveTeamMemberIdentity = (entry: TeamMemberRaw): string => {
  const rnsIdentity = String(entry.rns_identity ?? "").trim();
  if (rnsIdentity) {
    return rnsIdentity;
  }
  return toStringList(entry.client_identities)[0] ?? "";
};

const teamMemberPrimaryLabel = (entry: TeamMemberRaw): string => {
  const identity = resolveTeamMemberIdentity(entry);
  const uid = String(entry.uid ?? "").trim();
  return resolveTeamMemberPrimaryLabel(entry, { identity, uid });
};

const memberCapabilitiesByIdentity = computed(() => {
  const map = new Map<string, string[]>();
  teamMemberSkillRecords.value.forEach((entry) => {
    const identity = normalizeIdentity(String(entry.team_member_rns_identity ?? ""));
    const skillUid = String(entry.skill_uid ?? "").trim();
    if (!identity || !skillUid) {
      return;
    }
    const skillName = skillNameByUid.value.get(skillUid) ?? skillUid;
    const level = Number(entry.level ?? 0);
    const label = level > 0 ? `${skillName}.L${level}` : skillName;
    const current = map.get(identity) ?? [];
    if (!current.includes(label)) {
      map.set(identity, [...current, label]);
    }
  });
  return map;
});

const taskNameByUid = computed(() => {
  const map = new Map<string, string>();
  checklistRecords.value.forEach((checklist) => {
    const preferredTaskColumnUid = resolveTaskNameColumnUid(checklist);
    toArray<ChecklistTaskRaw>(checklist.tasks).forEach((task) => {
      const taskUid = String(task.task_uid ?? "").trim();
      if (!taskUid) {
        return;
      }
      map.set(taskUid, resolveChecklistTaskName(checklist, task, preferredTaskColumnUid));
    });
  });
  return map;
});

const requirementCountByTaskUid = computed(() => {
  const map = new Map<string, number>();
  taskSkillRequirementRecords.value.forEach((entry) => {
    const taskUid = String(entry.task_uid ?? "").trim();
    if (!taskUid) {
      return;
    }
    map.set(taskUid, (map.get(taskUid) ?? 0) + 1);
  });
  return map;
});

const memberByIdentity = computed(() => {
  const map = new Map<string, { callsign: string; uid: string }>();
  memberRecords.value.forEach((entry) => {
    const uid = String(entry.uid ?? "").trim();
    const identity = resolveTeamMemberIdentity(entry);
    if (!uid || !identity) {
      return;
    }
    const callsign = teamMemberPrimaryLabel(entry);
    map.set(normalizeIdentity(identity), { callsign, uid });
  });
  return map;
});

const assetNameByUid = computed(() => {
  const map = new Map<string, string>();
  assetRecords.value.forEach((entry) => {
    const uid = String(entry.asset_uid ?? "").trim();
    if (!uid) {
      return;
    }
    map.set(uid, String(entry.name ?? uid));
  });
  return map;
});

const screensByTab: Record<PrimaryTab, Array<{ id: ScreenId; label: string }>> = {
  mission: [
    { id: "missionOverview", label: "Mission Overview" },
    { id: "assetRegistry", label: "Asset Registry" }
  ],
  checklists: [{ id: "checklistOverview", label: "Checklist Management" }]
};

const screenMeta: Record<ScreenId, { title: string; subtitle: string; actions: string[] }> = {
  missionDirectory: { title: "Mission Directory", subtitle: "Mission list and operational status registry.", actions: ["Filter", "Export"] },
  missionCreate: {
    title: "Mission Create",
    subtitle: "Create a new mission with metadata and reference links.",
    actions: ["Save", "Reset"]
  },
  missionEdit: {
    title: "Mission Edit",
    subtitle: "Edit selected mission metadata and reference links.",
    actions: ["Save", "Reset"]
  },
  missionOverview: {
    title: "Mission Overview",
    subtitle: "Unified dashboard for mission profile, Excheck, zones, and mission activity.",
    actions: ["Refresh", "Broadcast", "Edit", "Checklists", "Logs", "Team", "Assets", "Zones"]
  },
  missionTeamMembers: { title: "Mission Team & Members", subtitle: "Team composition, roles, and capabilities.", actions: ["Add Team", "Add Member"] },
  assignAssets: { title: "Assign Assets to Mission", subtitle: "Bind registered assets to mission tasks and operators.", actions: ["Assign", "Revoke"] },
  assignZones: { title: "Assign Zones to Mission", subtitle: "Zone selection and geographic mission boundaries.", actions: ["Commit", "New Zone"] },
  assetRegistry: { title: "Asset Registry", subtitle: "Hardware inventory, status, and readiness.", actions: [] },
  checklistOverview: { title: "Checklists", subtitle: "Manage checklist instances and templates.", actions: [] },
  checklistDetails: { title: "Checklist Details", subtitle: "Task grid, callsigns, due relative DTG, and status.", actions: ["Edit Cell", "Sync"] },
  checklistCreation: { title: "Checklist Creation Page", subtitle: "Create online/offline checklist runs from templates.", actions: ["Create", "Validate"] },
  checklistRunDetail: { title: "Checklist Run Detail", subtitle: "Task status transitions and operator updates.", actions: ["Set Status", "Upload"] },
  taskAssignmentWorkspace: { title: "Task Assignment Workspace", subtitle: "Task ownership and asset mapping controls.", actions: ["Assign", "Reassign"] },
  checklistImportCsv: { title: "Import from CSV", subtitle: "Import checklist rows from CSV payloads.", actions: ["Import", "Preview"] },
  checklistPublish: { title: "Checklist Publish to Mission", subtitle: "Publish checklist feed to mission sync channel.", actions: ["Join", "Publish"] },
  checklistProgress: { title: "Checklist Progress & Compliance", subtitle: "Progress metrics and on-time compliance views.", actions: ["Recompute", "Export"] },
  missionExcheckBoard: { title: "Mission Excheck Board", subtitle: "Board lanes for pending, late, and completed tasks.", actions: ["Sync Board", "Publish"] }
};

const actionIconMap: Record<string, ButtonIconName> = {
  Filter: "filter",
  Export: "download",
  Save: "save",
  "Save Mission": "save",
  "Save Template": "save",
  Reset: "undo",
  Refresh: "refresh",
  Recompute: "refresh",
  Sync: "refresh",
  "Sync Board": "refresh",
  Broadcast: "send",
  Edit: "edit",
  Checklists: "list",
  Logs: "list",
  Team: "users",
  Assets: "link",
  Zones: "tool",
  "Add Team": "users",
  "Add Member": "plus",
  Assign: "link",
  Reassign: "route",
  Revoke: "ban",
  Commit: "check",
  "New Zone": "plus",
  "Start New": "plus",
  Create: "plus",
  Import: "upload",
  Preview: "eye",
  Join: "link",
  Upload: "upload",
  Publish: "send",
  "Set Status": "check",
  "Edit Cell": "edit",
  Validate: "check",
  "Export Log": "download",
  Snapshot: "image",
  Deploy: "send",
  "Open Assets": "layers",
  "Open Logs": "list",
  Clone: "layers",
  Archive: "file",
  "Add Column": "plus"
};

const iconForAction = (action: string): ButtonIconName => actionIconMap[action] ?? "tool";

const readPersistedMissionUid = (): string => {
  const stored = loadJson<string>(MISSION_SELECTION_STORAGE_KEY, "");
  return typeof stored === "string" ? stored.trim() : "";
};

const selectedMissionUid = ref(queryText(route.query.mission_uid) || readPersistedMissionUid());
const selectedChecklistUid = ref("");
const primaryTab = ref<PrimaryTab>("mission");
const secondaryScreen = ref<ScreenId>("missionOverview");
const missionDraftName = ref("");
const missionDraftTopic = ref("");
const missionDraftStatus = ref("MISSION_ACTIVE");
const missionDraftDescription = ref("");
const missionDraftParentUid = ref("");
const missionDraftTeamUid = ref("");
const missionDraftPath = ref("");
const missionDraftClassification = ref("");
const missionDraftTool = ref("");
const missionDraftKeywords = ref("");
const missionDraftDefaultRole = ref("");
const missionDraftOwnerRole = ref("");
const missionDraftPriority = ref("");
const missionDraftMissionRdeRole = ref("");
const missionDraftToken = ref("");
const missionDraftFeeds = ref("");
const missionDraftExpiration = ref("");
const missionDraftInviteOnly = ref(false);
const missionAdvancedPropertiesOpen = ref(false);
const missionDraftZoneUids = ref<string[]>([]);
const missionDraftAssetUids = ref<string[]>([]);
const checklistTemplateModalOpen = ref(false);
const checklistTemplateSelectionUid = ref("");
const checklistTemplateNameDraft = ref("");
const checklistTemplateSubmitting = ref(false);
const checklistDetailUid = ref("");
const checklistTaskDueDraft = ref("10");
const checklistTaskStatusBusyByTaskUid = ref<Record<string, boolean>>({});
const checklistDeleteBusy = ref(false);
const checklistLinkMissionModalOpen = ref(false);
const checklistLinkMissionSelectionUid = ref("");
const checklistLinkMissionSubmitting = ref(false);
const checklistTemplateDeleteBusyByUid = ref<Record<string, boolean>>({});
const checklistSearchQuery = ref("");
const checklistWorkspaceView = ref<"active" | "templates">("active");
const checklistTemplateEditorSelectionUid = ref("");
const checklistTemplateEditorSelectionSourceType = ref<ChecklistTemplateSourceType | "">("");
const checklistTemplateEditorMode = ref<ChecklistTemplateEditorMode>("create");
const checklistTemplateEditorDirty = ref(false);
const checklistTemplateEditorSaving = ref(false);
const checklistTemplateEditorHydrating = ref(false);
const checklistTemplateDraftTemplateUid = ref("");
const checklistTemplateDraftName = ref("");
const checklistTemplateDraftDescription = ref("");
const checklistTemplateDraftColumns = ref<ChecklistTemplateDraftColumn[]>([]);
const setChecklistSearchQuery = (value: string): void => {
  checklistSearchQuery.value = value;
};
const setChecklistTaskDueDraft = (value: string): void => {
  checklistTaskDueDraft.value = value;
};
const setChecklistTemplateDraftName = (value: string): void => {
  checklistTemplateDraftName.value = value;
};
const setChecklistTemplateDraftDescription = (value: string): void => {
  checklistTemplateDraftDescription.value = value;
};
const teamAllocationModalOpen = ref(false);
const teamAllocationSubmitting = ref(false);
const teamAllocationExistingTeamUid = ref("");
const teamAllocationNewTeamName = ref("");
const teamAllocationNewTeamDescription = ref("");
const memberAllocationModalOpen = ref(false);
const memberAllocationSubmitting = ref(false);
const memberAllocationTeamUid = ref("");
const memberAllocationMemberUid = ref("");
const missionCountdownNow = ref(Date.now());
let missionCountdownTimerId: number | undefined;

const missionStatusOptions: string[] = [...MISSION_STATUS_ENUM];

const currentScreen = computed(() => screenMeta[secondaryScreen.value]);
const isChecklistPrimaryTab = computed(() => primaryTab.value === "checklists");
const showScreenHeader = computed(
  () => !isChecklistPrimaryTab.value || secondaryScreen.value === "checklistImportCsv"
);

const selectedMission = computed(() => missions.value.find((entry) => entry.uid === selectedMissionUid.value));
const topicNameById = computed(() => {
  const map = new Map<string, string>();
  topicRecords.value.forEach((entry) => {
    const id = String(entry.TopicID ?? "").trim();
    if (!id) {
      return;
    }
    const name = String(entry.TopicName ?? "").trim();
    map.set(id, name || id);
  });
  return map;
});
const selectedMissionTopicName = computed(() => {
  const topicId = String(selectedMission.value?.topic ?? "").trim();
  if (!topicId) {
    return "-";
  }
  return topicNameById.value.get(topicId) ?? topicId;
});
const missionEndCountdown = computed(() => {
  const fallback = { hasEnd: false, display: "00.00.00" };
  const expiration = String(selectedMission.value?.expiration ?? "").trim();
  if (!expiration) {
    return fallback;
  }

  const target = Date.parse(expiration);
  if (Number.isNaN(target)) {
    return fallback;
  }

  const remainingMs = Math.max(0, target - missionCountdownNow.value);
  const totalMinutes = Math.floor(remainingMs / 60_000);
  const days = Math.floor(totalMinutes / (24 * 60));
  const hours = Math.floor((totalMinutes % (24 * 60)) / 60);
  const minutes = totalMinutes % 60;
  return {
    hasEnd: true,
    display: `${formatCountdownSegment(days)}.${formatCountdownSegment(hours)}.${formatCountdownSegment(minutes)}`
  };
});
const isMissionCreateScreen = computed(() => secondaryScreen.value === "missionCreate");
const isMissionEditScreen = computed(() => secondaryScreen.value === "missionEdit");
const isMissionFormScreen = computed(() => isMissionCreateScreen.value || isMissionEditScreen.value);
const missionDraftUidLabel = computed(() => (isMissionEditScreen.value ? selectedMission.value?.uid || "-" : "AUTO"));
const missionTopicOptions = computed(() => {
  const options = topicRecords.value
    .map((entry) => {
      const id = String(entry.TopicID ?? "").trim();
      if (!id) {
        return null;
      }
      const name = String(entry.TopicName ?? "").trim();
      const path = String(entry.TopicPath ?? "").trim();
      return {
        value: id,
        label: name && path ? `${name} (${path})` : name || path || id
      };
    })
    .filter((entry): entry is { value: string; label: string } => entry !== null)
    .sort((left, right) => left.label.localeCompare(right.label));

  const selectedTopic = missionDraftTopic.value.trim();
  if (selectedTopic.length > 0 && !options.some((entry) => entry.value === selectedTopic)) {
    options.unshift({
      value: selectedTopic,
      label: `${selectedTopic} (current)`
    });
  }

  return [{ value: "", label: "No topic scope" }, ...options];
});
const missionParentOptions = computed(() => [
  { label: "No parent mission", value: "" },
  ...missions.value
    .filter((entry) => !isMissionEditScreen.value || entry.uid !== selectedMissionUid.value)
    .map((entry) => ({ label: entry.mission_name, value: entry.uid }))
]);
const missionReferenceTeamOptions = computed(() => [
  { label: "No linked team", value: "" },
  ...teams.value
    .slice()
    .sort((left, right) => left.name.localeCompare(right.name))
    .map((entry) => ({ label: entry.name, value: entry.uid }))
]);
const missionReferenceZoneOptions = computed(() =>
  zoneRecords.value
    .map((entry) => {
      const uid = String(entry.zone_id ?? "").trim();
      if (!uid) {
        return null;
      }
      return {
        value: uid,
        label: String(entry.name ?? uid)
      };
    })
    .filter((entry): entry is { value: string; label: string } => entry !== null)
    .sort((left, right) => left.label.localeCompare(right.label))
);
const missionReferenceAssetOptions = computed(() =>
  assetRecords.value
    .map((entry) => {
      const uid = String(entry.asset_uid ?? "").trim();
      if (!uid) {
        return null;
      }
      const name = String(entry.name ?? uid).trim() || uid;
      const type = String(entry.asset_type ?? "ASSET").trim() || "ASSET";
      return {
        value: uid,
        label: `${name} (${type})`
      };
    })
    .filter((entry): entry is { value: string; label: string } => entry !== null)
    .sort((left, right) => left.label.localeCompare(right.label))
);
const missionDraftParentLabel = computed(
  () => missionParentOptions.value.find((entry) => entry.value === missionDraftParentUid.value)?.label ?? "-"
);
const missionDraftTeamLabel = computed(
  () => missionReferenceTeamOptions.value.find((entry) => entry.value === missionDraftTeamUid.value)?.label ?? "-"
);
const missionDraftZoneLabel = computed(() => {
  if (!missionDraftZoneUids.value.length) {
    return "-";
  }
  const names = new Map(missionReferenceZoneOptions.value.map((entry) => [entry.value, entry.label]));
  return missionDraftZoneUids.value.map((uid) => names.get(uid) ?? uid).join(", ");
});
const missionDraftAssetLabel = computed(() => {
  if (!missionDraftAssetUids.value.length) {
    return "-";
  }
  const names = new Map(missionReferenceAssetOptions.value.map((entry) => [entry.value, entry.label]));
  return missionDraftAssetUids.value.map((uid) => names.get(uid) ?? uid).join(", ");
});
const showMissionDirectoryPanel = computed(() => primaryTab.value !== "checklists");
const workspacePanelTitle = computed(() => {
  if (primaryTab.value === "checklists") {
    return "Checklists";
  }
  return selectedMission.value?.mission_name || "Mission Details";
});
const workspacePanelSubtitle = computed(() => {
  if (primaryTab.value === "checklists") {
    return "Manage checklist instances and templates.";
  }
  return selectedMission.value?.topic || "Select a mission";
});
const missionChecklists = computed(() => checklists.value.filter((entry) => entry.mission_uid === selectedMissionUid.value));
const selectedChecklistRaw = computed(() =>
  checklistRecords.value.find((entry) => String(entry.uid ?? "").trim() === selectedChecklistUid.value)
);
const allChecklistsSorted = computed(() => {
  return [...checklists.value].sort((left, right) => {
    const diff = toEpoch(right.created_at) - toEpoch(left.created_at);
    if (diff !== 0) {
      return diff;
    }
    return left.name.localeCompare(right.name);
  });
});

const resolvedChecklistDetailUid = computed(() => {
  if (checklistDetailUid.value) {
    return checklistDetailUid.value;
  }
  if (["checklistDetails", "checklistRunDetail"].includes(secondaryScreen.value)) {
    return selectedChecklistUid.value;
  }
  return "";
});

const checklistDetailRecord = computed(() => {
  const detailUid = resolvedChecklistDetailUid.value;
  if (!detailUid) {
    return null;
  }
  return checklists.value.find((entry) => entry.uid === detailUid) ?? null;
});

const canCreateFromDetailTemplate = computed(() => {
  const detailUid = checklistDetailRecord.value?.uid ?? "";
  if (!detailUid) {
    return false;
  }
  return checklistTemplateOptions.value.some((entry) => entry.uid === detailUid);
});

const checklistDetailRaw = computed(() => {
  const detailUid = resolvedChecklistDetailUid.value;
  if (!detailUid) {
    return null;
  }
  return checklistRecords.value.find((entry) => String(entry.uid ?? "").trim() === detailUid) ?? null;
});

const checklistDetailColumns = computed(() => {
  const checklist = checklistDetailRaw.value;
  if (!checklist) {
    return [] as Array<{ uid: string; name: string }>;
  }

  const dueColumnUid =
    toArray<ChecklistColumnRaw>(checklist.columns).find(
      (column) => String(column.system_key ?? "").trim().toUpperCase() === "DUE_RELATIVE_DTG"
    )?.column_uid ?? "";

  const columns = toArray<ChecklistColumnRaw>(checklist.columns)
    .map((column) => ({
      uid: String(column.column_uid ?? "").trim(),
      name: String(column.column_name ?? "").trim(),
      system_key: String(column.system_key ?? "").trim().toUpperCase(),
      display_order: Number(column.display_order ?? 0)
    }))
    .filter((column) => column.uid.length > 0 && column.system_key !== "DUE_RELATIVE_DTG")
    .sort((left, right) => left.display_order - right.display_order);
  const mergedColumns = [...columns];
  const knownColumnUids = new Set(mergedColumns.map((column) => column.uid));
  toArray<ChecklistTaskRaw>(checklist.tasks).forEach((task) => {
    toArray<ChecklistCellRaw>(task.cells).forEach((cell) => {
      const columnUid = String(cell.column_uid ?? "").trim();
      if (!columnUid || columnUid === String(dueColumnUid).trim() || knownColumnUids.has(columnUid)) {
        return;
      }
      knownColumnUids.add(columnUid);
      mergedColumns.push({
        uid: columnUid,
        name: "",
        system_key: "",
        display_order: mergedColumns.length + 1000
      });
    });
  });

  return mergedColumns.map((column, index) => ({
    uid: column.uid,
    name: column.name || `Column ${index + 1}`
  }));
});

const checklistDetailRows = computed(() => {
  const checklist = checklistDetailRaw.value;
  if (!checklist) {
    return [] as Array<{
      id: string;
      task_uid: string;
      number: number;
      done: boolean;
      column_values: Record<string, string>;
      due: string;
      status: string;
      completeDtg: string;
    }>;
  }
  const preferredTaskColumnUid = resolveTaskNameColumnUid(checklist);
  const dueColumnUid =
    toArray<ChecklistColumnRaw>(checklist.columns).find(
      (column) => String(column.system_key ?? "").trim().toUpperCase() === "DUE_RELATIVE_DTG"
    )?.column_uid ?? "";
  return toArray<ChecklistTaskRaw>(checklist.tasks)
    .map((task) => {
      const taskUid = String(task.task_uid ?? "").trim();
      const status = normalizeTaskStatus(task.task_status ?? task.user_status);
      const done = status.startsWith("COMPLETE");
      const dueDtg = String(task.due_dtg ?? "").trim();
      let due = dueDtg ? formatChecklistDateTime(dueDtg) : "-";
      if (!dueDtg && task.due_relative_minutes !== null && task.due_relative_minutes !== undefined) {
        due = formatDueRelativeMinutesLabel(task.due_relative_minutes);
      } else if (!dueDtg && dueColumnUid) {
        const dueCell = toArray<ChecklistCellRaw>(task.cells).find(
          (cell) => String(cell.column_uid ?? "").trim() === String(dueColumnUid).trim()
        );
        if (typeof dueCell?.value === "string" && dueCell.value.trim()) {
          due = dueCell.value.trim();
        }
      }
      return {
        id: taskUid || `task-${String(task.number ?? 0)}`,
        task_uid: taskUid,
        number: Number(task.number ?? 0),
        done,
        column_values: (() => {
          const values = toArray<ChecklistCellRaw>(task.cells).reduce((map, cell) => {
            const columnUid = String(cell.column_uid ?? "").trim();
            if (columnUid) {
              map[columnUid] = String(cell.value ?? "").trim();
            }
            return map;
          }, {} as Record<string, string>);
          if (preferredTaskColumnUid && !values[preferredTaskColumnUid]) {
            values[preferredTaskColumnUid] = resolveChecklistTaskName(checklist, task, preferredTaskColumnUid);
          }
          return values;
        })(),
        due,
        status,
        completeDtg: formatChecklistDateTime(task.completed_at)
      };
    })
    .sort((left, right) => left.number - right.number);
});

const missionNameByUid = computed(() => {
  const map = new Map<string, string>();
  missions.value.forEach((mission) => {
    map.set(mission.uid, mission.mission_name);
  });
  return map;
});

const checklistMissionLabel = (missionUid?: string | null): string => {
  const uid = String(missionUid ?? "").trim();
  if (!uid) {
    return "Unscoped";
  }
  return missionNameByUid.value.get(uid) ?? uid;
};

const checklistDetailMissionUid = computed(() => String(checklistDetailRecord.value?.mission_uid ?? "").trim());

const checklistMissionLinkSelectOptions = computed(() => {
  const options: Array<{ label: string; value: string }> = [{ label: "Unscoped", value: "" }];
  const seen = new Set<string>([""]);
  [...missions.value]
    .sort((left, right) => left.mission_name.localeCompare(right.mission_name))
    .forEach((mission) => {
      const uid = String(mission.uid ?? "").trim();
      if (!uid || seen.has(uid)) {
        return;
      }
      seen.add(uid);
      options.push({
        value: uid,
        label: String(mission.mission_name ?? "").trim() || uid
      });
    });
  const currentMissionUid = checklistDetailMissionUid.value;
  if (currentMissionUid && !seen.has(currentMissionUid)) {
    options.push({
      value: currentMissionUid,
      label: `${currentMissionUid} (Unavailable)`
    });
  }
  return options;
});

const checklistLinkMissionActionLabel = computed(() =>
  checklistLinkMissionSelectionUid.value.trim() ? "Link Mission" : "Clear Link"
);

const canSubmitChecklistMissionLink = computed(() => {
  const checklistUid = String(checklistDetailRecord.value?.uid ?? "").trim();
  if (!checklistUid) {
    return false;
  }
  return checklistLinkMissionSelectionUid.value.trim() !== checklistDetailMissionUid.value;
});

const checklistSearchNeedle = computed(() => checklistSearchQuery.value.trim().toUpperCase());

const checklistActiveCount = computed(() => allChecklistsSorted.value.length);
const checklistTemplateCount = computed(() => checklistTemplateOptions.value.length);

const filteredChecklistCards = computed(() => {
  const needle = checklistSearchNeedle.value;
  if (!needle) {
    return allChecklistsSorted.value;
  }
  return allChecklistsSorted.value.filter((checklist) => {
    const haystack = [
      checklist.name,
      checklist.description,
      checklist.checklist_status,
      checklist.mode,
      checklist.sync_state,
      checklistMissionLabel(checklist.mission_uid)
    ]
      .join(" ")
      .toUpperCase();
    return haystack.includes(needle);
  });
});

const filteredChecklistTemplates = computed(() => {
  const sorted = [...checklistTemplateOptions.value].sort((left, right) => left.name.localeCompare(right.name));
  const needle = checklistSearchNeedle.value;
  if (!needle) {
    return sorted;
  }
  return sorted.filter((template) => {
    const haystack = [template.name, template.description, template.owner, template.source_type]
      .join(" ")
      .toUpperCase();
    return haystack.includes(needle);
  });
});

const selectedChecklistTemplateEditorOption = computed(() => {
  const uid = checklistTemplateEditorSelectionUid.value.trim();
  const sourceType = checklistTemplateEditorSelectionSourceType.value;
  if (!uid || !sourceType) {
    return null;
  }
  return (
    checklistTemplateOptions.value.find((entry) => entry.uid === uid && entry.source_type === sourceType) ?? null
  );
});

const checklistTemplateEditorTitle = computed(() => {
  if (checklistTemplateEditorMode.value === "create") {
    return "New Checklist Template";
  }
  if (checklistTemplateEditorMode.value === "csv_readonly") {
    return "CSV Import Template (Read Only)";
  }
  return "Checklist Template Editor";
});

const checklistTemplateEditorSubtitle = computed(() => {
  if (checklistTemplateEditorMode.value === "create") {
    return "Build a new server template with metadata and ordered columns.";
  }
  if (checklistTemplateEditorMode.value === "csv_readonly") {
    return "CSV-derived entries are read-only until converted into a server template.";
  }
  return "Edit template metadata and columns. Save updates or save as new.";
});

const checklistTemplateEditorStatusLabel = computed(() => {
  const state = checklistTemplateEditorDirty.value ? "Unsaved changes" : "Saved";
  if (checklistTemplateEditorSaving.value) {
    return "Saving...";
  }
  if (checklistTemplateEditorMode.value === "csv_readonly") {
    return "Read-only CSV entry";
  }
  if (checklistTemplateEditorMode.value === "create") {
    return checklistTemplateEditorDirty.value ? "Draft not saved" : "Blank template draft";
  }
  return state;
});

const isChecklistTemplateDraftReadonly = computed(() => checklistTemplateEditorMode.value === "csv_readonly");

const {
  checklistTemplateColumnTypeOptions,
  checklistTemplateColumnColorValue,
  isChecklistTemplateDueColumn,
  normalizeChecklistTemplateDraftColumns,
  toChecklistTemplateColumnPayload,
  validateChecklistTemplateDraftPayload,
  createBlankChecklistTemplateDraftColumns,
  setChecklistTemplateColumnName,
  setChecklistTemplateColumnType,
  setChecklistTemplateColumnEditable,
  setChecklistTemplateColumnBackgroundColor,
  setChecklistTemplateColumnTextColor,
  addChecklistTemplateColumn,
  canMoveChecklistTemplateColumnUp,
  canMoveChecklistTemplateColumnDown,
  moveChecklistTemplateColumnUp,
  moveChecklistTemplateColumnDown,
  canDeleteChecklistTemplateColumn,
  deleteChecklistTemplateColumn
} = useChecklistTemplateDraft({
  buildTimestampTag,
  getDraftColumns: () => checklistTemplateDraftColumns.value,
  setDraftColumns: (columns) => {
    checklistTemplateDraftColumns.value = columns as ChecklistTemplateDraftColumn[];
  },
  isReadonly: () => isChecklistTemplateDraftReadonly.value,
  isSaving: () => checklistTemplateEditorSaving.value
});

if (!checklistTemplateDraftColumns.value.length) {
  checklistTemplateDraftColumns.value = createBlankChecklistTemplateDraftColumns() as ChecklistTemplateDraftColumn[];
}

const canAddChecklistTemplateColumn = computed(
  () => !isChecklistTemplateDraftReadonly.value && !checklistTemplateEditorSaving.value
);

const canSaveChecklistTemplateDraft = computed(
  () =>
    checklistTemplateEditorMode.value === "edit" &&
    !isChecklistTemplateDraftReadonly.value &&
    checklistTemplateDraftTemplateUid.value.trim().length > 0 &&
    checklistTemplateEditorDirty.value &&
    !checklistTemplateEditorSaving.value
);

const canSaveChecklistTemplateDraftAsNew = computed(
  () =>
    checklistTemplateEditorMode.value !== "csv_readonly" &&
    !checklistTemplateEditorSaving.value &&
    checklistTemplateDraftName.value.trim().length > 0
);

const canCloneChecklistTemplateDraft = computed(
  () =>
    checklistTemplateEditorMode.value === "edit" &&
    checklistTemplateDraftTemplateUid.value.trim().length > 0 &&
    !checklistTemplateEditorSaving.value
);

const canArchiveChecklistTemplateDraft = computed(
  () =>
    checklistTemplateEditorMode.value === "edit" &&
    checklistTemplateDraftTemplateUid.value.trim().length > 0 &&
    !checklistTemplateEditorSaving.value
);

const canConvertChecklistTemplateDraft = computed(
  () =>
    checklistTemplateEditorMode.value === "csv_readonly" &&
    checklistTemplateEditorSelectionUid.value.trim().length > 0 &&
    !checklistTemplateEditorSaving.value
);

const canDeleteChecklistTemplateDraft = computed(() => {
  const selected = selectedChecklistTemplateEditorOption.value;
  if (!selected || checklistTemplateEditorSaving.value) {
    return false;
  }
  return !checklistTemplateDeleteBusyByUid.value[selected.uid];
});

const missionChecklistCountByMission = computed(() => {
  const map = new Map<string, number>();
  checklists.value.forEach((entry) => {
    if (!entry.mission_uid) {
      return;
    }
    map.set(entry.mission_uid, (map.get(entry.mission_uid) ?? 0) + 1);
  });
  return map;
});

const missionOpenTaskCountByMission = computed(() => {
  const map = new Map<string, number>();
  checklists.value.forEach((entry) => {
    if (!entry.mission_uid) {
      return;
    }
    const openTasks = entry.tasks.filter((task) => {
      const status = normalizeTaskStatus(task.status);
      return !(status.startsWith("COMPLETE") || status === "DONE");
    }).length;
    map.set(entry.mission_uid, (map.get(entry.mission_uid) ?? 0) + openTasks);
  });
  return map;
});

const missionTeams = computed(() => {
  const missionUid = selectedMissionUid.value;
  if (!missionUid) {
    return [] as Team[];
  }
  return teams.value.filter((entry) => entry.mission_uids.includes(missionUid));
});
const missionTeamUidSet = computed(() => new Set(missionTeams.value.map((entry) => entry.uid)));
const missionHasAllocatedTeam = computed(() => missionTeams.value.length > 0);
const screenActions = computed(() => {
  const actions = [...currentScreen.value.actions];
  if (secondaryScreen.value === "missionTeamMembers" && !missionHasAllocatedTeam.value) {
    return actions.filter((action) => action !== "Add Member");
  }
  return actions;
});

const teamNameByUid = computed(() => {
  const map = new Map<string, string>();
  teams.value.forEach((team) => {
    map.set(team.uid, team.name);
  });
  return map;
});

const teamAllocationExistingTeamOptions = computed(() => {
  const options = teams.value
    .filter((entry) => !missionTeamUidSet.value.has(entry.uid))
    .sort((left, right) => left.name.localeCompare(right.name))
    .map((entry) => ({
      label: entry.name,
      value: entry.uid
    }));
  return [{ label: "Select team", value: "" }, ...options];
});

const canAssignExistingTeam = computed(
  () => selectedMissionUid.value.trim().length > 0 && teamAllocationExistingTeamUid.value.trim().length > 0
);
const canCreateMissionTeam = computed(
  () => selectedMissionUid.value.trim().length > 0 && teamAllocationNewTeamName.value.trim().length > 0
);

const memberAllocationTeamOptions = computed(() => [
  { label: "Select team", value: "" },
  ...missionTeams.value
    .slice()
    .sort((left, right) => left.name.localeCompare(right.name))
    .map((entry) => ({
      label: entry.name,
      value: entry.uid
    }))
]);

const memberAllocationExistingMemberOptions = computed(() => {
  const teamUid = memberAllocationTeamUid.value.trim();
  if (!teamUid) {
    return [{ label: "Select team first", value: "" }];
  }

  const selectedMemberUid = memberAllocationMemberUid.value.trim();
  const options = memberRecords.value
    .filter((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) {
        return false;
      }
      const identity = resolveTeamMemberIdentity(entry);
      if (!identity) {
        return false;
      }
      if (uid === selectedMemberUid) {
        return true;
      }
      return String(entry.team_uid ?? "").trim() !== teamUid;
    })
    .sort((left, right) => teamMemberPrimaryLabel(left).localeCompare(teamMemberPrimaryLabel(right)))
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      const identity = resolveTeamMemberIdentity(entry);
      const labelBase = teamMemberPrimaryLabel(entry);
      const assignedTeamUid = String(entry.team_uid ?? "").trim();
      const teamSuffix =
        assignedTeamUid && assignedTeamUid !== teamUid
          ? ` - currently in ${teamNameByUid.value.get(assignedTeamUid) ?? assignedTeamUid}`
          : "";
      return {
        label: `${labelBase} (${identity})${teamSuffix}`,
        value: uid
      };
    });

  return [{ label: "Select member", value: "" }, ...options];
});

const canAssignExistingMember = computed(
  () =>
    selectedMissionUid.value.trim().length > 0 &&
    memberAllocationTeamUid.value.trim().length > 0 &&
    memberAllocationMemberUid.value.trim().length > 0
);

const missionMembers = computed<Member[]>(() => {
  const teamUids = missionTeamUidSet.value;
  return memberRecords.value
    .filter((entry) => {
      const uid = String(entry.uid ?? "").trim();
      const teamUid = String(entry.team_uid ?? "").trim();
      return uid.length > 0 && teamUid.length > 0 && teamUids.has(teamUid);
    })
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      const identity = resolveTeamMemberIdentity(entry);
      const callsign = teamMemberPrimaryLabel(entry);
      return {
        uid,
        mission_uid: selectedMissionUid.value,
        callsign,
        role: String(entry.role ?? "UNASSIGNED"),
        capabilities: memberCapabilitiesByIdentity.value.get(normalizeIdentity(identity)) ?? []
      };
    });
});

const missionAssignmentsRaw = computed(() =>
  assignmentRecords.value.filter((entry) => String(entry.mission_uid ?? "").trim() === selectedMissionUid.value)
);

const missionAssignments = computed<Assignment[]>(() => {
  return missionAssignmentsRaw.value
    .map((entry) => {
      const assignmentUid = String(entry.assignment_uid ?? "").trim();
      const taskUid = String(entry.task_uid ?? "").trim();
      const memberIdentity = String(entry.team_member_rns_identity ?? "").trim();
      let taskLabel = taskNameByUid.value.get(taskUid) ?? taskUid;
      const requirementCount = requirementCountByTaskUid.value.get(taskUid) ?? 0;
      if (requirementCount > 0 && taskLabel) {
        taskLabel = `${taskLabel} (${requirementCount} skill req)`;
      }
      const memberLabel = memberByIdentity.value.get(normalizeIdentity(memberIdentity))?.callsign ?? memberIdentity;
      const assetsForTask = toStringList(entry.assets).map((assetUid) => assetNameByUid.value.get(assetUid) ?? assetUid);
      return {
        uid: assignmentUid || `${taskUid}-${memberIdentity}`,
        mission_uid: selectedMissionUid.value,
        task: taskLabel || "Task",
        member: memberLabel || "Unassigned",
        assets: assetsForTask
      };
    })
    .filter((entry) => entry.uid.length > 0);
});

const missionAssets = computed<Asset[]>(() => {
  const memberUids = new Set(missionMembers.value.map((entry) => entry.uid));
  const assignmentAssetUids = new Set<string>();
  missionAssignmentsRaw.value.forEach((entry) => {
    toStringList(entry.assets).forEach((assetUid) => assignmentAssetUids.add(assetUid));
  });
  return assetRecords.value
    .map((entry) => {
      const uid = String(entry.asset_uid ?? "").trim();
      if (!uid) {
        return null;
      }
      const assignedMemberUid = String(entry.team_member_uid ?? "").trim();
      if (selectedMissionUid.value) {
        const includeLinked = assignedMemberUid.length > 0 && memberUids.has(assignedMemberUid);
        const includeAssigned = assignmentAssetUids.has(uid);
        if (!includeLinked && !includeAssigned && (memberUids.size > 0 || assignmentAssetUids.size > 0)) {
          return null;
        }
      }
      return {
        uid,
        mission_uid: selectedMissionUid.value,
        name: String(entry.name ?? uid),
        type: String(entry.asset_type ?? "ASSET"),
        status: String(entry.status ?? "UNKNOWN")
      };
    })
    .filter((entry): entry is Asset => entry !== null);
});

const assets = computed<Asset[]>(() =>
  assetRecords.value
    .map((entry) => {
      const uid = String(entry.asset_uid ?? "").trim();
      if (!uid) {
        return null;
      }
      return {
        uid,
        mission_uid: "",
        name: String(entry.name ?? uid),
        type: String(entry.asset_type ?? "ASSET"),
        status: String(entry.status ?? "UNKNOWN")
      };
    })
    .filter((entry): entry is Asset => entry !== null)
);

const committedZoneIdsByMission = computed(() => {
  const map = new Map<string, string[]>();
  missions.value.forEach((mission) => {
    map.set(mission.uid, [...mission.zone_ids]);
  });
  return map;
});

const selectedZoneIds = computed(() => {
  const missionUid = selectedMissionUid.value;
  if (!missionUid) {
    return new Set<string>();
  }
  const draft = zoneDraftByMission.value[missionUid];
  if (Array.isArray(draft)) {
    return new Set(draft);
  }
  return new Set(committedZoneIdsByMission.value.get(missionUid) ?? []);
});

const zones = computed<Zone[]>(() => {
  return zoneRecords.value
    .map((entry) => {
      const uid = String(entry.zone_id ?? "").trim();
      if (!uid) {
        return null;
      }
      return {
        uid,
        mission_uid: selectedMissionUid.value,
        name: String(entry.name ?? uid),
        assigned: selectedZoneIds.value.has(uid)
      };
    })
    .filter((entry): entry is Zone => entry !== null);
});

const missionAudit = computed<AuditEvent[]>(() => {
  const missionUid = selectedMissionUid.value;
  if (!missionUid) {
    return [];
  }
  const missionChecklistUids = new Set(missionChecklists.value.map((entry) => entry.uid));

  const events = eventRecords.value
    .filter((entry) => {
      const aggregateUid = String(entry.aggregate_uid ?? "").trim();
      if (aggregateUid && aggregateUid === missionUid) {
        return true;
      }
      if (String(entry.aggregate_type ?? "").trim() === "checklist" && missionChecklistUids.has(aggregateUid)) {
        return true;
      }
      const payload = asRecord(entry.payload);
      const payloadMissionUid = String(payload.mission_uid ?? payload.mission_id ?? "").trim();
      if (payloadMissionUid && payloadMissionUid === missionUid) {
        return true;
      }
      const payloadChecklistUid = String(payload.checklist_uid ?? "").trim();
      return payloadChecklistUid.length > 0 && missionChecklistUids.has(payloadChecklistUid);
    })
    .map((entry) => {
      const createdAt = String(entry.created_at ?? "");
      const eventType = String(entry.event_type ?? "domain.event").trim();
      const payload = asRecord(entry.payload);
      return {
        uid: String(entry.event_uid ?? `${entry.event_type}-${createdAt}`),
        mission_uid: missionUid,
        timestamp: createdAt,
        time: formatAuditTime(createdAt),
        type: toAuditTypeLabel(eventType),
        message: formatDomainEventMessage(entry),
        details: {
          source: "domain_event",
          event_uid: String(entry.event_uid ?? "").trim() || null,
          domain: String(entry.domain ?? "").trim() || null,
          aggregate_type: String(entry.aggregate_type ?? "").trim() || null,
          aggregate_uid: String(entry.aggregate_uid ?? "").trim() || null,
          event_type: eventType || null,
          payload
        },
        sortTs: toEpoch(createdAt),
      };
    });

  const changes = missionChanges.value
    .filter((entry) => String(entry.mission_uid ?? "").trim() === missionUid)
    .map((entry) => {
      const timestamp = String(entry.timestamp ?? "");
      const name = String(entry.name ?? "Mission change").trim();
      const notes = String(entry.notes ?? "").trim();
      return {
        uid: String(entry.uid ?? `${name}-${timestamp}`),
        mission_uid: missionUid,
        timestamp,
        time: formatAuditTime(timestamp),
        type: toAuditTypeLabel(entry.change_type),
        message: notes ? `${name}: ${notes}` : name,
        details: {
          source: "mission_change",
          uid: String(entry.uid ?? "").trim() || null,
          mission_uid: missionUid,
          change_type: String(entry.change_type ?? "").trim() || null,
          name: name || null,
          notes: notes || null,
          hashes: toStringList(entry.hashes),
          timestamp
        },
        sortTs: toEpoch(timestamp),
      };
    });

  const logs = logEntryRecords.value
    .filter((entry) => String(entry.mission_uid ?? "").trim() === missionUid)
    .map((entry) => {
      const serverTime = String(entry.server_time ?? "").trim();
      const clientTime = String(entry.client_time ?? "").trim();
      const createdAt = String(entry.created_at ?? "").trim();
      const timestamp = serverTime || clientTime || createdAt;
      const content = String(entry.content ?? "").trim();
      const entryUid = String(entry.entry_uid ?? "").trim();
      return {
        uid: entryUid || `log-entry-${timestamp || createdAt}`,
        mission_uid: missionUid,
        timestamp,
        time: formatAuditTime(timestamp),
        type: "MISSION_LOG_ENTRY",
        message: content || "Mission log entry",
        details: {
          source: "log_entry",
          entry_uid: entryUid || null,
          mission_uid: missionUid,
          content: content || null,
          server_time: serverTime || null,
          client_time: clientTime || null,
          content_hashes: toStringList(entry.content_hashes),
          keywords: toStringList(entry.keywords),
          created_at: createdAt || null,
          updated_at: String(entry.updated_at ?? "").trim() || null
        },
        sortTs: toEpoch(timestamp || createdAt),
      };
    });

  return [...events, ...changes, ...logs]
    .sort((left, right) => right.sortTs - left.sortTs)
    .map(({ uid, mission_uid, timestamp, time, type, message, details }) => ({
      uid,
      mission_uid,
      timestamp,
      time,
      type,
      message,
      details
    }));
});

const activeMissions = computed(() => missions.value.filter((entry) => entry.status.includes("ACTIVE")).length);

const boardCounts = computed(() => {
  const tasks = missionChecklists.value.flatMap((checklist) => checklist.tasks);
  let pending = 0;
  let late = 0;
  let complete = 0;
  tasks.forEach((task) => {
    const status = normalizeTaskStatus(task.status);
    if (status.startsWith("COMPLETE")) {
      complete += 1;
      return;
    }
    if (status === "LATE") {
      late += 1;
      return;
    }
    pending += 1;
  });
  return { pending, late, complete };
});

const missionOpenTaskTotal = computed(() => boardCounts.value.pending + boardCounts.value.late);
const missionTotalTasks = computed(() => missionOpenTaskTotal.value + boardCounts.value.complete);

const boardLaneTasks = computed(() => {
  const pending: Array<{ id: string; name: string; meta: string }> = [];
  const late: Array<{ id: string; name: string; meta: string }> = [];
  const complete: Array<{ id: string; name: string; meta: string }> = [];

  missionChecklists.value.forEach((checklist) => {
    checklist.tasks.forEach((task) => {
      const laneItem = {
        id: task.id,
        name: task.name,
        meta: `${checklist.name} / ${task.assignee}`
      };
      const status = normalizeTaskStatus(task.status);
      if (status.startsWith("COMPLETE")) {
        complete.push(laneItem);
        return;
      }
      if (status === "LATE") {
        late.push(laneItem);
        return;
      }
      pending.push(laneItem);
    });
  });

  return {
    pending: pending.slice(0, 8),
    late: late.slice(0, 8),
    complete: complete.slice(0, 8)
  };
});

const assignedZones = computed(() => zones.value.filter((zone) => zone.assigned));
const zoneCoveragePercent = computed(() => {
  const total = zones.value.length;
  if (!total) {
    return 0;
  }
  return Math.round((assignedZones.value.length / total) * 100);
});

const showChecklistArea = computed(() => {
  return primaryTab.value === "checklists";
});

const showAssetArea = computed(() => {
  return ["assetRegistry", "assignAssets", "taskAssignmentWorkspace"].includes(secondaryScreen.value);
});

const progressWidth = (value: number): string => {
  if (!Number.isFinite(value)) {
    return "0%";
  }
  return `${Math.max(0, Math.min(100, Math.round(value)))}%`;
};

const statusChipClass = (status: string): string => {
  const normalized = normalizeTaskStatus(status);
  if (normalized.startsWith("COMPLETE")) {
    return "checklist-chip-success";
  }
  if (normalized === "LATE") {
    return "checklist-chip-warning";
  }
  return "checklist-chip-info";
};

const syncChipClass = (syncState: string): string => {
  const normalized = String(syncState ?? "").trim().toUpperCase();
  if (normalized === "SYNCED") {
    return "checklist-chip-success";
  }
  if (normalized === "PENDING") {
    return "checklist-chip-warning";
  }
  return "checklist-chip-info";
};

const modeChipClass = (mode: string): string => {
  const normalized = String(mode ?? "").trim().toUpperCase();
  if (normalized === "ONLINE") {
    return "checklist-chip-info";
  }
  if (normalized === "OFFLINE") {
    return "checklist-chip-warning";
  }
  return "checklist-chip-muted";
};

const checklistOriginLabel = (originType?: string | null): string => {
  const normalized = String(originType ?? "").trim().toUpperCase();
  if (normalized === "CSV_IMPORT") {
    return "CSV IMPORT";
  }
  if (normalized === "RCH_TEMPLATE") {
    return "TEMPLATE";
  }
  if (normalized === "BLANK_TEMPLATE") {
    return "BLANK";
  }
  return normalized || "UNSPECIFIED";
};

const checklistDescriptionLabel = (description: string): string => {
  const text = String(description ?? "").trim();
  return text || "No description provided";
};

const openChecklistDetailView = async (checklistUid: string) => {
  const uid = String(checklistUid ?? "").trim();
  if (!uid) {
    return;
  }
  selectedChecklistUid.value = uid;
  checklistDetailUid.value = uid;
  try {
    await hydrateChecklistRecord(uid);
  } catch (error) {
    handleApiError(error, "Unable to load checklist details");
  }
};

const closeChecklistDetailView = () => {
  checklistLinkMissionModalOpen.value = false;
  checklistDetailUid.value = "";
  if (secondaryScreen.value === "checklistDetails" || secondaryScreen.value === "checklistRunDetail") {
    secondaryScreen.value = "checklistOverview";
  }
};

const createChecklistFromDetailTemplate = () => {
  const detailUid = checklistDetailRecord.value?.uid ?? "";
  if (!detailUid) {
    return;
  }
  if (checklistTemplateOptions.value.some((entry) => entry.uid === detailUid)) {
    checklistTemplateSelectionUid.value = detailUid;
  }
  try {
    openChecklistTemplateModal();
  } catch (error) {
    handleApiError(error, "Unable to open checklist template selector");
  }
};

const openChecklistCreationModal = () => {
  try {
    openChecklistTemplateModal();
  } catch (error) {
    handleApiError(error, "Unable to open checklist template selector");
  }
};

const openChecklistMissionLinkModal = () => {
  const checklist = checklistDetailRecord.value;
  if (!checklist?.uid) {
    toastStore.push("Select a checklist first", "warning");
    return;
  }
  const currentMissionUid = String(checklist.mission_uid ?? "").trim();
  if (currentMissionUid) {
    checklistLinkMissionSelectionUid.value = currentMissionUid;
  } else {
    const preferredMissionUid = String(selectedMissionUid.value ?? "").trim();
    const missionExists = missions.value.some((mission) => mission.uid === preferredMissionUid);
    checklistLinkMissionSelectionUid.value = missionExists ? preferredMissionUid : "";
  }
  checklistLinkMissionModalOpen.value = true;
};

const closeChecklistMissionLinkModal = () => {
  if (checklistLinkMissionSubmitting.value) {
    return;
  }
  checklistLinkMissionModalOpen.value = false;
};

const showChecklistFilterNotice = () => {
  toastStore.push("Checklist filter presets can be added from this workspace", "info");
};

const setChecklistWorkspaceView = (view: "active" | "templates") => {
  checklistLinkMissionModalOpen.value = false;
  checklistWorkspaceView.value = view;
  if (view === "templates") {
    checklistDetailUid.value = "";
    syncChecklistTemplateEditorSelection();
  }
};

const openTemplateBuilderFromChecklist = () => {
  setPrimaryTab("checklists");
  secondaryScreen.value = "checklistOverview";
  setChecklistWorkspaceView("templates");
};

const openChecklistImportFromChecklist = () => {
  setPrimaryTab("checklists");
  secondaryScreen.value = "checklistImportCsv";
};

const navigateToChecklistTemplateList = () => {
  setPrimaryTab("checklists");
  secondaryScreen.value = "checklistOverview";
  setChecklistWorkspaceView("templates");
};

const deleteChecklistFromDetail = async () => {
  if (checklistDeleteBusy.value) {
    return;
  }
  const checklistUid = String(checklistDetailRecord.value?.uid ?? "").trim();
  if (!checklistUid) {
    toastStore.push("Select a checklist first", "warning");
    return;
  }
  const checklistName = String(checklistDetailRecord.value?.name ?? checklistUid).trim() || checklistUid;
  if (!window.confirm(`Delete checklist "${checklistName}"?`)) {
    return;
  }
  checklistDeleteBusy.value = true;
  try {
    await deleteRequest(`${endpoints.checklists}/${checklistUid}`);
    if (selectedChecklistUid.value === checklistUid) {
      selectedChecklistUid.value = "";
    }
    if (checklistDetailUid.value === checklistUid) {
      checklistDetailUid.value = "";
    }
    checklistLinkMissionModalOpen.value = false;
    await loadWorkspace();
    toastStore.push("Checklist removed", "success");
  } catch (error) {
    handleApiError(error, "Unable to remove checklist");
  } finally {
    checklistDeleteBusy.value = false;
  }
};

const submitChecklistMissionLink = async () => {
  if (checklistLinkMissionSubmitting.value) {
    return;
  }
  const checklistUid = String(checklistDetailRecord.value?.uid ?? "").trim();
  if (!checklistUid) {
    toastStore.push("Select a checklist first", "warning");
    return;
  }
  if (!canSubmitChecklistMissionLink.value) {
    checklistLinkMissionModalOpen.value = false;
    return;
  }
  checklistLinkMissionSubmitting.value = true;
  const missionUid = checklistLinkMissionSelectionUid.value.trim();
  try {
    await patchRequest(`${endpoints.checklists}/${checklistUid}`, {
      patch: { mission_uid: missionUid || null }
    });
    await loadWorkspace();
    selectedChecklistUid.value = checklistUid;
    checklistDetailUid.value = checklistUid;
    try {
      await hydrateChecklistRecord(checklistUid);
    } catch (error) {
      handleApiError(error, "Checklist mission link saved but detail refresh failed");
    }
    checklistLinkMissionModalOpen.value = false;
    toastStore.push(missionUid ? "Checklist linked to mission" : "Checklist mission link cleared", "success");
  } catch (error) {
    handleApiError(error, "Unable to link checklist to mission");
  } finally {
    checklistLinkMissionSubmitting.value = false;
  }
};

const addChecklistTaskFromDetail = async () => {
  const checklist = checklistDetailRecord.value;
  if (!checklist?.uid) {
    toastStore.push("Select a checklist first", "warning");
    return;
  }
  selectedChecklistUid.value = checklist.uid;
  try {
    const nextNumber = checklistDetailRows.value.reduce((max, row) => Math.max(max, row.number), 0) + 1;
    const payload: Record<string, unknown> = { number: nextNumber };
    const parsedDue = Number(checklistTaskDueDraft.value);
    if (Number.isFinite(parsedDue)) {
      payload.due_relative_minutes = Math.trunc(parsedDue);
    }
    await post(`${endpoints.checklists}/${checklist.uid}/tasks`, payload);
    await loadWorkspace();
    toastStore.push("Checklist task added", "success");
  } catch (error) {
    handleApiError(error, "Unable to add checklist task");
  }
};

const toggleChecklistTaskDone = async (row: { task_uid: string; done: boolean }) => {
  const checklist = checklistDetailRaw.value;
  const checklistUid = String(checklist?.uid ?? "").trim();
  const taskUid = String(row.task_uid ?? "").trim();
  if (!checklistUid || !taskUid) {
    toastStore.push("Unable to update task status", "warning");
    return;
  }
  if (checklistTaskStatusBusyByTaskUid.value[taskUid]) {
    return;
  }
  checklistTaskStatusBusyByTaskUid.value = {
    ...checklistTaskStatusBusyByTaskUid.value,
    [taskUid]: true
  };
  try {
    const userStatus = row.done ? "PENDING" : "COMPLETE";
    await post(`${endpoints.checklists}/${checklistUid}/tasks/${taskUid}/status`, {
      user_status: userStatus,
      changed_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY
    });
    await loadWorkspace();
    toastStore.push("Task status updated", "success");
  } catch (error) {
    handleApiError(error, "Unable to update task status");
  } finally {
    const next = { ...checklistTaskStatusBusyByTaskUid.value };
    delete next[taskUid];
    checklistTaskStatusBusyByTaskUid.value = next;
  }
};

const setPrimaryTab = (tab: PrimaryTab, syncRoute = true) => {
  primaryTab.value = tab;
  secondaryScreen.value = screensByTab[tab][0].id;
  if (tab !== "checklists") {
    checklistDetailUid.value = "";
  }
  if (tab === "checklists" && !checklistDetailUid.value) {
    checklistWorkspaceView.value = "active";
  }
  if (!syncRoute) {
    return;
  }
  const missionUid = selectedMissionUid.value.trim();
  const missionQuery = missionUid ? { mission_uid: missionUid } : undefined;
  if (tab === "checklists") {
    if (route.path !== "/checklists" || queryText(route.query.mission_uid) !== missionUid) {
      router.push({ path: "/checklists", query: missionQuery }).catch(() => undefined);
    }
    return;
  }
  if (route.path === "/checklists") {
    router.push({ path: "/missions", query: missionQuery }).catch(() => undefined);
  }
};

const setSecondaryScreen = (screen: ScreenId) => {
  if (screen === "missionEdit" && !selectedMissionUid.value) {
    toastStore.push("Select a mission before opening mission edit", "warning");
    return;
  }
  if (screen === "missionCreate") {
    resetMissionDraft("create");
  } else if (screen === "missionEdit") {
    resetMissionDraft("edit", selectedMission.value);
  }
  secondaryScreen.value = screen;
};

const openMissionEditScreen = () => {
  setSecondaryScreen("missionEdit");
};

const openMissionLogsPage = () => {
  router
    .push({
      path: "/missions/logs",
      query: selectedMissionUid.value ? { mission_uid: selectedMissionUid.value } : undefined
    })
    .catch(() => undefined);
};

const openTopicCreatePage = async () => {
  await router.push("/topics");
};

const selectMission = (missionUid: string) => {
  selectedMissionUid.value = missionUid;
  primaryTab.value = "mission";
  setSecondaryScreen("missionOverview");
  if (route.path === "/checklists") {
    router.push({ path: "/missions", query: { mission_uid: missionUid } }).catch(() => undefined);
  }
};

const loadWorkspace = async () => {
  loadingWorkspace.value = true;
  try {
    const [
      missionData,
      topicData,
      checklistPayload,
      templatePayload,
      teamData,
      teamMemberData,
      assetData,
      assignmentData,
      eventData,
      missionChangeData,
      logEntryData,
      zoneData,
      skillData,
      teamMemberSkillData,
      taskSkillRequirementData
    ] = await Promise.all([
      get<MissionRaw[]>(endpoints.r3aktMissions),
      get<TopicRaw[]>(endpoints.topics),
      get<{ checklists?: ChecklistRaw[] }>(endpoints.checklists),
      get<{ templates?: TemplateRaw[] }>(endpoints.checklistTemplates),
      get<TeamRaw[]>(endpoints.r3aktTeams),
      get<TeamMemberRaw[]>(endpoints.r3aktTeamMembers),
      get<AssetRaw[]>(endpoints.r3aktAssets),
      get<AssignmentRaw[]>(endpoints.r3aktAssignments),
      get<DomainEventRaw[]>(endpoints.r3aktEvents),
      get<MissionChangeRaw[]>(endpoints.r3aktMissionChanges),
      get<LogEntryRaw[]>(endpoints.r3aktLogEntries),
      get<ZoneRaw[]>(endpoints.zones),
      get<SkillRaw[]>(endpoints.r3aktSkills),
      get<TeamMemberSkillRaw[]>(endpoints.r3aktTeamMemberSkills),
      get<TaskSkillRequirementRaw[]>(endpoints.r3aktTaskSkillRequirements)
    ]);

    missions.value = toArray<MissionRaw>(missionData)
      .map((entry) => {
        const uid = String(entry.uid ?? "").trim();
        if (!uid) {
          return null;
        }
        return {
          uid,
          mission_name: String(entry.mission_name ?? uid),
          description: String(entry.description ?? ""),
          topic: String(entry.topic_id ?? "unscoped"),
          status: normalizeMissionStatus(entry.mission_status),
          zone_ids: toStringList(entry.zones),
          path: String(entry.path ?? ""),
          classification: String(entry.classification ?? ""),
          tool: String(entry.tool ?? ""),
          keywords: toStringList(entry.keywords),
          parent_uid: String(entry.parent_uid ?? ""),
          feeds: toStringList(entry.feeds),
          default_role: String(entry.default_role ?? ""),
          mission_priority: (() => {
            const parsed = Number(entry.mission_priority);
            return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
          })(),
          owner_role: String(entry.owner_role ?? ""),
          token: String(entry.token ?? ""),
          invite_only: Boolean(entry.invite_only),
          expiration: String(entry.expiration ?? ""),
          mission_rde_role: String(entry.mission_rde_role ?? ""),
          asset_uids: toStringList(entry.asset_uids)
        };
      })
      .filter((entry): entry is Mission => entry !== null);

    topicRecords.value = toArray<TopicRaw>(topicData);
    checklistRecords.value = toArray<ChecklistRaw>(checklistPayload.checklists);
    templateRecords.value = toArray<TemplateRaw>(templatePayload.templates);
    teamRecords.value = toArray<TeamRaw>(teamData);
    memberRecords.value = toArray<TeamMemberRaw>(teamMemberData);
    assetRecords.value = toArray<AssetRaw>(assetData);
    assignmentRecords.value = toArray<AssignmentRaw>(assignmentData);
    eventRecords.value = toArray<DomainEventRaw>(eventData);
    missionChanges.value = toArray<MissionChangeRaw>(missionChangeData);
    logEntryRecords.value = toArray<LogEntryRaw>(logEntryData);
    zoneRecords.value = toArray<ZoneRaw>(zoneData);
    skillRecords.value = toArray<SkillRaw>(skillData);
    teamMemberSkillRecords.value = toArray<TeamMemberSkillRaw>(teamMemberSkillData);
    taskSkillRequirementRecords.value = toArray<TaskSkillRequirementRaw>(taskSkillRequirementData);

    const activeDetailUid = String(checklistDetailUid.value || selectedChecklistUid.value || "").trim();
    if (activeDetailUid) {
      try {
        await hydrateChecklistRecord(activeDetailUid);
      } catch (error) {
        handleApiError(error, "Checklist detail refresh failed");
      }
    }
  } finally {
    loadingWorkspace.value = false;
  }
};

const {
  startNewChecklistTemplateDraft,
  selectChecklistTemplateForEditor,
  syncChecklistTemplateEditorSelection,
  saveChecklistTemplateDraft,
  saveChecklistTemplateDraftAsNew,
  cloneChecklistTemplateDraft,
  archiveChecklistTemplateDraft,
  convertChecklistTemplateDraftToServerTemplate,
  deleteChecklistTemplateDraft
} = useChecklistTemplateCrud({
  buildTimestampTag,
  loadWorkspace,
  pushToast: (message, tone) => toastStore.push(message, tone),
  handleApiError,
  confirmDelete: (message) => window.confirm(message),
  defaultSourceIdentity: DEFAULT_SOURCE_IDENTITY,
  checklistTemplateOptions,
  selectedChecklistTemplateEditorOption,
  checklistTemplateEditorMode,
  checklistTemplateEditorHydrating,
  checklistTemplateEditorSelectionUid,
  checklistTemplateEditorSelectionSourceType,
  checklistTemplateDraftTemplateUid,
  checklistTemplateDraftName,
  checklistTemplateDraftDescription,
  checklistTemplateDraftColumns,
  checklistTemplateEditorDirty,
  checklistTemplateEditorSaving,
  checklistTemplateSelectionUid,
  checklistTemplateDeleteBusyByUid,
  templateRecords,
  checklistRecords,
  selectedChecklistUid,
  checklistDetailUid,
  canSaveChecklistTemplateDraft,
  canSaveChecklistTemplateDraftAsNew,
  canCloneChecklistTemplateDraft,
  canArchiveChecklistTemplateDraft,
  canConvertChecklistTemplateDraft,
  canDeleteChecklistTemplateDraft,
  normalizeChecklistTemplateDraftColumns,
  createBlankChecklistTemplateDraftColumns,
  validateChecklistTemplateDraftPayload,
  toChecklistTemplateColumnPayload
});

const runAction = async (
  operation: () => Promise<void>,
  successMessage: string,
  failureMessage: string
) => {
  try {
    await operation();
    toastStore.push(successMessage, "success");
  } catch (error) {
    handleApiError(error, failureMessage);
  }
};

const ensureMissionSelected = (): string => {
  const missionUid = selectedMissionUid.value;
  if (!missionUid) {
    throw new Error("Select a mission first");
  }
  return missionUid;
};

const ensureChecklistSelected = (): ChecklistRaw => {
  const checklist = selectedChecklistRaw.value;
  if (!checklist?.uid) {
    throw new Error("Select a checklist first");
  }
  return checklist;
};

const resolveMissionChecklistRaw = (missionUid: string): ChecklistRaw | null => {
  const selected = selectedChecklistRaw.value;
  if (selected?.uid && String(selected.mission_id ?? "").trim() === missionUid) {
    return selected;
  }
  const candidates = checklistRecords.value
    .filter((entry) => {
      const uid = String(entry.uid ?? "").trim();
      const checklistMissionUid = String(entry.mission_id ?? "").trim();
      return uid.length > 0 && checklistMissionUid === missionUid;
    })
    .sort((left, right) => {
      const createdDiff = toEpoch(right.created_at) - toEpoch(left.created_at);
      if (createdDiff !== 0) {
        return createdDiff;
      }
      return String(left.uid ?? "").localeCompare(String(right.uid ?? ""));
    });
  return candidates[0] ?? null;
};

const resetTeamAllocationModalDraft = () => {
  teamAllocationExistingTeamUid.value = teamAllocationExistingTeamOptions.value[1]?.value ?? "";
  const missionName = String(selectedMission.value?.mission_name ?? "Mission").trim() || "Mission";
  teamAllocationNewTeamName.value = `${missionName} Team ${missionTeams.value.length + 1}`;
  teamAllocationNewTeamDescription.value = "";
};

const openTeamAllocationModal = () => {
  ensureMissionSelected();
  resetTeamAllocationModalDraft();
  teamAllocationModalOpen.value = true;
};

const closeTeamAllocationModal = () => {
  if (teamAllocationSubmitting.value) {
    return;
  }
  teamAllocationModalOpen.value = false;
};

const assignExistingTeamToMission = async () => {
  const missionUid = ensureMissionSelected();
  const teamUid = teamAllocationExistingTeamUid.value.trim();
  if (!teamUid) {
    throw new Error("Select a team to assign");
  }
  if (missionTeamUidSet.value.has(teamUid)) {
    throw new Error("Selected team is already linked to this mission");
  }
  teamAllocationSubmitting.value = true;
  try {
    await put(`${endpoints.r3aktTeams}/${encodeURIComponent(teamUid)}/missions/${encodeURIComponent(missionUid)}`);
    await loadWorkspace();
    teamAllocationModalOpen.value = false;
    toastStore.push("Team linked to mission", "success");
  } catch (error) {
    handleApiError(error, "Unable to link team to mission");
  } finally {
    teamAllocationSubmitting.value = false;
  }
};

const createMissionTeamFromModal = async () => {
  const missionUid = ensureMissionSelected();
  const teamName = teamAllocationNewTeamName.value.trim();
  if (!teamName) {
    throw new Error("Team name is required");
  }
  teamAllocationSubmitting.value = true;
  try {
    await post<TeamRaw>(endpoints.r3aktTeams, {
      mission_uid: missionUid,
      mission_uids: [missionUid],
      team_name: teamName,
      team_description: teamAllocationNewTeamDescription.value.trim() || "Created from Mission workspace"
    });
    await loadWorkspace();
    teamAllocationModalOpen.value = false;
    toastStore.push("Mission team created", "success");
  } catch (error) {
    handleApiError(error, "Unable to create mission team");
  } finally {
    teamAllocationSubmitting.value = false;
  }
};

const resetMemberAllocationModalDraft = () => {
  memberAllocationTeamUid.value = missionTeams.value[0]?.uid ?? "";
  memberAllocationMemberUid.value = "";
};

const openMemberAllocationModal = () => {
  ensureMissionSelected();
  if (!missionTeams.value.length) {
    throw new Error("Assign a team to this mission before adding members");
  }
  resetMemberAllocationModalDraft();
  memberAllocationModalOpen.value = true;
};

const closeMemberAllocationModal = () => {
  if (memberAllocationSubmitting.value) {
    return;
  }
  memberAllocationModalOpen.value = false;
};

const assignExistingMemberToTeam = async () => {
  const selectedMemberUid = memberAllocationMemberUid.value.trim();
  const teamUid = memberAllocationTeamUid.value.trim();
  if (!selectedMemberUid || !teamUid) {
    throw new Error("Select both a team and a member");
  }

  const selectedMember = memberRecords.value.find((entry) => String(entry.uid ?? "").trim() === selectedMemberUid);
  if (!selectedMember) {
    throw new Error("Selected member could not be resolved");
  }
  const identity = resolveTeamMemberIdentity(selectedMember);
  if (!identity) {
    throw new Error("Selected member has no RNS identity");
  }
  if (String(selectedMember.team_uid ?? "").trim() === teamUid) {
    throw new Error("Selected member is already assigned to this team");
  }

  memberAllocationSubmitting.value = true;
  try {
    await post<TeamMemberRaw>(endpoints.r3aktTeamMembers, {
      uid: selectedMemberUid,
      team_uid: teamUid,
      rns_identity: identity,
      display_name: String(selectedMember.display_name ?? selectedMember.callsign ?? identity).trim() || identity,
      role: selectedMember.role ?? "TEAM_MEMBER",
      callsign: selectedMember.callsign ?? null
    });
    await loadWorkspace();
    memberAllocationModalOpen.value = false;
    toastStore.push("Team member assigned", "success");
  } catch (error) {
    handleApiError(error, "Unable to assign team member");
  } finally {
    memberAllocationSubmitting.value = false;
  }
};

const openTeamMemberCreateWorkspace = async () => {
  const preferredTeamUid = memberAllocationTeamUid.value.trim() || missionTeams.value[0]?.uid || "";
  await router.push({
    path: "/users",
    query: {
      tab: "team-members",
      create_team_member: "1",
      team_uid: preferredTeamUid || undefined
    }
  });
};

const addTeamAction = async () => {
  openTeamAllocationModal();
};

const addMemberAction = async () => {
  openMemberAllocationModal();
};

const ensureMemberIdentityForMission = async (): Promise<{ uid: string; identity: string }> => {
  const member = missionMembers.value[0];
  if (!member) {
    throw new Error("No mission member is assigned. Use Add Member to assign existing team members.");
  }
  const raw = memberRecords.value.find((entry) => String(entry.uid ?? "").trim() === member.uid);
  const identity = raw ? resolveTeamMemberIdentity(raw) : "";
  if (!identity) {
    throw new Error("Mission member identity is missing");
  }
  return { uid: member.uid, identity };
};

const ensureChecklistTaskContext = async (): Promise<{ checklistUid: string; taskUid: string }> => {
  const missionUid = ensureMissionSelected();
  let checklist = resolveMissionChecklistRaw(missionUid);
  if (!checklist?.uid) {
    await createChecklistAction();
    checklist = resolveMissionChecklistRaw(missionUid);
  }
  if (!checklist?.uid) {
    throw new Error("No checklist is available for this mission");
  }
  const checklistUid = String(checklist.uid).trim();
  selectedChecklistUid.value = checklistUid;
  let taskUid = toArray<ChecklistTaskRaw>(checklist.tasks).find((task) => String(task.task_uid ?? "").trim().length > 0)
    ?.task_uid;
  if (!taskUid) {
    await post(`${endpoints.checklists}/${checklistUid}/tasks`, {
      number: 1,
      due_relative_minutes: 10
    });
    await loadWorkspace();
    checklist =
      checklistRecords.value.find((entry) => String(entry.uid ?? "").trim() === checklistUid) ??
      resolveMissionChecklistRaw(missionUid);
    taskUid = toArray<ChecklistTaskRaw>(checklist?.tasks).find((task) => String(task.task_uid ?? "").trim().length > 0)
      ?.task_uid;
  }
  if (!taskUid) {
    throw new Error("Checklist task context could not be created");
  }
  return { checklistUid, taskUid };
};

const deployAssetAction = async () => {
  const member = missionMembers.value[0];
  const payload: Record<string, unknown> = {
    name: `ASSET-${buildTimestampTag().slice(-6)}`,
    asset_type: "FIELD_UNIT",
    status: "AVAILABLE"
  };
  if (member?.uid) {
    payload.team_member_uid = member.uid;
  }
  await post<AssetRaw>(endpoints.r3aktAssets, payload);
  await loadWorkspace();
};

const ensureAssetForMission = async (): Promise<string> => {
  let missionAsset = missionAssets.value[0];
  if (!missionAsset) {
    await deployAssetAction();
    missionAsset = missionAssets.value[0];
  }
  if (!missionAsset) {
    throw new Error("No mission asset is available");
  }
  return missionAsset.uid;
};

const resetMissionDraft = (mode: "create" | "edit", mission?: Mission) => {
  if (mode === "edit" && mission) {
    missionDraftName.value = mission.mission_name;
    missionDraftTopic.value = mission.topic;
    missionDraftStatus.value = toMissionStatusValue(mission.status);
    missionDraftDescription.value = mission.description;
    missionDraftParentUid.value = mission.parent_uid;
    missionDraftPath.value = mission.path;
    missionDraftClassification.value = mission.classification;
    missionDraftTool.value = mission.tool;
    missionDraftKeywords.value = joinCommaSeparated(mission.keywords);
    missionDraftDefaultRole.value = mission.default_role;
    missionDraftOwnerRole.value = mission.owner_role;
    missionDraftPriority.value = mission.mission_priority === null ? "" : String(mission.mission_priority);
    missionDraftMissionRdeRole.value = mission.mission_rde_role;
    missionDraftToken.value = mission.token;
    missionDraftFeeds.value = joinCommaSeparated(mission.feeds);
    missionDraftExpiration.value = toDatetimeLocalValue(mission.expiration);
    missionDraftInviteOnly.value = mission.invite_only;
    missionDraftTeamUid.value = missionTeams.value[0]?.uid ?? "";
    missionDraftZoneUids.value = [...mission.zone_ids];
    missionDraftAssetUids.value = mission.asset_uids.length
      ? [...mission.asset_uids]
      : missionAssets.value.map((entry) => entry.uid);
    return;
  }

  missionDraftName.value = "";
  missionDraftTopic.value = "";
  missionDraftStatus.value = "MISSION_ACTIVE";
  missionDraftDescription.value = "";
  missionDraftParentUid.value = "";
  missionDraftTeamUid.value = "";
  missionDraftPath.value = "";
  missionDraftClassification.value = "";
  missionDraftTool.value = "";
  missionDraftKeywords.value = "";
  missionDraftDefaultRole.value = "";
  missionDraftOwnerRole.value = "";
  missionDraftPriority.value = "";
  missionDraftMissionRdeRole.value = "";
  missionDraftToken.value = "";
  missionDraftFeeds.value = "";
  missionDraftExpiration.value = "";
  missionDraftInviteOnly.value = false;
  missionDraftZoneUids.value = [];
  missionDraftAssetUids.value = [];
};

const buildMissionDraftPayload = () => {
  const missionName = missionDraftName.value.trim();
  if (!missionName) {
    throw new Error("Mission name is required");
  }

  return {
    mission_name: missionName,
    mission_status: toMissionStatusValue(missionDraftStatus.value),
    topic_id: missionDraftTopic.value.trim() || null,
    description: missionDraftDescription.value.trim(),
    path: missionDraftPath.value.trim() || null,
    classification: missionDraftClassification.value.trim() || null,
    tool: missionDraftTool.value.trim() || null,
    keywords: splitCommaSeparated(missionDraftKeywords.value),
    parent_uid: missionDraftParentUid.value.trim() || null,
    feeds: splitCommaSeparated(missionDraftFeeds.value),
    default_role: missionDraftDefaultRole.value.trim() || null,
    mission_priority: toOptionalInteger(missionDraftPriority.value),
    owner_role: missionDraftOwnerRole.value.trim() || null,
    token: missionDraftToken.value.trim() || null,
    invite_only: missionDraftInviteOnly.value,
    expiration: fromDatetimeLocalValue(missionDraftExpiration.value),
    mission_rde_role: missionDraftMissionRdeRole.value.trim() || null,
    zones: [...missionDraftZoneUids.value],
    asset_uids: [...missionDraftAssetUids.value]
  };
};

const syncMissionReferenceLinks = async (missionUid: string) => {
  const selectedTeamUid = missionDraftTeamUid.value.trim();
  const linkedTeamUids = teams.value.filter((entry) => entry.mission_uids.includes(missionUid)).map((entry) => entry.uid);
  const teamLinkOperations: Promise<unknown>[] = [];

  if (selectedTeamUid) {
    if (!linkedTeamUids.includes(selectedTeamUid)) {
      teamLinkOperations.push(
        put(`${endpoints.r3aktTeams}/${encodeURIComponent(selectedTeamUid)}/missions/${encodeURIComponent(missionUid)}`)
      );
    }
  }

  linkedTeamUids
    .filter((uid) => uid !== selectedTeamUid)
    .forEach((uid) => {
      teamLinkOperations.push(
        deleteRequest(`${endpoints.r3aktTeams}/${encodeURIComponent(uid)}/missions/${encodeURIComponent(missionUid)}`)
      );
    });

  const committedZones = new Set(committedZoneIdsByMission.value.get(missionUid) ?? []);
  const selectedZones = new Set(missionDraftZoneUids.value);
  const missionZonesBase = `${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}/zones`;
  const zoneOperations: Promise<unknown>[] = [
    ...[...selectedZones]
      .filter((zoneUid) => !committedZones.has(zoneUid))
      .map((zoneUid) => put(`${missionZonesBase}/${encodeURIComponent(zoneUid)}`)),
    ...[...committedZones]
      .filter((zoneUid) => !selectedZones.has(zoneUid))
      .map((zoneUid) => deleteRequest(`${missionZonesBase}/${encodeURIComponent(zoneUid)}`))
  ];

  await Promise.all([...teamLinkOperations, ...zoneOperations]);
};

const createMissionAction = async () => {
  const payload = buildMissionDraftPayload();
  const created = await post<MissionRaw>(endpoints.r3aktMissions, payload);
  const createdUid = String(created.uid ?? "").trim();
  if (createdUid) {
    await syncMissionReferenceLinks(createdUid);
  }
  await loadWorkspace();
  if (createdUid) {
    selectedMissionUid.value = createdUid;
  }
};

const updateMissionAction = async () => {
  const missionUid = ensureMissionSelected();
  const payload = buildMissionDraftPayload();
  await patchRequest(`${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}`, {
    patch: payload
  });
  await syncMissionReferenceLinks(missionUid);
  await loadWorkspace();
};

const broadcastMissionAction = async () => {
  const missionUid = ensureMissionSelected();
  await post<MissionChangeRaw>(endpoints.r3aktMissionChanges, {
    mission_uid: missionUid,
    name: "Mission broadcast",
    change_type: "ADD_CONTENT",
    notes: "Broadcast emitted from mission workspace",
    team_member_rns_identity: DEFAULT_SOURCE_IDENTITY,
    timestamp: new Date().toISOString()
  });
  await loadWorkspace();
};

const createChecklistAction = async () => {
  const missionUid = selectedMissionUid.value || undefined;
  const missionName = selectedMission.value?.mission_name || "Mission";
  const suffix = new Date().toISOString().slice(11, 19).replace(/:/g, "");
  const checklistName = `${missionName} Checklist ${suffix}`;
  const firstTemplate = templateRecords.value.find((entry) => String(entry.uid ?? "").trim().length > 0);
  if (firstTemplate?.uid) {
    await post<ChecklistRaw>(endpoints.checklists, {
      template_uid: firstTemplate.uid,
      mission_uid: missionUid,
      name: checklistName,
      source_identity: DEFAULT_SOURCE_IDENTITY
    });
  } else {
    await post<ChecklistRaw>(endpoints.checklistsOffline, {
      mission_uid: missionUid,
      name: checklistName,
      origin_type: "BLANK_TEMPLATE",
      source_identity: DEFAULT_SOURCE_IDENTITY
    });
  }
  await loadWorkspace();
};

const toSortedChecklistColumns = (columns: ChecklistColumnRaw[]): ChecklistColumnRaw[] => {
  return [...columns].sort((left, right) => {
    const leftOrder = Number(left.display_order ?? 0);
    const rightOrder = Number(right.display_order ?? 0);
    return leftOrder - rightOrder;
  });
};

const toChecklistColumnPayload = (columns: ChecklistColumnRaw[]) => {
  return toSortedChecklistColumns(columns).map((column, index) => ({
    column_name: String(column.column_name ?? `Column ${index + 1}`),
    display_order: index + 1,
    column_type: String(column.column_type ?? "SHORT_STRING"),
    column_editable: Boolean(column.column_editable ?? true),
    is_removable: Boolean(column.is_removable ?? true),
    system_key: column.system_key ?? undefined,
    background_color: column.background_color ?? undefined,
    text_color: column.text_color ?? undefined
  }));
};

const findDueColumnUid = (columns: ChecklistColumnRaw[]): string => {
  return (
    toSortedChecklistColumns(columns)
      .find((column) => String(column.system_key ?? "").trim().toUpperCase() === "DUE_RELATIVE_DTG")
      ?.column_uid?.trim() || ""
  );
};

const parseDueRelativeMinutes = (task: ChecklistTaskRaw, sourceDueColumnUid: string): number | undefined => {
  if (task.due_relative_minutes !== null && task.due_relative_minutes !== undefined) {
    const dueRelative = Number(task.due_relative_minutes);
    if (!Number.isNaN(dueRelative) && Number.isFinite(dueRelative)) {
      return Math.trunc(dueRelative);
    }
  }
  if (!sourceDueColumnUid) {
    return undefined;
  }
  const dueCell = toArray<ChecklistCellRaw>(task.cells).find(
    (cell) => String(cell.column_uid ?? "").trim() === sourceDueColumnUid
  );
  const parsed = Number(String(dueCell?.value ?? "").trim());
  if (Number.isNaN(parsed) || !Number.isFinite(parsed)) {
    return undefined;
  }
  return Math.trunc(parsed);
};

const parseCsvDueRelativeMinutes = (value: string): number | undefined => {
  const raw = String(value ?? "").trim();
  if (!raw) {
    return undefined;
  }
  const direct = Number(raw);
  if (Number.isFinite(direct)) {
    return Math.trunc(direct);
  }
  const match = raw.match(/^T?\s*([+-])?\s*(\d{1,3})(?::(\d{1,2}))?$/i);
  if (!match) {
    return undefined;
  }
  const sign = match[1] === "-" ? -1 : 1;
  const hours = Number(match[2] ?? "0");
  const minutes = Number(match[3] ?? "0");
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return undefined;
  }
  return sign * (Math.trunc(hours) * 60 + Math.trunc(minutes));
};

const normalizeCsvHeaderLabel = (value: string): string =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[_-]/g, " ")
    .replace(/\s+/g, " ");

const createChecklistFromUploadedCsvAction = async (
  checklistName: string,
  missionUid?: string
): Promise<ChecklistRaw> => {
  const headers = [...csvImportHeaders.value];
  const rows = [...csvImportRows.value];
  if (!headers.length || !rows.length) {
    throw new Error("Upload a CSV file before importing");
  }

  const dueAliases = new Set(["DUE", "DUE RELATIVE MINUTES", "DUE MINUTES"]);
  const dueHeaderIndex = headers.findIndex((header) => dueAliases.has(normalizeCsvHeaderLabel(header)));
  const columns: Array<Record<string, unknown>> = [];
  if (dueHeaderIndex < 0) {
    columns.push({
      column_name: "Due",
      display_order: 1,
      column_type: "RELATIVE_TIME",
      column_editable: false,
      is_removable: false,
      system_key: "DUE_RELATIVE_DTG"
    });
    headers.forEach((header, index) => {
      columns.push({
        column_name: header || `Column ${index + 1}`,
        display_order: index + 2,
        column_type: "SHORT_STRING",
        column_editable: true,
        is_removable: true
      });
    });
  } else {
    headers.forEach((header, index) => {
      if (index === dueHeaderIndex) {
        columns.push({
          column_name: header || "Due",
          display_order: index + 1,
          column_type: "RELATIVE_TIME",
          column_editable: false,
          is_removable: false,
          system_key: "DUE_RELATIVE_DTG"
        });
        return;
      }
      columns.push({
        column_name: header || `Column ${index + 1}`,
        display_order: index + 1,
        column_type: "SHORT_STRING",
        column_editable: true,
        is_removable: true
      });
    });
  }

  const created = await post<ChecklistRaw>(endpoints.checklistsOffline, {
    mission_uid: missionUid,
    name: checklistName,
    origin_type: "CSV_IMPORT",
    source_identity: DEFAULT_SOURCE_IDENTITY,
    columns
  });
  const createdChecklistUid = String(created.uid ?? "").trim();
  if (!createdChecklistUid) {
    throw new Error("Checklist import failed");
  }

  const createdColumns = toSortedChecklistColumns(toArray<ChecklistColumnRaw>(created.columns));
  const dueColumnOrder = dueHeaderIndex < 0 ? 1 : dueHeaderIndex + 1;
  const dueColumnUid =
    createdColumns.find((column) => Number(column.display_order ?? 0) === dueColumnOrder)?.column_uid ?? "";
  const targetByHeaderIndex = new Map<number, string>();
  headers.forEach((_, headerIndex) => {
    if (headerIndex === dueHeaderIndex) {
      return;
    }
    const displayOrder = dueHeaderIndex < 0 ? headerIndex + 2 : headerIndex + 1;
    const columnUid = createdColumns.find((column) => Number(column.display_order ?? 0) === displayOrder)?.column_uid ?? "";
    if (columnUid) {
      targetByHeaderIndex.set(headerIndex, columnUid);
    }
  });

  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex];
    const taskNumber = rowIndex + 1;
    const taskPayload: Record<string, unknown> = { number: taskNumber };
    const rowLegacyValue =
      headers
        .map((_, headerIndex) => ({
          headerIndex,
          value: String(row[headerIndex] ?? "").trim()
        }))
        .find(
          (entry) =>
            entry.value.length > 0 &&
            (dueHeaderIndex < 0 || entry.headerIndex !== dueHeaderIndex)
        )?.value ?? "";
    if (rowLegacyValue) {
      taskPayload.legacy_value = rowLegacyValue;
    }
    if (dueHeaderIndex >= 0) {
      const dueValue = String(row[dueHeaderIndex] ?? "").trim();
      const dueMinutes = parseCsvDueRelativeMinutes(dueValue);
      if (dueMinutes !== undefined) {
        taskPayload.due_relative_minutes = dueMinutes;
      }
    }
    const taskCreated = await post<ChecklistRaw>(`${endpoints.checklists}/${createdChecklistUid}/tasks`, taskPayload);
    const createdTaskUid = String(
      toArray<ChecklistTaskRaw>(taskCreated.tasks).find((task) => Number(task.number ?? 0) === taskNumber)?.task_uid ?? ""
    ).trim();
    if (!createdTaskUid) {
      continue;
    }
    for (const [headerIndex, targetColumnUid] of targetByHeaderIndex.entries()) {
      const value = String(row[headerIndex] ?? "").trim();
      if (!value) {
        continue;
      }
      if (targetColumnUid === dueColumnUid) {
        continue;
      }
      await patchRequest(`${endpoints.checklists}/${createdChecklistUid}/tasks/${createdTaskUid}/cells/${targetColumnUid}`, {
        value,
        updated_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY
      });
    }
  }

  const hydrated = await hydrateChecklistRecord(createdChecklistUid);
  return hydrated ?? created;
};

const createChecklistFromCsvImportAction = async (
  sourceChecklistUid: string,
  checklistName: string,
  missionUid?: string
): Promise<ChecklistRaw> => {
  let sourceChecklist = checklistRecords.value.find((entry) => String(entry.uid ?? "").trim() === sourceChecklistUid);
  try {
    const hydrated = await hydrateChecklistRecord(sourceChecklistUid);
    if (hydrated) {
      sourceChecklist = hydrated;
    }
  } catch (error) {
    if (!sourceChecklist) {
      throw error;
    }
  }
  if (!sourceChecklist) {
    throw new Error("Selected CSV template could not be found");
  }
  const sourceColumns = toSortedChecklistColumns(toArray<ChecklistColumnRaw>(sourceChecklist.columns));
  if (!sourceColumns.length) {
    throw new Error("Selected CSV template has no columns");
  }

  const created = await post<ChecklistRaw>(endpoints.checklistsOffline, {
    mission_uid: missionUid,
    name: checklistName,
    origin_type: "RCH_TEMPLATE",
    source_identity: DEFAULT_SOURCE_IDENTITY,
    columns: toChecklistColumnPayload(sourceColumns)
  });

  const createdChecklistUid = String(created.uid ?? "").trim();
  if (!createdChecklistUid) {
    throw new Error("Checklist creation failed");
  }

  const createdColumns = toSortedChecklistColumns(toArray<ChecklistColumnRaw>(created.columns));
  const sourceColumnUidByOrder = new Map<number, string>();
  sourceColumns.forEach((column, index) => {
    const columnUid = String(column.column_uid ?? "").trim();
    if (!columnUid) {
      return;
    }
    sourceColumnUidByOrder.set(index + 1, columnUid);
  });
  const targetColumnUidByOrder = new Map<number, string>();
  createdColumns.forEach((column, index) => {
    const columnUid = String(column.column_uid ?? "").trim();
    if (!columnUid) {
      return;
    }
    targetColumnUidByOrder.set(index + 1, columnUid);
  });
  const sourceToTargetColumnUid = new Map<string, string>();
  sourceColumnUidByOrder.forEach((sourceColumnUid, order) => {
    const targetColumnUid = targetColumnUidByOrder.get(order);
    if (!targetColumnUid) {
      return;
    }
    sourceToTargetColumnUid.set(sourceColumnUid, targetColumnUid);
  });

  const sourceDueColumnUid = findDueColumnUid(sourceColumns);
  const sourceTasks = [...toArray<ChecklistTaskRaw>(sourceChecklist.tasks)].sort(
    (left, right) => Number(left.number ?? 0) - Number(right.number ?? 0)
  );

  for (let index = 0; index < sourceTasks.length; index += 1) {
    const sourceTask = sourceTasks[index];
    const taskNumber = index + 1;
    const dueRelativeMinutes = parseDueRelativeMinutes(sourceTask, sourceDueColumnUid);
    const taskPayload: Record<string, unknown> = { number: taskNumber };
    const legacyValue = String(sourceTask.legacy_value ?? "").trim() || resolveChecklistTaskName(sourceChecklist, sourceTask);
    if (legacyValue) {
      taskPayload.legacy_value = legacyValue;
    }
    if (dueRelativeMinutes !== undefined) {
      taskPayload.due_relative_minutes = dueRelativeMinutes;
    }
    const taskCreated = await post<ChecklistRaw>(`${endpoints.checklists}/${createdChecklistUid}/tasks`, taskPayload);
    const createdTaskUid = String(
      toArray<ChecklistTaskRaw>(taskCreated.tasks).find((task) => Number(task.number ?? 0) === taskNumber)?.task_uid ?? ""
    ).trim();
    if (!createdTaskUid) {
      continue;
    }

    const sourceCells = toArray<ChecklistCellRaw>(sourceTask.cells);
    for (const sourceCell of sourceCells) {
      const sourceColumnUid = String(sourceCell.column_uid ?? "").trim();
      const targetColumnUid = sourceToTargetColumnUid.get(sourceColumnUid);
      const value = String(sourceCell.value ?? "").trim();
      if (!sourceColumnUid || !targetColumnUid || !value) {
        continue;
      }
      if (sourceColumnUid === sourceDueColumnUid) {
        continue;
      }
      await patchRequest(
        `${endpoints.checklists}/${createdChecklistUid}/tasks/${createdTaskUid}/cells/${targetColumnUid}`,
        {
          value,
          updated_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY
        }
      );
    }
  }

  const hydrated = await hydrateChecklistRecord(createdChecklistUid);
  return hydrated ?? created;
};

const buildChecklistDraftName = (): string => {
  const missionName = selectedMission.value?.mission_name || "Mission";
  const suffix = new Date().toISOString().slice(11, 19).replace(/:/g, "");
  return `${missionName} Checklist ${suffix}`;
};

const openChecklistTemplateModal = () => {
  checklistTemplateNameDraft.value = buildChecklistDraftName();
  if (!checklistTemplateOptions.value.length) {
    checklistTemplateSelectionUid.value = "";
    checklistTemplateModalOpen.value = true;
    return;
  }
  if (!checklistTemplateOptions.value.some((entry) => entry.uid === checklistTemplateSelectionUid.value)) {
    checklistTemplateSelectionUid.value = checklistTemplateOptions.value[0].uid;
  }
  checklistTemplateModalOpen.value = true;
};

const closeChecklistTemplateModal = () => {
  if (checklistTemplateSubmitting.value) {
    return;
  }
  checklistTemplateModalOpen.value = false;
};

const createChecklistFromSelectedTemplateAction = async () => {
  const selectionUid = checklistTemplateSelectionUid.value.trim();
  if (!selectionUid) {
    throw new Error("Select a checklist template");
  }
  const selectedTemplate = checklistTemplateOptions.value.find((entry) => entry.uid === selectionUid);
  if (!selectedTemplate) {
    throw new Error("Selected checklist template could not be found");
  }
  const missionUid = selectedMissionUid.value || undefined;
  const checklistName = checklistTemplateNameDraft.value.trim() || buildChecklistDraftName();
  const created =
    selectedTemplate.source_type === "template"
      ? await post<ChecklistRaw>(endpoints.checklists, {
          template_uid: selectionUid,
          mission_uid: missionUid,
          name: checklistName,
          source_identity: DEFAULT_SOURCE_IDENTITY
        })
      : await createChecklistFromCsvImportAction(selectionUid, checklistName, missionUid);
  await loadWorkspace();
  const createdUid = String(created.uid ?? "").trim();
  if (createdUid) {
    selectedChecklistUid.value = createdUid;
    checklistDetailUid.value = createdUid;
    checklistWorkspaceView.value = "active";
    try {
      await hydrateChecklistRecord(createdUid);
    } catch (error) {
      handleApiError(error, "Checklist run created but detail refresh failed");
    }
  }
};

const submitChecklistTemplateSelection = async () => {
  if (checklistTemplateSubmitting.value) {
    return;
  }
  checklistTemplateSubmitting.value = true;
  try {
    await createChecklistFromSelectedTemplateAction();
    checklistTemplateModalOpen.value = false;
    toastStore.push("Checklist run created", "success");
  } catch (error) {
    handleApiError(error, "Unable to create checklist run");
  } finally {
    checklistTemplateSubmitting.value = false;
  }
};

const importChecklistAction = async () => {
  if (!csvImportBase64.value || !csvImportHeaders.value.length || !csvImportRows.value.length) {
    throw new Error("Upload a CSV file before importing");
  }
  const missionUid = selectedMissionUid.value || undefined;
  const baseName = (csvImportFilename.value || "Checklist CSV").replace(/\.csv$/i, "").trim() || "Checklist CSV";
  const imported = await createChecklistFromUploadedCsvAction(baseName, missionUid);
  await loadWorkspace();
  const importedUid = String(imported.uid ?? "").trim();
  if (importedUid) {
    selectedChecklistUid.value = importedUid;
    checklistDetailUid.value = importedUid;
    checklistWorkspaceView.value = "active";
    try {
      await hydrateChecklistRecord(importedUid);
    } catch (error) {
      handleApiError(error, "Checklist imported but detail refresh failed");
    }
  }
};

const joinChecklistAction = async () => {
  const checklist = ensureChecklistSelected();
  await post<ChecklistRaw>(`${endpoints.checklists}/${checklist.uid}/join`, {
    source_identity: DEFAULT_SOURCE_IDENTITY
  });
  await loadWorkspace();
};

const uploadChecklistAction = async () => {
  const checklist = ensureChecklistSelected();
  await post<ChecklistRaw>(`${endpoints.checklists}/${checklist.uid}/upload`, {
    source_identity: DEFAULT_SOURCE_IDENTITY
  });
  await loadWorkspace();
};

const publishChecklistAction = async () => {
  const checklist = ensureChecklistSelected();
  const checklistUid = String(checklist.uid ?? "").trim();
  if (
    String(checklist.mode ?? "").toUpperCase() === "OFFLINE" &&
    String(checklist.sync_state ?? "").toUpperCase() !== "SYNCED"
  ) {
    await post<ChecklistRaw>(`${endpoints.checklists}/${checklistUid}/upload`, {
      source_identity: DEFAULT_SOURCE_IDENTITY
    });
  }
  const missionFeedUid = selectedMissionUid.value || "mission-feed";
  await post(`${endpoints.checklists}/${checklistUid}/feeds/${encodeURIComponent(missionFeedUid)}`, {
    source_identity: DEFAULT_SOURCE_IDENTITY
  });
  await loadWorkspace();
};

const setChecklistTaskStatusAction = async () => {
  const checklist = ensureChecklistSelected();
  const checklistUid = String(checklist.uid ?? "").trim();
  const tasks = toArray<ChecklistTaskRaw>(checklist.tasks);
  const firstTask = tasks.find((task) => String(task.task_uid ?? "").trim().length > 0);
  if (!firstTask?.task_uid) {
    await post(`${endpoints.checklists}/${checklistUid}/tasks`, {
      number: 1,
      due_relative_minutes: 10
    });
    await loadWorkspace();
    return;
  }
  const userStatus = String(firstTask.user_status ?? "PENDING").toUpperCase() === "COMPLETE" ? "PENDING" : "COMPLETE";
  await post(`${endpoints.checklists}/${checklistUid}/tasks/${firstTask.task_uid}/status`, {
    user_status: userStatus,
    changed_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY
  });
  await loadWorkspace();
};

const createZoneAction = async () => {
  const baseOffset = zoneRecords.value.length * 0.02;
  const lat = 34.0 + baseOffset;
  const lon = -118.0 + baseOffset;
  const created = await post<{ zone_id?: string }>(endpoints.zones, {
    name: `Mission Zone ${zoneRecords.value.length + 1}`,
    points: [
      { lat, lon },
      { lat: lat + 0.01, lon },
      { lat: lat + 0.01, lon: lon + 0.01 },
      { lat, lon: lon + 0.01 }
    ]
  });

  const missionUid = selectedMissionUid.value;
  const zoneUid = String(created.zone_id ?? "").trim();
  if (missionUid && zoneUid) {
    const next = new Set(selectedZoneIds.value);
    next.add(zoneUid);
    zoneDraftByMission.value = {
      ...zoneDraftByMission.value,
      [missionUid]: [...next]
    };
  }

  await loadWorkspace();
};

const commitZonesAction = async () => {
  const missionUid = ensureMissionSelected();
  const selected = new Set(selectedZoneIds.value);
  const committed = new Set(committedZoneIdsByMission.value.get(missionUid) ?? []);
  const missionZonesBase = `${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}/zones`;
  const toLink = [...selected].filter((zoneId) => !committed.has(zoneId));
  const toUnlink = [...committed].filter((zoneId) => !selected.has(zoneId));

  await Promise.all([
    ...toLink.map((zoneId) => put(`${missionZonesBase}/${encodeURIComponent(zoneId)}`)),
    ...toUnlink.map((zoneId) => deleteRequest(`${missionZonesBase}/${encodeURIComponent(zoneId)}`))
  ]);

  const nextDraft = { ...zoneDraftByMission.value };
  delete nextDraft[missionUid];
  zoneDraftByMission.value = nextDraft;
  await loadWorkspace();
};

const assignTaskAction = async () => {
  const missionUid = ensureMissionSelected();
  const { taskUid } = await ensureChecklistTaskContext();
  const member = await ensureMemberIdentityForMission();
  const assetUid = await ensureAssetForMission();
  const existing = missionAssignmentsRaw.value.find((entry) => String(entry.task_uid ?? "").trim() === taskUid);
  const payload: {
    mission_uid: string;
    task_uid: string;
    team_member_rns_identity: string;
    assets: string[];
    status: string;
    assignment_uid?: string;
  } = {
    mission_uid: missionUid,
    task_uid: taskUid,
    team_member_rns_identity: member.identity,
    assets: [assetUid],
    status: "PENDING"
  };
  if (existing?.assignment_uid) {
    payload.assignment_uid = String(existing.assignment_uid);
  }
  await post<AssignmentRaw>(endpoints.r3aktAssignments, payload);
  await loadWorkspace();
};

const reassignTaskAction = async () => {
  if (missionMembers.value.length < 2) {
    throw new Error("At least two mission members are required. Use Add Member to assign another member.");
  }
  const assignment = missionAssignmentsRaw.value[0];
  if (!assignment) {
    await assignTaskAction();
    return;
  }
  const identities = missionMembers.value
    .map((member) => {
      const raw = memberRecords.value.find((entry) => String(entry.uid ?? "").trim() === member.uid);
      return raw ? resolveTeamMemberIdentity(raw) : "";
    })
    .filter((entry) => entry.length > 0);
  if (identities.length === 0) {
    throw new Error("No mission member identity available for reassignment");
  }
  const current = String(assignment.team_member_rns_identity ?? "").trim();
  const targetIdentity = identities.find((identity) => identity !== current) ?? identities[0];
  const payload: {
    assignment_uid?: string;
    mission_uid: string;
    task_uid: string;
    team_member_rns_identity: string;
    assets: string[];
    status: string;
  } = {
    mission_uid: String(assignment.mission_uid ?? ensureMissionSelected()),
    task_uid: String(assignment.task_uid ?? ""),
    team_member_rns_identity: targetIdentity,
    assets: toStringList(assignment.assets),
    status: String(assignment.status ?? "PENDING")
  };
  if (!payload.task_uid) {
    throw new Error("Assignment has no task UID");
  }
  if (assignment.assignment_uid) {
    payload.assignment_uid = String(assignment.assignment_uid);
  }
  await post<AssignmentRaw>(endpoints.r3aktAssignments, payload);
  await loadWorkspace();
};

const revokeAssignmentAction = async () => {
  let assignment = missionAssignmentsRaw.value[0];
  if (!assignment) {
    await assignTaskAction();
    assignment = missionAssignmentsRaw.value[0];
  }
  if (!assignment) {
    throw new Error("No assignment is available to revoke");
  }
  const missionUid = String(assignment.mission_uid ?? ensureMissionSelected()).trim();
  const taskUid = String(assignment.task_uid ?? "").trim();
  const memberIdentity = String(assignment.team_member_rns_identity ?? "").trim();
  if (!missionUid || !taskUid || !memberIdentity) {
    throw new Error("Assignment payload is incomplete");
  }
  await post<AssignmentRaw>(endpoints.r3aktAssignments, {
    assignment_uid: String(assignment.assignment_uid ?? ""),
    mission_uid: missionUid,
    task_uid: taskUid,
    team_member_rns_identity: memberIdentity,
    assets: [],
    status: "REVOKED",
    notes: "Revoked from Mission workspace"
  });
  await loadWorkspace();
};

const editChecklistCellAction = async () => {
  const checklist = ensureChecklistSelected();
  const checklistUid = String(checklist.uid ?? "").trim();
  const tasks = toArray<ChecklistTaskRaw>(checklist.tasks);
  const taskUid = String(tasks[0]?.task_uid ?? "").trim();
  if (!taskUid) {
    throw new Error("Checklist has no task row to edit");
  }
  const columns = toArray<ChecklistColumnRaw>(checklist.columns);
  const editable = columns.find(
    (column) =>
      column.column_uid &&
      String(column.system_key ?? "").trim().length === 0 &&
      String(column.column_type ?? "").toUpperCase() === "SHORT_STRING"
  );
  const fallback = columns.find((column) => String(column.column_uid ?? "").trim().length > 0);
  const columnUid = String(editable?.column_uid ?? fallback?.column_uid ?? "").trim();
  if (!columnUid) {
    throw new Error("Checklist has no editable column");
  }
  const member = await ensureMemberIdentityForMission();
  await patchRequest(`${endpoints.checklists}/${checklistUid}/tasks/${taskUid}/cells/${columnUid}`, {
    value: `Updated @ ${new Date().toISOString()}`,
    updated_by_team_member_rns_identity: member.identity
  });
  await loadWorkspace();
};

const validateChecklistAction = async () => {
  const payload = await get<{ templates?: TemplateRaw[] }>(endpoints.checklistTemplates);
  const templates = toArray<TemplateRaw>(payload.templates);
  if (!templates.length) {
    throw new Error("No checklist templates found");
  }
};

const exportMissionsAction = async () => {
  downloadJson(`missions-${buildTimestampTag()}.json`, missions.value);
};

const exportAuditAction = async () => {
  const missionUid = ensureMissionSelected();
  downloadJson(`mission-audit-${missionUid}.json`, missionAudit.value);
};

const snapshotAction = async () => {
  const missionUid = ensureMissionSelected();
  const snapshots = await get<
    Array<{ aggregate_uid?: string; aggregate_type?: string; state?: unknown; created_at?: string }>
  >(endpoints.r3aktSnapshots);
  const filtered = snapshots.filter((entry) => String(entry.aggregate_uid ?? "") === missionUid);
  downloadJson(`mission-snapshots-${missionUid}.json`, filtered);
};

const exportChecklistProgressAction = async () => {
  const checklist = ensureChecklistSelected();
  downloadJson(`checklist-progress-${checklist.uid}.json`, checklist);
};

const previewCsvAction = async () => {
  if (!csvImportHeaders.value.length || !csvImportRows.value.length) {
    throw new Error("Upload a CSV file before previewing");
  }
  const csv = renderUploadedCsv();
  const baseName = (csvImportFilename.value || "checklist-import").replace(/\.csv$/i, "");
  downloadText(`${baseName}-preview-${buildTimestampTag()}.csv`, csv, "text/csv");
};

const previewAction = async (action: string) => {
  if (loadingWorkspace.value) {
    return;
  }

  if (["Refresh", "Sync", "Recompute", "Sync Board"].includes(action)) {
    await runAction(loadWorkspace, "Mission workspace refreshed", "Unable to refresh mission workspace");
    return;
  }

  if (action === "Reset" && isMissionFormScreen.value) {
    if (isMissionEditScreen.value) {
      resetMissionDraft("edit", selectedMission.value);
    } else {
      resetMissionDraft("create");
    }
    toastStore.push("Mission draft reset", "info");
    return;
  }

  if (action === "Filter") {
    toastStore.push(`${currentScreen.value.title}: filter applied`, "info");
    return;
  }

  if (action === "Export" && secondaryScreen.value === "missionDirectory") {
    await runAction(exportMissionsAction, "Mission directory exported", "Unable to export mission directory");
    return;
  }

  if (action === "Export" && secondaryScreen.value === "checklistProgress") {
    await runAction(
      exportChecklistProgressAction,
      "Checklist progress exported",
      "Unable to export checklist progress"
    );
    return;
  }

  if (action === "Commit") {
    await runAction(commitZonesAction, "Mission zone assignments committed", "Unable to commit zone assignments");
    return;
  }

  if (action === "New Zone") {
    await runAction(createZoneAction, "Zone created", "Unable to create zone");
    return;
  }

  if (action === "Broadcast") {
    await runAction(broadcastMissionAction, "Mission broadcast logged", "Unable to broadcast mission update");
    return;
  }

  if (action === "Edit") {
    openMissionEditScreen();
    return;
  }

  if (action === "Checklists") {
    setPrimaryTab("checklists");
    return;
  }

  if (action === "Logs") {
    openMissionLogsPage();
    return;
  }

  if (action === "Team") {
    setSecondaryScreen("missionTeamMembers");
    return;
  }

  if (action === "Assets") {
    setSecondaryScreen("assetRegistry");
    return;
  }

  if (action === "Zones") {
    setSecondaryScreen("assignZones");
    return;
  }

  if ((action === "Save" || action === "Save Mission") && isMissionCreateScreen.value) {
    await runAction(createMissionAction, "Mission created", "Unable to create mission");
    return;
  }

  if ((action === "Save" || action === "Save Mission") && isMissionEditScreen.value) {
    await runAction(updateMissionAction, "Mission updated", "Unable to update mission");
    return;
  }

  if (action === "Add Team") {
    try {
      await addTeamAction();
    } catch (error) {
      handleApiError(error, "Unable to open mission team allocation");
    }
    return;
  }

  if (action === "Add Member") {
    try {
      await addMemberAction();
    } catch (error) {
      handleApiError(error, "Unable to open mission member allocation");
    }
    return;
  }

  if (action === "Assign") {
    await runAction(assignTaskAction, "Assignment updated", "Unable to assign task");
    return;
  }

  if (action === "Reassign") {
    await runAction(reassignTaskAction, "Task reassigned", "Unable to reassign task");
    return;
  }

  if (action === "Revoke") {
    await runAction(revokeAssignmentAction, "Assignment revoked", "Unable to revoke assignment");
    return;
  }

  if (action === "Start New" || (action === "Create" && secondaryScreen.value === "checklistCreation")) {
    try {
      openChecklistTemplateModal();
    } catch (error) {
      handleApiError(error, "Unable to open checklist template selector");
    }
    return;
  }

  if (action === "Import") {
    await runAction(importChecklistAction, "Checklist imported from CSV", "Unable to import checklist from CSV");
    return;
  }

  if (action === "Preview" && secondaryScreen.value === "checklistImportCsv") {
    await runAction(previewCsvAction, "CSV preview exported", "Unable to export CSV preview");
    return;
  }

  if (action === "Join") {
    await runAction(joinChecklistAction, "Checklist joined", "Unable to join checklist");
    return;
  }

  if (action === "Upload") {
    await runAction(uploadChecklistAction, "Checklist uploaded", "Unable to upload checklist");
    return;
  }

  if (action === "Publish") {
    await runAction(publishChecklistAction, "Checklist published to mission feed", "Unable to publish checklist");
    return;
  }

  if (action === "Set Status") {
    await runAction(setChecklistTaskStatusAction, "Checklist task status updated", "Unable to update checklist task status");
    return;
  }

  if (action === "Edit Cell") {
    await runAction(editChecklistCellAction, "Checklist cell updated", "Unable to edit checklist cell");
    return;
  }

  if (action === "Validate") {
    await runAction(validateChecklistAction, "Checklist template validation passed", "Checklist validation failed");
    return;
  }

  if (action === "Export Log") {
    await runAction(exportAuditAction, "Mission audit exported", "Unable to export mission audit");
    return;
  }

  if (action === "Open Assets") {
    router
      .push({
        path: "/missions/assets",
        query: selectedMissionUid.value ? { mission_uid: selectedMissionUid.value } : undefined
      })
      .catch(() => undefined);
    return;
  }

  if (action === "Open Logs") {
    openMissionLogsPage();
    return;
  }

  if (action === "Snapshot") {
    await runAction(snapshotAction, "Mission snapshots exported", "Unable to export mission snapshots");
    return;
  }

  if (action === "Deploy") {
    await runAction(deployAssetAction, "Asset deployed", "Unable to deploy asset");
    return;
  }

  toastStore.push(`${currentScreen.value.title}: ${action} not wired yet`, "info");
};

const toggleZone = (zoneUid: string) => {
  const missionUid = selectedMissionUid.value;
  if (!missionUid) {
    toastStore.push("Select a mission before assigning zones", "warning");
    return;
  }
  const next = new Set(selectedZoneIds.value);
  if (next.has(zoneUid)) {
    next.delete(zoneUid);
  } else {
    next.add(zoneUid);
  }
  zoneDraftByMission.value = {
    ...zoneDraftByMission.value,
    [missionUid]: [...next]
  };
};

watch(
  [checklistTemplateDraftName, checklistTemplateDraftDescription, checklistTemplateDraftColumns],
  () => {
    if (checklistTemplateEditorHydrating.value || checklistTemplateEditorMode.value === "csv_readonly") {
      return;
    }
    checklistTemplateEditorDirty.value = true;
  },
  { deep: true }
);

watch(
  checklistTemplateOptions,
  (entries) => {
    if (checklistTemplateSelectionUid.value && !entries.some((entry) => entry.uid === checklistTemplateSelectionUid.value)) {
      checklistTemplateSelectionUid.value = entries[0]?.uid ?? "";
    }

    const selected = selectedChecklistTemplateEditorOption.value;
    if (selected) {
      return;
    }

    if (!entries.length) {
      if (checklistWorkspaceView.value === "templates") {
        startNewChecklistTemplateDraft();
      }
      return;
    }

    if (checklistTemplateEditorMode.value === "create") {
      return;
    }
    const first = entries[0];
    selectChecklistTemplateForEditor(first.uid, first.source_type);
  },
  { immediate: true }
);

watch(
  checklistWorkspaceView,
  (view) => {
    if (view !== "templates") {
      return;
    }
    if (checklistTemplateOptions.value.length) {
      syncChecklistTemplateEditorSelection();
      return;
    }
    startNewChecklistTemplateDraft();
  },
  { immediate: true }
);

watch(
  () => route.query.mission_uid,
  (value) => {
    const next = queryText(value);
    if (next) {
      if (next !== selectedMissionUid.value) {
        selectedMissionUid.value = next;
      }
      return;
    }
    if (!selectedMissionUid.value) {
      const persistedMissionUid = readPersistedMissionUid();
      if (persistedMissionUid) {
        selectedMissionUid.value = persistedMissionUid;
      }
    }
  },
  { immediate: true }
);

watch(
  selectedMissionUid,
  (missionUid) => {
    const normalizedMissionUid = missionUid.trim();
    saveJson(MISSION_SELECTION_STORAGE_KEY, normalizedMissionUid);
    const current = queryText(route.query.mission_uid);
    if (current === normalizedMissionUid) {
      return;
    }
    const nextQuery = { ...route.query };
    if (normalizedMissionUid) {
      nextQuery.mission_uid = normalizedMissionUid;
    } else {
      delete nextQuery.mission_uid;
    }
    router.replace({ path: route.path, query: nextQuery }).catch(() => undefined);
  },
  { immediate: true }
);

watch(
  missions,
  (entries) => {
    if (!entries.some((entry) => entry.uid === selectedMissionUid.value)) {
      selectedMissionUid.value = entries[0]?.uid ?? "";
    }
  },
  { immediate: true }
);

watch(
  selectedMission,
  (mission) => {
    if (isMissionEditScreen.value) {
      resetMissionDraft("edit", mission);
    }
  },
  { immediate: true }
);

watch(
  secondaryScreen,
  (screen) => {
    if (screen === "missionCreate") {
      missionAdvancedPropertiesOpen.value = false;
      resetMissionDraft("create");
      return;
    }
    if (screen === "missionEdit") {
      missionAdvancedPropertiesOpen.value = true;
      resetMissionDraft("edit", selectedMission.value);
    }
  },
  { immediate: true }
);

watch(selectedMissionUid, (missionUid, previousMissionUid) => {
  if (!missionUid || missionUid === previousMissionUid) {
    return;
  }
  if (primaryTab.value === "mission") {
    setSecondaryScreen("missionOverview");
  }
});

watch(
  missionTeams,
  (entries) => {
    const validTeamUids = new Set(entries.map((entry) => entry.uid));
    if (!validTeamUids.has(memberAllocationTeamUid.value)) {
      memberAllocationTeamUid.value = entries[0]?.uid ?? "";
    }
    if (!entries.length) {
      memberAllocationModalOpen.value = false;
    }
  },
  { immediate: true }
);

watch(
  checklists,
  (entries) => {
    if (selectedChecklistUid.value && !entries.some((entry) => entry.uid === selectedChecklistUid.value)) {
      selectedChecklistUid.value = "";
    }
    if (checklistDetailUid.value && !entries.some((entry) => entry.uid === checklistDetailUid.value)) {
      checklistDetailUid.value = "";
    }
  },
  { immediate: true }
);

watch(
  () => route.path,
  (path) => {
    const desiredTab: PrimaryTab = path === "/checklists" ? "checklists" : "mission";
    if (primaryTab.value !== desiredTab) {
      setPrimaryTab(desiredTab, false);
    }
  },
  { immediate: true }
);

onMounted(() => {
  missionCountdownNow.value = Date.now();
  missionCountdownTimerId = window.setInterval(() => {
    missionCountdownNow.value = Date.now();
  }, 1000);
  loadWorkspace().catch((error) => {
    handleApiError(error, "Unable to load mission workspace");
  });
});

onBeforeUnmount(() => {
  if (missionCountdownTimerId !== undefined) {
    window.clearInterval(missionCountdownTimerId);
    missionCountdownTimerId = undefined;
  }
});
</script>

<style scoped src="./missions/MissionsPage.css"></style>







