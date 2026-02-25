<template>
  <div v-if="secondaryScreen === 'missionTeamMembers'" class="screen-grid two-col">
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
      <div class="mission-asset-list-shell">
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
      </div>
      <div v-if="secondaryScreen === 'assetRegistry'" class="mission-asset-registry-actions">
        <BaseButton size="sm" variant="secondary" icon-left="refresh" @click="previewAction('Refresh')">
          Refresh
        </BaseButton>
        <BaseButton size="sm" variant="secondary" icon-left="plus" @click="previewAction('Deploy')">
          New Asset
        </BaseButton>
        <BaseButton size="sm" variant="secondary" icon-left="layers" @click="previewAction('Open Assets')">
          Asset Inventory
        </BaseButton>
      </div>
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
          <span>{{ selectedMissionTopic || "-" }}</span>
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
</template>

<script setup lang="ts">
import BaseButton from "../../components/BaseButton.vue";

interface MissionTeamSummary {
  uid: string;
  name: string;
  description: string;
}

interface MissionMemberSummary {
  uid: string;
  callsign: string;
  role: string;
  capabilities: string[];
}

interface MissionAssetSummary {
  uid: string;
  name: string;
  type: string;
  status: string;
}

interface MissionAssignmentSummary {
  uid: string;
  task: string;
  member: string;
  assets: string[];
}

interface MissionZoneSummary {
  uid: string;
  name: string;
  assigned: boolean;
}

defineProps<{
  secondaryScreen: string;
  showAssetArea: boolean;
  missionTeams: MissionTeamSummary[];
  missionMembers: MissionMemberSummary[];
  missionAssets: MissionAssetSummary[];
  missionAssignments: MissionAssignmentSummary[];
  zones: MissionZoneSummary[];
  assignedZones: MissionZoneSummary[];
  zoneCoveragePercent: number;
  selectedMissionTopic: string;
  previewAction: (action: string) => void | Promise<void>;
  toggleZone: (zoneUid: string) => void | Promise<void>;
}>();
</script>

<style scoped src="./MissionOperationsScreen.css"></style>
