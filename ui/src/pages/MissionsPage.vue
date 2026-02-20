<template>
  <div class="missions-workspace">
    <div class="registry-shell">
      <header class="registry-top">
        <div class="registry-title">Mission Workspace</div>
        <div class="registry-status">
          <OnlineHelpLauncher />
          <span class="cui-status-pill" :class="connectionClass">{{ connectionLabel }}</span>
          <span class="cui-status-pill" :class="wsClass">{{ wsLabel }}</span>
          <span class="status-url">{{ baseUrl }}</span>
        </div>
      </header>

      <section class="mission-kpis">
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

      <div class="registry-grid">
        <aside class="panel registry-tree">
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
              @click="selectedMissionUid = mission.uid"
            >
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">{{ mission.mission_name }}</span>
              <span class="tree-count">{{ mission.status }}</span>
            </button>
          </div>
        </aside>

        <section class="panel registry-main">
          <div class="panel-header">
            <div>
              <div class="panel-title">{{ selectedMission?.mission_name || "Mission Details" }}</div>
              <div class="panel-subtitle">{{ selectedMission?.topic || "Select a mission" }}</div>
            </div>
            <div class="panel-tabs">
              <button
                v-for="tab in primaryTabs"
                :key="tab.id"
                class="panel-tab"
                :class="{ active: primaryTab === tab.id }"
                type="button"
                @click="setPrimaryTab(tab.id)"
              >
                {{ tab.label }}
              </button>
            </div>
          </div>

          <div class="screen-tabs">
            <button
              v-for="screen in activeScreens"
              :key="screen.id"
              class="screen-tab"
              :class="{ active: secondaryScreen === screen.id }"
              type="button"
              @click="secondaryScreen = screen.id"
            >
              {{ screen.label }}
            </button>
          </div>

          <article class="screen-shell">
            <header class="screen-header">
              <h3>{{ currentScreen.title }}</h3>
              <p>{{ currentScreen.subtitle }}</p>
              <div class="screen-actions">
                <BaseButton
                  v-for="action in currentScreen.actions"
                  :key="`${secondaryScreen}-${action}`"
                  variant="secondary"
                  size="sm"
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

            <div v-else-if="secondaryScreen === 'missionCreateEdit'" class="screen-grid two-col">
              <article class="stage-card">
                <h4>Mission Create / Edit</h4>
                <div class="field-grid">
                  <label class="field-control">
                    <span>Name</span>
                    <input v-model="missionDraftName" type="text" placeholder="Mission Name" />
                  </label>
                  <label class="field-control">
                    <span>Topic Scope</span>
                    <input v-model="missionDraftTopic" type="text" placeholder="mission.region.operation" />
                  </label>
                  <label class="field-control">
                    <span>Status</span>
                    <select v-model="missionDraftStatus">
                      <option v-for="status in missionStatusOptions" :key="status" :value="status">
                        {{ status }}
                      </option>
                    </select>
                  </label>
                  <label class="field-control full">
                    <span>Description</span>
                    <textarea
                      v-model="missionDraftDescription"
                      rows="4"
                      placeholder="Mission objective and constraints..."
                    ></textarea>
                  </label>
                </div>
              </article>

              <article class="stage-card">
                <h4>Draft Preview</h4>
                <ul class="stack-list">
                  <li><strong>Name</strong><span>{{ missionDraftName || "Mission Name" }}</span></li>
                  <li><strong>Topic</strong><span>{{ missionDraftTopic || "mission.unassigned" }}</span></li>
                  <li><strong>Status</strong><span>{{ missionDraftStatus }}</span></li>
                  <li><strong>Description</strong><span>{{ missionDraftDescription || "-" }}</span></li>
                </ul>
              </article>
            </div>

            <div v-else-if="secondaryScreen === 'missionAudit'" class="screen-grid two-col">
              <article class="stage-card">
                <h4>Mission Activity / Audit</h4>
                <ul class="stack-list timeline">
                  <li v-for="event in missionAudit" :key="event.uid">
                    <strong>{{ event.time }}</strong>
                    <span>{{ event.message }}</span>
                  </li>
                </ul>
              </article>

              <article class="stage-card">
                <h4>Mission Change Feed</h4>
                <table class="mini-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Type</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="change in missionChangesForSelected" :key="`change-${change.uid}`">
                      <td>{{ formatAuditTime(change.timestamp) }}</td>
                      <td>{{ change.change_type || "change" }}</td>
                      <td>{{ change.notes || change.name || "-" }}</td>
                    </tr>
                  </tbody>
                </table>
              </article>
            </div>

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

            <div v-else-if="showChecklistArea" class="screen-grid two-col">
              <article class="stage-card">
                <h4>{{ checklistPanelTitle }}</h4>
                <div class="checklist-list">
                  <button
                    v-for="checklist in missionChecklists"
                    :key="checklist.uid"
                    class="checklist-item"
                    :class="{ active: checklist.uid === selectedChecklistUid }"
                    type="button"
                    @click="selectedChecklistUid = checklist.uid"
                  >
                    <span>{{ checklist.name }}</span>
                    <span>{{ checklist.progress }}%</span>
                  </button>
                </div>
              </article>

              <article class="stage-card">
                <h4>Checklist Run Detail</h4>
                <table class="mini-table">
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Status</th>
                      <th>Assignee</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="task in selectedChecklist?.tasks || []" :key="task.id">
                      <td>{{ task.name }}</td>
                      <td>{{ task.status }}</td>
                      <td>{{ task.assignee }}</td>
                    </tr>
                  </tbody>
                </table>
              </article>
            </div>

            <div v-else-if="secondaryScreen === 'missionTeamMembers'" class="screen-grid two-col">
              <article class="stage-card">
                <h4>Teams</h4>
                <ul class="stack-list">
                  <li v-for="team in missionTeams" :key="team.uid">
                    <strong>{{ team.name }}</strong>
                    <span>{{ team.description }}</span>
                  </li>
                </ul>
              </article>

              <article class="stage-card">
                <h4>Members &amp; Capabilities</h4>
                <ul class="stack-list">
                  <li v-for="member in missionMembers" :key="member.uid">
                    <strong>{{ member.callsign }}</strong>
                    <span>{{ member.role }}</span>
                    <div class="cap-list">
                      <span v-for="cap in member.capabilities" :key="`${member.uid}-${cap}`" class="cap-chip">{{ cap }}</span>
                    </div>
                  </li>
                </ul>
              </article>
            </div>

            <div v-else-if="showAssetArea" class="screen-grid two-col">
              <article class="stage-card">
                <h4>Asset Registry</h4>
                <table class="mini-table">
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Type</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="asset in missionAssets" :key="asset.uid">
                      <td>{{ asset.name }}</td>
                      <td>{{ asset.type }}</td>
                      <td>{{ asset.status }}</td>
                    </tr>
                  </tbody>
                </table>
              </article>

              <article class="stage-card">
                <h4>Task Assignment Workspace</h4>
                <table class="mini-table">
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Member</th>
                      <th>Assets</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="assignment in missionAssignments" :key="assignment.uid">
                      <td>{{ assignment.task }}</td>
                      <td>{{ assignment.member }}</td>
                      <td>{{ assignment.assets.join(", ") }}</td>
                    </tr>
                  </tbody>
                </table>
              </article>
            </div>

            <div v-else-if="secondaryScreen === 'assignZones'" class="screen-grid two-col">
              <article class="stage-card">
                <h4>Assign Zones to Mission</h4>
                <ul class="stack-list">
                  <li v-for="zone in zones" :key="zone.uid">
                    <label class="zone-toggle">
                      <input type="checkbox" :checked="zone.assigned" @change="toggleZone(zone.uid)" />
                      <span>{{ zone.name }}</span>
                    </label>
                  </li>
                </ul>
              </article>

              <article class="stage-card">
                <h4>Mission Activity / Audit</h4>
                <ul class="stack-list timeline">
                  <li v-for="event in missionAudit" :key="event.uid">
                    <strong>{{ event.time }}</strong>
                    <span>{{ event.message }}</span>
                  </li>
                </ul>
              </article>
            </div>

            <div v-else-if="showTemplateArea" class="screen-grid two-col">
              <article class="stage-card">
                <h4>Excheck Template Library</h4>
                <ul class="stack-list">
                  <li v-for="template in templates" :key="template.uid">
                    <strong>{{ template.name }}</strong>
                    <span>{{ template.columns }} columns</span>
                  </li>
                </ul>
              </article>

              <article class="stage-card">
                <h4>Excheck Template Builder</h4>
                <div class="builder-preview">
                  <p>System Column: <strong>DUE_RELATIVE_DTG</strong></p>
                  <p>Custom Columns: Task, Callsign, Location, Codeword, Notes</p>
                  <BaseButton size="sm" @click="previewAction('Save Template')">Save Template</BaseButton>
                </div>
              </article>
            </div>

            <div v-else class="screen-grid two-col">
              <article class="stage-card">
                <h4>Mission Overview</h4>
                <ul class="stack-list">
                  <li><strong>Mission ID</strong><span>{{ selectedMission?.uid }}</span></li>
                  <li><strong>Status</strong><span>{{ selectedMission?.status }}</span></li>
                  <li><strong>Checklist Runs</strong><span>{{ missionChecklists.length }}</span></li>
                  <li><strong>Open Tasks</strong><span>{{ boardCounts.pending + boardCounts.late }}</span></li>
                </ul>
              </article>

              <article class="stage-card">
                <h4>Mission Excheck Board</h4>
                <div class="board-preview">
                  <div class="board-col">
                    <h5>Pending</h5>
                    <span>{{ boardCounts.pending }}</span>
                  </div>
                  <div class="board-col">
                    <h5>Late</h5>
                    <span>{{ boardCounts.late }}</span>
                  </div>
                  <div class="board-col">
                    <h5>Complete</h5>
                    <span>{{ boardCounts.complete }}</span>
                  </div>
                </div>
              </article>
            </div>
          </article>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type { ApiError } from "../api/client";
import { get, patch as patchRequest, post } from "../api/client";
import { endpoints } from "../api/endpoints";
import BaseButton from "../components/BaseButton.vue";
import OnlineHelpLauncher from "../components/OnlineHelpLauncher.vue";
import { useConnectionStore } from "../stores/connection";
import { useToastStore } from "../stores/toasts";

type PrimaryTab = "mission" | "checklists" | "templates" | "board";

type ScreenId =
  | "missionDirectory"
  | "missionCreateEdit"
  | "missionOverview"
  | "missionTeamMembers"
  | "assignAssets"
  | "assignZones"
  | "missionAudit"
  | "assetRegistry"
  | "checklistOverview"
  | "checklistDetails"
  | "checklistCreation"
  | "checklistRunDetail"
  | "taskAssignmentWorkspace"
  | "checklistImportCsv"
  | "checklistPublish"
  | "checklistProgress"
  | "templateLibrary"
  | "templateBuilder"
  | "missionExcheckBoard";

interface Mission {
  uid: string;
  mission_name: string;
  description: string;
  topic: string;
  status: string;
}

interface Checklist {
  uid: string;
  mission_uid: string;
  name: string;
  progress: number;
  tasks: Array<{ id: string; name: string; status: string; assignee: string }>;
}

interface Team {
  uid: string;
  mission_uid: string;
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
  time: string;
  message: string;
}

interface Template {
  uid: string;
  name: string;
  columns: number;
}

interface MissionRaw {
  uid?: string;
  mission_name?: string | null;
  description?: string | null;
  topic_id?: string | null;
  mission_status?: string | null;
}

interface ChecklistCellRaw {
  column_uid?: string | null;
  value?: string | null;
}

interface ChecklistTaskRaw {
  task_uid?: string;
  number?: number;
  user_status?: string | null;
  task_status?: string | null;
  completed_by_team_member_rns_identity?: string | null;
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
  progress_percent?: number | null;
  checklist_status?: string | null;
  mode?: string | null;
  sync_state?: string | null;
  tasks?: ChecklistTaskRaw[];
  columns?: ChecklistColumnRaw[];
}

interface TeamRaw {
  uid?: string;
  mission_uid?: string | null;
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

interface ZoneRaw {
  zone_id?: string;
  name?: string;
}

interface TemplateRaw {
  uid?: string;
  template_name?: string | null;
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

const connectionStore = useConnectionStore();
const toastStore = useToastStore();

const DEFAULT_SOURCE_IDENTITY = "ui.operator";

const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

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

const normalizeMissionStatus = (value?: string | null): string => {
  const text = String(value ?? "").trim().toUpperCase();
  if (!text) {
    return "UNKNOWN";
  }
  if (text.startsWith("MISSION_")) {
    return text.slice("MISSION_".length);
  }
  return text;
};

const toMissionStatusValue = (value?: string | null): string => {
  const text = String(value ?? "").trim().toUpperCase();
  if (!text) {
    return "MISSION_ACTIVE";
  }
  if (text.startsWith("MISSION_")) {
    return text;
  }
  return `MISSION_${text}`;
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
  if (typeof task.number === "number") {
    return `Task ${task.number}`;
  }
  const taskUid = String(task.task_uid ?? "").trim();
  if (taskUid) {
    return `Task ${taskUid.slice(0, 8)}`;
  }
  return "Task";
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

const formatDomainEventMessage = (event: DomainEventRaw): string => {
  const eventType = String(event.event_type ?? "domain.event").trim();
  const payload = asRecord(event.payload);
  const name = payload.name;
  if (typeof name === "string" && name.trim()) {
    return `${eventType}: ${name.trim()}`;
  }
  const notes = payload.notes;
  if (typeof notes === "string" && notes.trim()) {
    return `${eventType}: ${notes.trim()}`;
  }
  const checklistUid = payload.checklist_uid;
  if (typeof checklistUid === "string" && checklistUid.trim()) {
    return `${eventType}: checklist ${checklistUid.trim()}`;
  }
  const missionUid = payload.mission_uid ?? payload.mission_id;
  if (typeof missionUid === "string" && missionUid.trim()) {
    return `${eventType}: mission ${missionUid.trim()}`;
  }
  return eventType;
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

const missions = ref<Mission[]>([]);
const checklistRecords = ref<ChecklistRaw[]>([]);
const teamRecords = ref<TeamRaw[]>([]);
const memberRecords = ref<TeamMemberRaw[]>([]);
const assetRecords = ref<AssetRaw[]>([]);
const assignmentRecords = ref<AssignmentRaw[]>([]);
const eventRecords = ref<DomainEventRaw[]>([]);
const missionChanges = ref<MissionChangeRaw[]>([]);
const zoneRecords = ref<ZoneRaw[]>([]);
const templateRecords = ref<TemplateRaw[]>([]);
const skillRecords = ref<SkillRaw[]>([]);
const teamMemberSkillRecords = ref<TeamMemberSkillRaw[]>([]);
const taskSkillRequirementRecords = ref<TaskSkillRequirementRaw[]>([]);

const loadingWorkspace = ref(false);
const zoneDraftByMission = ref<Record<string, string[]>>({});

const checklists = computed<Checklist[]>(() => {
  return checklistRecords.value
    .map((entry) => {
      const checklistUid = String(entry.uid ?? "").trim();
      if (!checklistUid) {
        return null;
      }
      const preferredTaskColumnUid = resolveTaskNameColumnUid(entry);
      const tasks = toArray<ChecklistTaskRaw>(entry.tasks).map((task) => {
        const taskUid = String(task.task_uid ?? "").trim();
        const taskStatus = normalizeTaskStatus(task.task_status ?? task.user_status);
        const taskName = resolveChecklistTaskName(entry, task, preferredTaskColumnUid);
        const assignee = String(task.completed_by_team_member_rns_identity ?? "").trim();
        return {
          id: taskUid || `${checklistUid}-task-${String(task.number ?? "0")}`,
          name: taskName,
          status: taskStatus,
          assignee: assignee || "-"
        };
      });
      const missionUid = String(entry.mission_id ?? "").trim();
      return {
        uid: checklistUid,
        mission_uid: missionUid,
        name: String(entry.name ?? checklistUid),
        progress: Number(entry.progress_percent ?? 0),
        tasks
      };
    })
    .filter((entry): entry is Checklist => entry !== null);
});

const teams = computed<Team[]>(() => {
  return teamRecords.value
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) {
        return null;
      }
      return {
        uid,
        mission_uid: String(entry.mission_uid ?? "").trim(),
        name: String(entry.team_name ?? uid),
        description: String(entry.team_description ?? "")
      };
    })
    .filter((entry): entry is Team => entry !== null);
});

const templates = computed<Template[]>(() => {
  return templateRecords.value
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) {
        return null;
      }
      return {
        uid,
        name: String(entry.template_name ?? uid),
        columns: toArray<unknown>(entry.columns).length
      };
    })
    .filter((entry): entry is Template => entry !== null);
});

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

const memberCapabilitiesByIdentity = computed(() => {
  const map = new Map<string, string[]>();
  teamMemberSkillRecords.value.forEach((entry) => {
    const identity = String(entry.team_member_rns_identity ?? "").trim();
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
    const identity = String(entry.rns_identity ?? "").trim();
    if (!uid || !identity) {
      return;
    }
    const callsign = String(entry.callsign ?? entry.display_name ?? identity).trim() || identity;
    map.set(identity, { callsign, uid });
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

const primaryTabs = [
  { id: "mission", label: "Mission" },
  { id: "checklists", label: "Checklists" },
  { id: "templates", label: "Excheck Templates" },
  { id: "board", label: "Excheck Board" }
] as const;

const screensByTab: Record<PrimaryTab, Array<{ id: ScreenId; label: string }>> = {
  mission: [
    { id: "missionDirectory", label: "Mission Directory" },
    { id: "missionCreateEdit", label: "Mission Create/Edit" },
    { id: "missionOverview", label: "Mission Overview" },
    { id: "missionTeamMembers", label: "Mission Team & Members" },
    { id: "assignAssets", label: "Assign Assets to Mission" },
    { id: "assignZones", label: "Assign Zones to Mission" },
    { id: "missionAudit", label: "Mission Activity / Audit" },
    { id: "assetRegistry", label: "Asset Registry" }
  ],
  checklists: [
    { id: "checklistOverview", label: "Checklist Overview" },
    { id: "checklistDetails", label: "Checklist Details" },
    { id: "checklistCreation", label: "Checklist Creation Page" },
    { id: "checklistRunDetail", label: "Checklist Run Detail" },
    { id: "taskAssignmentWorkspace", label: "Task Assignment Workspace" },
    { id: "checklistImportCsv", label: "Checklist Import from CSV" },
    { id: "checklistPublish", label: "Checklist Publish to Mission" },
    { id: "checklistProgress", label: "Checklist Progress & Compliance" }
  ],
  templates: [
    { id: "templateLibrary", label: "Excheck Template Library" },
    { id: "templateBuilder", label: "Excheck Template Builder" }
  ],
  board: [{ id: "missionExcheckBoard", label: "Mission Excheck Board" }]
};

const screenMeta: Record<ScreenId, { title: string; subtitle: string; actions: string[] }> = {
  missionDirectory: { title: "Mission Directory", subtitle: "Mission list and operational status registry.", actions: ["Filter", "Export"] },
  missionCreateEdit: { title: "Mission Create/Edit", subtitle: "Create and edit mission metadata and topic bindings.", actions: ["Save", "Reset"] },
  missionOverview: { title: "Mission Overview", subtitle: "Live mission summary with checklists, teams, and assets.", actions: ["Refresh", "Broadcast"] },
  missionTeamMembers: { title: "Mission Team & Members", subtitle: "Team composition, roles, and capabilities.", actions: ["Add Team", "Add Member"] },
  assignAssets: { title: "Assign Assets to Mission", subtitle: "Bind registered assets to mission tasks and operators.", actions: ["Assign", "Revoke"] },
  assignZones: { title: "Assign Zones to Mission", subtitle: "Zone selection and geographic mission boundaries.", actions: ["Commit", "New Zone"] },
  missionAudit: { title: "Mission Activity / Audit", subtitle: "Mission timeline, status transitions, and forensic log.", actions: ["Export Log", "Snapshot"] },
  assetRegistry: { title: "Asset Registry", subtitle: "Hardware inventory, status, and readiness.", actions: ["Deploy", "Filter"] },
  checklistOverview: { title: "Checklist Overview", subtitle: "Checklist runs mapped to this mission.", actions: ["Start New", "Join"] },
  checklistDetails: { title: "Checklist Details", subtitle: "Task grid, callsigns, due relative DTG, and status.", actions: ["Edit Cell", "Sync"] },
  checklistCreation: { title: "Checklist Creation Page", subtitle: "Create online/offline checklist runs from templates.", actions: ["Create", "Validate"] },
  checklistRunDetail: { title: "Checklist Run Detail", subtitle: "Task status transitions and operator updates.", actions: ["Set Status", "Upload"] },
  taskAssignmentWorkspace: { title: "Task Assignment Workspace", subtitle: "Task ownership and asset mapping controls.", actions: ["Assign", "Reassign"] },
  checklistImportCsv: { title: "Checklist Import from CSV", subtitle: "Import checklist rows from CSV payloads.", actions: ["Import", "Preview"] },
  checklistPublish: { title: "Checklist Publish to Mission", subtitle: "Publish checklist feed to mission sync channel.", actions: ["Join", "Publish"] },
  checklistProgress: { title: "Checklist Progress & Compliance", subtitle: "Progress metrics and on-time compliance views.", actions: ["Recompute", "Export"] },
  templateLibrary: { title: "Excheck Template Library", subtitle: "Template catalog with versions and ownership.", actions: ["Clone", "Archive"] },
  templateBuilder: { title: "Excheck Template Builder", subtitle: "Template columns and system field configuration.", actions: ["Add Column", "Save"] },
  missionExcheckBoard: { title: "Mission Excheck Board", subtitle: "Board lanes for pending, late, and completed tasks.", actions: ["Sync Board", "Publish"] }
};

const selectedMissionUid = ref("");
const selectedChecklistUid = ref("");
const primaryTab = ref<PrimaryTab>("mission");
const secondaryScreen = ref<ScreenId>("missionDirectory");
const missionDraftName = ref("");
const missionDraftTopic = ref("");
const missionDraftStatus = ref("MISSION_ACTIVE");
const missionDraftDescription = ref("");

const missionStatusOptions = [
  "MISSION_ACTIVE",
  "MISSION_PLANNED",
  "MISSION_STANDBY",
  "MISSION_COMPLETE",
  "MISSION_ARCHIVED"
] as const;

const baseUrl = computed(() => connectionStore.baseUrlDisplay);
const connectionLabel = computed(() => connectionStore.statusLabel);
const wsLabel = computed(() => connectionStore.wsLabel);

const connectionClass = computed(() => {
  if (connectionStore.status === "online") {
    return "cui-status-success";
  }
  if (connectionStore.status === "offline") {
    return "cui-status-danger";
  }
  return "cui-status-accent";
});

const wsClass = computed(() => {
  if (connectionStore.wsLabel.toLowerCase() === "live") {
    return "cui-status-success";
  }
  return "cui-status-accent";
});

const activeScreens = computed(() => screensByTab[primaryTab.value]);
const currentScreen = computed(() => screenMeta[secondaryScreen.value]);

const selectedMission = computed(() => missions.value.find((entry) => entry.uid === selectedMissionUid.value));
const missionChecklists = computed(() => checklists.value.filter((entry) => entry.mission_uid === selectedMissionUid.value));
const selectedChecklist = computed(() => missionChecklists.value.find((entry) => entry.uid === selectedChecklistUid.value));
const selectedChecklistRaw = computed(() =>
  checklistRecords.value.find((entry) => String(entry.uid ?? "").trim() === selectedChecklistUid.value)
);

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

const missionTeams = computed(() => teams.value.filter((entry) => entry.mission_uid === selectedMissionUid.value));
const missionTeamUidSet = computed(() => new Set(missionTeams.value.map((entry) => entry.uid)));

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
      const identity = String(entry.rns_identity ?? "").trim();
      const callsign = String(entry.callsign ?? entry.display_name ?? identity ?? uid).trim() || uid;
      return {
        uid,
        mission_uid: selectedMissionUid.value,
        callsign,
        role: String(entry.role ?? "UNASSIGNED"),
        capabilities: memberCapabilitiesByIdentity.value.get(identity) ?? []
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
      const memberLabel = memberByIdentity.value.get(memberIdentity)?.callsign ?? memberIdentity;
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
  const ordered = [...missionChanges.value].sort((left, right) => toEpoch(left.timestamp) - toEpoch(right.timestamp));
  const map = new Map<string, string[]>();
  ordered.forEach((change) => {
    if (String(change.change_type ?? "").trim().toLowerCase() !== "zone.assignment") {
      return;
    }
    const missionUid = String(change.mission_uid ?? "").trim();
    if (!missionUid) {
      return;
    }
    map.set(missionUid, toStringList(change.hashes));
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
      return {
        uid: String(entry.event_uid ?? `${entry.event_type}-${createdAt}`),
        mission_uid: missionUid,
        time: formatAuditTime(createdAt),
        message: formatDomainEventMessage(entry),
        sortTs: toEpoch(createdAt)
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
        time: formatAuditTime(timestamp),
        message: notes ? `${name}: ${notes}` : name,
        sortTs: toEpoch(timestamp)
      };
    });

  return [...events, ...changes]
    .sort((left, right) => right.sortTs - left.sortTs)
    .slice(0, 20)
    .map(({ uid, mission_uid, time, message }) => ({ uid, mission_uid, time, message }));
});

const missionChangesForSelected = computed(() => {
  const missionUid = selectedMissionUid.value;
  if (!missionUid) {
    return [] as MissionChangeRaw[];
  }
  return missionChanges.value
    .filter((entry) => String(entry.mission_uid ?? "").trim() === missionUid)
    .sort((left, right) => toEpoch(right.timestamp) - toEpoch(left.timestamp))
    .slice(0, 20);
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

const showChecklistArea = computed(() => {
  return [
    "checklistOverview",
    "checklistDetails",
    "checklistCreation",
    "checklistRunDetail",
    "checklistImportCsv",
    "checklistPublish",
    "checklistProgress"
  ].includes(secondaryScreen.value);
});

const showAssetArea = computed(() => {
  return ["assetRegistry", "assignAssets", "taskAssignmentWorkspace"].includes(secondaryScreen.value);
});

const showTemplateArea = computed(() => {
  return ["templateLibrary", "templateBuilder"].includes(secondaryScreen.value);
});

const checklistPanelTitle = computed(() => {
  if (secondaryScreen.value === "checklistProgress") {
    return "Checklist Progress & Compliance";
  }
  if (secondaryScreen.value === "checklistPublish") {
    return "Checklist Publish to Mission";
  }
  if (secondaryScreen.value === "checklistImportCsv") {
    return "Checklist Import from CSV";
  }
  return "Checklist Overview";
});

const setPrimaryTab = (tab: PrimaryTab) => {
  primaryTab.value = tab;
  secondaryScreen.value = screensByTab[tab][0].id;
};

const loadWorkspace = async () => {
  loadingWorkspace.value = true;
  try {
    const [
      missionData,
      checklistPayload,
      templatePayload,
      teamData,
      teamMemberData,
      assetData,
      assignmentData,
      eventData,
      missionChangeData,
      zoneData,
      skillData,
      teamMemberSkillData,
      taskSkillRequirementData
    ] = await Promise.all([
      get<MissionRaw[]>(endpoints.r3aktMissions),
      get<{ checklists?: ChecklistRaw[] }>(endpoints.checklists),
      get<{ templates?: TemplateRaw[] }>(endpoints.checklistTemplates),
      get<TeamRaw[]>(endpoints.r3aktTeams),
      get<TeamMemberRaw[]>(endpoints.r3aktTeamMembers),
      get<AssetRaw[]>(endpoints.r3aktAssets),
      get<AssignmentRaw[]>(endpoints.r3aktAssignments),
      get<DomainEventRaw[]>(endpoints.r3aktEvents),
      get<MissionChangeRaw[]>(endpoints.r3aktMissionChanges),
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
          status: normalizeMissionStatus(entry.mission_status)
        };
      })
      .filter((entry): entry is Mission => entry !== null);

    checklistRecords.value = toArray<ChecklistRaw>(checklistPayload.checklists);
    templateRecords.value = toArray<TemplateRaw>(templatePayload.templates);
    teamRecords.value = toArray<TeamRaw>(teamData);
    memberRecords.value = toArray<TeamMemberRaw>(teamMemberData);
    assetRecords.value = toArray<AssetRaw>(assetData);
    assignmentRecords.value = toArray<AssignmentRaw>(assignmentData);
    eventRecords.value = toArray<DomainEventRaw>(eventData);
    missionChanges.value = toArray<MissionChangeRaw>(missionChangeData);
    zoneRecords.value = toArray<ZoneRaw>(zoneData);
    skillRecords.value = toArray<SkillRaw>(skillData);
    teamMemberSkillRecords.value = toArray<TeamMemberSkillRaw>(teamMemberSkillData);
    taskSkillRequirementRecords.value = toArray<TaskSkillRequirementRaw>(taskSkillRequirementData);
  } finally {
    loadingWorkspace.value = false;
  }
};

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

const addTeamAction = async () => {
  const missionUid = ensureMissionSelected();
  await post<TeamRaw>(endpoints.r3aktTeams, {
    mission_uid: missionUid,
    team_name: `Team ${missionTeams.value.length + 1}`,
    team_description: "Created from Mission workspace"
  });
  await loadWorkspace();
};

const addMemberAction = async () => {
  ensureMissionSelected();
  let teamUid = missionTeams.value[0]?.uid;
  if (!teamUid) {
    await addTeamAction();
    teamUid = missionTeams.value[0]?.uid;
  }
  if (!teamUid) {
    throw new Error("Unable to resolve a mission team");
  }
  const suffix = `${buildTimestampTag().slice(-6)}-${Math.floor(Math.random() * 1000)}`;
  await post<TeamMemberRaw>(endpoints.r3aktTeamMembers, {
    team_uid: teamUid,
    rns_identity: `ui.member.${suffix}`,
    display_name: `operator-${missionMembers.value.length + 1}`,
    callsign: `op-${missionMembers.value.length + 1}`,
    role: "SUBSCRIBER"
  });
  await loadWorkspace();
};

const ensureMemberIdentityForMission = async (): Promise<{ uid: string; identity: string }> => {
  let member = missionMembers.value[0];
  if (!member) {
    await addMemberAction();
    member = missionMembers.value[0];
  }
  if (!member) {
    throw new Error("No mission member is available");
  }
  const raw = memberRecords.value.find((entry) => String(entry.uid ?? "").trim() === member.uid);
  const identity = String(raw?.rns_identity ?? "").trim();
  if (!identity) {
    throw new Error("Mission member identity is missing");
  }
  return { uid: member.uid, identity };
};

const ensureChecklistTaskContext = async (): Promise<{ checklistUid: string; taskUid: string }> => {
  let checklist = selectedChecklistRaw.value;
  if (!checklist?.uid) {
    await createChecklistAction();
    checklist = selectedChecklistRaw.value;
  }
  if (!checklist?.uid) {
    throw new Error("No checklist is available for this mission");
  }
  const checklistUid = String(checklist.uid).trim();
  let taskUid = toArray<ChecklistTaskRaw>(checklist.tasks).find((task) => String(task.task_uid ?? "").trim().length > 0)
    ?.task_uid;
  if (!taskUid) {
    await post(`${endpoints.checklists}/${checklistUid}/tasks`, {
      number: 1,
      due_relative_minutes: 10
    });
    await loadWorkspace();
    checklist = selectedChecklistRaw.value;
    taskUid = toArray<ChecklistTaskRaw>(checklist?.tasks).find((task) => String(task.task_uid ?? "").trim().length > 0)
      ?.task_uid;
  }
  if (!taskUid) {
    throw new Error("Checklist task context could not be created");
  }
  return { checklistUid, taskUid };
};

const deployAssetAction = async () => {
  let member = missionMembers.value[0];
  if (!member) {
    await addMemberAction();
    member = missionMembers.value[0];
  }
  await post<AssetRaw>(endpoints.r3aktAssets, {
    team_member_uid: member?.uid,
    name: `ASSET-${buildTimestampTag().slice(-6)}`,
    asset_type: "FIELD_UNIT",
    status: "ACTIVE"
  });
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

const resetMissionDraft = (mission?: Mission) => {
  if (mission) {
    missionDraftName.value = mission.mission_name;
    missionDraftTopic.value = mission.topic;
    missionDraftStatus.value = toMissionStatusValue(mission.status);
    missionDraftDescription.value = mission.description;
    return;
  }
  const timestamp = buildTimestampTag();
  missionDraftName.value = `Mission ${timestamp}`;
  missionDraftTopic.value = `mission.${timestamp.toLowerCase()}`;
  missionDraftStatus.value = "MISSION_ACTIVE";
  missionDraftDescription.value = "";
};

const createMissionAction = async () => {
  const fallbackTag = buildTimestampTag();
  const missionName = missionDraftName.value.trim() || `Mission ${fallbackTag}`;
  const topic = missionDraftTopic.value.trim() || `mission.${fallbackTag.toLowerCase()}`;
  const status = toMissionStatusValue(missionDraftStatus.value);
  const description = missionDraftDescription.value.trim();
  const selectedMissionId = selectedMissionUid.value;

  if (secondaryScreen.value === "missionCreateEdit" && selectedMissionId) {
    try {
      await patchRequest(`${endpoints.r3aktMissions}/${selectedMissionId}`, {
        patch: {
          mission_name: missionName,
          mission_status: status,
          topic_id: topic,
          description
        }
      });
      await loadWorkspace();
      return;
    } catch (error) {
      const apiError = error as ApiError;
      if (!apiError?.status || ![404, 405].includes(apiError.status)) {
        throw error;
      }
    }
  }

  const created = await post<MissionRaw>(endpoints.r3aktMissions, {
    mission_name: missionName,
    mission_status: status,
    topic_id: topic,
    description
  });
  await loadWorkspace();
  const createdUid = String(created.uid ?? "").trim();
  if (createdUid) {
    selectedMissionUid.value = createdUid;
  }
};

const broadcastMissionAction = async () => {
  const missionUid = ensureMissionSelected();
  await post<MissionChangeRaw>(endpoints.r3aktMissionChanges, {
    mission_uid: missionUid,
    name: "Mission broadcast",
    change_type: "broadcast",
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

const importChecklistAction = async () => {
  const csvPayload = "10,Task 1\n20,Task 2\n";
  const encoded = btoa(csvPayload);
  await post<ChecklistRaw>(endpoints.checklistsImportCsv, {
    csv_filename: `mission-import-${Date.now()}.csv`,
    csv_base64: encoded,
    source_identity: DEFAULT_SOURCE_IDENTITY
  });
  await loadWorkspace();
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
  const selected = [...selectedZoneIds.value];
  await post<MissionChangeRaw>(endpoints.r3aktMissionChanges, {
    mission_uid: missionUid,
    name: "Zone assignment update",
    change_type: "zone.assignment",
    notes: `Assigned zones: ${selected.length}`,
    team_member_rns_identity: DEFAULT_SOURCE_IDENTITY,
    hashes: selected,
    timestamp: new Date().toISOString()
  });
  const nextDraft = { ...zoneDraftByMission.value };
  delete nextDraft[missionUid];
  zoneDraftByMission.value = nextDraft;
  await loadWorkspace();
};

const saveTemplateAction = async () => {
  const timestamp = new Date().toISOString().slice(11, 19).replace(/:/g, "");
  await post(endpoints.checklistTemplates, {
    template: {
      template_name: `Workspace Template ${timestamp}`,
      description: "Generated from Mission Workspace",
      created_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY,
      columns: [
        {
          column_name: "Due",
          display_order: 1,
          column_type: "RELATIVE_TIME",
          column_editable: false,
          is_removable: false,
          system_key: "DUE_RELATIVE_DTG"
        },
        {
          column_name: "Task",
          display_order: 2,
          column_type: "SHORT_STRING",
          column_editable: true,
          is_removable: true
        }
      ]
    }
  });
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
    await addMemberAction();
  }
  const assignment = missionAssignmentsRaw.value[0];
  if (!assignment) {
    await assignTaskAction();
    return;
  }
  const identities = missionMembers.value
    .map((member) => {
      const raw = memberRecords.value.find((entry) => String(entry.uid ?? "").trim() === member.uid);
      return String(raw?.rns_identity ?? "").trim();
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

const cloneTemplateAction = async () => {
  const template = templateRecords.value[0];
  if (!template?.uid) {
    throw new Error("No template available for cloning");
  }
  await post(`${endpoints.checklistTemplates}/${template.uid}/clone`, {
    template_name: `${String(template.template_name ?? "Template")} Copy ${buildTimestampTag().slice(-4)}`,
    description: "Cloned from Mission workspace",
    created_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY
  });
  await loadWorkspace();
};

const archiveTemplateAction = async () => {
  const template = templateRecords.value[0];
  if (!template?.uid) {
    throw new Error("No template available to archive");
  }
  const name = String(template.template_name ?? "Template");
  const archivedName = name.includes("[ARCHIVED]") ? name : `${name} [ARCHIVED]`;
  await patchRequest(`${endpoints.checklistTemplates}/${template.uid}`, {
    patch: { template_name: archivedName }
  });
  await loadWorkspace();
};

const addTemplateColumnAction = async () => {
  const template = templateRecords.value[0];
  if (!template?.uid) {
    throw new Error("No template available to update");
  }
  const existing = toArray<ChecklistColumnRaw>(template.columns);
  if (!existing.length) {
    throw new Error("Template has no base columns");
  }
  const nextOrder = Math.max(...existing.map((column) => Number(column.display_order ?? 0)), 0) + 1;
  const nextColumns = existing.map((column, index) => ({
    column_uid: String(column.column_uid ?? `${template.uid}-col-${index + 1}`),
    column_name: String(column.column_name ?? `Column ${index + 1}`),
    display_order: Number(column.display_order ?? index + 1),
    column_type: String(column.column_type ?? "SHORT_STRING"),
    column_editable: Boolean(column.column_editable ?? true),
    is_removable: Boolean(column.is_removable ?? true),
    system_key: column.system_key ?? undefined,
    background_color: column.background_color ?? undefined,
    text_color: column.text_color ?? undefined
  }));
  nextColumns.push({
    column_uid: `${template.uid}-custom-${buildTimestampTag().slice(-6)}`,
    column_name: `Field ${nextOrder}`,
    display_order: nextOrder,
    column_type: "SHORT_STRING",
    column_editable: true,
    is_removable: true
  });
  await patchRequest(`${endpoints.checklistTemplates}/${template.uid}`, {
    patch: { columns: nextColumns }
  });
  await loadWorkspace();
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
  const filtered = toArray(snapshots).filter((entry) => String(entry.aggregate_uid ?? "") === missionUid);
  downloadJson(`mission-snapshots-${missionUid}.json`, filtered);
};

const exportChecklistProgressAction = async () => {
  const checklist = ensureChecklistSelected();
  downloadJson(`checklist-progress-${checklist.uid}.json`, checklist);
};

const previewCsvAction = async () => {
  const csv = ["due_relative_minutes,task", "10,Task 1", "20,Task 2", "30,Task 3"].join("\n");
  downloadText(`checklist-import-preview-${buildTimestampTag()}.csv`, csv, "text/csv");
};

const previewAction = async (action: string) => {
  if (loadingWorkspace.value) {
    return;
  }

  if (["Refresh", "Sync", "Recompute", "Sync Board"].includes(action)) {
    await runAction(loadWorkspace, "Mission workspace refreshed", "Unable to refresh mission workspace");
    return;
  }

  if (action === "Reset" && secondaryScreen.value === "missionCreateEdit") {
    resetMissionDraft(selectedMission.value);
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

  if ((action === "Save" && secondaryScreen.value === "missionCreateEdit") || action === "Save Mission") {
    const savedMissionUid = selectedMissionUid.value;
    await runAction(
      createMissionAction,
      savedMissionUid ? "Mission saved" : "Mission created",
      "Unable to save mission"
    );
    return;
  }

  if (action === "Add Team") {
    await runAction(addTeamAction, "Mission team created", "Unable to create mission team");
    return;
  }

  if (action === "Add Member") {
    await runAction(addMemberAction, "Mission member added", "Unable to add mission member");
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
    await runAction(createChecklistAction, "Checklist run created", "Unable to create checklist run");
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

  if (action === "Snapshot") {
    await runAction(snapshotAction, "Mission snapshots exported", "Unable to export mission snapshots");
    return;
  }

  if (action === "Deploy") {
    await runAction(deployAssetAction, "Asset deployed", "Unable to deploy asset");
    return;
  }

  if (action === "Clone") {
    await runAction(cloneTemplateAction, "Template cloned", "Unable to clone template");
    return;
  }

  if (action === "Archive") {
    await runAction(archiveTemplateAction, "Template archived", "Unable to archive template");
    return;
  }

  if (action === "Add Column") {
    await runAction(addTemplateColumnAction, "Template column added", "Unable to add template column");
    return;
  }

  if (action === "Save Template" || (action === "Save" && secondaryScreen.value === "templateBuilder")) {
    await runAction(saveTemplateAction, "Checklist template saved", "Unable to save checklist template");
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
    resetMissionDraft(mission);
  },
  { immediate: true }
);

watch(
  missionChecklists,
  (entries) => {
    if (!entries.some((entry) => entry.uid === selectedChecklistUid.value)) {
      selectedChecklistUid.value = entries[0]?.uid ?? "";
    }
  },
  { immediate: true }
);

onMounted(() => {
  loadWorkspace().catch((error) => {
    handleApiError(error, "Unable to load mission workspace");
  });
});
</script>

<style scoped>
.missions-workspace {
  --neon: #37f2ff;
  --panel-dark: rgba(4, 12, 22, 0.96);
  --panel-light: rgba(10, 30, 45, 0.94);
  --amber: #ffb35c;
  color: #dffcff;
  font-family: "Orbitron", "Rajdhani", "Barlow", sans-serif;
}

.registry-shell {
  position: relative;
  padding: 20px 22px 26px;
  border-radius: 18px;
  border: 1px solid rgba(55, 242, 255, 0.25);
  background: radial-gradient(circle at top, rgba(42, 210, 255, 0.12), transparent 55%),
    linear-gradient(145deg, rgba(5, 16, 28, 0.96), rgba(2, 6, 12, 0.98));
  box-shadow: 0 18px 55px rgba(1, 6, 12, 0.65), inset 0 0 0 1px rgba(55, 242, 255, 0.08);
  overflow: hidden;
}

.registry-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 1px 1px, rgba(55, 242, 255, 0.08) 1px, transparent 0) 0 0 / 18px 18px;
  opacity: 0.6;
  pointer-events: none;
}

.registry-top {
  position: relative;
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 16px;
  z-index: 1;
}

.registry-title {
  justify-self: center;
  font-size: 20px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #d4fbff;
  text-shadow: 0 0 12px rgba(55, 242, 255, 0.5);
}

.registry-status {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-self: end;
}

.status-url {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(215, 243, 255, 0.8);
}

.mission-kpis {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.kpi-card {
  border: 1px solid rgba(55, 242, 255, 0.24);
  background: rgba(8, 22, 34, 0.78);
  border-radius: 10px;
  padding: 10px;
  display: grid;
  gap: 4px;
}

.kpi-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: rgba(209, 251, 255, 0.66);
}

.kpi-value {
  font-size: 28px;
  line-height: 1;
}

.registry-grid {
  display: grid;
  grid-template-columns: minmax(260px, 300px) 1fr;
  gap: 18px;
  z-index: 1;
  position: relative;
  margin-top: 14px;
}

.panel {
  position: relative;
  padding: 16px;
  background: linear-gradient(145deg, var(--panel-light), var(--panel-dark));
  border: 1px solid rgba(55, 242, 255, 0.25);
  box-shadow: inset 0 0 0 1px rgba(55, 242, 255, 0.08), 0 12px 30px rgba(1, 6, 12, 0.6);
  clip-path: polygon(0 0, calc(100% - 24px) 0, 100% 24px, 100% 100%, 24px 100%, 0 calc(100% - 24px));
}

.panel::before {
  content: "";
  position: absolute;
  inset: 0;
  border: 1px solid rgba(55, 242, 255, 0.2);
  clip-path: polygon(1px 1px, calc(100% - 25px) 1px, calc(100% - 1px) 25px, calc(100% - 1px) calc(100% - 1px), 25px calc(100% - 1px), 1px calc(100% - 25px));
  pointer-events: none;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-title {
  font-size: 16px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #d1fbff;
}

.panel-subtitle {
  font-size: 12px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.65);
  margin-top: 4px;
}

.panel-chip {
  border: 1px solid var(--amber);
  color: var(--amber);
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 999px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.panel-tabs,
.screen-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.panel-tab,
.screen-tab {
  border: 1px solid rgba(55, 242, 255, 0.26);
  background: rgba(7, 18, 26, 0.8);
  color: rgba(209, 251, 255, 0.66);
  padding: 6px 10px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 10px;
}

.panel-tab.active,
.screen-tab.active {
  border-color: rgba(55, 242, 255, 0.65);
  color: #e0feff;
  background: rgba(55, 242, 255, 0.14);
}

.tree-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tree-item {
  display: grid;
  grid-template-columns: 10px 1fr auto;
  align-items: center;
  gap: 8px;
  border: 1px solid transparent;
  background: rgba(7, 18, 28, 0.6);
  color: rgba(213, 251, 255, 0.9);
  padding: 8px 10px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 10px;
}

.tree-item.active {
  border-color: rgba(55, 242, 255, 0.65);
  background: rgba(55, 242, 255, 0.12);
}

.tree-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--neon);
}

.tree-count {
  border: 1px solid rgba(55, 242, 255, 0.45);
  border-radius: 999px;
  padding: 2px 8px;
}

.tree-label {
  text-align: left;
}

.screen-shell {
  margin-top: 10px;
  border: 1px solid rgba(55, 242, 255, 0.2);
  border-radius: 10px;
  background: rgba(6, 14, 24, 0.75);
  padding: 12px;
  display: grid;
  gap: 10px;
}

.screen-header h3 {
  margin: 0;
  font-size: 14px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.screen-header p {
  margin: 4px 0 0;
  font-size: 12px;
  color: rgba(209, 251, 255, 0.72);
}

.screen-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.screen-grid {
  display: grid;
  gap: 10px;
}

.screen-grid.two-col {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.stage-card {
  border: 1px solid rgba(55, 242, 255, 0.24);
  border-radius: 10px;
  background: rgba(8, 18, 28, 0.74);
  padding: 10px;
  display: grid;
  gap: 8px;
}

.stage-card h4 {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

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

.timeline li strong {
  color: #37f2ff;
}

.cap-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.cap-chip {
  border: 1px solid rgba(55, 242, 255, 0.45);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.mini-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.mini-table th {
  text-align: left;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: rgba(209, 251, 255, 0.7);
  padding: 6px;
  border-bottom: 1px solid rgba(55, 242, 255, 0.3);
}

.mini-table td {
  padding: 6px;
  border-bottom: 1px solid rgba(55, 242, 255, 0.14);
}

.checklist-list {
  display: grid;
  gap: 6px;
}

.checklist-item {
  border: 1px solid rgba(55, 242, 255, 0.3);
  background: rgba(7, 18, 28, 0.75);
  color: #dffcff;
  border-radius: 8px;
  padding: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-size: 10px;
}

.checklist-item.active {
  border-color: rgba(55, 242, 255, 0.65);
  background: rgba(55, 242, 255, 0.12);
}

.board-preview {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.board-col {
  border: 1px solid rgba(55, 242, 255, 0.26);
  border-radius: 8px;
  padding: 8px;
  text-align: center;
}

.board-col h5 {
  margin: 0;
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.board-col span {
  display: block;
  margin-top: 6px;
  font-size: 22px;
}

.zone-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.builder-preview {
  font-size: 12px;
  color: rgba(214, 251, 255, 0.85);
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.field-control {
  display: grid;
  gap: 6px;
}

.field-control.full {
  grid-column: 1 / -1;
}

.field-control span {
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(205, 248, 255, 0.74);
}

.field-control input,
.field-control select,
.field-control textarea {
  border: 1px solid rgba(55, 242, 255, 0.34);
  border-radius: 8px;
  background: rgba(5, 14, 22, 0.84);
  color: #dffcff;
  padding: 8px 10px;
  font-family: inherit;
  font-size: 12px;
}

.field-control textarea {
  resize: vertical;
}

.board-lanes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.board-lane {
  text-align: left;
}

.board-lane-pending {
  border-color: rgba(55, 242, 255, 0.38);
}

.board-lane-late {
  border-color: rgba(255, 95, 141, 0.5);
}

.board-lane-complete {
  border-color: rgba(58, 244, 179, 0.45);
}

.lane-list {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.lane-list li {
  border: 1px solid rgba(55, 242, 255, 0.2);
  border-radius: 8px;
  padding: 8px;
  background: rgba(8, 18, 30, 0.8);
  display: grid;
  gap: 3px;
}

.lane-list li strong {
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.lane-list li span {
  font-size: 10px;
  color: rgba(203, 246, 255, 0.72);
  letter-spacing: 0.08em;
}

:deep(.missions-workspace .cui-btn) {
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 10px;
}

@media (max-width: 1200px) {
  .registry-grid,
  .screen-grid.two-col {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 800px) {
  .mission-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .field-grid,
  .board-lanes {
    grid-template-columns: 1fr;
  }

  .registry-top {
    grid-template-columns: 1fr;
  }

  .registry-status {
    justify-content: center;
    flex-wrap: wrap;
  }
}
</style>
