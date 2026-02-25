<template>
  <div class="checklists-workspace">
    <div class="registry-shell">
      <CosmicTopStatus title="Checklist" />

      <section class="panel registry-main">
        <div class="screen-shell">
          <article class="stage-card checklist-workspace">
            <template v-if="!checklistDetailRecord">
              <div class="checklist-manager-controls">
                <label class="field-control full checklist-manager-search">
                  <input
                    v-model="checklistSearchQuery"
                    type="search"
                    placeholder="Search checklists and templates..."
                  />
                </label>
                <div class="checklist-manager-actions">
                  <BaseButton size="sm" icon-left="plus" @click="openChecklistCreationModal">New</BaseButton>
                  <BaseButton size="sm" variant="secondary" icon-left="filter" @click="showChecklistFilterNotice">Filter</BaseButton>
                  <BaseButton size="sm" variant="secondary" icon-left="edit" @click="openTemplateBuilderFromChecklist">
                    Template Builder
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
            </template>

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
                    <input v-model="checklistTaskDueDraft" type="number" step="1" min="-1440" />
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
              <div v-if="showChecklistImportCsv" class="screen-grid two-col">
                <article class="stage-card">
                  <h4>CSV Upload</h4>
                  <div class="field-grid single-col">
                    <label class="field-control full">
                      <span>Select CSV File</span>
                      <input ref="csvUploadInputRef" class="csv-upload-native" type="file" accept=".csv,text/csv" @change="handleCsvUpload" />
                      <div class="csv-upload-picker">
                        <BaseButton size="sm" variant="secondary" icon-left="upload" @click="openCsvUploadPicker">Choose File</BaseButton>
                        <span class="csv-upload-filename">{{ csvImportFilename || "No file chosen" }}</span>
                      </div>
                    </label>
                  </div>
                  <ul class="stack-list csv-meta">
                    <li><strong>Selected File</strong><span>{{ csvImportFilename || "No file selected" }}</span></li>
                    <li><strong>Header Columns</strong><span>{{ csvImportHeaders.length }}</span></li>
                    <li><strong>Task Rows</strong><span>{{ csvImportRows.length }}</span></li>
                    <li><strong>Template Type</strong><span>CSV Import</span></li>
                  </ul>
                  <div class="template-modal-actions" style="margin-top: 12px;">
                    <BaseButton variant="ghost" size="sm" icon-left="chevron-left" @click="closeChecklistImportView">Back</BaseButton>
                    <BaseButton size="sm" variant="secondary" icon-left="eye" @click="previewCsvAction" :disabled="!csvImportHeaders.length">Preview</BaseButton>
                    <BaseButton size="sm" icon-left="upload" @click="importChecklistFromCsvAction" :disabled="!csvImportHeaders.length || !csvImportRows.length || checklistCsvImportLoading">Import</BaseButton>
                  </div>
                </article>

                <article class="stage-card">
                  <h4>CSV Preview</h4>
                  <div v-if="csvImportHeaders.length && csvImportRows.length" class="csv-preview">
                    <table class="mini-table">
                      <thead>
                        <tr><th>#</th><th v-for="(header, headerIndex) in csvImportHeaders" :key="`csv-header-${headerIndex}`">{{ header }}</th></tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, rowIndex) in csvImportPreviewRows" :key="`csv-row-${rowIndex}`">
                          <td>{{ rowIndex + 1 }}</td>
                          <td v-for="(header, columnIndex) in csvImportHeaders" :key="`csv-cell-${rowIndex}-${columnIndex}`">{{ row[columnIndex] || "-" }}</td>
                        </tr>
                      </tbody>
                    </table>
                    <p v-if="csvImportRows.length > csvImportPreviewRows.length" class="csv-preview-note">Showing first {{ csvImportPreviewRows.length }} of {{ csvImportRows.length }} rows.</p>
                  </div>
                  <div v-else class="builder-preview">
                    <p>Upload a CSV file to preview its columns.</p>
                    <p>The first row becomes the column headers for your template.</p>
                  </div>
                </article>
              </div>

              <div v-else class="checklist-template-workspace">
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
                  <BaseButton
                    size="sm"
                    variant="secondary"
                    icon-left="upload"
                    @click="openChecklistImportFromChecklist"
                    style="margin-top: 12px; width: 100%; flex-shrink: 0;"
                  >
                    Import from CSV
                  </BaseButton>
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
                          v-model="checklistTemplateDraftName"
                          type="text"
                          :disabled="isChecklistTemplateDraftReadonly"
                        />
                      </label>
                      <label class="field-control full">
                        <span>Description</span>
                        <textarea
                          v-model="checklistTemplateDraftDescription"
                          rows="3"
                          :disabled="isChecklistTemplateDraftReadonly"
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
      </section>
    </div>

    <BaseModal
      :open="checklistTemplateModalOpen"
      title="Create Checklist from Template"
      @close="closeChecklistTemplateModal"
    >
      <div class="template-modal">
        <label class="field-control full">
          <span>Checklist Name</span>
          <input v-model="checklistTemplateNameDraft" type="text" placeholder="Mission Checklist" />
        </label>

        <div v-if="checklistTemplateOptions.length" class="template-modal-list">
          <BaseSelect
            v-model="checklistTemplateSelectionUid"
            label="Template"
            :options="checklistTemplateSelectOptions"
          />
          <p v-if="selectedChecklistTemplateOption" class="template-modal-hint">
            {{ selectedChecklistTemplateOption.columns }} columns
            <span v-if="selectedChecklistTemplateOption.task_rows > 0">
              | {{ selectedChecklistTemplateOption.task_rows }} tasks
            </span>
            <span v-if="selectedChecklistTemplateOption.source_type === 'csv_import'"> | sourced from CSV import</span>
          </p>
        </div>
        <p v-else class="template-modal-empty">No checklist templates available.</p>

        <div class="template-modal-actions">
          <BaseButton variant="ghost" icon-left="undo" @click="closeChecklistTemplateModal">Cancel</BaseButton>
          <BaseButton
            icon-left="plus"
            :disabled="checklistTemplateSubmitting || !checklistTemplateSelectionUid"
            @click="submitChecklistTemplateSelection"
          >
            {{ checklistTemplateSubmitting ? "Creating..." : "Create" }}
          </BaseButton>
        </div>
      </div>
    </BaseModal>

    <BaseModal
      :open="checklistLinkMissionModalOpen"
      title="Link Checklist to Mission"
      @close="closeChecklistMissionLinkModal"
    >
      <div class="template-modal">
        <p class="template-modal-hint">Associate this checklist with a mission or leave it unscoped.</p>
        <BaseSelect v-model="checklistLinkMissionSelectionUid" label="Mission" :options="checklistMissionLinkSelectOptions" />
        <div class="template-modal-actions">
          <BaseButton
            variant="ghost"
            icon-left="undo"
            :disabled="checklistLinkMissionSubmitting"
            @click="closeChecklistMissionLinkModal"
          >
            Cancel
          </BaseButton>
          <BaseButton
            icon-left="link"
            :disabled="checklistLinkMissionSubmitting || !canSubmitChecklistMissionLink"
            @click="submitChecklistMissionLink"
          >
            {{ checklistLinkMissionSubmitting ? "Saving..." : checklistLinkMissionActionLabel }}
          </BaseButton>
        </div>
      </div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type { ApiError } from "../api/client";
import { del as deleteRequest, get, patch as patchRequest, post } from "../api/client";
import { endpoints } from "../api/endpoints";
import BaseButton from "../components/BaseButton.vue";
import CosmicTopStatus from "../components/cosmic/CosmicTopStatus.vue";
import BaseModal from "../components/BaseModal.vue";
import BaseSelect from "../components/BaseSelect.vue";
import { useToastStore } from "../stores/toasts";

// Types
interface Mission {
  uid: string;
  mission_name: string;
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

interface MissionRaw {
  uid?: string;
  mission_name?: string | null;
}

interface TemplateRaw {
  uid?: string;
  template_name?: string | null;
  description?: string | null;
  created_at?: string | null;
  created_by_team_member_rns_identity?: string | null;
  columns?: unknown;
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
  system_key?: string | null;
  background_color?: string | null;
  text_color?: string | null;
}

// Constants
const DEFAULT_SOURCE_IDENTITY = "ui.operator";
const SYSTEM_DUE_COLUMN_KEY = "DUE_RELATIVE_DTG";
const checklistTemplateColumnTypeOptions: ChecklistTemplateColumnType[] = [
  "SHORT_STRING",
  "LONG_STRING",
  "INTEGER",
  "ACTUAL_TIME",
  "RELATIVE_TIME"
];
const checklistTemplateColumnTypeSet = new Set<ChecklistTemplateColumnType>(checklistTemplateColumnTypeOptions);

// Utilities
const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);
const asRecord = (value: unknown): Record<string, unknown> => {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
};
const toEpoch = (value?: string | null): number => {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
};
const normalizeTaskStatus = (value?: string | null): string => {
  const text = String(value ?? "PENDING").trim().toUpperCase();
  return text || "PENDING";
};
const resolveTaskNameColumnUid = (checklist: ChecklistRaw): string | undefined => {
  const columns = toArray<ChecklistColumnRaw>(checklist.columns);
  const namedTask = columns.find((column) => String(column.column_name ?? "").trim().toUpperCase() === "TASK");
  if (namedTask?.column_uid) return namedTask.column_uid;
  const shortString = columns.find(
    (column) =>
      String(column.column_type ?? "").trim().toUpperCase() === "SHORT_STRING" &&
      String(column.system_key ?? "").trim().length === 0
  );
  if (shortString?.column_uid) return shortString.column_uid;
  return columns.find((column) => column.column_uid)?.column_uid;
};
const resolveChecklistTaskName = (checklist: ChecklistRaw, task: ChecklistTaskRaw, preferredColumnUid?: string): string => {
  const cells = toArray<ChecklistCellRaw>(task.cells);
  const taskColumnUid = preferredColumnUid ?? resolveTaskNameColumnUid(checklist);
  if (taskColumnUid) {
    const preferredCell = cells.find((cell) => String(cell.column_uid ?? "").trim() === taskColumnUid);
    if (typeof preferredCell?.value === "string" && preferredCell.value.trim()) {
      return preferredCell.value.trim();
    }
  }
  const firstTextCell = cells.find((cell) => typeof cell.value === "string" && cell.value.trim().length > 0);
  if (typeof firstTextCell?.value === "string") return firstTextCell.value.trim();
  const legacyValue = String(task.legacy_value ?? "").trim();
  if (legacyValue) return legacyValue;
  if (typeof task.number === "number") return `Task ${task.number}`;
  const taskUid = String(task.task_uid ?? "").trim();
  if (taskUid) return `Task ${taskUid.slice(0, 8)}`;
  return "Task";
};
const resolveColumnUidByNames = (checklist: ChecklistRaw, candidateNames: string[]): string | undefined => {
  const normalizedCandidates = candidateNames.map((name) => name.trim().toUpperCase()).filter((name) => name.length > 0);
  if (!normalizedCandidates.length) return undefined;
  const columns = toArray<ChecklistColumnRaw>(checklist.columns);
  const exactMatch = columns.find((column) =>
    normalizedCandidates.includes(String(column.column_name ?? "").trim().toUpperCase())
  );
  return exactMatch?.column_uid;
};
const resolveTaskDescription = (checklist: ChecklistRaw, task: ChecklistTaskRaw, preferredDescriptionColumnUid?: string, preferredTaskColumnUid?: string): string => {
  const cells = toArray<ChecklistCellRaw>(task.cells);
  if (preferredDescriptionColumnUid) {
    const descriptionCell = cells.find((cell) => String(cell.column_uid ?? "").trim() === preferredDescriptionColumnUid);
    if (typeof descriptionCell?.value === "string" && descriptionCell.value.trim()) {
      return descriptionCell.value.trim();
    }
  }
  const fallback = cells.find((cell) => {
    const columnUid = String(cell.column_uid ?? "").trim();
    if (!columnUid || (preferredTaskColumnUid && columnUid === preferredTaskColumnUid)) return false;
    return typeof cell.value === "string" && cell.value.trim().length > 0;
  });
  if (typeof fallback?.value === "string") return fallback.value.trim();
  return "";
};
const extractErrorDetail = (error: ApiError): string | undefined => {
  if (typeof error.body === "string" && error.body.trim()) return error.body.trim();
  const payload = asRecord(error.body);
  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
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
const formatChecklistDateTime = (value?: string | null): string => {
  if (!value) return "--";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};
const formatDueRelativeMinutesLabel = (value?: number | null): string => {
  const minutes = Number(value);
  if (!Number.isFinite(minutes)) return "-";
  const rounded = Math.trunc(minutes);
  const sign = rounded < 0 ? "-" : "+";
  const abs = Math.abs(rounded);
  const hours = String(Math.trunc(abs / 60)).padStart(2, "0");
  const mins = String(abs % 60).padStart(2, "0");
  return `T${sign}${hours}:${mins}`;
};
const buildTimestampTag = (): string => new Date().toISOString().replace(/[^0-9]/g, "").slice(0, 14);
const normalizeChecklistTemplateColumnType = (value?: string | null): ChecklistTemplateColumnType => {
  const normalized = String(value ?? "").trim().toUpperCase() as ChecklistTemplateColumnType;
  return checklistTemplateColumnTypeSet.has(normalized) ? normalized : "SHORT_STRING";
};
const isChecklistTemplateDueColumn = (column?: { system_key?: string | null }): boolean =>
  String(column?.system_key ?? "").trim().toUpperCase() === SYSTEM_DUE_COLUMN_KEY;
const buildChecklistTemplateColumnUid = (): string =>
  `tmpl-col-${buildTimestampTag().slice(-10)}-${Math.floor(Math.random() * 1_000_000).toString(16).padStart(5, "0")}`;
const createDueChecklistTemplateDraftColumn = (): ChecklistTemplateDraftColumn => ({
  column_uid: buildChecklistTemplateColumnUid(),
  column_name: "Due",
  display_order: 1,
  column_type: "RELATIVE_TIME",
  column_editable: false,
  is_removable: false,
  system_key: SYSTEM_DUE_COLUMN_KEY,
  background_color: null,
  text_color: null
});
const createTaskChecklistTemplateDraftColumn = (): ChecklistTemplateDraftColumn => ({
  column_uid: buildChecklistTemplateColumnUid(),
  column_name: "Task",
  display_order: 2,
  column_type: "SHORT_STRING",
  column_editable: true,
  is_removable: true,
  system_key: null,
  background_color: null,
  text_color: null
});
const normalizeChecklistTemplateColor = (value?: string | null): string | null => {
  const normalized = String(value ?? "").trim();
  if (!normalized) return null;
  if (/^#[0-9a-fA-F]{6}$/.test(normalized)) return normalized.toUpperCase();
  return null;
};
const checklistTemplateColumnColorValue = (value?: string | null): string =>
  normalizeChecklistTemplateColor(value) ?? "#001F2B";
const normalizeChecklistTemplateDraftColumns = (columns: Array<ChecklistColumnRaw | ChecklistTemplateDraftColumn>, options?: { ensureTaskColumn?: boolean }): ChecklistTemplateDraftColumn[] => {
  const normalizedRows = columns.map((column, index) => ({
    column_uid: String(column.column_uid ?? "").trim() || buildChecklistTemplateColumnUid(),
    column_name: String(column.column_name ?? `Column ${index + 1}`).trim() || `Column ${index + 1}`,
    display_order: Number(column.display_order ?? index + 1),
    column_type: normalizeChecklistTemplateColumnType(column.column_type),
    column_editable: Boolean(column.column_editable ?? true),
    is_removable: Boolean(column.is_removable ?? true),
    system_key: String(column.system_key ?? "").trim() || null,
    background_color: normalizeChecklistTemplateColor(column.background_color),
    text_color: normalizeChecklistTemplateColor(column.text_color)
  }));
  const sorted = [...normalizedRows].sort((left, right) => left.display_order - right.display_order);
  const dueColumn = sorted.find((column) => isChecklistTemplateDueColumn(column)) ?? createDueChecklistTemplateDraftColumn();
  const normalizedDueColumn: ChecklistTemplateDraftColumn = {
    ...dueColumn,
    column_name: String(dueColumn.column_name || "Due"),
    column_type: "RELATIVE_TIME",
    column_editable: false,
    is_removable: false,
    system_key: SYSTEM_DUE_COLUMN_KEY
  };
  const customColumns = sorted
    .filter((column) => !isChecklistTemplateDueColumn(column))
    .map((column) => ({ ...column, system_key: null, column_type: normalizeChecklistTemplateColumnType(column.column_type) }));
  if (options?.ensureTaskColumn && !customColumns.length) {
    customColumns.push(createTaskChecklistTemplateDraftColumn());
  }
  return [normalizedDueColumn, ...customColumns].map((column, index) => ({ ...column, display_order: index + 1 }));
};
const toChecklistTemplateColumnPayload = (columns: ChecklistTemplateDraftColumn[]) =>
  normalizeChecklistTemplateDraftColumns(columns).map((column, index) => ({
    column_uid: column.column_uid || buildChecklistTemplateColumnUid(),
    column_name: String(column.column_name ?? "").trim() || `Column ${index + 1}`,
    display_order: index + 1,
    column_type: normalizeChecklistTemplateColumnType(column.column_type),
    column_editable: isChecklistTemplateDueColumn(column) ? false : Boolean(column.column_editable),
    is_removable: isChecklistTemplateDueColumn(column) ? false : Boolean(column.is_removable),
    system_key: isChecklistTemplateDueColumn(column) ? SYSTEM_DUE_COLUMN_KEY : undefined,
    background_color: normalizeChecklistTemplateColor(column.background_color) ?? undefined,
    text_color: normalizeChecklistTemplateColor(column.text_color) ?? undefined
  }));
const validateChecklistTemplateDraftPayload = (templateName: string, columns: ChecklistTemplateDraftColumn[]): string | null => {
  if (!templateName.trim()) return "Template name is required";
  const normalizedColumns = normalizeChecklistTemplateDraftColumns(columns);
  if (!normalizedColumns.length) return "Template must include at least one column";
  if (!isChecklistTemplateDueColumn(normalizedColumns[0])) return "Due Relative DTG system column must be first";
  const dueColumns = normalizedColumns.filter((column) => isChecklistTemplateDueColumn(column));
  if (dueColumns.length !== 1) return "Exactly one Due Relative DTG system column is required";
  if (dueColumns[0].column_type !== "RELATIVE_TIME") return "Due Relative DTG system column must be RELATIVE_TIME";
  if (dueColumns[0].is_removable) return "Due Relative DTG system column cannot be removable";
  const invalidType = normalizedColumns.find((column) => !checklistTemplateColumnTypeSet.has(column.column_type));
  if (invalidType) return `Unsupported column type: ${invalidType.column_type}`;
  return null;
};
const createBlankChecklistTemplateDraftColumns = (): ChecklistTemplateDraftColumn[] =>
  normalizeChecklistTemplateDraftColumns([createDueChecklistTemplateDraftColumn(), createTaskChecklistTemplateDraftColumn()], { ensureTaskColumn: true });

// Stores
const toastStore = useToastStore();

// State
const missions = ref<Mission[]>([]);
const checklistRecords = ref<ChecklistRaw[]>([]);
const templateRecords = ref<TemplateRaw[]>([]);
const checklistSearchQuery = ref("");
const checklistWorkspaceView = ref<"active" | "templates">("active");
const checklistCsvImportView = ref(false);
const checklistDetailUid = ref("");
const checklistTaskDueDraft = ref("10");
const checklistTaskStatusBusyByTaskUid = ref<Record<string, boolean>>({});
const checklistDeleteBusy = ref(false);
const checklistLinkMissionModalOpen = ref(false);
const checklistLinkMissionSelectionUid = ref("");
const checklistLinkMissionSubmitting = ref(false);
const checklistTemplateDeleteBusyByUid = ref<Record<string, boolean>>({});
const checklistTemplateModalOpen = ref(false);
const checklistTemplateSelectionUid = ref("");
const checklistTemplateNameDraft = ref("");
const checklistTemplateSubmitting = ref(false);
const checklistTemplateEditorSelectionUid = ref("");
const checklistTemplateEditorSelectionSourceType = ref<ChecklistTemplateSourceType | "">("");
const checklistTemplateEditorMode = ref<ChecklistTemplateEditorMode>("create");
const checklistTemplateEditorDirty = ref(false);
const checklistTemplateEditorSaving = ref(false);
const checklistTemplateEditorHydrating = ref(false);
const checklistCsvImportLoading = ref(false);
const checklistTemplateDraftTemplateUid = ref("");
const checklistTemplateDraftName = ref("");
const checklistTemplateDraftDescription = ref("");
const checklistTemplateDraftColumns = ref<ChecklistTemplateDraftColumn[]>(createBlankChecklistTemplateDraftColumns());
const csvImportFilename = ref("");
const csvImportBase64 = ref("");
const csvImportHeaders = ref<string[]>([]);
const csvImportRows = ref<string[][]>([]);
const csvUploadInputRef = ref<HTMLInputElement | null>(null);
const csvImportPreviewRows = computed(() => csvImportRows.value.slice(0, 12));

// Computed
const showChecklistImportCsv = computed(() => checklistCsvImportView.value);

const upsertChecklistRecord = (record: ChecklistRaw) => {
  const uid = String(record.uid ?? "").trim();
  if (!uid) return;
  const next = [...checklistRecords.value];
  const index = next.findIndex((entry) => String(entry.uid ?? "").trim() === uid);
  if (index >= 0) next[index] = record;
  else next.push(record);
  checklistRecords.value = next;
};

const hydrateChecklistRecord = async (checklistUid: string): Promise<ChecklistRaw | null> => {
  const uid = String(checklistUid ?? "").trim();
  if (!uid) return null;
  const detail = await get<ChecklistRaw>(`${endpoints.checklists}/${uid}`);
  upsertChecklistRecord(detail);
  return detail;
};

const checklists = computed<Checklist[]>(() => {
  return checklistRecords.value
    .map((entry) => {
      const checklistUid = String(entry.uid ?? "").trim();
      if (!checklistUid) return null;
      const preferredTaskColumnUid = resolveTaskNameColumnUid(entry);
      const preferredDescriptionColumnUid = resolveColumnUidByNames(entry, ["DESCRIPTION", "DETAILS", "NOTES"]);
      const tasks = toArray<ChecklistTaskRaw>(entry.tasks)
        .map((task) => {
          const taskUid = String(task.task_uid ?? "").trim();
          const taskStatus = normalizeTaskStatus(task.task_status ?? task.user_status);
          const taskName = resolveChecklistTaskName(entry, task, preferredTaskColumnUid);
          const taskDescription = resolveTaskDescription(entry, task, preferredDescriptionColumnUid, preferredTaskColumnUid);
          const assignee = String(task.completed_by_team_member_rns_identity ?? "").trim();
          return {
            id: taskUid || `${checklistUid}-task-${String(task.number ?? "0")}`,
            number: Number(task.number ?? 0),
            name: taskName,
            description: taskDescription,
            status: taskStatus,
            assignee: assignee || "-",
            due_dtg: String(task.due_dtg ?? ""),
            due_relative_minutes: Number.isFinite(Number(task.due_relative_minutes)) ? Math.trunc(Number(task.due_relative_minutes)) : null,
            completed_at: String(task.completed_at ?? ""),
            cells: toArray<ChecklistCellRaw>(task.cells).length
          };
        })
        .sort((left, right) => left.number - right.number);
      const missionUid = String(entry.mission_id ?? "").trim();
      const pendingCount = Number(entry.counts?.pending_count ?? NaN);
      const lateCount = Number(entry.counts?.late_count ?? NaN);
      const completeCount = Number(entry.counts?.complete_count ?? NaN);
      let computedPending = 0, computedLate = 0, computedComplete = 0;
      tasks.forEach((task) => {
        const status = normalizeTaskStatus(task.status);
        if (status.startsWith("COMPLETE")) computedComplete += 1;
        else if (status === "LATE") computedLate += 1;
        else computedPending += 1;
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

const allChecklistsSorted = computed(() => {
  return [...checklists.value].sort((left, right) => {
    const diff = toEpoch(right.created_at) - toEpoch(left.created_at);
    return diff !== 0 ? diff : left.name.localeCompare(right.name);
  });
});

const checklistActiveCount = computed(() => allChecklistsSorted.value.length);
const checklistSearchNeedle = computed(() => checklistSearchQuery.value.trim().toUpperCase());

const filteredChecklistCards = computed(() => {
  const needle = checklistSearchNeedle.value;
  if (!needle) return allChecklistsSorted.value;
  return allChecklistsSorted.value.filter((checklist) => {
    const haystack = [checklist.name, checklist.description, checklist.checklist_status, checklist.mode, checklist.sync_state, checklistMissionLabel(checklist.mission_uid)].join(" ").toUpperCase();
    return haystack.includes(needle);
  });
});

const missionNameByUid = computed(() => {
  const map = new Map<string, string>();
  missions.value.forEach((mission) => map.set(mission.uid, mission.mission_name));
  return map;
});

const checklistMissionLabel = (missionUid: string): string => {
  const uid = String(missionUid ?? "").trim();
  if (!uid) return "Unscoped";
  return missionNameByUid.value.get(uid) ?? uid;
};

const checklistDetailRecord = computed(() => {
  const detailUid = checklistDetailUid.value;
  if (!detailUid) return null;
  return checklists.value.find((entry) => entry.uid === detailUid) ?? null;
});

const checklistDetailRaw = computed(() => {
  const detailUid = checklistDetailUid.value;
  if (!detailUid) return null;
  return checklistRecords.value.find((entry) => String(entry.uid ?? "").trim() === detailUid) ?? null;
});

const canCreateFromDetailTemplate = computed(() => {
  const detailUid = checklistDetailRecord.value?.uid ?? "";
  if (!detailUid) return false;
  return checklistTemplateOptions.value.some((entry) => entry.uid === detailUid);
});

const checklistDetailColumns = computed(() => {
  const checklist = checklistDetailRaw.value;
  if (!checklist) return [] as Array<{ uid: string; name: string }>;
  const dueColumnUid = toArray<ChecklistColumnRaw>(checklist.columns).find((column) => String(column.system_key ?? "").trim().toUpperCase() === "DUE_RELATIVE_DTG")?.column_uid ?? "";
  const columns = toArray<ChecklistColumnRaw>(checklist.columns)
    .map((column) => ({ uid: String(column.column_uid ?? "").trim(), name: String(column.column_name ?? "").trim(), system_key: String(column.system_key ?? "").trim().toUpperCase(), display_order: Number(column.display_order ?? 0) }))
    .filter((column) => column.uid.length > 0 && column.system_key !== "DUE_RELATIVE_DTG")
    .sort((left, right) => left.display_order - right.display_order);
  const mergedColumns = [...columns];
  const knownColumnUids = new Set(mergedColumns.map((column) => column.uid));
  toArray<ChecklistTaskRaw>(checklist.tasks).forEach((task) => {
    toArray<ChecklistCellRaw>(task.cells).forEach((cell) => {
      const columnUid = String(cell.column_uid ?? "").trim();
      if (!columnUid || columnUid === String(dueColumnUid).trim() || knownColumnUids.has(columnUid)) return;
      knownColumnUids.add(columnUid);
      mergedColumns.push({ uid: columnUid, name: "", system_key: "", display_order: mergedColumns.length + 1000 });
    });
  });
  return mergedColumns.map((column, index) => ({ uid: column.uid, name: column.name || `Column ${index + 1}` }));
});

const checklistDetailRows = computed(() => {
  const checklist = checklistDetailRaw.value;
  if (!checklist) return [] as Array<{ id: string; task_uid: string; number: number; done: boolean; column_values: Record<string, string>; due: string; status: string; completeDtg: string }>;
  const preferredTaskColumnUid = resolveTaskNameColumnUid(checklist);
  const dueColumnUid = toArray<ChecklistColumnRaw>(checklist.columns).find((column) => String(column.system_key ?? "").trim().toUpperCase() === "DUE_RELATIVE_DTG")?.column_uid ?? "";
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
        const dueCell = toArray<ChecklistCellRaw>(task.cells).find((cell) => String(cell.column_uid ?? "").trim() === String(dueColumnUid).trim());
        if (typeof dueCell?.value === "string" && dueCell.value.trim()) due = dueCell.value.trim();
      }
      return {
        id: taskUid || `task-${String(task.number ?? 0)}`,
        task_uid: taskUid,
        number: Number(task.number ?? 0),
        done,
        column_values: (() => {
          const values = toArray<ChecklistCellRaw>(task.cells).reduce((map, cell) => {
            const columnUid = String(cell.column_uid ?? "").trim();
            if (columnUid) map[columnUid] = String(cell.value ?? "").trim();
            return map;
          }, {} as Record<string, string>);
          if (preferredTaskColumnUid && !values[preferredTaskColumnUid]) values[preferredTaskColumnUid] = resolveChecklistTaskName(checklist, task, preferredTaskColumnUid);
          return values;
        })(),
        due,
        status,
        completeDtg: formatChecklistDateTime(task.completed_at)
      };
    })
    .sort((left, right) => left.number - right.number);
});

const checklistDetailMissionUid = computed(() => String(checklistDetailRecord.value?.mission_uid ?? "").trim());

const checklistMissionLinkSelectOptions = computed(() => {
  const options: Array<{ label: string; value: string }> = [{ label: "Unscoped", value: "" }];
  const seen = new Set<string>([""]);
  [...missions.value].sort((left, right) => left.mission_name.localeCompare(right.mission_name)).forEach((mission) => {
    const uid = String(mission.uid ?? "").trim();
    if (!uid || seen.has(uid)) return;
    seen.add(uid);
    options.push({ value: uid, label: String(mission.mission_name ?? "").trim() || uid });
  });
  const currentMissionUid = checklistDetailMissionUid.value;
  if (currentMissionUid && !seen.has(currentMissionUid)) {
    options.push({ value: currentMissionUid, label: `${currentMissionUid} (Unavailable)` });
  }
  return options;
});

const checklistLinkMissionActionLabel = computed(() => checklistLinkMissionSelectionUid.value.trim() ? "Link Mission" : "Clear Link");

const canSubmitChecklistMissionLink = computed(() => {
  const checklistUid = String(checklistDetailRecord.value?.uid ?? "").trim();
  if (!checklistUid) return false;
  return checklistLinkMissionSelectionUid.value.trim() !== checklistDetailMissionUid.value;
});

const hasPopulatedChecklistCells = (checklist: ChecklistRaw): boolean =>
  toArray<ChecklistTaskRaw>(checklist.tasks).some((task) =>
    toArray<ChecklistCellRaw>(task.cells).some((cell) => String(cell.value ?? "").trim().length > 0)
  );

const isRenderableCsvImportTemplate = (checklist: ChecklistRaw): boolean => {
  const nonDueColumns = toArray<ChecklistColumnRaw>(checklist.columns).filter((column) => String(column.system_key ?? "").trim().toUpperCase() !== "DUE_RELATIVE_DTG");
  if (nonDueColumns.length > 1) return true;
  return hasPopulatedChecklistCells(checklist);
};

const collectChecklistTemplateOptions = (): ChecklistTemplateOption[] => {
  const serverTemplates = templateRecords.value
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) return null;
      return { uid, name: String(entry.template_name ?? uid), columns: toArray<ChecklistColumnRaw>(entry.columns).length, source_type: "template" as const, task_rows: 0, description: String(entry.description ?? "").trim(), created_at: String(entry.created_at ?? ""), owner: String(entry.created_by_team_member_rns_identity ?? "").trim() };
    })
    .filter((entry): entry is ChecklistTemplateOption => entry !== null);
  const csvImportedTemplates = checklistRecords.value
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) return null;
      const originType = String(entry.origin_type ?? "").trim().toUpperCase();
      if (originType !== "CSV_IMPORT") return null;
      if (!isRenderableCsvImportTemplate(entry)) return null;
      return { uid, name: String(entry.name ?? uid), columns: toArray<ChecklistColumnRaw>(entry.columns).length, source_type: "csv_import" as const, task_rows: toArray<ChecklistTaskRaw>(entry.tasks).length, description: String(entry.description ?? "").trim(), created_at: String(entry.created_at ?? ""), owner: String(entry.created_by_team_member_rns_identity ?? "").trim() };
    })
    .filter((entry): entry is ChecklistTemplateOption => entry !== null);
  const seen = new Set<string>();
  return [...serverTemplates, ...csvImportedTemplates].filter((entry) => {
    if (seen.has(entry.uid)) return false;
    seen.add(entry.uid);
    return true;
  });
};

const checklistTemplateOptions = computed<ChecklistTemplateOption[]>(() => collectChecklistTemplateOptions().sort((left, right) => left.name.localeCompare(right.name)));
const checklistTemplateCount = computed(() => checklistTemplateOptions.value.length);

const checklistTemplateSelectOptions = computed(() =>
  checklistTemplateOptions.value.map((entry) => ({ value: entry.uid, label: entry.source_type === "csv_import" ? `${entry.name} (${entry.columns} columns, CSV import)` : entry.name }))
);

const selectedChecklistTemplateOption = computed(() => checklistTemplateOptions.value.find((entry) => entry.uid === checklistTemplateSelectionUid.value));

const filteredChecklistTemplates = computed(() => {
  const sorted = [...checklistTemplateOptions.value].sort((left, right) => left.name.localeCompare(right.name));
  const needle = checklistSearchNeedle.value;
  if (!needle) return sorted;
  return sorted.filter((template) => [template.name, template.description, template.owner, template.source_type].join(" ").toUpperCase().includes(needle));
});

const selectedChecklistTemplateEditorOption = computed(() => {
  const uid = checklistTemplateEditorSelectionUid.value.trim();
  const sourceType = checklistTemplateEditorSelectionSourceType.value;
  if (!uid || !sourceType) return null;
  return checklistTemplateOptions.value.find((entry) => entry.uid === uid && entry.source_type === sourceType) ?? null;
});

const checklistTemplateEditorTitle = computed(() => {
  if (checklistTemplateEditorMode.value === "create") return "New Checklist Template";
  if (checklistTemplateEditorMode.value === "csv_readonly") return "CSV Import Template (Read Only)";
  return "Checklist Template Editor";
});

const checklistTemplateEditorSubtitle = computed(() => {
  if (checklistTemplateEditorMode.value === "create") return "Build a new server template with metadata and ordered columns.";
  if (checklistTemplateEditorMode.value === "csv_readonly") return "CSV-derived entries are read-only until converted into a server template.";
  return "Edit template metadata and columns. Save updates or save as new.";
});

const checklistTemplateEditorStatusLabel = computed(() => {
  if (checklistTemplateEditorSaving.value) return "Saving...";
  if (checklistTemplateEditorMode.value === "csv_readonly") return "Read-only CSV entry";
  if (checklistTemplateEditorMode.value === "create") return checklistTemplateEditorDirty.value ? "Draft not saved" : "Blank template draft";
  return checklistTemplateEditorDirty.value ? "Unsaved changes" : "Saved";
});

const isChecklistTemplateDraftReadonly = computed(() => checklistTemplateEditorMode.value === "csv_readonly");
const canAddChecklistTemplateColumn = computed(() => !isChecklistTemplateDraftReadonly.value && !checklistTemplateEditorSaving.value);
const canSaveChecklistTemplateDraft = computed(() => checklistTemplateEditorMode.value === "edit" && !isChecklistTemplateDraftReadonly.value && checklistTemplateDraftTemplateUid.value.trim().length > 0 && checklistTemplateEditorDirty.value && !checklistTemplateEditorSaving.value);
const canSaveChecklistTemplateDraftAsNew = computed(() => checklistTemplateEditorMode.value !== "csv_readonly" && !checklistTemplateEditorSaving.value && checklistTemplateDraftName.value.trim().length > 0);
const canCloneChecklistTemplateDraft = computed(() => checklistTemplateEditorMode.value === "edit" && checklistTemplateDraftTemplateUid.value.trim().length > 0 && !checklistTemplateEditorSaving.value);
const canArchiveChecklistTemplateDraft = computed(() => checklistTemplateEditorMode.value === "edit" && checklistTemplateDraftTemplateUid.value.trim().length > 0 && !checklistTemplateEditorSaving.value);
const canConvertChecklistTemplateDraft = computed(() => checklistTemplateEditorMode.value === "csv_readonly" && checklistTemplateEditorSelectionUid.value.trim().length > 0 && !checklistTemplateEditorSaving.value);
const canDeleteChecklistTemplateDraft = computed(() => {
  const selected = selectedChecklistTemplateEditorOption.value;
  if (!selected || checklistTemplateEditorSaving.value) return false;
  return !checklistTemplateDeleteBusyByUid.value[selected.uid];
});

// Methods
const progressWidth = (value: number): string => {
  if (!Number.isFinite(value)) return "0%";
  return `${Math.max(0, Math.min(100, Math.round(value)))}%`;
};
const statusChipClass = (status: string): string => {
  const normalized = normalizeTaskStatus(status);
  if (normalized.startsWith("COMPLETE")) return "checklist-chip-success";
  if (normalized === "LATE") return "checklist-chip-warning";
  return "checklist-chip-info";
};
const syncChipClass = (syncState: string): string => {
  const normalized = String(syncState ?? "").trim().toUpperCase();
  if (normalized === "SYNCED") return "checklist-chip-success";
  if (normalized === "PENDING") return "checklist-chip-warning";
  return "checklist-chip-info";
};
const modeChipClass = (mode: string): string => {
  const normalized = String(mode ?? "").trim().toUpperCase();
  if (normalized === "ONLINE") return "checklist-chip-info";
  if (normalized === "OFFLINE") return "checklist-chip-warning";
  return "checklist-chip-muted";
};
const checklistOriginLabel = (originType: string): string => {
  const normalized = String(originType ?? "").trim().toUpperCase();
  if (normalized === "CSV_IMPORT") return "CSV IMPORT";
  if (normalized === "RCH_TEMPLATE") return "TEMPLATE";
  if (normalized === "BLANK_TEMPLATE") return "BLANK";
  return normalized || "UNSPECIFIED";
};
const checklistDescriptionLabel = (description: string): string => String(description ?? "").trim() || "No description provided";
const openChecklistDetailView = async (checklistUid: string) => {
  const uid = String(checklistUid ?? "").trim();
  if (!uid) return;
  checklistDetailUid.value = uid;
  try { await hydrateChecklistRecord(uid); } catch (error) { handleApiError(error, "Unable to load checklist details"); }
};
const closeChecklistDetailView = () => { checklistLinkMissionModalOpen.value = false; checklistDetailUid.value = ""; checklistCsvImportView.value = false; };
const navigateToChecklistTemplateList = () => { checklistCsvImportView.value = false; clearCsvUpload(); };
const clearCsvUpload = () => { csvImportFilename.value = ""; csvImportBase64.value = ""; csvImportHeaders.value = []; csvImportRows.value = []; };
const openCsvUploadPicker = () => { csvUploadInputRef.value?.click(); };
const parseCsvRows = (payload: string): string[][] => {
  const rows: string[][] = []; let row: string[] = []; let cell = ""; let inQuotes = false;
  for (let index = 0; index < payload.length; index += 1) {
    const char = payload[index];
    if (inQuotes) { if (char === "\"") { if (payload[index + 1] === "\"") { cell += "\""; index += 1; } else { inQuotes = false; } } else { cell += char; } continue; }
    if (char === "\"") { inQuotes = true; continue; }
    if (char === ",") { row.push(cell); cell = ""; continue; }
    if (char === "\n" || char === "\r") { if (char === "\r" && payload[index + 1] === "\n") { index += 1; } row.push(cell); rows.push(row); row = []; cell = ""; continue; }
    cell += char;
  }
  if (cell.length > 0 || row.length > 0) { row.push(cell); rows.push(row); }
  return rows;
};
const normalizeCsvRows = (rows: string[][]): string[][] => {
  return rows.map((row, rowIndex) => row.map((cell, columnIndex) => { const cleanCell = rowIndex === 0 && columnIndex === 0 ? cell.replace(/^\uFEFF/, "") : cell; return cleanCell.trim(); })).filter((row) => row.some((cell) => cell.length > 0));
};
const uint8ArrayToBase64 = (bytes: Uint8Array): string => {
  const chunkSize = 0x8000; let binary = "";
  for (let index = 0; index < bytes.length; index += chunkSize) { const chunk = bytes.subarray(index, index + chunkSize); binary += String.fromCharCode(...chunk); }
  return btoa(binary);
};
const handleCsvUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement | null;
  const file = target?.files?.[0];
  if (!file) { clearCsvUpload(); return; }
  try {
    if (!file.name.toLowerCase().endsWith(".csv")) throw new Error("Select a file with .csv extension");
    const bytes = new Uint8Array(await file.arrayBuffer());
    const text = new TextDecoder("utf-8").decode(bytes);
    const parsedRows = normalizeCsvRows(parseCsvRows(text));
    if (parsedRows.length < 2) throw new Error("CSV must include a header row and at least one task row");
    const headerRow = parsedRows[0];
    const taskRows = parsedRows.slice(1);
    const maxColumns = taskRows.reduce((max, row) => Math.max(max, row.length), headerRow.length);
    if (maxColumns <= 0) throw new Error("CSV header row is empty");
    const headers = Array.from({ length: maxColumns }, (_, index) => { const value = String(headerRow[index] ?? "").trim(); return value || `Column ${index + 1}`; });
    const normalizedTaskRows = taskRows.map((row) => headers.map((_, columnIndex) => String(row[columnIndex] ?? "").trim()));
    csvImportFilename.value = file.name;
    csvImportBase64.value = uint8ArrayToBase64(bytes);
    csvImportHeaders.value = headers;
    csvImportRows.value = normalizedTaskRows;
    toastStore.push(`Loaded ${file.name}: ${normalizedTaskRows.length} task rows`, "info");
  } catch (error) {
    clearCsvUpload();
    if (error instanceof Error) { toastStore.push(`CSV upload failed: ${error.message}`, "warning"); return; }
    toastStore.push("CSV upload failed", "warning");
  }
};
const createChecklistFromDetailTemplate = () => {
  const detailUid = checklistDetailRecord.value?.uid ?? "";
  if (!detailUid) return;
  if (checklistTemplateOptions.value.some((entry) => entry.uid === detailUid)) checklistTemplateSelectionUid.value = detailUid;
  try { openChecklistTemplateModal(); } catch (error) { handleApiError(error, "Unable to open checklist template selector"); }
};
const openChecklistCreationModal = () => { try { openChecklistTemplateModal(); } catch (error) { handleApiError(error, "Unable to open checklist template selector"); } };
const openChecklistMissionLinkModal = () => {
  const checklist = checklistDetailRecord.value;
  if (!checklist?.uid) { toastStore.push("Select a checklist first", "warning"); return; }
  const currentMissionUid = String(checklist.mission_uid ?? "").trim();
  if (currentMissionUid) checklistLinkMissionSelectionUid.value = currentMissionUid;
  else { const preferredMissionUid = missions.value[0]?.uid ?? ""; const missionExists = missions.value.some((mission) => mission.uid === preferredMissionUid); checklistLinkMissionSelectionUid.value = missionExists ? preferredMissionUid : ""; }
  checklistLinkMissionModalOpen.value = true;
};
const closeChecklistMissionLinkModal = () => { if (checklistLinkMissionSubmitting.value) return; checklistLinkMissionModalOpen.value = false; };
const showChecklistFilterNotice = () => { toastStore.push("Checklist filter presets can be added from this workspace", "info"); };
const setChecklistWorkspaceView = (view: "active" | "templates") => {
  checklistLinkMissionModalOpen.value = false;
  checklistCsvImportView.value = false;
  clearCsvUpload();
  checklistWorkspaceView.value = view;
  if (view === "templates") { checklistDetailUid.value = ""; syncChecklistTemplateEditorSelection(); }
};
const openTemplateBuilderFromChecklist = () => { setChecklistWorkspaceView("templates"); };
const openChecklistImportFromChecklist = () => { checklistCsvImportView.value = true; checklistTemplateEditorSelectionUid.value = ""; checklistTemplateEditorSelectionSourceType.value = ""; };
const closeChecklistImportView = () => { checklistCsvImportView.value = false; clearCsvUpload(); };
const importChecklistFromCsvAction = async () => {
  if (!csvImportHeaders.value.length || !csvImportRows.value.length) {
    throw new Error("Upload a CSV file before importing");
  }
  checklistCsvImportLoading.value = true;
  try {
    const baseName = (csvImportFilename.value || "CSV Template").replace(/\.csv$/i, "").trim() || "CSV Template";
    const imported = await createTemplateFromUploadedCsvAction(baseName);
    await loadWorkspace();
    const importedUid = String(imported.uid ?? "").trim();
    if (importedUid) {
      checklistCsvImportView.value = false;
      clearCsvUpload();
      // Select the imported CSV as a template option
      syncChecklistTemplateEditorSelection(importedUid, "csv_import");
      toastStore.push("Template imported from CSV", "success");
    }
  } finally {
    checklistCsvImportLoading.value = false;
  }
};
const previewCsvAction = () => {
  if (!csvImportHeaders.value.length || !csvImportRows.value.length) {
    throw new Error("Upload a CSV file before previewing");
  }
  const rows = [csvImportHeaders.value, ...csvImportRows.value];
  const csvContent = rows.map((row) => row.map((cell) => { const value = String(cell ?? ""); if (/[",\r\n]/.test(value)) return `"${value.replace(/"/g, "\"\"")}"`; return value; }).join(",")).join("\n");
  const blob = new Blob([csvContent], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `preview-${csvImportFilename.value || "checklist.csv"}`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};
const normalizeCsvHeaderLabel = (value: string): string => String(value ?? "").trim().toUpperCase().replace(/[^A-Z0-9]/g, " ");
const createTemplateFromUploadedCsvAction = async (templateName: string): Promise<ChecklistRaw> => {
  const headers = [...csvImportHeaders.value];
  const rows = [...csvImportRows.value];
  if (!headers.length || !rows.length) throw new Error("Upload a CSV file before importing");
  const dueAliases = new Set(["DUE", "DUE RELATIVE MINUTES", "DUE MINUTES"]);
  const dueHeaderIndex = headers.findIndex((header) => dueAliases.has(normalizeCsvHeaderLabel(header)));
  const columns: Array<Record<string, unknown>> = [];
  if (dueHeaderIndex < 0) {
    columns.push({ column_name: "Due", display_order: 1, column_type: "RELATIVE_TIME", column_editable: false, is_removable: false, system_key: "DUE_RELATIVE_DTG" });
    headers.forEach((header, index) => columns.push({ column_name: header || `Column ${index + 1}`, display_order: index + 2, column_type: "SHORT_STRING", column_editable: true, is_removable: true }));
  } else {
    headers.forEach((header, index) => {
      if (index === dueHeaderIndex) { columns.push({ column_name: header || "Due", display_order: index + 1, column_type: "RELATIVE_TIME", column_editable: false, is_removable: false, system_key: "DUE_RELATIVE_DTG" }); return; }
      columns.push({ column_name: header || `Column ${index + 1}`, display_order: index + 1, column_type: "SHORT_STRING", column_editable: true, is_removable: true });
    });
  }
  
  // Create checklist with CSV_IMPORT origin (acts as a template with rows)
  const created = await post<ChecklistRaw>(endpoints.checklistsOffline, {
    name: templateName,
    origin_type: "CSV_IMPORT",
    source_identity: DEFAULT_SOURCE_IDENTITY,
    columns
  });
  const createdChecklistUid = String(created.uid ?? "").trim();
  if (!createdChecklistUid) throw new Error("Template creation failed");
  
  // Create tasks from CSV rows
  const createdColumns = toSortedChecklistColumns(toArray<ChecklistColumnRaw>(created.columns));
  const targetByHeaderIndex = new Map<number, string>();
  headers.forEach((_, headerIndex) => {
    if (headerIndex === dueHeaderIndex) return;
    const displayOrder = dueHeaderIndex < 0 ? headerIndex + 2 : headerIndex + 1;
    const columnUid = createdColumns.find((column) => Number(column.display_order ?? 0) === displayOrder)?.column_uid ?? "";
    if (columnUid) targetByHeaderIndex.set(headerIndex, columnUid);
  });
  
  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex];
    const taskNumber = rowIndex + 1;
    const taskPayload: Record<string, unknown> = { number: taskNumber };
    
    // Get first non-due cell value as legacy value
    const rowLegacyValue = headers.map((_, headerIndex) => ({ headerIndex, value: String(row[headerIndex] ?? "").trim() }))
      .find((entry) => entry.value.length > 0 && (dueHeaderIndex < 0 || entry.headerIndex !== dueHeaderIndex))?.value ?? "";
    if (rowLegacyValue) taskPayload.legacy_value = rowLegacyValue;
    
    // Set due minutes if present
    if (dueHeaderIndex >= 0) {
      const dueValue = String(row[dueHeaderIndex] ?? "").trim();
      const dueMinutes = dueValue ? Math.trunc(Number(dueValue)) : undefined;
      if (dueMinutes !== undefined && !Number.isNaN(dueMinutes)) taskPayload.due_relative_minutes = dueMinutes;
    }
    
    // Create task
    const taskCreated = await post<ChecklistRaw>(`${endpoints.checklists}/${createdChecklistUid}/tasks`, taskPayload);
    const createdTaskUid = String(toArray<ChecklistTaskRaw>(taskCreated.tasks).find((task) => Number(task.number ?? 0) === taskNumber)?.task_uid ?? "").trim();
    if (!createdTaskUid) continue;
    
    // Set cell values
    for (const [headerIndex, targetColumnUid] of targetByHeaderIndex.entries()) {
      const value = String(row[headerIndex] ?? "").trim();
      if (!value) continue;
      await patchRequest(`${endpoints.checklists}/${createdChecklistUid}/tasks/${createdTaskUid}/cells/${targetColumnUid}`, {
        value,
        updated_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY
      });
    }
  }
  
  return created;
};
const buildChecklistTemplateDraftName = (): string => `Template ${buildTimestampTag().slice(-6)}`;
const applyChecklistTemplateEditorDraft = (payload: { selectionUid: string; selectionSourceType: ChecklistTemplateSourceType | ""; mode: ChecklistTemplateEditorMode; templateUid: string; templateName: string; description: string; columns: Array<ChecklistColumnRaw | ChecklistTemplateDraftColumn>; ensureTaskColumn?: boolean }) => {
  checklistTemplateEditorHydrating.value = true;
  checklistTemplateEditorSelectionUid.value = payload.selectionUid;
  checklistTemplateEditorSelectionSourceType.value = payload.selectionSourceType;
  checklistTemplateEditorMode.value = payload.mode;
  checklistTemplateDraftTemplateUid.value = payload.templateUid;
  checklistTemplateDraftName.value = payload.templateName.trim() || buildChecklistTemplateDraftName();
  checklistTemplateDraftDescription.value = payload.description;
  checklistTemplateDraftColumns.value = normalizeChecklistTemplateDraftColumns(payload.columns, { ensureTaskColumn: payload.ensureTaskColumn ?? payload.mode !== "csv_readonly" });
  checklistTemplateEditorDirty.value = false;
  checklistTemplateEditorHydrating.value = false;
};
const startNewChecklistTemplateDraft = () => applyChecklistTemplateEditorDraft({ selectionUid: "", selectionSourceType: "", mode: "create", templateUid: "", templateName: buildChecklistTemplateDraftName(), description: "", columns: createBlankChecklistTemplateDraftColumns(), ensureTaskColumn: true });
const selectChecklistTemplateForEditor = (templateUid: string, sourceType: ChecklistTemplateSourceType) => {
  const uid = String(templateUid ?? "").trim();
  if (!uid) return;
  const option = checklistTemplateOptions.value.find((entry) => entry.uid === uid && entry.source_type === sourceType) ?? null;
  if (!option) return;
  checklistTemplateSelectionUid.value = option.uid;
  if (option.source_type === "template") {
    const templateRecord = templateRecords.value.find((entry) => String(entry.uid ?? "").trim() === option.uid) ?? null;
    if (!templateRecord) { toastStore.push("Selected template is unavailable", "warning"); return; }
    applyChecklistTemplateEditorDraft({ selectionUid: option.uid, selectionSourceType: option.source_type, mode: "edit", templateUid: option.uid, templateName: String(templateRecord.template_name ?? option.name), description: String(templateRecord.description ?? ""), columns: toArray<ChecklistColumnRaw>(templateRecord.columns), ensureTaskColumn: true });
    return;
  }
  const checklistRecord = checklistRecords.value.find((entry) => String(entry.uid ?? "").trim() === option.uid) ?? null;
  if (!checklistRecord) { toastStore.push("Selected CSV entry is unavailable", "warning"); return; }
  applyChecklistTemplateEditorDraft({ selectionUid: option.uid, selectionSourceType: option.source_type, mode: "csv_readonly", templateUid: "", templateName: String(checklistRecord.name ?? option.name), description: String(checklistRecord.description ?? ""), columns: toArray<ChecklistColumnRaw>(checklistRecord.columns), ensureTaskColumn: false });
};
const syncChecklistTemplateEditorSelection = (preferredUid = "", preferredType: ChecklistTemplateSourceType | "" = "") => {
  const options = checklistTemplateOptions.value;
  if (!options.length) { startNewChecklistTemplateDraft(); return; }
  const preferred = (preferredUid && preferredType ? options.find((entry) => entry.uid === preferredUid && entry.source_type === preferredType) : null) ?? null;
  if (preferred) { selectChecklistTemplateForEditor(preferred.uid, preferred.source_type); return; }
  const selected = selectedChecklistTemplateEditorOption.value;
  if (selected) { if (checklistTemplateEditorMode.value !== "create") selectChecklistTemplateForEditor(selected.uid, selected.source_type); return; }
  selectChecklistTemplateForEditor(options[0].uid, options[0].source_type);
};
const mutateChecklistTemplateDraftColumns = (mutate: (columns: ChecklistTemplateDraftColumn[]) => ChecklistTemplateDraftColumn[]) => {
  if (isChecklistTemplateDraftReadonly.value || checklistTemplateEditorSaving.value) return;
  const cloned = checklistTemplateDraftColumns.value.map((column) => ({ ...column }));
  const mutated = mutate(cloned);
  checklistTemplateDraftColumns.value = normalizeChecklistTemplateDraftColumns(mutated, { ensureTaskColumn: true });
};
const setChecklistTemplateColumnName = (columnIndex: number, event: Event) => {
  const value = String((event.target as HTMLInputElement | null)?.value ?? "");
  mutateChecklistTemplateDraftColumns((columns) => columns.map((column, index) => index === columnIndex && !isChecklistTemplateDueColumn(column) ? { ...column, column_name: value.trim() || column.column_name } : column));
};
const setChecklistTemplateColumnType = (columnIndex: number, event: Event) => {
  const value = String((event.target as HTMLSelectElement | null)?.value ?? "");
  mutateChecklistTemplateDraftColumns((columns) => columns.map((column, index) => index === columnIndex && !isChecklistTemplateDueColumn(column) ? { ...column, column_type: normalizeChecklistTemplateColumnType(value) } : column));
};
const setChecklistTemplateColumnEditable = (columnIndex: number, event: Event) => {
  const checked = Boolean((event.target as HTMLInputElement | null)?.checked);
  mutateChecklistTemplateDraftColumns((columns) => columns.map((column, index) => index === columnIndex && !isChecklistTemplateDueColumn(column) ? { ...column, column_editable: checked } : column));
};
const setChecklistTemplateColumnBackgroundColor = (columnIndex: number, event: Event) => {
  const value = String((event.target as HTMLInputElement | null)?.value ?? "");
  mutateChecklistTemplateDraftColumns((columns) => columns.map((column, index) => index === columnIndex ? { ...column, background_color: normalizeChecklistTemplateColor(value) } : column));
};
const setChecklistTemplateColumnTextColor = (columnIndex: number, event: Event) => {
  const value = String((event.target as HTMLInputElement | null)?.value ?? "");
  mutateChecklistTemplateDraftColumns((columns) => columns.map((column, index) => index === columnIndex ? { ...column, text_color: normalizeChecklistTemplateColor(value) } : column));
};
const addChecklistTemplateColumn = () => mutateChecklistTemplateDraftColumns((columns) => { const customCount = columns.filter((column) => !isChecklistTemplateDueColumn(column)).length; return [...columns, { column_uid: buildChecklistTemplateColumnUid(), column_name: `Field ${customCount + 1}`, display_order: columns.length + 1, column_type: "SHORT_STRING", column_editable: true, is_removable: true, system_key: null, background_color: null, text_color: null }]; });
const canMoveChecklistTemplateColumnUp = (columnIndex: number): boolean => {
  if (isChecklistTemplateDraftReadonly.value || checklistTemplateEditorSaving.value) return false;
  const column = checklistTemplateDraftColumns.value[columnIndex];
  if (!column || isChecklistTemplateDueColumn(column)) return false;
  return columnIndex > 1;
};
const canMoveChecklistTemplateColumnDown = (columnIndex: number): boolean => {
  if (isChecklistTemplateDraftReadonly.value || checklistTemplateEditorSaving.value) return false;
  const columns = checklistTemplateDraftColumns.value;
  const column = columns[columnIndex];
  if (!column || isChecklistTemplateDueColumn(column)) return false;
  return columnIndex >= 1 && columnIndex < columns.length - 1;
};
const moveChecklistTemplateColumnUp = (columnIndex: number) => {
  if (!canMoveChecklistTemplateColumnUp(columnIndex)) return;
  mutateChecklistTemplateDraftColumns((columns) => { const next = [...columns]; [next[columnIndex - 1], next[columnIndex]] = [next[columnIndex], next[columnIndex - 1]]; return next; });
};
const moveChecklistTemplateColumnDown = (columnIndex: number) => {
  if (!canMoveChecklistTemplateColumnDown(columnIndex)) return;
  mutateChecklistTemplateDraftColumns((columns) => { const next = [...columns]; [next[columnIndex + 1], next[columnIndex]] = [next[columnIndex], next[columnIndex + 1]]; return next; });
};
const canDeleteChecklistTemplateColumn = (columnIndex: number): boolean => {
  if (isChecklistTemplateDraftReadonly.value || checklistTemplateEditorSaving.value) return false;
  const column = checklistTemplateDraftColumns.value[columnIndex];
  if (!column || isChecklistTemplateDueColumn(column)) return false;
  return Boolean(column.is_removable);
};
const deleteChecklistTemplateColumn = (columnIndex: number) => { if (!canDeleteChecklistTemplateColumn(columnIndex)) return; mutateChecklistTemplateDraftColumns((columns) => columns.filter((_, index) => index !== columnIndex)); };
const buildChecklistTemplateDraftPayload = () => {
  const templateName = checklistTemplateDraftName.value.trim();
  const validationError = validateChecklistTemplateDraftPayload(templateName, checklistTemplateDraftColumns.value);
  if (validationError) throw new Error(validationError);
  return { template_name: templateName, description: checklistTemplateDraftDescription.value.trim(), columns: toChecklistTemplateColumnPayload(checklistTemplateDraftColumns.value) };
};
const saveChecklistTemplateDraft = async () => {
  if (!canSaveChecklistTemplateDraft.value) return;
  const templateUid = checklistTemplateDraftTemplateUid.value.trim();
  if (!templateUid) return;
  checklistTemplateEditorSaving.value = true;
  try {
    const payload = buildChecklistTemplateDraftPayload();
    await patchRequest(`${endpoints.checklistTemplates}/${templateUid}`, { patch: payload });
    await loadWorkspace();
    syncChecklistTemplateEditorSelection(templateUid, "template");
    toastStore.push("Template saved", "success");
  } catch (error) { handleApiError(error, "Unable to save template"); } finally { checklistTemplateEditorSaving.value = false; }
};
const saveChecklistTemplateDraftAsNew = async () => {
  if (!canSaveChecklistTemplateDraftAsNew.value) return;
  checklistTemplateEditorSaving.value = true;
  try {
    const payload = buildChecklistTemplateDraftPayload();
    const created = await post<TemplateRaw>(endpoints.checklistTemplates, { template: { ...payload, created_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY } });
    await loadWorkspace();
    const createdUid = String(created.uid ?? "").trim();
    if (createdUid) syncChecklistTemplateEditorSelection(createdUid, "template"); else syncChecklistTemplateEditorSelection();
    toastStore.push("Template created", "success");
  } catch (error) { handleApiError(error, "Unable to create template"); } finally { checklistTemplateEditorSaving.value = false; }
};
const cloneChecklistTemplateDraft = async () => {
  if (!canCloneChecklistTemplateDraft.value) return;
  const templateUid = checklistTemplateDraftTemplateUid.value.trim();
  if (!templateUid) return;
  checklistTemplateEditorSaving.value = true;
  try {
    const baseName = checklistTemplateDraftName.value.trim() || "Template";
    const cloned = await post<TemplateRaw>(`${endpoints.checklistTemplates}/${templateUid}/clone`, { template_name: `${baseName} Copy ${buildTimestampTag().slice(-4)}`, description: checklistTemplateDraftDescription.value.trim(), created_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY });
    await loadWorkspace();
    const clonedUid = String(cloned.uid ?? "").trim();
    if (clonedUid) syncChecklistTemplateEditorSelection(clonedUid, "template"); else syncChecklistTemplateEditorSelection();
    toastStore.push("Template cloned", "success");
  } catch (error) { handleApiError(error, "Unable to clone template"); } finally { checklistTemplateEditorSaving.value = false; }
};
const archiveChecklistTemplateDraft = async () => {
  if (!canArchiveChecklistTemplateDraft.value) return;
  const templateUid = checklistTemplateDraftTemplateUid.value.trim();
  if (!templateUid) return;
  const templateName = checklistTemplateDraftName.value.trim() || "Template";
  if (/\[ARCHIVED\]/i.test(templateName)) { toastStore.push("Template already archived", "info"); return; }
  checklistTemplateEditorSaving.value = true;
  try {
    await patchRequest(`${endpoints.checklistTemplates}/${templateUid}`, { patch: { template_name: `${templateName} [ARCHIVED]` } });
    await loadWorkspace();
    syncChecklistTemplateEditorSelection(templateUid, "template");
    toastStore.push("Template archived", "success");
  } catch (error) { handleApiError(error, "Unable to archive template"); } finally { checklistTemplateEditorSaving.value = false; }
};
const convertChecklistTemplateDraftToServerTemplate = async () => {
  if (!canConvertChecklistTemplateDraft.value) return;
  checklistTemplateEditorSaving.value = true;
  try {
    const payload = buildChecklistTemplateDraftPayload();
    const created = await post<TemplateRaw>(endpoints.checklistTemplates, { template: { ...payload, created_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY } });
    await loadWorkspace();
    const createdUid = String(created.uid ?? "").trim();
    if (createdUid) syncChecklistTemplateEditorSelection(createdUid, "template"); else syncChecklistTemplateEditorSelection();
    toastStore.push("CSV template converted", "success");
  } catch (error) { handleApiError(error, "Unable to convert CSV template"); } finally { checklistTemplateEditorSaving.value = false; }
};
const isChecklistTemplateDeleteBusy = (templateUid: string): boolean => {
  const uid = String(templateUid ?? "").trim();
  if (!uid) return false;
  return Boolean(checklistTemplateDeleteBusyByUid.value[uid]);
};
const deleteChecklistTemplateFromCard = async (templateUid: string, sourceType: ChecklistTemplateOption["source_type"], templateName: string): Promise<boolean> => {
  const uid = String(templateUid ?? "").trim();
  if (!uid || isChecklistTemplateDeleteBusy(uid)) return false;
  const name = String(templateName ?? uid).trim() || uid;
  const targetLabel = sourceType === "template" ? "template" : "CSV import template";
  if (!window.confirm(`Delete ${targetLabel} "${name}"?`)) return false;
  checklistTemplateDeleteBusyByUid.value = { ...checklistTemplateDeleteBusyByUid.value, [uid]: true };
  try {
    if (sourceType === "template") await deleteRequest(`${endpoints.checklistTemplates}/${uid}`); else await deleteRequest(`${endpoints.checklists}/${uid}`);
    if (checklistTemplateSelectionUid.value === uid) checklistTemplateSelectionUid.value = "";
    await loadWorkspace();
    toastStore.push(sourceType === "template" ? "Template deleted" : "CSV import template deleted", "success");
    return true;
  } catch (error) { handleApiError(error, sourceType === "template" ? "Unable to delete template" : "Unable to delete CSV import template"); return false; } finally { const next = { ...checklistTemplateDeleteBusyByUid.value }; delete next[uid]; checklistTemplateDeleteBusyByUid.value = next; }
};
const deleteChecklistTemplateDraft = async () => {
  if (!canDeleteChecklistTemplateDraft.value) return;
  const selected = selectedChecklistTemplateEditorOption.value;
  if (!selected) return;
  const removed = await deleteChecklistTemplateFromCard(selected.uid, selected.source_type, selected.name);
  if (!removed) return;
  syncChecklistTemplateEditorSelection();
};
const deleteChecklistFromDetail = async () => {
  if (checklistDeleteBusy.value) return;
  const checklistUid = String(checklistDetailRecord.value?.uid ?? "").trim();
  if (!checklistUid) { toastStore.push("Select a checklist first", "warning"); return; }
  const checklistName = String(checklistDetailRecord.value?.name ?? checklistUid).trim() || checklistUid;
  if (!window.confirm(`Delete checklist "${checklistName}"?`)) return;
  checklistDeleteBusy.value = true;
  try {
    await deleteRequest(`${endpoints.checklists}/${checklistUid}`);
    checklistDetailUid.value = "";
    checklistLinkMissionModalOpen.value = false;
    await loadWorkspace();
    toastStore.push("Checklist removed", "success");
  } catch (error) { handleApiError(error, "Unable to remove checklist"); } finally { checklistDeleteBusy.value = false; }
};
const submitChecklistMissionLink = async () => {
  if (checklistLinkMissionSubmitting.value) return;
  const checklistUid = String(checklistDetailRecord.value?.uid ?? "").trim();
  if (!checklistUid) { toastStore.push("Select a checklist first", "warning"); return; }
  if (!canSubmitChecklistMissionLink.value) { checklistLinkMissionModalOpen.value = false; return; }
  checklistLinkMissionSubmitting.value = true;
  const missionUid = checklistLinkMissionSelectionUid.value.trim();
  try {
    await patchRequest(`${endpoints.checklists}/${checklistUid}`, { patch: { mission_uid: missionUid || null } });
    await loadWorkspace();
    checklistDetailUid.value = checklistUid;
    try { await hydrateChecklistRecord(checklistUid); } catch (error) { handleApiError(error, "Checklist mission link saved but detail refresh failed"); }
    checklistLinkMissionModalOpen.value = false;
    toastStore.push(missionUid ? "Checklist linked to mission" : "Checklist mission link cleared", "success");
  } catch (error) { handleApiError(error, "Unable to link checklist to mission"); } finally { checklistLinkMissionSubmitting.value = false; }
};
const addChecklistTaskFromDetail = async () => {
  const checklist = checklistDetailRecord.value;
  if (!checklist?.uid) { toastStore.push("Select a checklist first", "warning"); return; }
  try {
    const nextNumber = checklistDetailRows.value.reduce((max, row) => Math.max(max, row.number), 0) + 1;
    const payload: Record<string, unknown> = { number: nextNumber };
    const parsedDue = Number(checklistTaskDueDraft.value);
    if (Number.isFinite(parsedDue)) payload.due_relative_minutes = Math.trunc(parsedDue);
    await post(`${endpoints.checklists}/${checklist.uid}/tasks`, payload);
    await loadWorkspace();
    toastStore.push("Checklist task added", "success");
  } catch (error) { handleApiError(error, "Unable to add checklist task"); }
};
const toggleChecklistTaskDone = async (row: { task_uid: string; done: boolean }) => {
  const checklist = checklistDetailRaw.value;
  const checklistUid = String(checklist?.uid ?? "").trim();
  const taskUid = String(row.task_uid ?? "").trim();
  if (!checklistUid || !taskUid) { toastStore.push("Unable to update task status", "warning"); return; }
  if (checklistTaskStatusBusyByTaskUid.value[taskUid]) return;
  checklistTaskStatusBusyByTaskUid.value = { ...checklistTaskStatusBusyByTaskUid.value, [taskUid]: true };
  try {
    const userStatus = row.done ? "PENDING" : "COMPLETE";
    await post(`${endpoints.checklists}/${checklistUid}/tasks/${taskUid}/status`, { user_status: userStatus, changed_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY });
    await loadWorkspace();
    toastStore.push("Task status updated", "success");
  } catch (error) { handleApiError(error, "Unable to update task status"); } finally { const next = { ...checklistTaskStatusBusyByTaskUid.value }; delete next[taskUid]; checklistTaskStatusBusyByTaskUid.value = next; }
};
const buildChecklistDraftName = (): string => `Checklist ${new Date().toISOString().slice(11, 19).replace(/:/g, "")}`;
const openChecklistTemplateModal = () => {
  checklistTemplateNameDraft.value = buildChecklistDraftName();
  if (!checklistTemplateOptions.value.length) {
    checklistTemplateSelectionUid.value = "";
    checklistTemplateModalOpen.value = true;
    return;
  }
  if (!checklistTemplateOptions.value.some((entry) => entry.uid === checklistTemplateSelectionUid.value)) checklistTemplateSelectionUid.value = checklistTemplateOptions.value[0].uid;
  checklistTemplateModalOpen.value = true;
};
const closeChecklistTemplateModal = () => { if (checklistTemplateSubmitting.value) return; checklistTemplateModalOpen.value = false; };
const createChecklistFromSelectedTemplateAction = async () => {
  const selectionUid = checklistTemplateSelectionUid.value.trim();
  if (!selectionUid) throw new Error("Select a checklist template");
  const selectedTemplate = checklistTemplateOptions.value.find((entry) => entry.uid === selectionUid);
  if (!selectedTemplate) throw new Error("Selected checklist template could not be found");
  const missionUid = checklistDetailRecord.value?.mission_uid || undefined;
  const checklistName = checklistTemplateNameDraft.value.trim() || buildChecklistDraftName();
  const created = selectedTemplate.source_type === "template" ? await post<ChecklistRaw>(endpoints.checklists, { template_uid: selectionUid, mission_uid: missionUid, name: checklistName, source_identity: DEFAULT_SOURCE_IDENTITY }) : await createChecklistFromCsvImportAction(selectionUid, checklistName, missionUid);
  await loadWorkspace();
  const createdUid = String(created.uid ?? "").trim();
  if (createdUid) { checklistDetailUid.value = createdUid; checklistWorkspaceView.value = "active"; try { await hydrateChecklistRecord(createdUid); } catch (error) { handleApiError(error, "Checklist run created but detail refresh failed"); } }
};
const submitChecklistTemplateSelection = async () => {
  if (checklistTemplateSubmitting.value) return;
  checklistTemplateSubmitting.value = true;
  try { await createChecklistFromSelectedTemplateAction(); checklistTemplateModalOpen.value = false; toastStore.push("Checklist run created", "success"); } catch (error) { handleApiError(error, "Unable to create checklist run"); } finally { checklistTemplateSubmitting.value = false; }
};
const toSortedChecklistColumns = (columns: ChecklistColumnRaw[]): ChecklistColumnRaw[] => [...columns].sort((left, right) => Number(left.display_order ?? 0) - Number(right.display_order ?? 0));
const findDueColumnUid = (columns: ChecklistColumnRaw[]): string => toSortedChecklistColumns(columns).find((column) => String(column.system_key ?? "").trim().toUpperCase() === "DUE_RELATIVE_DTG")?.column_uid?.trim() || "";
const parseDueRelativeMinutes = (task: ChecklistTaskRaw, sourceDueColumnUid: string): number | undefined => {
  if (task.due_relative_minutes !== null && task.due_relative_minutes !== undefined) { const dueRelative = Number(task.due_relative_minutes); if (!Number.isNaN(dueRelative) && Number.isFinite(dueRelative)) return Math.trunc(dueRelative); }
  if (!sourceDueColumnUid) return undefined;
  const dueCell = toArray<ChecklistCellRaw>(task.cells).find((cell) => String(cell.column_uid ?? "").trim() === sourceDueColumnUid);
  const parsed = Number(String(dueCell?.value ?? "").trim());
  if (Number.isNaN(parsed) || !Number.isFinite(parsed)) return undefined;
  return Math.trunc(parsed);
};
const createChecklistFromCsvImportAction = async (sourceChecklistUid: string, checklistName: string, missionUid?: string): Promise<ChecklistRaw> => {
  let sourceChecklist = checklistRecords.value.find((entry) => String(entry.uid ?? "").trim() === sourceChecklistUid);
  try { const hydrated = await hydrateChecklistRecord(sourceChecklistUid); if (hydrated) sourceChecklist = hydrated; } catch (error) { if (!sourceChecklist) throw error; }
  if (!sourceChecklist) throw new Error("Selected CSV template could not be found");
  const sourceColumns = toSortedChecklistColumns(toArray<ChecklistColumnRaw>(sourceChecklist.columns));
  if (!sourceColumns.length) throw new Error("Selected CSV template has no columns");
  const created = await post<ChecklistRaw>(endpoints.checklistsOffline, { mission_uid: missionUid, name: checklistName, origin_type: "RCH_TEMPLATE", source_identity: DEFAULT_SOURCE_IDENTITY, columns: toChecklistTemplateColumnPayload(sourceColumns) });
  const createdChecklistUid = String(created.uid ?? "").trim();
  if (!createdChecklistUid) throw new Error("Checklist creation failed");
  const createdColumns = toSortedChecklistColumns(toArray<ChecklistColumnRaw>(created.columns));
  const sourceColumnUidByOrder = new Map<number, string>();
  sourceColumns.forEach((column, index) => { const columnUid = String(column.column_uid ?? "").trim(); if (columnUid) sourceColumnUidByOrder.set(index + 1, columnUid); });
  const targetColumnUidByOrder = new Map<number, string>();
  createdColumns.forEach((column, index) => { const columnUid = String(column.column_uid ?? "").trim(); if (columnUid) targetColumnUidByOrder.set(index + 1, columnUid); });
  const sourceToTargetColumnUid = new Map<string, string>();
  sourceColumnUidByOrder.forEach((sourceColumnUid, order) => { const targetColumnUid = targetColumnUidByOrder.get(order); if (targetColumnUid) sourceToTargetColumnUid.set(sourceColumnUid, targetColumnUid); });
  const sourceDueColumnUid = findDueColumnUid(sourceColumns);
  const sourceTasks = [...toArray<ChecklistTaskRaw>(sourceChecklist.tasks)].sort((left, right) => Number(left.number ?? 0) - Number(right.number ?? 0));
  for (let index = 0; index < sourceTasks.length; index += 1) {
    const sourceTask = sourceTasks[index];
    const taskNumber = index + 1;
    const dueRelativeMinutes = parseDueRelativeMinutes(sourceTask, sourceDueColumnUid);
    const taskPayload: Record<string, unknown> = { number: taskNumber };
    const legacyValue = String(sourceTask.legacy_value ?? "").trim() || resolveChecklistTaskName(sourceChecklist, sourceTask);
    if (legacyValue) taskPayload.legacy_value = legacyValue;
    if (dueRelativeMinutes !== undefined) taskPayload.due_relative_minutes = dueRelativeMinutes;
    const taskCreated = await post<ChecklistRaw>(`${endpoints.checklists}/${createdChecklistUid}/tasks`, taskPayload);
    const createdTaskUid = String(toArray<ChecklistTaskRaw>(taskCreated.tasks).find((task) => Number(task.number ?? 0) === taskNumber)?.task_uid ?? "").trim();
    if (!createdTaskUid) continue;
    const sourceCells = toArray<ChecklistCellRaw>(sourceTask.cells);
    for (const sourceCell of sourceCells) {
      const sourceColumnUid = String(sourceCell.column_uid ?? "").trim();
      const targetColumnUid = sourceToTargetColumnUid.get(sourceColumnUid);
      const value = String(sourceCell.value ?? "").trim();
      if (!sourceColumnUid || !targetColumnUid || !value) continue;
      if (sourceColumnUid === sourceDueColumnUid) continue;
      await patchRequest(`${endpoints.checklists}/${createdChecklistUid}/tasks/${createdTaskUid}/cells/${targetColumnUid}`, { value, updated_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY });
    }
  }
  const hydrated = await hydrateChecklistRecord(createdChecklistUid);
  return hydrated ?? created;
};

// Data loading
const loadWorkspace = async () => {
  try {
    const [missionData, checklistPayload, templatePayload] = await Promise.all([
      get<MissionRaw[]>(endpoints.r3aktMissions),
      get<{ checklists?: ChecklistRaw[] }>(endpoints.checklists),
      get<{ templates?: TemplateRaw[] }>(endpoints.checklistTemplates)
    ]);
    missions.value = toArray<MissionRaw>(missionData).map((entry) => { const uid = String(entry.uid ?? "").trim(); if (!uid) return null; return { uid, mission_name: String(entry.mission_name ?? uid) }; }).filter((entry): entry is Mission => entry !== null);
    checklistRecords.value = toArray<ChecklistRaw>(checklistPayload.checklists);
    templateRecords.value = toArray<TemplateRaw>(templatePayload.templates);
    const activeDetailUid = String(checklistDetailUid.value ?? "").trim();
    if (activeDetailUid) { try { await hydrateChecklistRecord(activeDetailUid); } catch (error) { handleApiError(error, "Checklist detail refresh failed"); } }
  } catch (error) { handleApiError(error, "Unable to load checklist workspace"); }
};

// Watchers
watch([checklistTemplateDraftName, checklistTemplateDraftDescription, checklistTemplateDraftColumns], () => { if (checklistTemplateEditorHydrating.value || checklistTemplateEditorMode.value === "csv_readonly") return; checklistTemplateEditorDirty.value = true; }, { deep: true });
watch(checklistTemplateOptions, (entries) => {
  if (checklistTemplateSelectionUid.value && !entries.some((entry) => entry.uid === checklistTemplateSelectionUid.value)) checklistTemplateSelectionUid.value = entries[0]?.uid ?? "";
  const selected = selectedChecklistTemplateEditorOption.value;
  if (selected) return;
  if (!entries.length) { if (checklistWorkspaceView.value === "templates") startNewChecklistTemplateDraft(); return; }
  if (checklistTemplateEditorMode.value === "create") return;
  const first = entries[0]; selectChecklistTemplateForEditor(first.uid, first.source_type);
}, { immediate: true });
watch(checklistWorkspaceView, (view) => { if (view !== "templates") return; if (checklistTemplateOptions.value.length) syncChecklistTemplateEditorSelection(); else startNewChecklistTemplateDraft(); }, { immediate: true });
watch(checklists, (entries) => { if (checklistDetailUid.value && !entries.some((entry) => entry.uid === checklistDetailUid.value)) checklistDetailUid.value = ""; }, { immediate: true });

onMounted(() => { loadWorkspace().catch((error) => { handleApiError(error, "Unable to load checklist workspace"); }); });
</script>

<style scoped src="./styles/ChecklistsPage.css"></style>




