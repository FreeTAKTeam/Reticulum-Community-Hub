<template>
  <div class="missions-workspace">
    <div class="registry-shell">
      <header class="registry-top">
        <div class="registry-title">{{ isChecklistPrimaryTab ? "Checklist" : "Mission Workspace" }}</div>
        <div class="registry-status">
          <OnlineHelpLauncher />
          <span class="cui-status-pill" :class="connectionClass">{{ connectionLabel }}</span>
          <span class="cui-status-pill" :class="wsClass">{{ wsLabel }}</span>
          <span class="status-url">{{ baseUrl }}</span>
        </div>
      </header>

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
          <div v-if="!isChecklistPrimaryTab" class="panel-header">
            <div>
              <div class="panel-title">{{ workspacePanelTitle }}</div>
              <div class="panel-subtitle">{{ workspacePanelSubtitle }}</div>
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

          <div v-if="activeScreens.length > 1" class="screen-tabs">
            <button
              v-for="screen in activeScreens"
              :key="screen.id"
              class="screen-tab"
              :class="{ active: secondaryScreen === screen.id }"
              type="button"
              @click="setSecondaryScreen(screen.id)"
            >
              {{ screen.label }}
            </button>
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
              <article class="stage-card">
                <h4>{{ isMissionCreateScreen ? "Mission Create" : "Mission Edit" }}</h4>
                <div class="field-grid">
                  <label class="field-control">
                    <span>Mission UID</span>
                    <input :value="missionDraftUidLabel" type="text" readonly />
                  </label>
                  <label class="field-control">
                    <span>Name</span>
                    <input v-model="missionDraftName" type="text" placeholder="Mission Name" />
                  </label>
                  <label class="field-control">
                    <span>Topic Scope</span>
                    <div class="field-inline-control">
                      <select v-model="missionDraftTopic">
                        <option v-for="option in missionTopicOptions" :key="`mission-topic-${option.value}`" :value="option.value">
                          {{ option.label }}
                        </option>
                      </select>
                      <BaseButton size="sm" variant="secondary" icon-left="plus" @click="openTopicCreatePage">
                        New
                      </BaseButton>
                    </div>
                  </label>
                  <label class="field-control">
                    <span>Status</span>
                    <select v-model="missionDraftStatus">
                      <option v-for="status in missionStatusOptions" :key="status" :value="status">
                        {{ status }}
                      </option>
                    </select>
                  </label>
                  <label class="field-control">
                    <span>Parent Mission</span>
                    <select v-model="missionDraftParentUid">
                      <option v-for="option in missionParentOptions" :key="`mission-parent-${option.value}`" :value="option.value">
                        {{ option.label }}
                      </option>
                    </select>
                  </label>
                  <label class="field-control">
                    <span>Reference Team</span>
                    <select v-model="missionDraftTeamUid">
                      <option v-for="option in missionReferenceTeamOptions" :key="`mission-team-${option.value}`" :value="option.value">
                        {{ option.label }}
                      </option>
                    </select>
                  </label>
                  <details class="mission-advanced-properties full" :open="missionAdvancedPropertiesOpen" @toggle="onMissionAdvancedPropertiesToggle">
                    <summary class="mission-advanced-properties__summary">
                      <span class="mission-advanced-properties__title">Advanced Properties</span>
                      <span class="mission-advanced-properties__meta">
                        {{ missionAdvancedPropertiesOpen ? "Expanded" : "Folded" }}
                      </span>
                    </summary>
                    <div class="field-grid mission-advanced-properties__grid">
                      <label class="field-control">
                        <span>Path</span>
                        <input v-model="missionDraftPath" type="text" placeholder="ops.region.path" />
                      </label>
                      <label class="field-control">
                        <span>Classification</span>
                        <input v-model="missionDraftClassification" type="text" placeholder="UNCLASSIFIED" />
                      </label>
                      <label class="field-control">
                        <span>Tool</span>
                        <input v-model="missionDraftTool" type="text" placeholder="ATAK" />
                      </label>
                      <label class="field-control">
                        <span>Keywords (comma separated)</span>
                        <input v-model="missionDraftKeywords" type="text" placeholder="winter,storm,rescue" />
                      </label>
                      <label class="field-control">
                        <span>Default Role</span>
                        <input v-model="missionDraftDefaultRole" type="text" placeholder="TEAM_MEMBER" />
                      </label>
                      <label class="field-control">
                        <span>Owner Role</span>
                        <input v-model="missionDraftOwnerRole" type="text" placeholder="TEAM_LEAD" />
                      </label>
                      <label class="field-control">
                        <span>Mission Priority</span>
                        <input v-model="missionDraftPriority" type="number" min="0" step="1" placeholder="1" />
                      </label>
                      <label class="field-control">
                        <span>Mission RDE Role</span>
                        <input v-model="missionDraftMissionRdeRole" type="text" placeholder="observer" />
                      </label>
                      <label class="field-control">
                        <span>Token</span>
                        <input v-model="missionDraftToken" type="text" placeholder="optional token" />
                      </label>
                      <label class="field-control">
                        <span>Feeds (comma separated)</span>
                        <input v-model="missionDraftFeeds" type="text" placeholder="feed-alpha,feed-bravo" />
                      </label>
                      <label class="field-control">
                        <span>Expiration</span>
                        <input v-model="missionDraftExpiration" type="datetime-local" />
                      </label>
                      <label class="field-control">
                        <span>Invite Only</span>
                        <select v-model="missionDraftInviteOnly">
                          <option :value="false">No</option>
                          <option :value="true">Yes</option>
                        </select>
                      </label>
                    </div>
                  </details>
                  <label class="field-control full">
                    <span>Reference Zones</span>
                    <select
                      class="field-control-multi"
                      multiple
                      :value="missionDraftZoneUids"
                      @change="onMissionDraftZoneSelectionChange"
                    >
                      <option v-for="option in missionReferenceZoneOptions" :key="`mission-zone-${option.value}`" :value="option.value">
                        {{ option.label }}
                      </option>
                    </select>
                    <small class="field-note">Use Ctrl/Cmd + click to select multiple zones.</small>
                  </label>
                  <label class="field-control full">
                    <span>Reference Assets</span>
                    <select
                      class="field-control-multi"
                      multiple
                      :value="missionDraftAssetUids"
                      @change="onMissionDraftAssetSelectionChange"
                    >
                      <option
                        v-for="option in missionReferenceAssetOptions"
                        :key="`mission-asset-${option.value}`"
                        :value="option.value"
                      >
                        {{ option.label }}
                      </option>
                    </select>
                    <small class="field-note">Preferred assets can be finalized in Assign Assets once tasks and members exist.</small>
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
                <h4>{{ isMissionCreateScreen ? "Create Preview" : "Edit Preview" }}</h4>
                <ul class="stack-list">
                  <li><strong>Name</strong><span>{{ missionDraftName || "-" }}</span></li>
                  <li><strong>UID</strong><span>{{ missionDraftUidLabel }}</span></li>
                  <li><strong>Topic</strong><span>{{ missionDraftTopic || "-" }}</span></li>
                  <li><strong>Status</strong><span>{{ missionDraftStatus }}</span></li>
                  <li><strong>Parent Mission</strong><span>{{ missionDraftParentLabel }}</span></li>
                  <li><strong>Reference Team</strong><span>{{ missionDraftTeamLabel }}</span></li>
                  <li><strong>Reference Zones</strong><span>{{ missionDraftZoneLabel }}</span></li>
                  <li><strong>Reference Assets</strong><span>{{ missionDraftAssetLabel }}</span></li>
                  <li><strong>Invite Only</strong><span>{{ missionDraftInviteOnly ? "YES" : "NO" }}</span></li>
                  <li><strong>Description</strong><span>{{ missionDraftDescription || "-" }}</span></li>
                </ul>
              </article>
            </div>

            <div v-else-if="secondaryScreen === 'missionOverview'" class="mission-overview-hud">
              <section class="overview-vitals">
                <article class="overview-vital-card">
                  <span class="overview-vital-label">Mission Status</span>
                  <strong class="overview-vital-value">{{ selectedMission?.status || "UNSCOPED" }}</strong>
                </article>
                <article class="overview-vital-card">
                  <span class="overview-vital-label">Checklist Runs</span>
                  <strong class="overview-vital-value">{{ missionChecklists.length }}</strong>
                </article>
                <article class="overview-vital-card">
                  <span class="overview-vital-label">Open Tasks</span>
                  <strong class="overview-vital-value">{{ missionOpenTaskTotal }}</strong>
                </article>
                <article class="overview-vital-card">
                  <span class="overview-vital-label">Team Members</span>
                  <strong class="overview-vital-value">{{ missionMembers.length }}</strong>
                </article>
                <article class="overview-vital-card">
                  <span class="overview-vital-label">Assigned Assets</span>
                  <strong class="overview-vital-value">{{ missionAssets.length }}</strong>
                </article>
                <article class="overview-vital-card">
                  <span class="overview-vital-label">Assigned Zones</span>
                  <strong class="overview-vital-value">{{ assignedZones.length }}</strong>
                </article>
              </section>

              <section class="overview-layout">
                <article class="stage-card overview-panel overview-panel-compact">
                  <div class="overview-compact-header">
                    <div>
                      <h4>Mission Profile</h4>
                      <div class="overview-compact-subtitle mono">
                        {{ selectedMission?.uid || "No mission selected" }}
                      </div>
                    </div>
                    <span class="overview-compact-tag">{{ selectedMission?.status || "UNSCOPED" }}</span>
                  </div>
                  <div class="overview-compact-meta">
                    <div>
                      <span>Topic</span>
                      <span>{{ selectedMission?.topic || "-" }}</span>
                    </div>
                    <div>
                      <span>Name</span>
                      <span>{{ selectedMission?.mission_name || "-" }}</span>
                    </div>
                    <div>
                      <span>Description</span>
                      <span class="overview-compact-truncate" :title="selectedMission?.description || '-'">
                        {{ selectedMission?.description || "-" }}
                      </span>
                    </div>
                    <div>
                      <span>Total Tasks</span>
                      <span>{{ missionTotalTasks }}</span>
                    </div>
                  </div>
                  <div class="overview-compact-actions">
                    <BaseButton size="sm" variant="secondary" icon-left="edit" @click="openMissionEditScreen">
                      Edit
                    </BaseButton>
                    <BaseButton size="sm" variant="secondary" icon-left="list" @click="openMissionLogsPage">
                      Logs
                    </BaseButton>
                    <BaseButton size="sm" variant="secondary" icon-left="users" @click="secondaryScreen = 'missionTeamMembers'">
                      Team
                    </BaseButton>
                    <BaseButton size="sm" variant="secondary" icon-left="link" @click="secondaryScreen = 'assignAssets'">
                      Assets
                    </BaseButton>
                    <BaseButton size="sm" variant="secondary" icon-left="tool" @click="secondaryScreen = 'assignZones'">
                      Zones
                    </BaseButton>
                  </div>
                </article>

                <article class="stage-card overview-panel overview-panel-compact">
                  <div class="overview-compact-header">
                    <div>
                      <h4>Mission Excheck Snapshot</h4>
                      <div class="overview-compact-subtitle">Condensed lane status</div>
                    </div>
                    <span class="overview-compact-tag">{{ missionTotalTasks }} Tasks</span>
                  </div>
                  <div class="overview-board overview-board-compact">
                    <div class="overview-board-col overview-board-col-pending">
                      <div class="overview-board-col-head">
                        <h5>Pending</h5>
                        <span>{{ boardCounts.pending }}</span>
                      </div>
                      <ul class="lane-list lane-list-compact">
                        <li v-for="task in boardLaneTasks.pending.slice(0, 3)" :key="`overview-pending-${task.id}`">
                          <strong>{{ task.name }}</strong>
                          <span>{{ task.meta }}</span>
                        </li>
                        <li v-if="!boardLaneTasks.pending.length" class="lane-empty">No pending tasks.</li>
                      </ul>
                    </div>
                    <div class="overview-board-col overview-board-col-late">
                      <div class="overview-board-col-head">
                        <h5>Late</h5>
                        <span>{{ boardCounts.late }}</span>
                      </div>
                      <ul class="lane-list lane-list-compact">
                        <li v-for="task in boardLaneTasks.late.slice(0, 3)" :key="`overview-late-${task.id}`">
                          <strong>{{ task.name }}</strong>
                          <span>{{ task.meta }}</span>
                        </li>
                        <li v-if="!boardLaneTasks.late.length" class="lane-empty">No late tasks.</li>
                      </ul>
                    </div>
                    <div class="overview-board-col overview-board-col-complete">
                      <div class="overview-board-col-head">
                        <h5>Complete</h5>
                        <span>{{ boardCounts.complete }}</span>
                      </div>
                      <ul class="lane-list lane-list-compact">
                        <li v-for="task in boardLaneTasks.complete.slice(0, 3)" :key="`overview-complete-${task.id}`">
                          <strong>{{ task.name }}</strong>
                          <span>{{ task.meta }}</span>
                        </li>
                        <li v-if="!boardLaneTasks.complete.length" class="lane-empty">No completed tasks.</li>
                      </ul>
                    </div>
                  </div>
                </article>

                <article class="stage-card overview-panel">
                  <div class="overview-panel-header">
                    <h4>Zones Assignment Status</h4>
                    <span class="overview-panel-meta">{{ zoneCoveragePercent }}% coverage</span>
                  </div>
                  <div class="overview-zone-progress" role="presentation">
                    <span class="overview-zone-progress-value" :style="{ width: `${zoneCoveragePercent}%` }"></span>
                  </div>
                  <div class="overview-zone-summary">
                    <span>{{ assignedZones.length }} of {{ zones.length }} zones assigned</span>
                    <span>Mission scope: {{ selectedMission?.topic || "-" }}</span>
                  </div>
                  <ul class="stack-list overview-zone-list">
                    <li v-for="zone in assignedZones.slice(0, 6)" :key="`overview-zone-${zone.uid}`">
                      <strong>{{ zone.name }}</strong>
                      <span>Assigned to mission</span>
                    </li>
                    <li v-if="!assignedZones.length">
                      <strong>No Zones Assigned</strong>
                      <span>Use Assign Zones to define operational boundaries.</span>
                    </li>
                  </ul>
                </article>

                <article class="stage-card overview-panel overview-panel-wide">
                  <div class="mission-audit-head">
                    <div>
                      <h4>Mission Activity / Audit</h4>
                      <span class="mission-audit-subtitle">
                        Unified mission activity stream (events + mission changes + log entries)
                      </span>
                    </div>
                    <span class="overview-panel-meta">Latest {{ missionAudit.length }} entries</span>
                  </div>
                  <div class="mission-audit-actions">
                    <BaseButton
                      size="sm"
                      variant="secondary"
                      :icon-left="iconForAction('Export Log')"
                      @click="previewAction('Export Log')"
                    >
                      Export Log
                    </BaseButton>
                    <BaseButton
                      size="sm"
                      variant="secondary"
                      :icon-left="iconForAction('Snapshot')"
                      @click="previewAction('Snapshot')"
                    >
                      Snapshot
                    </BaseButton>
                    <BaseButton
                      size="sm"
                      variant="secondary"
                      :icon-left="iconForAction('Open Logs')"
                      @click="previewAction('Open Logs')"
                    >
                      Open Logs
                    </BaseButton>
                  </div>
                  <div v-if="!missionAudit.length" class="mission-audit-empty">No mission activity yet.</div>
                  <div v-else class="mission-audit-table-shell">
                    <table class="mission-audit-table">
                      <thead>
                        <tr>
                          <th>Event</th>
                          <th>Type</th>
                          <th>Time</th>
                          <th class="mission-audit-cell-action">Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        <template v-for="event in missionAudit" :key="`mission-audit-${event.uid}`">
                          <tr class="mission-audit-row">
                            <td class="mission-audit-cell-message">{{ event.message }}</td>
                            <td class="mission-audit-cell-type">
                              <span class="mission-audit-type-chip">{{ event.type }}</span>
                            </td>
                            <td class="mission-audit-cell-time">{{ formatAuditDateTime(event.timestamp) }}</td>
                            <td class="mission-audit-cell-action">
                              <button
                                type="button"
                                class="mission-audit-toggle"
                                :disabled="!hasMissionAuditDetails(event.details)"
                                @click="toggleMissionAuditExpanded(event.uid)"
                              >
                                {{ isMissionAuditExpanded(event.uid) ? "Hide" : "Details" }}
                              </button>
                            </td>
                          </tr>
                          <tr v-if="isMissionAuditExpanded(event.uid)" class="mission-audit-details-row">
                            <td colspan="4">
                              <div class="mission-audit-details">
                                <BaseFormattedOutput class="mission-audit-json" :value="event.details" />
                              </div>
                            </td>
                          </tr>
                        </template>
                      </tbody>
                    </table>
                  </div>
                </article>
              </section>
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

            <div v-else-if="showChecklistArea" class="screen-grid">
              <article class="stage-card checklist-workspace">
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
                    <tr v-if="!missionAssets.length">
                      <td colspan="3">No mission assets available yet.</td>
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
                    <tr v-if="!missionAssignments.length">
                      <td colspan="3">No task assignments available yet.</td>
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
                <h4>Zone Assignment Status</h4>
                <ul class="stack-list">
                  <li>
                    <strong>Assigned Zones</strong>
                    <span>{{ assignedZones.length }} / {{ zones.length }}</span>
                  </li>
                  <li>
                    <strong>Coverage</strong>
                    <span>{{ zoneCoveragePercent }}%</span>
                  </li>
                  <li>
                    <strong>Mission Scope</strong>
                    <span>{{ selectedMission?.topic || "-" }}</span>
                  </li>
                </ul>
                <ul class="stack-list">
                  <li v-for="zone in assignedZones" :key="`assign-zone-${zone.uid}`">
                    <strong>{{ zone.name }}</strong>
                    <span>Assigned</span>
                  </li>
                  <li v-if="!assignedZones.length">
                    <strong>No Zones Assigned</strong>
                    <span>Select one or more zones and commit the mission boundary.</span>
                  </li>
                </ul>
              </article>
            </div>

            <div v-else class="screen-grid">
              <article class="stage-card">
                <h4>Mission Workspace</h4>
                <p class="builder-preview">Select a workspace tab to continue.</p>
              </article>
            </div>
          </article>
        </section>
      </div>
    </div>

    <BaseModal
      :open="teamAllocationModalOpen"
      title="Mission Team Allocation"
      @close="closeTeamAllocationModal"
    >
      <div class="template-modal mission-allocation-modal">
        <p class="template-modal-hint">
          Link an existing team to this mission or create a new mission team.
        </p>
        <div class="allocation-grid">
          <section class="allocation-card">
            <h4>Assign Existing Team</h4>
            <BaseSelect
              v-model="teamAllocationExistingTeamUid"
              label="Existing Team"
              :options="teamAllocationExistingTeamOptions"
            />
            <p class="template-modal-empty" v-if="teamAllocationExistingTeamOptions.length <= 1">
              No unassigned teams are currently available.
            </p>
            <div class="allocation-card-actions">
              <BaseButton
                icon-left="link"
                :disabled="teamAllocationSubmitting || !canAssignExistingTeam"
                @click="assignExistingTeamToMission"
              >
                {{ teamAllocationSubmitting ? "Assigning..." : "Assign Team" }}
              </BaseButton>
            </div>
          </section>

          <section class="allocation-card">
            <h4>Create New Team</h4>
            <label class="field-control full">
              <span>Team Name</span>
              <input v-model="teamAllocationNewTeamName" type="text" maxlength="96" placeholder="Mission Team" />
            </label>
            <label class="field-control full">
              <span>Description</span>
              <textarea
                v-model="teamAllocationNewTeamDescription"
                rows="3"
                maxlength="512"
                placeholder="Operational role and purpose"
              ></textarea>
            </label>
            <div class="allocation-card-actions">
              <BaseButton
                icon-left="plus"
                :disabled="teamAllocationSubmitting || !canCreateMissionTeam"
                @click="createMissionTeamFromModal"
              >
                {{ teamAllocationSubmitting ? "Creating..." : "Create Team" }}
              </BaseButton>
            </div>
          </section>
        </div>

        <div class="template-modal-actions">
          <BaseButton
            variant="ghost"
            icon-left="undo"
            :disabled="teamAllocationSubmitting"
            @click="closeTeamAllocationModal"
          >
            Cancel
          </BaseButton>
        </div>
      </div>
    </BaseModal>

    <BaseModal
      :open="memberAllocationModalOpen"
      title="Mission Team Member Allocation"
      @close="closeMemberAllocationModal"
    >
      <div class="template-modal mission-allocation-modal">
        <p class="template-modal-hint">
          Assign an existing team member to a mission team.
        </p>
        <div class="allocation-grid single-column">
          <section class="allocation-card">
            <BaseSelect v-model="memberAllocationTeamUid" label="Team" :options="memberAllocationTeamOptions" />
            <BaseSelect
              v-model="memberAllocationMemberUid"
              label="Existing Team Member"
              :options="memberAllocationExistingMemberOptions"
            />
            <p class="template-modal-empty" v-if="memberAllocationExistingMemberOptions.length <= 1">
              No assignable team members found for this team.
            </p>
            <div class="allocation-card-actions">
              <BaseButton
                icon-left="link"
                :disabled="memberAllocationSubmitting || !canAssignExistingMember"
                @click="assignExistingMemberToTeam"
              >
                {{ memberAllocationSubmitting ? "Assigning..." : "Assign Member" }}
              </BaseButton>
              <BaseButton
                variant="secondary"
                icon-left="plus"
                :disabled="memberAllocationSubmitting"
                @click="openTeamMemberCreateWorkspace"
              >
                Create New Member
              </BaseButton>
            </div>
          </section>
        </div>

        <div class="template-modal-actions">
          <BaseButton
            variant="ghost"
            icon-left="undo"
            :disabled="memberAllocationSubmitting"
            @click="closeMemberAllocationModal"
          >
            Cancel
          </BaseButton>
        </div>
      </div>
    </BaseModal>

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
import { useRoute, useRouter } from "vue-router";
import type { ApiError } from "../api/client";
import { del as deleteRequest, get, patch as patchRequest, post, put } from "../api/client";
import { endpoints } from "../api/endpoints";
import BaseButton from "../components/BaseButton.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import BaseModal from "../components/BaseModal.vue";
import BaseSelect from "../components/BaseSelect.vue";
import OnlineHelpLauncher from "../components/OnlineHelpLauncher.vue";
import { useConnectionStore } from "../stores/connection";
import { useToastStore } from "../stores/toasts";
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
  system_key?: string | null;
  background_color?: string | null;
  text_color?: string | null;
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

const connectionStore = useConnectionStore();
const toastStore = useToastStore();
const route = useRoute();
const router = useRouter();

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

const formatAuditDateTime = (value?: string | null): string => {
  if (!value) {
    return "--";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
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

const normalizeChecklistTemplateColumnType = (value?: string | null): ChecklistTemplateColumnType => {
  const normalized = String(value ?? "").trim().toUpperCase() as ChecklistTemplateColumnType;
  if (checklistTemplateColumnTypeSet.has(normalized)) {
    return normalized;
  }
  return "SHORT_STRING";
};

const isChecklistTemplateDueColumn = (column?: { system_key?: string | null }): boolean =>
  String(column?.system_key ?? "")
    .trim()
    .toUpperCase() === SYSTEM_DUE_COLUMN_KEY;

const buildChecklistTemplateColumnUid = (): string =>
  `tmpl-col-${buildTimestampTag().slice(-10)}-${Math.floor(Math.random() * 1_000_000)
    .toString(16)
    .padStart(5, "0")}`;

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
  if (!normalized) {
    return null;
  }
  if (/^#[0-9a-fA-F]{6}$/.test(normalized)) {
    return normalized.toUpperCase();
  }
  return null;
};

const checklistTemplateColumnColorValue = (value?: string | null): string =>
  normalizeChecklistTemplateColor(value) ?? "#001F2B";

const normalizeChecklistTemplateDraftColumns = (
  columns: Array<ChecklistColumnRaw | ChecklistTemplateDraftColumn>,
  options?: { ensureTaskColumn?: boolean }
): ChecklistTemplateDraftColumn[] => {
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
    .map((column) => ({
      ...column,
      system_key: null,
      column_type: normalizeChecklistTemplateColumnType(column.column_type)
    }));

  if (options?.ensureTaskColumn && !customColumns.length) {
    customColumns.push(createTaskChecklistTemplateDraftColumn());
  }

  return [normalizedDueColumn, ...customColumns].map((column, index) => ({
    ...column,
    display_order: index + 1
  }));
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

const validateChecklistTemplateDraftPayload = (
  templateName: string,
  columns: ChecklistTemplateDraftColumn[]
): string | null => {
  if (!templateName.trim()) {
    return "Template name is required";
  }
  const normalizedColumns = normalizeChecklistTemplateDraftColumns(columns);
  if (!normalizedColumns.length) {
    return "Template must include at least one column";
  }
  if (!isChecklistTemplateDueColumn(normalizedColumns[0])) {
    return "Due Relative DTG system column must be first";
  }
  const dueColumns = normalizedColumns.filter((column) => isChecklistTemplateDueColumn(column));
  if (dueColumns.length !== 1) {
    return "Exactly one Due Relative DTG system column is required";
  }
  if (dueColumns[0].column_type !== "RELATIVE_TIME") {
    return "Due Relative DTG system column must be RELATIVE_TIME";
  }
  if (dueColumns[0].is_removable) {
    return "Due Relative DTG system column cannot be removable";
  }
  const invalidType = normalizedColumns.find((column) => !checklistTemplateColumnTypeSet.has(column.column_type));
  if (invalidType) {
    return `Unsupported column type: ${invalidType.column_type}`;
  }
  return null;
};

const createBlankChecklistTemplateDraftColumns = (): ChecklistTemplateDraftColumn[] =>
  normalizeChecklistTemplateDraftColumns([createDueChecklistTemplateDraftColumn(), createTaskChecklistTemplateDraftColumn()], {
    ensureTaskColumn: true
  });

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
  const serverTemplates = templateRecords.value
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) {
        return null;
      }
      return {
        uid,
        name: String(entry.template_name ?? uid),
        columns: toArray<ChecklistColumnRaw>(entry.columns).length,
        source_type: "template" as const,
        task_rows: 0,
        description: String(entry.description ?? "").trim(),
        created_at: String(entry.created_at ?? ""),
        owner: String(entry.created_by_team_member_rns_identity ?? "").trim()
      };
    })
    .filter((entry): entry is ChecklistTemplateOption => entry !== null);

  const csvImportedTemplates = checklistRecords.value
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) {
        return null;
      }
      const originType = String(entry.origin_type ?? "").trim().toUpperCase();
      if (originType !== "CSV_IMPORT") {
        return null;
      }
      if (!isRenderableCsvImportTemplate(entry)) {
        return null;
      }
      return {
        uid,
        name: String(entry.name ?? uid),
        columns: toArray<ChecklistColumnRaw>(entry.columns).length,
        source_type: "csv_import" as const,
        task_rows: toArray<ChecklistTaskRaw>(entry.tasks).length,
        description: String(entry.description ?? "").trim(),
        created_at: String(entry.created_at ?? ""),
        owner: String(entry.created_by_team_member_rns_identity ?? "").trim()
      };
    })
    .filter((entry): entry is ChecklistTemplateOption => entry !== null);

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

const primaryTabs = [
  { id: "mission", label: "Mission" },
  { id: "checklists", label: "Checklists" }
] as const;

const screensByTab: Record<PrimaryTab, Array<{ id: ScreenId; label: string }>> = {
  mission: [
    { id: "missionOverview", label: "Mission Overview" },
    { id: "missionTeamMembers", label: "Mission Team & Members" },
    { id: "assignAssets", label: "Assign Assets to Mission" },
    { id: "assignZones", label: "Assign Zones to Mission" },
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
    actions: ["Refresh", "Broadcast"]
  },
  missionTeamMembers: { title: "Mission Team & Members", subtitle: "Team composition, roles, and capabilities.", actions: ["Add Team", "Add Member"] },
  assignAssets: { title: "Assign Assets to Mission", subtitle: "Bind registered assets to mission tasks and operators.", actions: ["Assign", "Revoke"] },
  assignZones: { title: "Assign Zones to Mission", subtitle: "Zone selection and geographic mission boundaries.", actions: ["Commit", "New Zone"] },
  assetRegistry: { title: "Asset Registry", subtitle: "Hardware inventory, status, and readiness.", actions: ["Deploy", "Filter", "Open Assets"] },
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

const selectedMissionUid = ref("");
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
const checklistTemplateDraftColumns = ref<ChecklistTemplateDraftColumn[]>(createBlankChecklistTemplateDraftColumns());
const teamAllocationModalOpen = ref(false);
const teamAllocationSubmitting = ref(false);
const teamAllocationExistingTeamUid = ref("");
const teamAllocationNewTeamName = ref("");
const teamAllocationNewTeamDescription = ref("");
const memberAllocationModalOpen = ref(false);
const memberAllocationSubmitting = ref(false);
const memberAllocationTeamUid = ref("");
const memberAllocationMemberUid = ref("");
const missionAuditExpandedRows = ref<Record<string, boolean>>({});

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
const isChecklistPrimaryTab = computed(() => primaryTab.value === "checklists");
const showScreenHeader = computed(
  () => !isChecklistPrimaryTab.value || secondaryScreen.value === "checklistImportCsv"
);

const selectedMission = computed(() => missions.value.find((entry) => entry.uid === selectedMissionUid.value));
const isMissionCreateScreen = computed(() => secondaryScreen.value === "missionCreate");
const isMissionEditScreen = computed(() => secondaryScreen.value === "missionEdit");
const isMissionFormScreen = computed(() => isMissionCreateScreen.value || isMissionEditScreen.value);
const onMissionAdvancedPropertiesToggle = (event: Event): void => {
  missionAdvancedPropertiesOpen.value = (event.currentTarget as HTMLDetailsElement).open;
};
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

const checklistMissionLabel = (missionUid: string): string => {
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

const buildChecklistTemplateDraftName = (): string => `Template ${buildTimestampTag().slice(-6)}`;

const applyChecklistTemplateEditorDraft = (payload: {
  selectionUid: string;
  selectionSourceType: ChecklistTemplateSourceType | "";
  mode: ChecklistTemplateEditorMode;
  templateUid: string;
  templateName: string;
  description: string;
  columns: Array<ChecklistColumnRaw | ChecklistTemplateDraftColumn>;
  ensureTaskColumn?: boolean;
}) => {
  checklistTemplateEditorHydrating.value = true;
  checklistTemplateEditorSelectionUid.value = payload.selectionUid;
  checklistTemplateEditorSelectionSourceType.value = payload.selectionSourceType;
  checklistTemplateEditorMode.value = payload.mode;
  checklistTemplateDraftTemplateUid.value = payload.templateUid;
  checklistTemplateDraftName.value = payload.templateName.trim() || buildChecklistTemplateDraftName();
  checklistTemplateDraftDescription.value = payload.description;
  checklistTemplateDraftColumns.value = normalizeChecklistTemplateDraftColumns(payload.columns, {
    ensureTaskColumn: payload.ensureTaskColumn ?? payload.mode !== "csv_readonly"
  });
  checklistTemplateEditorDirty.value = false;
  checklistTemplateEditorHydrating.value = false;
};

const startNewChecklistTemplateDraft = () => {
  applyChecklistTemplateEditorDraft({
    selectionUid: "",
    selectionSourceType: "",
    mode: "create",
    templateUid: "",
    templateName: buildChecklistTemplateDraftName(),
    description: "",
    columns: createBlankChecklistTemplateDraftColumns(),
    ensureTaskColumn: true
  });
};

const selectChecklistTemplateForEditor = (templateUid: string, sourceType: ChecklistTemplateSourceType) => {
  const uid = String(templateUid ?? "").trim();
  if (!uid) {
    return;
  }
  const option =
    checklistTemplateOptions.value.find((entry) => entry.uid === uid && entry.source_type === sourceType) ?? null;
  if (!option) {
    return;
  }
  checklistTemplateSelectionUid.value = option.uid;
  if (option.source_type === "template") {
    const templateRecord =
      templateRecords.value.find((entry) => String(entry.uid ?? "").trim() === option.uid) ?? null;
    if (!templateRecord) {
      toastStore.push("Selected template is unavailable", "warning");
      return;
    }
    applyChecklistTemplateEditorDraft({
      selectionUid: option.uid,
      selectionSourceType: option.source_type,
      mode: "edit",
      templateUid: option.uid,
      templateName: String(templateRecord.template_name ?? option.name),
      description: String(templateRecord.description ?? ""),
      columns: toArray<ChecklistColumnRaw>(templateRecord.columns),
      ensureTaskColumn: true
    });
    return;
  }
  const checklistRecord =
    checklistRecords.value.find((entry) => String(entry.uid ?? "").trim() === option.uid) ?? null;
  if (!checklistRecord) {
    toastStore.push("Selected CSV entry is unavailable", "warning");
    return;
  }
  applyChecklistTemplateEditorDraft({
    selectionUid: option.uid,
    selectionSourceType: option.source_type,
    mode: "csv_readonly",
    templateUid: "",
    templateName: String(checklistRecord.name ?? option.name),
    description: String(checklistRecord.description ?? ""),
    columns: toArray<ChecklistColumnRaw>(checklistRecord.columns),
    ensureTaskColumn: false
  });
};

const syncChecklistTemplateEditorSelection = (preferredUid = "", preferredType: ChecklistTemplateSourceType | "" = "") => {
  const options = checklistTemplateOptions.value;
  if (!options.length) {
    startNewChecklistTemplateDraft();
    return;
  }
  const preferred =
    (preferredUid && preferredType
      ? options.find((entry) => entry.uid === preferredUid && entry.source_type === preferredType)
      : null) ?? null;
  if (preferred) {
    selectChecklistTemplateForEditor(preferred.uid, preferred.source_type);
    return;
  }
  const selected = selectedChecklistTemplateEditorOption.value;
  if (selected) {
    if (checklistTemplateEditorMode.value !== "create") {
      selectChecklistTemplateForEditor(selected.uid, selected.source_type);
    }
    return;
  }
  selectChecklistTemplateForEditor(options[0].uid, options[0].source_type);
};

const mutateChecklistTemplateDraftColumns = (
  mutate: (columns: ChecklistTemplateDraftColumn[]) => ChecklistTemplateDraftColumn[]
) => {
  if (isChecklistTemplateDraftReadonly.value || checklistTemplateEditorSaving.value) {
    return;
  }
  const cloned = checklistTemplateDraftColumns.value.map((column) => ({ ...column }));
  const mutated = mutate(cloned);
  checklistTemplateDraftColumns.value = normalizeChecklistTemplateDraftColumns(mutated, { ensureTaskColumn: true });
};

const setChecklistTemplateColumnName = (columnIndex: number, event: Event) => {
  const value = String((event.target as HTMLInputElement | null)?.value ?? "");
  mutateChecklistTemplateDraftColumns((columns) =>
    columns.map((column, index) =>
      index === columnIndex && !isChecklistTemplateDueColumn(column)
        ? { ...column, column_name: value.trim() || column.column_name }
        : column
    )
  );
};

const setChecklistTemplateColumnType = (columnIndex: number, event: Event) => {
  const value = String((event.target as HTMLSelectElement | null)?.value ?? "");
  mutateChecklistTemplateDraftColumns((columns) =>
    columns.map((column, index) =>
      index === columnIndex && !isChecklistTemplateDueColumn(column)
        ? { ...column, column_type: normalizeChecklistTemplateColumnType(value) }
        : column
    )
  );
};

const setChecklistTemplateColumnEditable = (columnIndex: number, event: Event) => {
  const checked = Boolean((event.target as HTMLInputElement | null)?.checked);
  mutateChecklistTemplateDraftColumns((columns) =>
    columns.map((column, index) =>
      index === columnIndex && !isChecklistTemplateDueColumn(column)
        ? { ...column, column_editable: checked }
        : column
    )
  );
};

const setChecklistTemplateColumnBackgroundColor = (columnIndex: number, event: Event) => {
  const value = String((event.target as HTMLInputElement | null)?.value ?? "");
  mutateChecklistTemplateDraftColumns((columns) =>
    columns.map((column, index) =>
      index === columnIndex
        ? { ...column, background_color: normalizeChecklistTemplateColor(value) }
        : column
    )
  );
};

const setChecklistTemplateColumnTextColor = (columnIndex: number, event: Event) => {
  const value = String((event.target as HTMLInputElement | null)?.value ?? "");
  mutateChecklistTemplateDraftColumns((columns) =>
    columns.map((column, index) =>
      index === columnIndex
        ? { ...column, text_color: normalizeChecklistTemplateColor(value) }
        : column
    )
  );
};

const addChecklistTemplateColumn = () => {
  mutateChecklistTemplateDraftColumns((columns) => {
    const customCount = columns.filter((column) => !isChecklistTemplateDueColumn(column)).length;
    return [
      ...columns,
      {
        column_uid: buildChecklistTemplateColumnUid(),
        column_name: `Field ${customCount + 1}`,
        display_order: columns.length + 1,
        column_type: "SHORT_STRING",
        column_editable: true,
        is_removable: true,
        system_key: null,
        background_color: null,
        text_color: null
      }
    ];
  });
};

const canMoveChecklistTemplateColumnUp = (columnIndex: number): boolean => {
  if (isChecklistTemplateDraftReadonly.value || checklistTemplateEditorSaving.value) {
    return false;
  }
  const column = checklistTemplateDraftColumns.value[columnIndex];
  if (!column || isChecklistTemplateDueColumn(column)) {
    return false;
  }
  if (columnIndex <= 1) {
    return false;
  }
  return true;
};

const canMoveChecklistTemplateColumnDown = (columnIndex: number): boolean => {
  if (isChecklistTemplateDraftReadonly.value || checklistTemplateEditorSaving.value) {
    return false;
  }
  const columns = checklistTemplateDraftColumns.value;
  const column = columns[columnIndex];
  if (!column || isChecklistTemplateDueColumn(column)) {
    return false;
  }
  return columnIndex >= 1 && columnIndex < columns.length - 1;
};

const moveChecklistTemplateColumnUp = (columnIndex: number) => {
  if (!canMoveChecklistTemplateColumnUp(columnIndex)) {
    return;
  }
  mutateChecklistTemplateDraftColumns((columns) => {
    const next = [...columns];
    const previousIndex = columnIndex - 1;
    [next[previousIndex], next[columnIndex]] = [next[columnIndex], next[previousIndex]];
    return next;
  });
};

const moveChecklistTemplateColumnDown = (columnIndex: number) => {
  if (!canMoveChecklistTemplateColumnDown(columnIndex)) {
    return;
  }
  mutateChecklistTemplateDraftColumns((columns) => {
    const next = [...columns];
    const nextIndex = columnIndex + 1;
    [next[nextIndex], next[columnIndex]] = [next[columnIndex], next[nextIndex]];
    return next;
  });
};

const canDeleteChecklistTemplateColumn = (columnIndex: number): boolean => {
  if (isChecklistTemplateDraftReadonly.value || checklistTemplateEditorSaving.value) {
    return false;
  }
  const column = checklistTemplateDraftColumns.value[columnIndex];
  if (!column || isChecklistTemplateDueColumn(column)) {
    return false;
  }
  return Boolean(column.is_removable);
};

const deleteChecklistTemplateColumn = (columnIndex: number) => {
  if (!canDeleteChecklistTemplateColumn(columnIndex)) {
    return;
  }
  mutateChecklistTemplateDraftColumns((columns) => columns.filter((_, index) => index !== columnIndex));
};

const buildChecklistTemplateDraftPayload = () => {
  const templateName = checklistTemplateDraftName.value.trim();
  const validationError = validateChecklistTemplateDraftPayload(templateName, checklistTemplateDraftColumns.value);
  if (validationError) {
    throw new Error(validationError);
  }
  return {
    template_name: templateName,
    description: checklistTemplateDraftDescription.value.trim(),
    columns: toChecklistTemplateColumnPayload(checklistTemplateDraftColumns.value)
  };
};

const saveChecklistTemplateDraft = async () => {
  if (!canSaveChecklistTemplateDraft.value) {
    return;
  }
  const templateUid = checklistTemplateDraftTemplateUid.value.trim();
  if (!templateUid) {
    return;
  }
  checklistTemplateEditorSaving.value = true;
  try {
    const payload = buildChecklistTemplateDraftPayload();
    await patchRequest(`${endpoints.checklistTemplates}/${templateUid}`, { patch: payload });
    await loadWorkspace();
    syncChecklistTemplateEditorSelection(templateUid, "template");
    toastStore.push("Template saved", "success");
  } catch (error) {
    handleApiError(error, "Unable to save template");
  } finally {
    checklistTemplateEditorSaving.value = false;
  }
};

const saveChecklistTemplateDraftAsNew = async () => {
  if (!canSaveChecklistTemplateDraftAsNew.value) {
    return;
  }
  checklistTemplateEditorSaving.value = true;
  try {
    const payload = buildChecklistTemplateDraftPayload();
    const created = await post<TemplateRaw>(endpoints.checklistTemplates, {
      template: {
        ...payload,
        created_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY
      }
    });
    await loadWorkspace();
    const createdUid = String(created.uid ?? "").trim();
    if (createdUid) {
      syncChecklistTemplateEditorSelection(createdUid, "template");
    } else {
      syncChecklistTemplateEditorSelection();
    }
    toastStore.push("Template created", "success");
  } catch (error) {
    handleApiError(error, "Unable to create template");
  } finally {
    checklistTemplateEditorSaving.value = false;
  }
};

const cloneChecklistTemplateDraft = async () => {
  if (!canCloneChecklistTemplateDraft.value) {
    return;
  }
  const templateUid = checklistTemplateDraftTemplateUid.value.trim();
  if (!templateUid) {
    return;
  }
  checklistTemplateEditorSaving.value = true;
  try {
    const baseName = checklistTemplateDraftName.value.trim() || "Template";
    const cloned = await post<TemplateRaw>(`${endpoints.checklistTemplates}/${templateUid}/clone`, {
      template_name: `${baseName} Copy ${buildTimestampTag().slice(-4)}`,
      description: checklistTemplateDraftDescription.value.trim(),
      created_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY
    });
    await loadWorkspace();
    const clonedUid = String(cloned.uid ?? "").trim();
    if (clonedUid) {
      syncChecklistTemplateEditorSelection(clonedUid, "template");
    } else {
      syncChecklistTemplateEditorSelection();
    }
    toastStore.push("Template cloned", "success");
  } catch (error) {
    handleApiError(error, "Unable to clone template");
  } finally {
    checklistTemplateEditorSaving.value = false;
  }
};

const archiveChecklistTemplateDraft = async () => {
  if (!canArchiveChecklistTemplateDraft.value) {
    return;
  }
  const templateUid = checklistTemplateDraftTemplateUid.value.trim();
  if (!templateUid) {
    return;
  }
  const templateName = checklistTemplateDraftName.value.trim() || "Template";
  if (/\[ARCHIVED\]/i.test(templateName)) {
    toastStore.push("Template already archived", "info");
    return;
  }
  checklistTemplateEditorSaving.value = true;
  try {
    await patchRequest(`${endpoints.checklistTemplates}/${templateUid}`, {
      patch: {
        template_name: `${templateName} [ARCHIVED]`
      }
    });
    await loadWorkspace();
    syncChecklistTemplateEditorSelection(templateUid, "template");
    toastStore.push("Template archived", "success");
  } catch (error) {
    handleApiError(error, "Unable to archive template");
  } finally {
    checklistTemplateEditorSaving.value = false;
  }
};

const convertChecklistTemplateDraftToServerTemplate = async () => {
  if (!canConvertChecklistTemplateDraft.value) {
    return;
  }
  checklistTemplateEditorSaving.value = true;
  try {
    const payload = buildChecklistTemplateDraftPayload();
    const created = await post<TemplateRaw>(endpoints.checklistTemplates, {
      template: {
        ...payload,
        created_by_team_member_rns_identity: DEFAULT_SOURCE_IDENTITY
      }
    });
    await loadWorkspace();
    const createdUid = String(created.uid ?? "").trim();
    if (createdUid) {
      syncChecklistTemplateEditorSelection(createdUid, "template");
    } else {
      syncChecklistTemplateEditorSelection();
    }
    toastStore.push("CSV template converted", "success");
  } catch (error) {
    handleApiError(error, "Unable to convert CSV template");
  } finally {
    checklistTemplateEditorSaving.value = false;
  }
};

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

const hasMissionAuditDetails = (value: Record<string, unknown> | null): boolean => {
  if (!value) {
    return false;
  }
  return Object.keys(value).length > 0;
};

const isMissionAuditExpanded = (uid: string): boolean => Boolean(missionAuditExpandedRows.value[uid]);

const toggleMissionAuditExpanded = (uid: string): void => {
  const current = missionAuditExpandedRows.value;
  missionAuditExpandedRows.value = {
    ...current,
    [uid]: !current[uid]
  };
};

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

const checklistOriginLabel = (originType: string): string => {
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

const isChecklistTemplateDeleteBusy = (templateUid: string): boolean => {
  const uid = String(templateUid ?? "").trim();
  if (!uid) {
    return false;
  }
  return Boolean(checklistTemplateDeleteBusyByUid.value[uid]);
};

const deleteChecklistTemplateFromCard = async (
  templateUid: string,
  sourceType: ChecklistTemplateOption["source_type"],
  templateName: string
): Promise<boolean> => {
  const uid = String(templateUid ?? "").trim();
  if (!uid || isChecklistTemplateDeleteBusy(uid)) {
    return false;
  }
  const name = String(templateName ?? uid).trim() || uid;
  const targetLabel = sourceType === "template" ? "template" : "CSV import template";
  if (!window.confirm(`Delete ${targetLabel} "${name}"?`)) {
    return false;
  }
  checklistTemplateDeleteBusyByUid.value = {
    ...checklistTemplateDeleteBusyByUid.value,
    [uid]: true
  };
  try {
    if (sourceType === "template") {
      await deleteRequest(`${endpoints.checklistTemplates}/${uid}`);
    } else {
      await deleteRequest(`${endpoints.checklists}/${uid}`);
      if (selectedChecklistUid.value === uid) {
        selectedChecklistUid.value = "";
      }
      if (checklistDetailUid.value === uid) {
        checklistDetailUid.value = "";
      }
    }
    if (checklistTemplateSelectionUid.value === uid) {
      checklistTemplateSelectionUid.value = "";
    }
    await loadWorkspace();
    toastStore.push(sourceType === "template" ? "Template deleted" : "CSV import template deleted", "success");
    return true;
  } catch (error) {
    handleApiError(
      error,
      sourceType === "template" ? "Unable to delete template" : "Unable to delete CSV import template"
    );
    return false;
  } finally {
    const next = { ...checklistTemplateDeleteBusyByUid.value };
    delete next[uid];
    checklistTemplateDeleteBusyByUid.value = next;
  }
};

const deleteChecklistTemplateDraft = async () => {
  if (!canDeleteChecklistTemplateDraft.value) {
    return;
  }
  const selected = selectedChecklistTemplateEditorOption.value;
  if (!selected) {
    return;
  }
  const removed = await deleteChecklistTemplateFromCard(selected.uid, selected.source_type, selected.name);
  if (!removed) {
    return;
  }
  syncChecklistTemplateEditorSelection();
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
  if (tab === "checklists") {
    if (route.path !== "/checklists") {
      router.push("/checklists").catch(() => undefined);
    }
    return;
  }
  if (route.path === "/checklists") {
    router.push("/missions").catch(() => undefined);
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
    router.push("/missions").catch(() => undefined);
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
  if (!member) {
    throw new Error("No mission member is assigned. Use Add Member before deploying assets.");
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

const readMultiSelectValues = (event: Event): string[] => {
  const target = event.target as HTMLSelectElement | null;
  if (!target) {
    return [];
  }
  return Array.from(target.selectedOptions)
    .map((entry) => entry.value.trim())
    .filter((entry) => entry.length > 0);
};

const onMissionDraftZoneSelectionChange = (event: Event) => {
  missionDraftZoneUids.value = readMultiSelectValues(event);
};

const onMissionDraftAssetSelectionChange = (event: Event) => {
  missionDraftAssetUids.value = readMultiSelectValues(event);
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
  if (!checklistTemplateOptions.value.length) {
    throw new Error("No checklist templates available. Create a template first");
  }
  checklistTemplateNameDraft.value = buildChecklistDraftName();
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
  const filtered = toArray(snapshots).filter((entry) => String(entry.aggregate_uid ?? "") === missionUid);
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
  missionAuditExpandedRows.value = {};
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
  position: relative;
  border: 1px solid rgba(55, 242, 255, 0.24);
  background: rgba(8, 22, 34, 0.78);
  border-radius: 12px;
  padding: 10px;
  display: grid;
  gap: 4px;
  box-shadow: inset 0 0 20px rgba(4, 20, 28, 0.8);
}

.kpi-card::after {
  content: "";
  position: absolute;
  top: 10px;
  right: 12px;
  width: 28px;
  height: 6px;
  background: linear-gradient(90deg, rgba(56, 244, 255, 0.8), transparent);
  opacity: 0.8;
  border-radius: 2px;
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
  font-family: "Orbitron", "Rajdhani", sans-serif;
  letter-spacing: 0.08em;
  color: #ffffff;
  text-shadow:
    0 0 5px rgba(56, 244, 255, 0.9),
    0 0 10px rgba(56, 244, 255, 0.7),
    0 0 20px rgba(56, 244, 255, 0.6),
    0 0 40px rgba(56, 244, 255, 0.35);
}

.registry-grid {
  display: grid;
  grid-template-columns: minmax(260px, 300px) 1fr;
  gap: 18px;
  z-index: 1;
  position: relative;
  margin-top: 14px;
}

.registry-grid-full {
  grid-template-columns: 1fr;
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

.registry-main > .panel-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 10px;
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
  flex-wrap: nowrap;
  gap: 6px;
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(55, 242, 255, 0.55) rgba(4, 18, 29, 0.68);
}

.panel-tabs::-webkit-scrollbar,
.screen-tabs::-webkit-scrollbar,
.checklist-overview-tabs::-webkit-scrollbar {
  height: 8px;
}

.panel-tabs::-webkit-scrollbar-track,
.screen-tabs::-webkit-scrollbar-track,
.checklist-overview-tabs::-webkit-scrollbar-track {
  background: rgba(4, 18, 29, 0.68);
  border-radius: 999px;
}

.panel-tabs::-webkit-scrollbar-thumb,
.screen-tabs::-webkit-scrollbar-thumb,
.checklist-overview-tabs::-webkit-scrollbar-thumb {
  background: rgba(55, 242, 255, 0.5);
  border-radius: 999px;
}

.panel-tabs::-webkit-scrollbar-thumb:hover,
.screen-tabs::-webkit-scrollbar-thumb:hover,
.checklist-overview-tabs::-webkit-scrollbar-thumb:hover {
  background: rgba(55, 242, 255, 0.72);
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
  flex: 0 0 auto;
  white-space: nowrap;
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

.mission-directory-actions {
  margin-top: 12px;
}

.mission-directory-create-button {
  width: 100%;
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

.mission-overview-hud {
  display: grid;
  gap: 12px;
}

.overview-vitals {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.overview-vital-card {
  position: relative;
  border: 1px solid rgba(55, 242, 255, 0.28);
  background: rgba(7, 20, 30, 0.82);
  border-radius: 12px;
  padding: 10px;
  display: grid;
  gap: 5px;
  box-shadow: inset 0 0 18px rgba(2, 14, 22, 0.9);
}

.overview-vital-card::after {
  content: "";
  position: absolute;
  top: 10px;
  right: 12px;
  width: 28px;
  height: 5px;
  background: linear-gradient(90deg, rgba(255, 179, 92, 0.88), transparent);
  border-radius: 2px;
}

.overview-vital-label {
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(211, 248, 255, 0.72);
}

.overview-vital-value {
  font-size: 22px;
  line-height: 1.1;
  letter-spacing: 0.08em;
  color: #ffffff;
  text-shadow: 0 0 8px rgba(55, 242, 255, 0.58);
}

.overview-layout {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.overview-panel {
  gap: 10px;
}

.overview-panel-compact {
  padding: 12px;
  gap: 10px;
}

.overview-panel-wide {
  grid-column: 1 / -1;
}

.overview-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.overview-panel-header h4 {
  margin: 0;
}

.overview-panel-meta {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(161, 240, 255, 0.82);
}

.overview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.overview-compact-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.overview-compact-header h4 {
  margin: 0;
}

.overview-compact-subtitle {
  margin-top: 4px;
  font-size: 11px;
  color: rgba(190, 246, 255, 0.72);
  letter-spacing: 0.08em;
}

.overview-compact-tag {
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: rgba(227, 252, 255, 0.85);
  font-size: 10px;
  border-radius: 999px;
  padding: 4px 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
}

.overview-compact-meta {
  display: grid;
  gap: 8px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  color: rgba(220, 251, 255, 0.86);
}

.overview-compact-meta div {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.overview-compact-meta div span:last-child {
  color: rgba(233, 253, 255, 0.9);
  text-align: right;
  max-width: 65%;
}

.overview-compact-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-compact-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.overview-board {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.overview-board-compact {
  gap: 6px;
}

.overview-board-col {
  border: 1px solid rgba(55, 242, 255, 0.25);
  border-radius: 10px;
  background: rgba(5, 16, 26, 0.76);
  padding: 8px;
  display: grid;
  gap: 6px;
  align-content: start;
}

.overview-board-col-pending {
  border-color: rgba(55, 242, 255, 0.36);
}

.overview-board-col-late {
  border-color: rgba(255, 179, 92, 0.46);
}

.overview-board-col-complete {
  border-color: rgba(62, 242, 180, 0.46);
}

.overview-board-col h5 {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.overview-board-col-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.overview-board-col-head span {
  font-size: 18px;
  letter-spacing: 0.08em;
  line-height: 1;
  color: #ffffff;
}

.lane-list-compact {
  margin: 0;
  max-height: 152px;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(55, 242, 255, 0.52) rgba(4, 18, 29, 0.68);
}

.lane-list-compact li {
  padding: 6px;
  gap: 2px;
}

.lane-list-compact li strong {
  font-size: 10px;
}

.lane-list-compact li span {
  font-size: 9px;
}

.lane-list-compact::-webkit-scrollbar {
  width: 7px;
}

.lane-list-compact::-webkit-scrollbar-track {
  background: rgba(4, 18, 29, 0.68);
  border-radius: 999px;
}

.lane-list-compact::-webkit-scrollbar-thumb {
  background: rgba(55, 242, 255, 0.5);
  border-radius: 999px;
}

.lane-list-compact::-webkit-scrollbar-thumb:hover {
  background: rgba(55, 242, 255, 0.72);
}

.lane-empty {
  border: 1px dashed rgba(55, 242, 255, 0.24);
  border-radius: 8px;
  padding: 8px;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(190, 243, 255, 0.72);
}

.overview-zone-progress {
  position: relative;
  width: 100%;
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(0, 62, 82, 0.74);
}

.overview-zone-progress-value {
  position: absolute;
  inset: 0 auto 0 0;
  background: linear-gradient(90deg, rgba(56, 244, 255, 0.96), rgba(20, 180, 228, 0.76));
}

.overview-zone-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(177, 239, 255, 0.86);
}

.overview-zone-list {
  max-height: 210px;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(55, 242, 255, 0.55) rgba(4, 18, 29, 0.68);
}

.overview-zone-list::-webkit-scrollbar {
  width: 8px;
}

.overview-zone-list::-webkit-scrollbar-track {
  background: rgba(4, 18, 29, 0.68);
  border-radius: 999px;
}

.overview-zone-list::-webkit-scrollbar-thumb {
  background: rgba(55, 242, 255, 0.5);
  border-radius: 999px;
}

.overview-zone-list::-webkit-scrollbar-thumb:hover {
  background: rgba(55, 242, 255, 0.72);
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

.mission-audit-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.mission-audit-subtitle {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(174, 239, 255, 0.78);
}

.mission-audit-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.mission-audit-empty {
  border: 1px dashed rgba(55, 242, 255, 0.28);
  border-radius: 10px;
  padding: 12px;
  font-size: 12px;
  color: rgba(202, 245, 255, 0.82);
}

.mission-audit-table-shell {
  border: 1px solid rgba(55, 242, 255, 0.22);
  border-radius: 10px;
  background: rgba(5, 16, 26, 0.82);
  overflow: auto;
  max-height: clamp(280px, calc(100vh - 360px), 640px);
  scrollbar-width: thin;
  scrollbar-color: rgba(55, 242, 255, 0.55) rgba(4, 18, 29, 0.68);
}

.mission-audit-table-shell::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.mission-audit-table-shell::-webkit-scrollbar-track {
  background: rgba(4, 18, 29, 0.68);
  border-radius: 999px;
}

.mission-audit-table-shell::-webkit-scrollbar-thumb {
  background: rgba(55, 242, 255, 0.5);
  border-radius: 999px;
  border: 2px solid rgba(4, 18, 29, 0.68);
}

.mission-audit-table-shell::-webkit-scrollbar-thumb:hover {
  background: rgba(55, 242, 255, 0.72);
}

.mission-audit-table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
  font-size: 12px;
}

.mission-audit-table th {
  text-align: left;
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(173, 238, 255, 0.72);
  padding: 10px 12px;
  border-bottom: 1px solid rgba(55, 242, 255, 0.24);
  white-space: nowrap;
}

.mission-audit-table td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(55, 242, 255, 0.16);
  vertical-align: top;
}

.mission-audit-row:hover td {
  background: rgba(10, 25, 36, 0.66);
}

.mission-audit-cell-message {
  color: rgba(223, 252, 255, 0.94);
}

.mission-audit-cell-type {
  width: 1%;
  white-space: nowrap;
}

.mission-audit-type-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgba(55, 242, 255, 0.42);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(171, 241, 255, 0.95);
  background: rgba(3, 14, 24, 0.82);
}

.mission-audit-cell-time {
  width: 1%;
  white-space: nowrap;
  color: rgba(198, 244, 255, 0.78);
}

.mission-audit-cell-action {
  width: 1%;
  text-align: right;
  white-space: nowrap;
}

.mission-audit-toggle {
  border: 1px solid rgba(55, 242, 255, 0.42);
  border-radius: 999px;
  background: rgba(6, 18, 28, 0.82);
  color: #39f2ff;
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 4px 10px;
  cursor: pointer;
}

.mission-audit-toggle:disabled {
  opacity: 0.35;
  cursor: default;
}

.mission-audit-details-row td {
  padding: 0;
  border-bottom: 1px solid rgba(55, 242, 255, 0.2);
}

.mission-audit-details {
  padding: 10px;
  background: rgba(2, 10, 18, 0.88);
}

.checklist-workspace {
  gap: 12px;
  --checklist-scroll-max-height: clamp(260px, calc(100vh - 340px), 640px);
}

.checklist-manager-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
}

.checklist-manager-search {
  margin: 0;
}

.checklist-manager-search input {
  min-height: 42px;
}

.checklist-manager-actions {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.checklist-overview-tabs {
  display: inline-flex;
  gap: 2px;
  border: 1px solid rgba(55, 242, 255, 0.34);
  border-radius: 8px;
  padding: 2px;
  width: fit-content;
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  background: rgba(2, 10, 16, 0.85);
  scrollbar-width: thin;
  scrollbar-color: rgba(55, 242, 255, 0.55) rgba(4, 18, 29, 0.68);
}

.checklist-overview-tab {
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: rgba(207, 249, 255, 0.86);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-size: 10px;
  padding: 7px 12px;
  cursor: pointer;
}

.checklist-overview-tab.active {
  background: rgba(23, 164, 225, 0.35);
  color: #7ef4ff;
}

.checklist-overview-list {
  display: grid;
  gap: 10px;
  max-height: var(--checklist-scroll-max-height);
  overflow-y: auto;
  overscroll-behavior: contain;
  align-content: start;
  padding-right: 6px;
  scrollbar-width: thin;
  scrollbar-color: rgba(55, 242, 255, 0.55) rgba(4, 18, 29, 0.68);
}

.checklist-template-list {
  min-height: var(--checklist-scroll-max-height);
}

.checklist-template-workspace {
  display: grid;
  grid-template-columns: minmax(280px, 0.92fr) minmax(0, 1.48fr);
  gap: 10px;
  min-height: var(--checklist-scroll-max-height);
  max-height: var(--checklist-scroll-max-height);
}

.checklist-template-library-pane,
.checklist-template-editor-pane {
  border: 1px solid rgba(55, 242, 255, 0.32);
  border-radius: 10px;
  background: rgba(6, 18, 28, 0.76);
  padding: 10px;
  display: grid;
  gap: 10px;
  min-height: 0;
}

.checklist-template-library-head {
  display: grid;
  gap: 4px;
}

.checklist-template-library-head h4 {
  margin: 0;
  font-size: 18px;
  letter-spacing: 0.05em;
  text-transform: none;
}

.checklist-template-library-head p {
  margin: 0;
  font-size: 12px;
  color: rgba(190, 243, 255, 0.78);
}

.checklist-template-library-list {
  display: grid;
  gap: 8px;
  overflow-y: auto;
  overscroll-behavior: contain;
  align-content: start;
  min-height: 0;
  padding-right: 6px;
  scrollbar-width: thin;
  scrollbar-color: rgba(55, 242, 255, 0.55) rgba(4, 18, 29, 0.68);
}

.checklist-overview-list::-webkit-scrollbar,
.checklist-template-library-list::-webkit-scrollbar,
.checklist-template-column-scroll::-webkit-scrollbar {
  width: 10px;
}

.checklist-overview-list::-webkit-scrollbar-track,
.checklist-template-library-list::-webkit-scrollbar-track,
.checklist-template-column-scroll::-webkit-scrollbar-track {
  background: rgba(4, 18, 29, 0.68);
  border-radius: 999px;
}

.checklist-overview-list::-webkit-scrollbar-thumb,
.checklist-template-library-list::-webkit-scrollbar-thumb,
.checklist-template-column-scroll::-webkit-scrollbar-thumb {
  background: rgba(55, 242, 255, 0.5);
  border-radius: 999px;
  border: 2px solid rgba(4, 18, 29, 0.68);
}

.checklist-overview-list::-webkit-scrollbar-thumb:hover,
.checklist-template-library-list::-webkit-scrollbar-thumb:hover,
.checklist-template-column-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(55, 242, 255, 0.72);
}

.checklist-template-library-item {
  border: 1px solid rgba(55, 242, 255, 0.32);
  border-radius: 10px;
  background: rgba(6, 18, 28, 0.72);
  padding: 12px;
  display: grid;
  gap: 8px;
  text-align: left;
  color: #dffcff;
  width: 100%;
  cursor: pointer;
  font-family: inherit;
}

.checklist-template-library-item:hover {
  border-color: rgba(55, 242, 255, 0.7);
  background: rgba(10, 28, 41, 0.86);
}

.checklist-template-library-item.active {
  border-color: rgba(55, 242, 255, 0.9);
  box-shadow: inset 0 0 0 1px rgba(55, 242, 255, 0.28);
}

.checklist-template-head {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.checklist-template-head h4 {
  margin: 0;
  font-size: 16px;
  letter-spacing: 0.05em;
  text-transform: none;
}

.checklist-template-library-item p {
  margin: 0;
  font-size: 12px;
  color: rgba(190, 243, 255, 0.88);
}

.checklist-template-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(155, 237, 255, 0.88);
}

.checklist-template-editor-pane {
  grid-template-rows: auto 1fr;
}

.checklist-template-editor-header {
  display: grid;
  gap: 8px;
}

.checklist-template-editor-header h4 {
  margin: 0;
  font-size: 18px;
  letter-spacing: 0.06em;
  text-transform: none;
}

.checklist-template-editor-header p {
  margin: 0;
  font-size: 12px;
  color: rgba(190, 243, 255, 0.82);
}

.checklist-template-editor-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.checklist-template-editor-form {
  display: grid;
  gap: 10px;
  min-height: 0;
}

.checklist-template-editor-note {
  margin: 0;
  font-size: 11px;
  color: rgba(186, 240, 255, 0.86);
  letter-spacing: 0.06em;
}

.checklist-template-column-scroll {
  border: 1px solid rgba(55, 242, 255, 0.24);
  border-radius: 8px;
  background: rgba(3, 12, 20, 0.68);
  padding: 8px;
  overflow: auto;
  max-height: calc(var(--checklist-scroll-max-height) - 250px);
  min-height: 180px;
  scrollbar-width: thin;
  scrollbar-color: rgba(55, 242, 255, 0.55) rgba(4, 18, 29, 0.68);
}

.checklist-template-column-table {
  table-layout: fixed;
}

.checklist-template-column-input {
  width: 100%;
  border: 1px solid rgba(55, 242, 255, 0.32);
  border-radius: 6px;
  background: rgba(5, 16, 26, 0.9);
  color: #dffcff;
  font-family: inherit;
  font-size: 11px;
  padding: 6px 8px;
}

.checklist-template-column-checkbox {
  text-align: center;
}

.checklist-template-color-input {
  width: 44px;
  height: 28px;
  border: 1px solid rgba(55, 242, 255, 0.35);
  border-radius: 6px;
  background: transparent;
  padding: 0;
}

.checklist-template-column-actions {
  display: inline-flex;
  gap: 6px;
  flex-wrap: wrap;
}

.checklist-overview-card {
  width: 100%;
  border: 1px solid rgba(55, 242, 255, 0.35);
  background: rgba(4, 16, 24, 0.78);
  border-radius: 10px;
  color: #dffcff;
  padding: 14px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  text-align: left;
}

.checklist-overview-card:hover {
  border-color: rgba(55, 242, 255, 0.75);
  background: rgba(9, 24, 35, 0.88);
}

.checklist-overview-content {
  display: grid;
  gap: 10px;
}

.checklist-overview-head {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.checklist-overview-head h4 {
  margin: 0;
  font-size: 16px;
  letter-spacing: 0.06em;
  text-transform: none;
}

.checklist-overview-content p {
  margin: 0;
  font-size: 13px;
  color: rgba(202, 245, 255, 0.9);
}

.checklist-overview-meta {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 12px;
  color: rgba(159, 238, 255, 0.9);
}

.checklist-overview-stats {
  display: grid;
  gap: 8px;
  justify-items: end;
  min-width: 250px;
}

.checklist-overview-counts {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: rgba(133, 241, 255, 0.92);
}

.checklist-overview-arrow {
  font-size: 26px;
  color: #2be8ff;
  line-height: 1;
}

.checklist-chip-row {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
}

.checklist-chip {
  border: 1px solid rgba(55, 242, 255, 0.35);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
}

.checklist-chip-info {
  border-color: rgba(47, 214, 255, 0.65);
  color: #53efff;
  background: rgba(47, 214, 255, 0.12);
}

.checklist-chip-success {
  border-color: rgba(58, 244, 179, 0.62);
  color: #42f2b2;
  background: rgba(43, 199, 141, 0.16);
}

.checklist-chip-warning {
  border-color: rgba(255, 178, 92, 0.72);
  color: #ffb35c;
  background: rgba(255, 179, 92, 0.16);
}

.checklist-chip-muted {
  border-color: rgba(139, 176, 198, 0.42);
  color: rgba(200, 221, 233, 0.92);
  background: rgba(92, 118, 133, 0.18);
}

.checklist-progress-track {
  position: relative;
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: rgba(0, 64, 84, 0.72);
  overflow: hidden;
}

.checklist-progress-track.compact {
  max-width: 240px;
}

.checklist-progress-value {
  position: absolute;
  inset: 0 auto 0 0;
  background: linear-gradient(90deg, rgba(33, 223, 255, 0.95), rgba(17, 178, 226, 0.8));
}

.checklist-detail-view {
  display: grid;
  gap: 12px;
}

.checklist-detail-header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 12px;
  align-items: start;
}

.checklist-detail-title {
  display: grid;
  gap: 7px;
}

.checklist-detail-actions {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-self: start;
}

.checklist-detail-title h4 {
  margin: 0;
  font-size: 38px;
  letter-spacing: 0.06em;
  text-transform: none;
}

.checklist-detail-title p {
  margin: 0;
  font-size: 20px;
  color: rgba(182, 242, 255, 0.92);
}

.checklist-detail-progress {
  text-align: right;
  display: grid;
  justify-items: end;
  gap: 2px;
}

.checklist-detail-progress strong {
  font-size: 44px;
  line-height: 1;
  color: #2fe7ff;
}

.checklist-detail-progress span {
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 11px;
  color: rgba(167, 242, 255, 0.88);
}

.checklist-detail-summary {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  font-size: 18px;
  color: rgba(130, 239, 255, 0.96);
}

.checklist-task-toolbar {
  border: 1px solid rgba(55, 242, 255, 0.28);
  border-radius: 10px;
  padding: 12px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  background: rgba(7, 17, 27, 0.68);
}

.checklist-task-input {
  display: grid;
  gap: 4px;
}

.checklist-task-input input {
  width: 120px;
  border: 1px solid rgba(55, 242, 255, 0.32);
  border-radius: 7px;
  background: rgba(4, 13, 22, 0.85);
  color: #ddfbff;
  padding: 8px 10px;
  font-size: 13px;
}

.checklist-task-input span {
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(204, 248, 255, 0.72);
}

.checklist-detail-table td {
  vertical-align: top;
}

.checklist-row-complete td {
  background: rgba(125, 192, 84, 0.78);
  color: #072312;
}

.checklist-done-button {
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
}

.checklist-done-button:disabled {
  cursor: wait;
  opacity: 0.7;
}

.checklist-done-indicator {
  width: 20px;
  height: 20px;
  border: 1px solid rgba(190, 214, 225, 0.42);
  border-radius: 3px;
  display: inline-grid;
  place-items: center;
  color: transparent;
}

.checklist-done-indicator.done {
  border-color: rgba(58, 244, 179, 0.62);
  background: rgba(58, 244, 179, 0.2);
  color: #42f2b2;
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

.field-grid.single-col {
  grid-template-columns: 1fr;
}

.field-control {
  display: grid;
  gap: 6px;
}

.field-control.full {
  grid-column: 1 / -1;
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

.template-modal {
  display: grid;
  gap: 12px;
}

.template-modal-list {
  display: grid;
  gap: 8px;
}

.template-modal-hint {
  margin: 0;
  font-size: 11px;
  color: rgba(204, 248, 255, 0.76);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.template-modal-empty {
  margin: 0;
  font-size: 12px;
  color: rgba(204, 248, 255, 0.75);
}

.template-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.template-modal :deep(.cui-combobox) {
  width: 100%;
}

.mission-allocation-modal {
  gap: 14px;
}

.allocation-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.allocation-grid.single-column {
  grid-template-columns: 1fr;
}

.allocation-card {
  border: 1px solid rgba(55, 242, 255, 0.28);
  border-radius: 12px;
  padding: 12px;
  background: linear-gradient(145deg, rgba(8, 24, 36, 0.86), rgba(4, 12, 20, 0.94));
  box-shadow: inset 0 0 0 1px rgba(55, 242, 255, 0.12), 0 10px 22px rgba(1, 8, 14, 0.45);
  display: grid;
  gap: 10px;
}

.allocation-card h4 {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(216, 251, 255, 0.92);
}

.allocation-card-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.field-control input[type="file"] {
  padding: 6px;
}

.csv-upload-native {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.csv-upload-picker {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.csv-upload-filename {
  font-size: 12px;
  color: rgba(201, 248, 255, 0.9);
}

.csv-meta {
  margin-top: 10px;
}

.csv-preview {
  display: grid;
  gap: 8px;
}

.csv-preview-note {
  margin: 0;
  font-size: 10px;
  color: rgba(205, 248, 255, 0.7);
  letter-spacing: 0.1em;
  text-transform: uppercase;
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

  .overview-vitals {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .overview-layout,
  .overview-board {
    grid-template-columns: 1fr;
  }

  .checklist-manager-controls {
    grid-template-columns: 1fr;
  }

  .checklist-manager-actions {
    justify-content: flex-start;
  }

  .checklist-workspace {
    --checklist-scroll-max-height: clamp(220px, calc(100vh - 320px), 520px);
  }

  .checklist-template-workspace {
    grid-template-columns: 1fr;
    max-height: none;
  }

  .checklist-template-library-pane {
    max-height: 220px;
  }

  .checklist-overview-card {
    grid-template-columns: 1fr;
  }

  .checklist-overview-stats {
    justify-items: start;
    min-width: 0;
  }

  .checklist-detail-header {
    grid-template-columns: 1fr;
  }

  .checklist-detail-progress {
    justify-items: start;
    text-align: left;
  }
}

@media (max-width: 800px) {
  .mission-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .overview-vitals {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .field-grid,
  .board-lanes,
  .allocation-grid {
    grid-template-columns: 1fr;
  }

  .registry-top {
    grid-template-columns: 1fr;
  }

  .registry-status {
    justify-content: center;
    flex-wrap: wrap;
  }

  .checklist-overview-meta,
  .checklist-overview-counts,
  .checklist-detail-summary {
    gap: 10px;
    font-size: 12px;
  }

  .checklist-detail-title h4 {
    font-size: 24px;
  }

  .checklist-detail-title p {
    font-size: 14px;
  }

  .checklist-detail-progress strong {
    font-size: 30px;
  }

  .checklist-template-head {
    align-items: flex-start;
  }

  .checklist-workspace {
    --checklist-scroll-max-height: clamp(190px, calc(100vh - 290px), 420px);
  }

  .checklist-template-column-actions {
    width: 100%;
  }

  .checklist-template-column-scroll {
    max-height: 260px;
  }
}
</style>

