<template>
  <div class="screen-grid">
    <article class="stage-card checklist-workspace">
      <div class="checklist-manager-controls">
        <label class="field-control full checklist-manager-search">
          <input
            :value="checklistSearchQuery"
            type="search"
            placeholder="Search checklists and templates..."
            @input="updateChecklistSearchQuery"
          />
        </label>
        <div class="checklist-manager-actions">
          <BaseButton size="sm" icon-left="plus" @click="openChecklistCreationModal">New</BaseButton>
          <BaseButton size="sm" variant="secondary" icon-left="filter" @click="showChecklistFilterNotice">Filter</BaseButton>
          <BaseButton size="sm" variant="secondary" icon-left="edit" @click="openTemplateBuilderFromChecklist">
            Template Builder
          </BaseButton>
          <BaseButton size="sm" variant="secondary" icon-left="upload" @click="openChecklistImportFromChecklist">
            Import from CSV
          </BaseButton>
        </div>
      </div>

      <div class="checklist-overview-tabs">
        <button
          type="button"
          class="checklist-overview-tab"
          :class="{ active: checklistWorkspaceView === 'active' }"
          @click="setChecklistWorkspaceView('active')"
        >
          Active Checklists ({{ checklistActiveCount }})
        </button>
        <button
          type="button"
          class="checklist-overview-tab"
          :class="{ active: checklistWorkspaceView === 'templates' }"
          @click="setChecklistWorkspaceView('templates')"
        >
          Templates ({{ checklistTemplateCount }})
        </button>
      </div>

      <div v-if="checklistWorkspaceView === 'active'">
        <div v-if="checklistDetailRecord" class="checklist-detail-view">
          <div class="checklist-detail-header">
            <BaseButton variant="ghost" size="sm" icon-left="chevron-left" @click="closeChecklistDetailView">Back</BaseButton>
            <div class="checklist-detail-title">
              <h4>{{ checklistDetailRecord.name }}</h4>
              <p>{{ checklistDescriptionLabel(checklistDetailRecord.description) }}</p>
              <div class="checklist-chip-row">
                <span class="checklist-chip" :class="modeChipClass(checklistDetailRecord.mode)">
                  {{ checklistDetailRecord.mode }}
                </span>
                <span class="checklist-chip" :class="syncChipClass(checklistDetailRecord.sync_state)">
                  {{ checklistDetailRecord.sync_state }}
                </span>
                <span class="checklist-chip" :class="statusChipClass(checklistDetailRecord.checklist_status)">
                  {{ checklistDetailRecord.checklist_status }}
                </span>
                <span class="checklist-chip checklist-chip-muted">
                  {{ checklistOriginLabel(checklistDetailRecord.origin_type) }}
                </span>
                <span class="checklist-chip checklist-chip-muted">
                  {{ checklistMissionLabel(checklistDetailRecord.mission_uid) }}
                </span>
              </div>
              <div class="checklist-detail-actions">
                <BaseButton
                  v-if="canCreateFromDetailTemplate"
                  size="sm"
                  variant="secondary"
                  icon-left="plus"
                  @click="createChecklistFromDetailTemplate"
                >
                  Create from Template
                </BaseButton>
                <BaseButton
                  size="sm"
                  variant="secondary"
                  icon-left="link"
                  :disabled="checklistLinkMissionSubmitting"
                  @click="openChecklistMissionLinkModal"
                >
                  Link Mission
                </BaseButton>
                <BaseButton
                  size="sm"
                  variant="danger"
                  icon-left="trash"
                  :disabled="checklistDeleteBusy"
                  @click="deleteChecklistFromDetail"
                >
                  Delete
                </BaseButton>
              </div>
            </div>
            <div class="checklist-detail-progress">
              <strong>{{ Math.round(checklistDetailRecord.progress) }}%</strong>
              <span>Complete</span>
            </div>
          </div>

          <div class="checklist-progress-track">
            <span class="checklist-progress-value" :style="{ width: progressWidth(checklistDetailRecord.progress) }"></span>
          </div>

          <div class="checklist-detail-summary">
            <span>{{ checklistDetailRecord.complete_count }} Complete</span>
            <span>{{ checklistDetailRecord.pending_count }} Pending</span>
            <span>{{ checklistDetailRecord.late_count }} Late</span>
          </div>

          <div class="checklist-task-toolbar">
            <label class="checklist-task-input">
              <input :value="checklistTaskDueDraft" type="number" step="1" min="-1440" placeholder="auto" @input="updateChecklistTaskDueDraft" />
              <span>Due minutes</span>
            </label>
            <BaseButton size="sm" icon-left="plus" @click="addChecklistTaskFromDetail">Add</BaseButton>
          </div>

          <table class="mini-table checklist-detail-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Done</th>
                <th v-for="column in checklistDetailColumns" :key="`detail-header-${column.uid}`">
                  {{ column.name }}
                </th>
                <th>Due Relative DTG</th>
                <th>Status</th>
                <th>Complete DTG</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in checklistDetailRows"
                :key="row.id"
                :class="{ 'checklist-row-complete': row.done }"
              >
                <td>{{ row.number }}</td>
                <td>
                  <button
                    type="button"
                    class="checklist-done-button"
                    :disabled="!row.task_uid || checklistTaskStatusBusyByTaskUid[row.task_uid]"
                    @click="toggleChecklistTaskDone(row)"
                  >
                    <span class="checklist-done-indicator" :class="{ done: row.done }">{{ row.done ? "X" : "" }}</span>
                  </button>
                </td>
                <td v-for="column in checklistDetailColumns" :key="`detail-cell-${row.id}-${column.uid}`">
                  {{ row.column_values[column.uid] || "-" }}
                </td>
                <td>{{ row.due }}</td>
                <td>
                  <span class="checklist-chip" :class="statusChipClass(row.status)">{{ row.status }}</span>
                </td>
                <td>{{ row.completeDtg }}</td>
              </tr>
              <tr v-if="!checklistDetailRows.length">
                <td :colspan="checklistDetailColumns.length + 5">No tasks yet.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else class="checklist-overview-list">
          <button
            v-for="checklist in filteredChecklistCards"
            :key="checklist.uid"
            class="checklist-overview-card"
            type="button"
            @click="openChecklistDetailView(checklist.uid)"
          >
            <div class="checklist-overview-content">
              <div class="checklist-overview-head">
                <h4>{{ checklist.name }}</h4>
                <div class="checklist-chip-row">
                  <span class="checklist-chip" :class="modeChipClass(checklist.mode)">{{ checklist.mode }}</span>
                  <span class="checklist-chip" :class="syncChipClass(checklist.sync_state)">{{ checklist.sync_state }}</span>
                  <span class="checklist-chip" :class="statusChipClass(checklist.checklist_status)">
                    {{ checklist.checklist_status }}
                  </span>
                  <span class="checklist-chip checklist-chip-muted">
                    {{ checklistOriginLabel(checklist.origin_type) }}
                  </span>
                  <span class="checklist-chip checklist-chip-muted">
                    {{ checklistMissionLabel(checklist.mission_uid) }}
                  </span>
                </div>
              </div>
              <p>{{ checklistDescriptionLabel(checklist.description) }}</p>
              <div class="checklist-overview-meta">
                <span>{{ formatChecklistDateTime(checklist.created_at) }}</span>
                <span>Tasks: {{ checklist.tasks.length }}</span>
                <span>Progress: {{ Math.round(checklist.progress) }}%</span>
              </div>
            </div>
            <div class="checklist-overview-stats">
              <div class="checklist-overview-counts">
                <span>{{ checklist.complete_count }} Complete</span>
                <span>{{ checklist.pending_count }} Pending</span>
                <span>{{ checklist.late_count }} Late</span>
              </div>
              <div class="checklist-progress-track compact">
                <span class="checklist-progress-value" :style="{ width: progressWidth(checklist.progress) }"></span>
              </div>
              <span class="checklist-overview-arrow" aria-hidden="true">></span>
            </div>
          </button>
          <p v-if="!filteredChecklistCards.length" class="template-modal-empty">
            No active checklist instances match your search.
          </p>
        </div>
      </div>

      <div v-else class="checklist-template-list">
        <div class="checklist-template-workspace">
          <article class="checklist-template-library-pane">
            <div class="checklist-template-library-head">
              <h4>Template Library</h4>
              <p>Select a template or CSV import entry to edit.</p>
            </div>
            <div class="checklist-template-library-list">
              <button
                v-for="template in filteredChecklistTemplates"
                :key="`checklist-template-${template.uid}`"
                type="button"
                class="checklist-template-library-item"
                :class="{
                  active:
                    checklistTemplateEditorSelectionUid === template.uid &&
                    checklistTemplateEditorSelectionSourceType === template.source_type
                }"
                @click="selectChecklistTemplateForEditor(template.uid, template.source_type)"
              >
                <div class="checklist-template-head">
                  <h4>{{ template.name }}</h4>
                  <div class="checklist-chip-row">
                    <span class="checklist-chip checklist-chip-info">{{ template.columns }} Columns</span>
                    <span v-if="template.source_type === 'csv_import'" class="checklist-chip checklist-chip-muted">
                      CSV Import
                    </span>
                  </div>
                </div>
                <p>{{ template.description || "Template catalog entry for checklist creation." }}</p>
                <div class="checklist-template-meta">
                  <span v-if="template.created_at">Created: {{ formatChecklistDateTime(template.created_at) }}</span>
                  <span v-if="template.owner">By: {{ template.owner }}</span>
                  <span v-if="template.task_rows > 0">Tasks: {{ template.task_rows }}</span>
                </div>
              </button>
              <p v-if="!filteredChecklistTemplates.length" class="template-modal-empty">
                No templates match your search.
              </p>
            </div>
          </article>

          <article class="checklist-template-editor-pane">
            <div class="checklist-template-editor-header">
              <div>
                <h4>{{ checklistTemplateEditorTitle }}</h4>
                <p>{{ checklistTemplateEditorSubtitle }}</p>
              </div>
              <div class="checklist-template-editor-actions">
                <BaseButton size="sm" icon-left="plus" @click="startNewChecklistTemplateDraft">New</BaseButton>
                <BaseButton
                  size="sm"
                  variant="secondary"
                  icon-left="plus"
                  :disabled="!canAddChecklistTemplateColumn"
                  @click="addChecklistTemplateColumn"
                >
                  Add Column
                </BaseButton>
                <BaseButton
                  size="sm"
                  variant="secondary"
                  icon-left="save"
                  :disabled="!canSaveChecklistTemplateDraft"
                  @click="saveChecklistTemplateDraft"
                >
                  Save
                </BaseButton>
                <BaseButton
                  size="sm"
                  variant="secondary"
                  icon-left="save"
                  :disabled="!canSaveChecklistTemplateDraftAsNew"
                  @click="saveChecklistTemplateDraftAsNew"
                >
                  Save As New
                </BaseButton>
                <BaseButton
                  size="sm"
                  variant="secondary"
                  icon-left="layers"
                  :disabled="!canCloneChecklistTemplateDraft"
                  @click="cloneChecklistTemplateDraft"
                >
                  Clone
                </BaseButton>
                <BaseButton
                  size="sm"
                  variant="secondary"
                  icon-left="file"
                  :disabled="!canArchiveChecklistTemplateDraft"
                  @click="archiveChecklistTemplateDraft"
                >
                  Archive
                </BaseButton>
                <BaseButton
                  size="sm"
                  variant="secondary"
                  icon-left="upload"
                  :disabled="!canConvertChecklistTemplateDraft"
                  @click="convertChecklistTemplateDraftToServerTemplate"
                >
                  Convert to Template
                </BaseButton>
                <BaseButton
                  size="sm"
                  variant="danger"
                  icon-left="trash"
                  :disabled="!canDeleteChecklistTemplateDraft"
                  @click="deleteChecklistTemplateDraft"
                >
                  Delete
                </BaseButton>
              </div>
            </div>

            <div class="checklist-template-editor-form">
              <div class="field-grid">
                <label class="field-control">
                  <span>Template Name</span>
                  <input
                    :value="checklistTemplateDraftName"
                    type="text"
                    :disabled="isChecklistTemplateDraftReadonly"
                    @input="updateChecklistTemplateDraftName"
                  />
                </label>
                <label class="field-control full">
                  <span>Description</span>
                  <textarea
                    :value="checklistTemplateDraftDescription"
                    rows="3"
                    :disabled="isChecklistTemplateDraftReadonly"
                    @input="updateChecklistTemplateDraftDescription"
                  ></textarea>
                </label>
              </div>

              <p class="checklist-template-editor-note">
                System column <strong>DUE_RELATIVE_DTG</strong> is pinned first and enforced as
                <strong>RELATIVE_TIME</strong>.
              </p>

              <div class="checklist-template-column-scroll">
                <table class="mini-table checklist-template-column-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Name</th>
                      <th>Type</th>
                      <th>Editable</th>
                      <th>BG</th>
                      <th>Text</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(column, columnIndex) in checklistTemplateDraftColumns"
                      :key="`checklist-template-column-${column.column_uid || columnIndex}`"
                    >
                      <td>{{ columnIndex + 1 }}</td>
                      <td>
                        <input
                          class="checklist-template-column-input"
                          :value="column.column_name"
                          type="text"
                          :disabled="isChecklistTemplateDraftReadonly || isChecklistTemplateDueColumn(column)"
                          @input="setChecklistTemplateColumnName(columnIndex, $event)"
                        />
                      </td>
                      <td>
                        <select
                          class="checklist-template-column-input"
                          :value="column.column_type"
                          :disabled="isChecklistTemplateDraftReadonly || isChecklistTemplateDueColumn(column)"
                          @change="setChecklistTemplateColumnType(columnIndex, $event)"
                        >
                          <option v-for="columnType in checklistTemplateColumnTypeOptions" :key="columnType" :value="columnType">
                            {{ columnType }}
                          </option>
                        </select>
                      </td>
                      <td class="checklist-template-column-checkbox">
                        <input
                          type="checkbox"
                          :checked="Boolean(column.column_editable)"
                          :disabled="isChecklistTemplateDraftReadonly || isChecklistTemplateDueColumn(column)"
                          @change="setChecklistTemplateColumnEditable(columnIndex, $event)"
                        />
                      </td>
                      <td>
                        <input
                          class="checklist-template-color-input"
                          type="color"
                          :value="checklistTemplateColumnColorValue(column.background_color)"
                          :disabled="isChecklistTemplateDraftReadonly"
                          @input="setChecklistTemplateColumnBackgroundColor(columnIndex, $event)"
                        />
                      </td>
                      <td>
                        <input
                          class="checklist-template-color-input"
                          type="color"
                          :value="checklistTemplateColumnColorValue(column.text_color)"
                          :disabled="isChecklistTemplateDraftReadonly"
                          @input="setChecklistTemplateColumnTextColor(columnIndex, $event)"
                        />
                      </td>
                      <td>
                        <div class="checklist-template-column-actions">
                          <BaseButton
                            size="sm"
                            variant="secondary"
                            icon-left="chevron-left"
                            :disabled="!canMoveChecklistTemplateColumnUp(columnIndex)"
                            @click="moveChecklistTemplateColumnUp(columnIndex)"
                          >
                            Up
                          </BaseButton>
                          <BaseButton
                            size="sm"
                            variant="secondary"
                            icon-left="chevron-right"
                            :disabled="!canMoveChecklistTemplateColumnDown(columnIndex)"
                            @click="moveChecklistTemplateColumnDown(columnIndex)"
                          >
                            Down
                          </BaseButton>
                          <BaseButton
                            size="sm"
                            variant="danger"
                            icon-left="trash"
                            :disabled="!canDeleteChecklistTemplateColumn(columnIndex)"
                            @click="deleteChecklistTemplateColumn(columnIndex)"
                          >
                            Delete
                          </BaseButton>
                        </div>
                      </td>
                    </tr>
                    <tr v-if="!checklistTemplateDraftColumns.length">
                      <td colspan="7">No columns configured.</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <p class="template-modal-hint">{{ checklistTemplateEditorStatusLabel }}</p>
            </div>
          </article>
        </div>
      </div>
    </article>
  </div>
</template>

<script setup lang="ts">
import BaseButton from "../../components/BaseButton.vue";

interface ChecklistCard {
  uid: string;
  name: string;
  description: string;
  mode: string;
  sync_state: string;
  checklist_status: string;
  origin_type: string;
  mission_uid: string;
  created_at: string;
  tasks: unknown[];
  progress: number;
  complete_count: number;
  pending_count: number;
  late_count: number;
}

interface ChecklistDetailColumn {
  uid: string;
  name: string;
}

interface ChecklistDetailRow {
  id: string;
  number: number;
  task_uid: string;
  done: boolean;
  column_values: Record<string, string>;
  due: string;
  status: string;
  completeDtg: string;
}

interface ChecklistTemplateOption {
  uid: string;
  name: string;
  description: string;
  columns: number;
  source_type: "template" | "csv_import";
  created_at?: string;
  owner?: string;
  task_rows: number;
}

interface ChecklistTemplateDraftColumn {
  column_uid: string;
  column_name: string;
  column_type: string;
  column_editable: boolean;
  background_color: string | null;
  text_color: string | null;
  system_key?: string | null;
}

defineProps<{
  checklistSearchQuery: string;
  checklistWorkspaceView: "active" | "templates";
  checklistActiveCount: number;
  checklistTemplateCount: number;
  checklistDetailRecord: ChecklistCard | null;
  canCreateFromDetailTemplate: boolean;
  checklistLinkMissionSubmitting: boolean;
  checklistDeleteBusy: boolean;
  checklistTaskDueDraft: string;
  checklistDetailColumns: ChecklistDetailColumn[];
  checklistDetailRows: ChecklistDetailRow[];
  checklistTaskStatusBusyByTaskUid: Record<string, boolean>;
  filteredChecklistCards: ChecklistCard[];
  filteredChecklistTemplates: ChecklistTemplateOption[];
  checklistTemplateEditorSelectionUid: string;
  checklistTemplateEditorSelectionSourceType: "template" | "csv_import" | "";
  checklistTemplateEditorTitle: string;
  checklistTemplateEditorSubtitle: string;
  canAddChecklistTemplateColumn: boolean;
  canSaveChecklistTemplateDraft: boolean;
  canSaveChecklistTemplateDraftAsNew: boolean;
  canCloneChecklistTemplateDraft: boolean;
  canArchiveChecklistTemplateDraft: boolean;
  canConvertChecklistTemplateDraft: boolean;
  canDeleteChecklistTemplateDraft: boolean;
  checklistTemplateDraftName: string;
  checklistTemplateDraftDescription: string;
  isChecklistTemplateDraftReadonly: boolean;
  checklistTemplateDraftColumns: ChecklistTemplateDraftColumn[];
  checklistTemplateColumnTypeOptions: string[];
  checklistTemplateEditorStatusLabel: string;
  setChecklistWorkspaceView: (view: "active" | "templates") => void;
  openChecklistCreationModal: () => void;
  showChecklistFilterNotice: () => void;
  openTemplateBuilderFromChecklist: () => void;
  openChecklistImportFromChecklist: () => void;
  closeChecklistDetailView: () => void;
  checklistDescriptionLabel: (value: string) => string;
  modeChipClass: (value: string) => string;
  syncChipClass: (value: string) => string;
  statusChipClass: (value: string) => string;
  checklistOriginLabel: (value?: string | null) => string;
  checklistMissionLabel: (value?: string | null) => string;
  createChecklistFromDetailTemplate: () => void;
  openChecklistMissionLinkModal: () => void;
  deleteChecklistFromDetail: () => void;
  progressWidth: (value: number) => string;
  addChecklistTaskFromDetail: () => void;
  toggleChecklistTaskDone: (row: ChecklistDetailRow) => void;
  openChecklistDetailView: (uid: string) => void;
  formatChecklistDateTime: (value?: string | null) => string;
  selectChecklistTemplateForEditor: (uid: string, sourceType: "template" | "csv_import") => void;
  startNewChecklistTemplateDraft: () => void;
  addChecklistTemplateColumn: () => void;
  saveChecklistTemplateDraft: () => void;
  saveChecklistTemplateDraftAsNew: () => void;
  cloneChecklistTemplateDraft: () => void;
  archiveChecklistTemplateDraft: () => void;
  convertChecklistTemplateDraftToServerTemplate: () => void;
  deleteChecklistTemplateDraft: () => void;
  isChecklistTemplateDueColumn: (column?: { system_key?: string | null }) => boolean;
  setChecklistTemplateColumnName: (columnIndex: number, event: Event) => void;
  setChecklistTemplateColumnType: (columnIndex: number, event: Event) => void;
  setChecklistTemplateColumnEditable: (columnIndex: number, event: Event) => void;
  checklistTemplateColumnColorValue: (value?: string | null) => string;
  setChecklistTemplateColumnBackgroundColor: (columnIndex: number, event: Event) => void;
  setChecklistTemplateColumnTextColor: (columnIndex: number, event: Event) => void;
  canMoveChecklistTemplateColumnUp: (columnIndex: number) => boolean;
  moveChecklistTemplateColumnUp: (columnIndex: number) => void;
  canMoveChecklistTemplateColumnDown: (columnIndex: number) => boolean;
  moveChecklistTemplateColumnDown: (columnIndex: number) => void;
  canDeleteChecklistTemplateColumn: (columnIndex: number) => boolean;
  deleteChecklistTemplateColumn: (columnIndex: number) => void;
}>();

const emit = defineEmits<{
  (event: "update:checklist-search-query", value: string): void;
  (event: "update:checklist-task-due-draft", value: string): void;
  (event: "update:checklist-template-draft-name", value: string): void;
  (event: "update:checklist-template-draft-description", value: string): void;
}>();

const readInputValue = (event: Event): string => {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement | null;
  return String(target?.value ?? "");
};

const updateChecklistSearchQuery = (event: Event): void => {
  emit("update:checklist-search-query", readInputValue(event));
};

const updateChecklistTaskDueDraft = (event: Event): void => {
  emit("update:checklist-task-due-draft", readInputValue(event));
};

const updateChecklistTemplateDraftName = (event: Event): void => {
  emit("update:checklist-template-draft-name", readInputValue(event));
};

const updateChecklistTemplateDraftDescription = (event: Event): void => {
  emit("update:checklist-template-draft-description", readInputValue(event));
};
</script>

<style scoped src="./MissionChecklistWorkspaceScreen.css"></style>
