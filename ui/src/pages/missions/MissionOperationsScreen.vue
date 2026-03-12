<template>
  <div v-if="secondaryScreen === 'missionTeamMembers'" class="screen-grid two-col">
    <article class="stage-card stage-card-teams">
      <h4>Teams</h4>
      <ul class="stack-list stack-list-teams">
        <li v-for="team in teamSummaries" :key="team.uid">
          <div class="team-summary-heading">
            <strong>{{ team.name }}</strong>
            <span class="team-summary-count">{{ team.memberCount }} {{ team.memberCount === 1 ? "member" : "members" }}</span>
          </div>
          <span>{{ team.description || "No team description available." }}</span>
        </li>
        <li v-if="!teamSummaries.length" class="stack-list-empty">
          <strong>No Teams Linked</strong>
          <span>Add a team to the mission to begin tracking member status.</span>
        </li>
      </ul>
    </article>

    <article class="stage-card stage-card-status-board">
      <div class="status-board-header">
        <div>
          <h4>Member Status Board</h4>
          <p class="stage-card-copy">Folded cards show each member's aggregated overall status. Expand a card for the six dimensions.</p>
        </div>
        <span class="status-board-badge">{{ missionMembers.length }} nodes</span>
      </div>
      <div v-if="sortedMissionMembers.length" class="mission-member-status-grid">
        <MissionMemberStatusCard
          v-for="member in sortedMissionMembers"
          :key="member.uid"
          :member="member"
          :pending-dimensions="pendingDimensionsByMember.get(member.uid) ?? []"
          @cycle-status="emit('cycle-status', member.uid, $event)"
        />
      </div>
      <p v-else class="builder-preview">No team members are assigned to this mission yet.</p>
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
import { computed } from "vue";
import BaseButton from "../../components/BaseButton.vue";
import MissionMemberStatusCard from "./MissionMemberStatusCard.vue";
import { compareMissionMemberStatuses } from "./mission-member-status";
import type { EamStatus } from "./mission-member-status";
import type { MissionMemberStatusKey } from "./mission-member-status";

interface MissionTeamSummary {
  uid: string;
  name: string;
  description: string;
}

interface MissionMemberSummary {
  uid: string;
  callsign: string;
  teamUid: string;
  teamName: string;
  role: string;
  capabilities: string[];
  overallStatus: EamStatus;
  securityStatus: EamStatus;
  capabilityStatus: EamStatus;
  preparednessStatus: EamStatus;
  medicalStatus: EamStatus;
  mobilityStatus: EamStatus;
  commsStatus: EamStatus;
  scorePercent: number;
  reportedAt: string;
  isExpired: boolean;
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

const props = defineProps<{
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
  pendingStatusKeys: string[];
}>();

const emit = defineEmits<{
  (event: "cycle-status", memberUid: string, dimension: MissionMemberStatusKey): void;
}>();

const teamSummaries = computed(() => {
  const memberCounts = new Map<string, number>();
  props.missionMembers.forEach((member) => {
    const key = member.teamUid || "unassigned";
    memberCounts.set(key, (memberCounts.get(key) ?? 0) + 1);
  });
  return props.missionTeams.map((team) => ({
    ...team,
    memberCount: memberCounts.get(team.uid) ?? 0
  }));
});

const sortedMissionMembers = computed(() => {
  return [...props.missionMembers].sort((left, right) => {
    const statusDelta = compareMissionMemberStatuses(left.overallStatus, right.overallStatus);
    if (statusDelta !== 0) {
      return statusDelta;
    }
    const teamDelta = left.teamName.localeCompare(right.teamName);
    if (teamDelta !== 0) {
      return teamDelta;
    }
    return left.callsign.localeCompare(right.callsign);
  });
});

const pendingDimensionsByMember = computed(() => {
  const map = new Map<string, MissionMemberStatusKey[]>();
  props.pendingStatusKeys.forEach((entry) => {
    const [memberUid, dimension] = entry.split(":");
    if (!memberUid || !dimension) {
      return;
    }
    const current = map.get(memberUid) ?? [];
    map.set(memberUid, [...current, dimension as MissionMemberStatusKey]);
  });
  return map;
});
</script>

<style scoped src="./MissionOperationsScreen.css"></style>
