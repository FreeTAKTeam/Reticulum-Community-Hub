<template>
  <div class="users-registry">
    <div class="registry-shell">
      <header class="registry-top">
        <div class="registry-title">User Registry</div>
        <div class="registry-status">
          <OnlineHelpLauncher />
          <span class="cui-status-pill" :class="connectionClass">{{ connectionLabel }}</span>
          <span class="cui-status-pill" :class="wsClass">{{ wsLabel }}</span>
          <span class="status-url">{{ baseUrl }}</span>
        </div>
      </header>

      <div class="registry-grid">
        <aside class="panel registry-tree">
          <div class="panel-header">
            <div>
              <div class="panel-title">Identity Console</div>
              <div class="panel-subtitle">Access Surface</div>
            </div>
            <div class="panel-chip">{{ totalRecords }} entries</div>
          </div>

          <div class="tree-list">
            <button class="tree-item" :class="{ active: activeTab === 'clients' }" type="button" @click="activeTab = 'clients'">
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">Users</span>
              <span class="tree-count">{{ usersStore.clients.length }}</span>
            </button>
            <button class="tree-item" :class="{ active: activeTab === 'identities' }" type="button" @click="activeTab = 'identities'">
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">Identities</span>
              <span class="tree-count">{{ usersStore.identities.length }}</span>
            </button>
            <button class="tree-item" :class="{ active: activeTab === 'routing' }" type="button" @click="activeTab = 'routing'">
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">Routing</span>
              <span class="tree-count">{{ routingDestinations.length }}</span>
            </button>
            <button class="tree-item" :class="{ active: activeTab === 'teams' }" type="button" @click="activeTab = 'teams'">
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">Teams</span>
              <span class="tree-count">{{ teamRecords.length }}</span>
            </button>
            <button
              class="tree-item"
              :class="{ active: activeTab === 'team-members' }"
              type="button"
              @click="activeTab = 'team-members'"
            >
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">Team Members</span>
              <span class="tree-count">{{ teamMemberRecords.length }}</span>
            </button>
          </div>

          <div v-if="activeTab === 'clients'" class="tree-search">
            <input v-model="clientFilter" type="text" placeholder="Filter users by name/hash" />
          </div>
          <div v-else-if="activeTab === 'identities'" class="tree-search">
            <input v-model="identityFilter" type="text" placeholder="Filter identities by name/hash" />
          </div>
          <div v-else-if="activeTab === 'teams'" class="tree-search">
            <input v-model="teamFilter" type="text" placeholder="Filter teams by name/mission" />
          </div>
          <div v-else-if="activeTab === 'team-members'" class="tree-search">
            <input v-model="teamMemberFilter" type="text" placeholder="Filter members by callsign/identity" />
          </div>
          <div v-else class="tree-note">
            Routing snapshot loads automatically when this tab is opened.
          </div>
        </aside>

        <section class="panel registry-main">
          <div class="panel-header">
            <div>
              <div class="panel-title">{{ activeTabTitle }}</div>
              <div class="panel-subtitle">Identity and Transport Operations</div>
            </div>
            <div class="panel-tabs">
              <button class="panel-tab" :class="{ active: activeTab === 'clients' }" type="button" @click="activeTab = 'clients'">
                Users
              </button>
              <button class="panel-tab" :class="{ active: activeTab === 'identities' }" type="button" @click="activeTab = 'identities'">
                Identities
              </button>
              <button class="panel-tab" :class="{ active: activeTab === 'routing' }" type="button" @click="activeTab = 'routing'">
                Routing
              </button>
              <button class="panel-tab" :class="{ active: activeTab === 'teams' }" type="button" @click="activeTab = 'teams'">
                Teams
              </button>
              <button
                class="panel-tab"
                :class="{ active: activeTab === 'team-members' }"
                type="button"
                @click="activeTab = 'team-members'"
              >
                Team Members
              </button>
            </div>
          </div>

          <LoadingSkeleton v-if="usersStore.loading && (activeTab === 'clients' || activeTab === 'identities')" />
          <div v-else>
            <div v-if="activeTab === 'clients'" class="card-grid">
              <div
                v-for="(client, index) in pagedClients"
                :key="`client-${client.id ?? index}`"
                class="registry-card cui-panel"
              >
                <div class="registry-card-header">
                  <div>
                    <div class="registry-card-title">
                      {{ resolveIdentityLabel(resolveClientDisplayName(client), client.id) }}
                    </div>
                    <div class="registry-card-subtitle mono">{{ client.id || "Unknown destination" }}</div>
                  </div>
                  <div class="registry-card-tag">{{ clientTag(client.last_seen_at) }}</div>
                </div>
                <div class="registry-card-meta">
                  <div><span>Last Seen</span><span>{{ formatTimestamp(client.last_seen_at) }}</span></div>
                  <div><span>Metadata</span><span class="mono">{{ formatMetadata(client.metadata) }}</span></div>
                </div>
                <div class="registry-card-actions">
                  <BaseButton variant="danger" icon-left="ban" @click="actOnClient(client.id, 'Ban')">Ban</BaseButton>
                  <BaseButton variant="success" icon-left="unban" @click="actOnClient(client.id, 'Unban')">Unban</BaseButton>
                  <BaseButton variant="secondary" icon-left="blackhole" @click="actOnClient(client.id, 'Blackhole')">Blackhole</BaseButton>
                  <BaseButton variant="secondary" icon-left="undo" @click="leaveClient(client.id)">Leave</BaseButton>
                </div>
              </div>
              <div v-if="pagedClients.length === 0" class="panel-empty">No users match the current filter.</div>
              <BasePagination
                v-if="filteredClients.length"
                v-model:page="clientsPage"
                class="panel-pagination"
                :page-size="clientsPageSize"
                :total="filteredClients.length"
              />
            </div>

            <div v-else-if="activeTab === 'identities'" class="card-grid">
              <div
                v-for="(identity, index) in pagedIdentities"
                :key="`identity-${identity.id ?? index}`"
                class="registry-card cui-panel"
              >
                <div class="registry-card-header">
                  <div>
                    <div class="registry-card-title">{{ resolveIdentityLabel(identity.display_name, identity.id) }}</div>
                    <div class="registry-card-subtitle mono">{{ identity.id || "Unknown destination" }}</div>
                  </div>
                  <div class="registry-card-tag">{{ identity.status || "Unknown" }}</div>
                </div>
                <div class="registry-card-meta">
                  <div><span>Last Seen</span><span>{{ formatTimestamp(identity.last_seen) }}</span></div>
                  <div><span>Status</span><span>{{ identity.status || "-" }}</span></div>
                </div>
                <div class="registry-card-badges">
                  <BaseBadge v-if="identity.banned" tone="danger">Banned</BaseBadge>
                  <BaseBadge v-if="identity.blackholed" tone="warning">Blackholed</BaseBadge>
                </div>
                <div class="registry-card-actions">
                  <BaseButton
                    variant="secondary"
                    icon-left="plus"
                    :disabled="isIdentityJoined(identity.id)"
                    @click="joinIdentity(identity.id)"
                  >
                    {{ isIdentityJoined(identity.id) ? "Joined" : "Join" }}
                  </BaseButton>
                </div>
              </div>
              <div v-if="pagedIdentities.length === 0" class="panel-empty">No identities match the current filter.</div>
              <BasePagination
                v-if="filteredIdentities.length"
                v-model:page="identitiesPage"
                class="panel-pagination"
                :page-size="identitiesPageSize"
                :total="filteredIdentities.length"
              />
            </div>

            <div v-else-if="activeTab === 'teams'" class="card-grid">
              <div v-if="teamsLoading" class="panel-empty">Loading teams...</div>
              <template v-else>
                <div v-for="team in pagedTeams" :key="team.uid" class="registry-card cui-panel">
                  <div class="registry-card-header">
                    <div>
                      <div class="registry-card-title">{{ team.team_name || "Unnamed team" }}</div>
                      <div class="registry-card-subtitle mono">{{ team.uid }}</div>
                    </div>
                    <div class="registry-card-tag">{{ team.color || "UNSPECIFIED" }}</div>
                  </div>
                  <div class="registry-card-meta">
                    <div><span>Missions</span><span>{{ teamMissionLabels(team).join(", ") || "-" }}</span></div>
                    <div><span>Description</span><span>{{ team.team_description || "-" }}</span></div>
                    <div><span>Updated</span><span>{{ formatTimestamp(team.updated_at || team.created_at) }}</span></div>
                  </div>
                  <div class="registry-card-actions">
                    <BaseButton variant="secondary" icon-left="users" @click="manageTeamMembers(team.uid)">
                      Members
                    </BaseButton>
                    <BaseButton variant="secondary" icon-left="edit" @click="openTeamEditor(team)">Edit</BaseButton>
                    <BaseButton variant="danger" icon-left="trash" @click="deleteTeam(team.uid)">Delete</BaseButton>
                  </div>
                </div>
                <div v-if="pagedTeams.length === 0" class="panel-empty">No teams match the current filter.</div>
                <BasePagination
                  v-if="filteredTeams.length"
                  v-model:page="teamsPage"
                  class="panel-pagination"
                  :page-size="teamsPageSize"
                  :total="filteredTeams.length"
                />
              </template>
            </div>

            <div v-else-if="activeTab === 'team-members'" class="card-grid">
              <div v-if="teamMembersLoading" class="panel-empty">Loading team members...</div>
              <template v-else>
                <div v-for="member in pagedTeamMembers" :key="member.uid" class="registry-card cui-panel">
                  <div class="registry-card-header">
                    <div>
                      <div class="registry-card-title">{{ teamMemberPrimaryLabel(member) }}</div>
                      <div class="registry-card-subtitle mono">{{ member.rns_identity || "-" }}</div>
                    </div>
                    <div class="registry-card-tag">{{ member.role || "TEAM_MEMBER" }}</div>
                  </div>
                  <div class="registry-card-meta">
                    <div>
                      <span>UID</span>
                      <span class="mono" :title="member.uid || '-'">{{ member.uid ? shortHash(member.uid, 4, 4) : "-" }}</span>
                    </div>
                    <div><span>Team</span><span>{{ teamNameForMember(member.team_uid) }}</span></div>
                    <div><span>Display Name</span><span>{{ member.display_name || "-" }}</span></div>
                    <div><span>Availability</span><span>{{ member.availability || "-" }}</span></div>
                  </div>
                  <div class="registry-card-badges">
                    <BaseBadge tone="neutral">Clients: {{ toStringList(member.client_identities).length }}</BaseBadge>
                    <BaseBadge v-if="member.certifications?.length" tone="success">
                      Certs: {{ member.certifications.length }}
                    </BaseBadge>
                  </div>
                  <div class="registry-card-actions">
                    <BaseButton variant="secondary" icon-left="edit" @click="openTeamMemberEditor(member)">Edit</BaseButton>
                    <BaseButton variant="danger" icon-left="trash" @click="deleteTeamMember(member.uid)">Delete</BaseButton>
                  </div>
                </div>
                <div v-if="pagedTeamMembers.length === 0" class="panel-empty">No team members match the current filter.</div>
                <BasePagination
                  v-if="filteredTeamMembers.length"
                  v-model:page="teamMembersPage"
                  class="panel-pagination"
                  :page-size="teamMembersPageSize"
                  :total="filteredTeamMembers.length"
                />
              </template>
            </div>

            <div v-else-if="activeTab === 'routing'">
              <div v-if="routingLoading" class="panel-empty">Loading routing snapshot...</div>
              <div v-else-if="routingRows.length === 0" class="panel-empty">
                {{ routingError ?? "No routing destinations are currently connected." }}
              </div>
              <div v-else class="routing-table-wrap">
                <table class="routing-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Destination</th>
                      <th>Identity</th>
                      <th>Status</th>
                      <th class="routing-cell--slot">Entry</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in routingRows" :key="row.id" class="routing-row">
                      <td class="routing-cell routing-cell--name">{{ row.name }}</td>
                      <td class="routing-cell routing-cell--destination mono">{{ row.destination }}</td>
                      <td class="routing-cell routing-cell--identity">{{ row.identityLabel }}</td>
                      <td class="routing-cell routing-cell--status">
                        <span class="routing-tag" :class="{ 'routing-tag--active': row.connected }">
                          {{ row.connected ? "Joined" : "Routed" }}
                        </span>
                      </td>
                      <td class="routing-cell routing-cell--slot">#{{ row.slot }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div class="panel-actions">
            <BaseButton
              v-if="activeTab === 'clients' || activeTab === 'identities'"
              variant="secondary"
              icon-left="refresh"
              @click="usersStore.fetchUsers()"
            >
              Refresh
            </BaseButton>
            <BaseButton v-if="activeTab === 'routing'" variant="secondary" icon-left="refresh" @click="loadRouting">
              Reload
            </BaseButton>
            <BaseButton v-if="activeTab === 'teams' || activeTab === 'team-members'" variant="secondary" icon-left="refresh" @click="loadTeamWorkspace">
              Refresh
            </BaseButton>
            <BaseButton v-if="activeTab === 'teams'" icon-left="plus" @click="openTeamEditor()">
              New Team
            </BaseButton>
            <BaseButton v-if="activeTab === 'team-members'" icon-left="plus" @click="openTeamMemberEditor()">
              New Team Member
            </BaseButton>
          </div>
        </section>
      </div>
    </div>

    <BaseModal :open="teamEditorOpen" :title="teamEditorTitle" @close="closeTeamEditor">
      <form class="editor-form" @submit.prevent="saveTeam">
        <label class="field-control">
          <span>Team Name</span>
          <input v-model="teamEditor.team_name" type="text" maxlength="96" required />
        </label>
        <BaseSelect v-model="teamEditor.color" label="Color" :options="teamColorOptions" />
        <label class="field-control full">
          <span>Description</span>
          <textarea v-model="teamEditor.team_description" rows="3" maxlength="512"></textarea>
        </label>
        <label class="field-control full">
          <span>Mission UIDs (comma separated)</span>
          <input v-model="teamEditor.mission_uids" type="text" placeholder="mission-alpha,mission-bravo" />
        </label>
        <div class="editor-actions">
          <BaseButton type="button" variant="ghost" icon-left="undo" @click="closeTeamEditor">Cancel</BaseButton>
          <BaseButton type="submit" icon-left="save" :disabled="teamSaving">
            {{ teamEditor.uid ? "Save Team" : "Create Team" }}
          </BaseButton>
        </div>
      </form>
    </BaseModal>

    <BaseModal :open="teamMemberEditorOpen" :title="teamMemberEditorTitle" @close="closeTeamMemberEditor">
      <form class="editor-form" @submit.prevent="saveTeamMember">
        <BaseSelect v-model="teamMemberEditor.team_uid" label="Team" :options="teamSelectOptions" />
        <BaseSelect v-model="teamMemberEditor.user_identity" label="User" :options="teamMemberUserOptions" />
        <label class="field-control">
          <span>RNS Identity (Derived)</span>
          <input :value="teamMemberDerivedIdentity" type="text" readonly />
        </label>
        <label class="field-control">
          <span>Display Name (Derived)</span>
          <input :value="teamMemberDerivedDisplayName" type="text" readonly />
        </label>
        <BaseSelect v-model="teamMemberEditor.role" label="Role" :options="teamRoleOptions" />
        <label class="field-control">
          <span>Callsign</span>
          <input v-model="teamMemberEditor.callsign" type="text" maxlength="64" @input="onCallsignInput" />
        </label>
        <label class="field-control">
          <span>Availability</span>
          <input v-model="teamMemberEditor.availability" type="text" maxlength="64" />
        </label>
        <label class="field-control">
          <span>Frequency</span>
          <input v-model="teamMemberEditor.freq" type="number" step="any" min="0" />
        </label>
        <label class="field-control">
          <span>Modulation</span>
          <input v-model="teamMemberEditor.modulation" type="text" maxlength="64" />
        </label>
        <label class="field-control">
          <span>Email</span>
          <input v-model="teamMemberEditor.email" type="email" maxlength="120" />
        </label>
        <label class="field-control">
          <span>Phone</span>
          <input v-model="teamMemberEditor.phone" type="text" maxlength="64" />
        </label>
        <label class="field-control full">
          <span>Certifications (comma separated)</span>
          <input v-model="teamMemberEditor.certifications" type="text" placeholder="emt,hrst,jtac" />
        </label>
        <div class="editor-actions">
          <BaseButton type="button" variant="ghost" icon-left="undo" @click="closeTeamMemberEditor">Cancel</BaseButton>
          <BaseButton type="submit" icon-left="save" :disabled="teamMemberSaving">
            {{ teamMemberEditor.uid ? "Save Member" : "Create Member" }}
          </BaseButton>
        </div>
      </form>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { ref } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";
import BaseBadge from "../components/BaseBadge.vue";
import BaseButton from "../components/BaseButton.vue";
import BaseModal from "../components/BaseModal.vue";
import BasePagination from "../components/BasePagination.vue";
import BaseSelect from "../components/BaseSelect.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import OnlineHelpLauncher from "../components/OnlineHelpLauncher.vue";
import type { ApiError } from "../api/client";
import { endpoints } from "../api/endpoints";
import { del as deleteRequest, get, post, put } from "../api/client";
import { useConnectionStore } from "../stores/connection";
import { useUsersStore } from "../stores/users";
import { useToastStore } from "../stores/toasts";
import { formatTimestamp } from "../utils/format";
import { clientPresenceTag } from "../utils/presence";
import { resolveIdentityLabel, shortHash } from "../utils/identity";
import { resolveTeamMemberPrimaryLabel } from "../utils/team-members";

interface MissionRecord {
  uid?: string;
  mission_name?: string | null;
}

interface TeamRecord {
  uid?: string;
  mission_uid?: string | null;
  mission_uids?: string[];
  color?: string | null;
  team_name?: string | null;
  team_description?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface TeamMemberRecord {
  uid?: string;
  team_uid?: string | null;
  rns_identity?: string | null;
  display_name?: string | null;
  icon?: string | null;
  role?: string | null;
  callsign?: string | null;
  freq?: number | null;
  email?: string | null;
  phone?: string | null;
  modulation?: string | null;
  availability?: string | null;
  certifications?: string[];
  client_identities?: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

type ActiveTab = "clients" | "identities" | "routing" | "teams" | "team-members";

const toStringList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter((item) => item.length > 0)
    : [];

const toCsv = (value: unknown): string => toStringList(value).join(",");
const splitCsv = (value: string): string[] =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);

const parseOptionalNumber = (value: string): number | null => {
  const text = value.trim();
  if (!text) {
    return null;
  }
  const numeric = Number(text);
  return Number.isFinite(numeric) ? numeric : null;
};

const queryText = (value: unknown): string =>
  Array.isArray(value) ? String(value[0] ?? "").trim() : String(value ?? "").trim();

const queryFlag = (value: unknown): boolean => {
  const normalized = queryText(value).toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
};

const usersStore = useUsersStore();
const connectionStore = useConnectionStore();
const toastStore = useToastStore();
const route = useRoute();
const router = useRouter();
const routing = ref<unknown>(null);
const routingLoading = ref(false);
const routingError = ref<string | null>(null);
const activeTab = ref<ActiveTab>("clients");
const clientsPage = ref(1);
const identitiesPage = ref(1);
const teamsPage = ref(1);
const teamMembersPage = ref(1);
const clientsPageSize = 9;
const identitiesPageSize = 9;
const teamsPageSize = 9;
const teamMembersPageSize = 9;
const identityFilter = ref("");
const clientFilter = ref("");
const teamFilter = ref("");
const teamMemberFilter = ref("");

const teamsLoading = ref(false);
const teamMembersLoading = ref(false);
const teamSaving = ref(false);
const teamMemberSaving = ref(false);

const missionRecords = ref<MissionRecord[]>([]);
const teamRecords = ref<TeamRecord[]>([]);
const teamMemberRecords = ref<TeamMemberRecord[]>([]);

const teamEditorOpen = ref(false);
const teamMemberEditorOpen = ref(false);
const isCallsignAuto = ref(true);

const teamEditor = ref({
  uid: "",
  team_name: "",
  color: "",
  team_description: "",
  mission_uids: ""
});

const teamMemberEditor = ref({
  uid: "",
  team_uid: "",
  user_identity: "",
  role: "TEAM_MEMBER",
  callsign: "",
  availability: "",
  freq: "",
  modulation: "",
  email: "",
  phone: "",
  certifications: ""
});

const baseUrl = computed(() => connectionStore.baseUrlDisplay);
const connectionLabel = computed(() => connectionStore.statusLabel);
const wsLabel = computed(() => connectionStore.wsLabel);
const totalRecords = computed(
  () =>
    usersStore.clients.length +
    usersStore.identities.length +
    teamRecords.value.length +
    teamMemberRecords.value.length
);
const activeTabTitle = computed(() => {
  if (activeTab.value === "clients") {
    return "Users";
  }
  if (activeTab.value === "identities") {
    return "Identities";
  }
  if (activeTab.value === "teams") {
    return "Teams";
  }
  if (activeTab.value === "team-members") {
    return "Team Members";
  }
  return "Routing";
});

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

const filteredClients = computed(() => {
  const filter = clientFilter.value.trim().toLowerCase();
  if (!filter) {
    return usersStore.clients;
  }
  return usersStore.clients.filter((client) => {
    const displayName = resolveClientDisplayName(client) ?? "";
    const id = client.id ?? "";
    return displayName.toLowerCase().includes(filter) || id.toLowerCase().includes(filter);
  });
});

const lastSeenValue = (value?: string | null) => {
  if (!value) {
    return 0;
  }
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? 0 : timestamp;
};

const sortedClients = computed(() => {
  return [...filteredClients.value].sort((a, b) => {
    const delta = lastSeenValue(b.last_seen_at) - lastSeenValue(a.last_seen_at);
    if (delta !== 0) {
      return delta;
    }
    return (a.id ?? "").localeCompare(b.id ?? "");
  });
});

const pagedClients = computed(() => {
  const start = (clientsPage.value - 1) * clientsPageSize;
  return sortedClients.value.slice(start, start + clientsPageSize);
});

const filteredIdentities = computed(() => {
  const filter = identityFilter.value.trim().toLowerCase();
  if (!filter) {
    return usersStore.identities;
  }
  return usersStore.identities.filter((identity) => {
    const displayName = identity.display_name ?? "";
    const id = identity.id ?? "";
    return displayName.toLowerCase().includes(filter) || id.toLowerCase().includes(filter);
  });
});

const sortedIdentities = computed(() => {
  return [...filteredIdentities.value].sort((a, b) => {
    const delta = lastSeenValue(b.last_seen) - lastSeenValue(a.last_seen);
    if (delta !== 0) {
      return delta;
    }
    return (a.id ?? "").localeCompare(b.id ?? "");
  });
});

const pagedIdentities = computed(() => {
  const start = (identitiesPage.value - 1) * identitiesPageSize;
  return sortedIdentities.value.slice(start, start + identitiesPageSize);
});

const missionNameByUid = computed(() => {
  const map = new Map<string, string>();
  missionRecords.value.forEach((mission) => {
    const uid = String(mission.uid ?? "").trim();
    if (uid) {
      map.set(uid, String(mission.mission_name ?? uid));
    }
  });
  return map;
});

const teamNameByUid = computed(() => {
  const map = new Map<string, string>();
  teamRecords.value.forEach((team) => {
    const uid = String(team.uid ?? "").trim();
    if (uid) {
      map.set(uid, String(team.team_name ?? uid));
    }
  });
  return map;
});

const filteredTeams = computed(() => {
  const filter = teamFilter.value.trim().toLowerCase();
  if (!filter) {
    return teamRecords.value;
  }
  return teamRecords.value.filter((team) => {
    const name = String(team.team_name ?? "").toLowerCase();
    const uid = String(team.uid ?? "").toLowerCase();
    const missionText = toStringList(team.mission_uids).join(" ").toLowerCase();
    return name.includes(filter) || uid.includes(filter) || missionText.includes(filter);
  });
});

const sortedTeams = computed(() =>
  [...filteredTeams.value].sort((a, b) => String(a.team_name ?? "").localeCompare(String(b.team_name ?? "")))
);

const pagedTeams = computed(() => {
  const start = (teamsPage.value - 1) * teamsPageSize;
  return sortedTeams.value.slice(start, start + teamsPageSize);
});

const filteredTeamMembers = computed(() => {
  const filter = teamMemberFilter.value.trim().toLowerCase();
  if (!filter) {
    return teamMemberRecords.value;
  }
  return teamMemberRecords.value.filter((member) => {
    const identity = String(member.rns_identity ?? "").toLowerCase();
    const callsign = String(member.callsign ?? "").toLowerCase();
    const displayName = String(member.display_name ?? "").toLowerCase();
    const teamName = teamNameByUid.value.get(String(member.team_uid ?? "").trim())?.toLowerCase() ?? "";
    return (
      identity.includes(filter) ||
      callsign.includes(filter) ||
      displayName.includes(filter) ||
      teamName.includes(filter) ||
      String(member.uid ?? "").toLowerCase().includes(filter)
    );
  });
});

const teamMemberPrimaryLabel = (member: TeamMemberRecord): string => resolveTeamMemberPrimaryLabel(member);

const sortedTeamMembers = computed(() =>
  [...filteredTeamMembers.value].sort((a, b) =>
    teamMemberPrimaryLabel(a).localeCompare(teamMemberPrimaryLabel(b))
  )
);

const pagedTeamMembers = computed(() => {
  const start = (teamMembersPage.value - 1) * teamMembersPageSize;
  return sortedTeamMembers.value.slice(start, start + teamMembersPageSize);
});

const identityDisplayNameById = computed(() => {
  const map = new Map<string, string>();
  usersStore.identities.forEach((identity) => {
    if (identity.id && identity.display_name) {
      map.set(identity.id, identity.display_name);
      map.set(identity.id.toLowerCase(), identity.display_name);
    }
  });
  return map;
});

const clientPageCount = computed(() => Math.max(1, Math.ceil(filteredClients.value.length / clientsPageSize)));
const identityPageCount = computed(() => Math.max(1, Math.ceil(filteredIdentities.value.length / identitiesPageSize)));
const teamsPageCount = computed(() => Math.max(1, Math.ceil(filteredTeams.value.length / teamsPageSize)));
const teamMembersPageCount = computed(
  () => Math.max(1, Math.ceil(filteredTeamMembers.value.length / teamMembersPageSize))
);

const clientIdentitySet = computed(() => {
  const set = new Set<string>();
  usersStore.clients.forEach((client) => {
    if (client.id) {
      set.add(client.id);
      set.add(client.id.toLowerCase());
    }
  });
  return set;
});

const normalizeRoutingValue = (value: unknown): string => {
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return "";
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

type RoutingEntry = {
  destination: string;
  identity: string;
  displayName?: string;
};

const normalizeRoutingText = (value: unknown): string => normalizeRoutingValue(value).trim();

const pickRoutingText = (source: Record<string, unknown>, keys: string[]): string => {
  for (const key of keys) {
    if (!(key in source)) {
      continue;
    }
    const value = normalizeRoutingText(source[key]);
    if (value) {
      return value;
    }
  }
  return "";
};

const parseRoutingEntry = (entry: unknown): RoutingEntry | null => {
  if (typeof entry === "string") {
    const value = normalizeRoutingText(entry);
    if (!value) {
      return null;
    }
    return { destination: value, identity: value };
  }
  if (!entry || typeof entry !== "object") {
    const value = normalizeRoutingText(entry);
    if (!value) {
      return null;
    }
    return { destination: value, identity: value };
  }
  const source = entry as Record<string, unknown>;
  const destination = pickRoutingText(source, [
    "destination",
    "Destination",
    "destination_hash",
    "destinationHash",
    "lxmf_destination",
    "lxmfDestination"
  ]);
  const identity = pickRoutingText(source, [
    "identity",
    "Identity",
    "identity_hash",
    "identityHash",
    "source_identity",
    "sourceIdentity"
  ]);
  const displayName = pickRoutingText(source, [
    "display_name",
    "displayName",
    "name",
    "label",
    "human_readable_name",
    "humanReadableName"
  ]);
  const resolvedDestination = destination || identity;
  if (!resolvedDestination) {
    return null;
  }
  return {
    destination: resolvedDestination,
    identity: identity || resolvedDestination,
    displayName: displayName || undefined
  };
};

const parseRoutingEntries = (payload: unknown): RoutingEntry[] => {
  let entries: unknown[] = [];
  if (Array.isArray(payload)) {
    entries = payload;
  } else if (payload && typeof payload === "object") {
    const source = payload as Record<string, unknown>;
    const candidates = [source.destinations, source.routes, source.items];
    for (const candidate of candidates) {
      if (Array.isArray(candidate)) {
        entries = candidate;
        break;
      }
    }
  }
  return entries
    .map((entry) => parseRoutingEntry(entry))
    .filter((entry): entry is RoutingEntry => entry !== null);
};

const routingEntries = computed(() => parseRoutingEntries(routing.value));

const clientDisplayNameById = computed(() => {
  const map = new Map<string, string>();
  usersStore.clients.forEach((client) => {
    if (client.id && client.display_name) {
      map.set(client.id, client.display_name);
      map.set(client.id.toLowerCase(), client.display_name);
    }
  });
  return map;
});

const lookupRoutingDisplayName = (identity?: string, destination?: string): string | undefined => {
  const keys = [identity, destination].filter((key): key is string => Boolean(key));
  for (const key of keys) {
    const lower = key.toLowerCase();
    const displayName =
      identityDisplayNameById.value.get(key) ??
      identityDisplayNameById.value.get(lower) ??
      clientDisplayNameById.value.get(key) ??
      clientDisplayNameById.value.get(lower);
    if (displayName) {
      return displayName;
    }
  }
  return undefined;
};

const routingRows = computed(() =>
  routingEntries.value.map((entry, index) => {
    const displayName = entry.displayName ?? lookupRoutingDisplayName(entry.identity, entry.destination);
    return {
      id: `${entry.destination}-${entry.identity}-${index}`,
      name: displayName || "Unknown",
      destination: entry.destination,
      identityLabel: resolveIdentityLabel(undefined, entry.identity),
      connected:
        clientIdentitySet.value.has(entry.identity) ||
        clientIdentitySet.value.has(entry.identity.toLowerCase()) ||
        clientIdentitySet.value.has(entry.destination) ||
        clientIdentitySet.value.has(entry.destination.toLowerCase()),
      slot: index + 1
    };
  })
);

const routingDestinations = computed(() =>
  routingRows.value.map((row) => row.destination)
);

const teamSelectOptions = computed(() => [
  { label: "Unassigned", value: "" },
  ...teamRecords.value.map((team) => ({
    label: String(team.team_name ?? team.uid ?? "Team"),
    value: String(team.uid ?? "")
  }))
]);

const userDisplayNameByIdentity = computed(() => {
  const map = new Map<string, string>();
  usersStore.clients.forEach((client) => {
    const identity = String(client.id ?? "").trim();
    if (!identity) {
      return;
    }
    const displayName =
      resolveClientDisplayName(client) ??
      identityDisplayNameById.value.get(identity.toLowerCase()) ??
      identity;
    map.set(identity.toLowerCase(), displayName);
  });
  return map;
});

const allUserOptions = computed(() => {
  const seen = new Set<string>();
  const options: Array<{ label: string; value: string }> = [];
  usersStore.clients.forEach((client) => {
    const identity = String(client.id ?? "").trim();
    if (!identity) {
      return;
    }
    const key = identity.toLowerCase();
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    const displayName = userDisplayNameByIdentity.value.get(key) ?? identity;
    options.push({
      label: `${displayName} (${identity})`,
      value: identity
    });
  });
  options.sort((a, b) => a.label.localeCompare(b.label));
  return options;
});

const linkedUserIdentitiesByOtherMembers = computed(() => {
  const currentUid = teamMemberEditor.value.uid.trim();
  const set = new Set<string>();
  teamMemberRecords.value.forEach((member) => {
    const uid = String(member.uid ?? "").trim();
    if (currentUid && uid && uid === currentUid) {
      return;
    }
    const linkedIdentity =
      toStringList(member.client_identities)[0] ??
      String(member.rns_identity ?? "").trim();
    if (linkedIdentity) {
      set.add(linkedIdentity.toLowerCase());
    }
  });
  return set;
});

const teamMemberDerivedIdentity = computed(() => teamMemberEditor.value.user_identity.trim());

const teamMemberDerivedDisplayName = computed(() => {
  const identity = teamMemberDerivedIdentity.value;
  if (!identity) {
    return "";
  }
  return userDisplayNameByIdentity.value.get(identity.toLowerCase()) ?? identity;
});

const teamMemberUserOptions = computed(() => {
  const selectedIdentity = teamMemberEditor.value.user_identity.trim().toLowerCase();
  const options = allUserOptions.value.filter((option) => {
    const key = option.value.toLowerCase();
    return key === selectedIdentity || !linkedUserIdentitiesByOtherMembers.value.has(key);
  });
  if (selectedIdentity && !options.some((option) => option.value.toLowerCase() === selectedIdentity)) {
    const identity = teamMemberEditor.value.user_identity.trim();
    const displayName = teamMemberDerivedDisplayName.value || identity;
    options.unshift({
      label: `${displayName} (${identity})`,
      value: identity
    });
  }
  return [{ label: "Select user", value: "" }, ...options];
});

const teamColorOptions = [
  { label: "Unspecified", value: "" },
  { label: "Yellow", value: "YELLOW" },
  { label: "Red", value: "RED" },
  { label: "Blue", value: "BLUE" },
  { label: "Orange", value: "ORANGE" },
  { label: "Magenta", value: "MAGENTA" },
  { label: "Maroon", value: "MAROON" },
  { label: "Purple", value: "PURPLE" },
  { label: "Dark Blue", value: "DARK_BLUE" },
  { label: "Cyan", value: "CYAN" },
  { label: "Teal", value: "TEAL" },
  { label: "Green", value: "GREEN" },
  { label: "Dark Green", value: "DARK_GREEN" },
  { label: "Brown", value: "BROWN" }
];

const teamRoleOptions = [
  { label: "Team Member", value: "TEAM_MEMBER" },
  { label: "Team Lead", value: "TEAM_LEAD" },
  { label: "HQ", value: "HQ" },
  { label: "Sniper", value: "SNIPER" },
  { label: "Medic", value: "MEDIC" },
  { label: "Forward Observer", value: "FORWARD_OBSERVER" },
  { label: "RTO", value: "RTO" },
  { label: "K9", value: "K9" }
];

const teamEditorTitle = computed(() => (teamEditor.value.uid ? "Edit Team" : "Create Team"));
const teamMemberEditorTitle = computed(() =>
  teamMemberEditor.value.uid ? "Edit Team Member" : "Create Team Member"
);

const teamNameForMember = (teamUid?: string | null): string => {
  const uid = String(teamUid ?? "").trim();
  if (!uid) {
    return "Unassigned";
  }
  return teamNameByUid.value.get(uid) ?? uid;
};

const teamMissionLabels = (team: TeamRecord): string[] => {
  const missionUids = toStringList(team.mission_uids);
  const primaryMissionUid = String(team.mission_uid ?? "").trim();
  if (!missionUids.length && primaryMissionUid) {
    missionUids.push(primaryMissionUid);
  }
  return missionUids.map((uid) => missionNameByUid.value.get(uid) ?? uid);
};

const clientTag = (lastSeenAt?: string) => {
  return clientPresenceTag(lastSeenAt);
};

const actOnClient = async (clientId?: string, action?: "Ban" | "Unban" | "Blackhole") => {
  if (!clientId || !action) {
    return;
  }
  try {
    await usersStore.actOnClient(clientId, action);
    toastStore.push(`Client ${action.toLowerCase()} action sent`, "success");
  } catch (error) {
    handleApiError(error, `Unable to ${action.toLowerCase()} client`);
  }
};

const leaveClient = async (clientId?: string) => {
  if (!clientId) {
    return;
  }
  try {
    await usersStore.leaveIdentity(clientId);
    await usersStore.fetchUsers();
    toastStore.push("Client left the hub", "warning");
  } catch (error) {
    handleApiError(error, "Unable to remove client");
  }
};

const joinIdentity = async (identityId?: string) => {
  if (!identityId) {
    return;
  }
  try {
    await usersStore.joinIdentity(identityId);
    await usersStore.fetchUsers();
    toastStore.push("Identity joined", "success");
  } catch (error) {
    handleApiError(error, "Unable to join identity");
  }
};

const isIdentityJoined = (identityId?: string) => {
  if (!identityId) {
    return false;
  }
  return clientIdentitySet.value.has(identityId) || clientIdentitySet.value.has(identityId.toLowerCase());
};

const loadRouting = async () => {
  routingLoading.value = true;
  routingError.value = null;
  try {
    const response = await get<unknown>(`${endpoints.command}/DumpRouting`);
    routing.value = response;
  } catch (error) {
    routing.value = null;
    routingError.value = "Unable to load routing snapshot.";
    handleApiError(error, "Unable to load routing snapshot");
  } finally {
    routingLoading.value = false;
  }
};

const loadTeamWorkspace = async () => {
  teamsLoading.value = true;
  teamMembersLoading.value = true;
  try {
    const [, missions, teams, members] = await Promise.all([
      usersStore.fetchUsers(),
      get<MissionRecord[]>(endpoints.r3aktMissions),
      get<TeamRecord[]>(endpoints.r3aktTeams),
      get<TeamMemberRecord[]>(endpoints.r3aktTeamMembers)
    ]);
    missionRecords.value = Array.isArray(missions) ? missions : [];
    teamRecords.value = Array.isArray(teams) ? teams : [];
    teamMemberRecords.value = Array.isArray(members) ? members : [];
  } catch (error) {
    handleApiError(error, "Unable to load teams and team members");
  } finally {
    teamsLoading.value = false;
    teamMembersLoading.value = false;
  }
};

const openTeamEditor = (team?: TeamRecord) => {
  if (!team) {
    teamEditor.value = {
      uid: "",
      team_name: "",
      color: "",
      team_description: "",
      mission_uids: ""
    };
    teamEditorOpen.value = true;
    return;
  }
  teamEditor.value = {
    uid: String(team.uid ?? ""),
    team_name: String(team.team_name ?? ""),
    color: String(team.color ?? ""),
    team_description: String(team.team_description ?? ""),
    mission_uids: toCsv(team.mission_uids)
  };
  teamEditorOpen.value = true;
};

const closeTeamEditor = () => {
  teamEditorOpen.value = false;
};

const saveTeam = async () => {
  const name = teamEditor.value.team_name.trim();
  if (!name) {
    toastStore.push("Team name is required", "warning");
    return;
  }
  const payload: Record<string, unknown> = {
    team_name: name,
    team_description: teamEditor.value.team_description.trim(),
    color: teamEditor.value.color.trim() || undefined,
    mission_uids: splitCsv(teamEditor.value.mission_uids)
  };
  if (teamEditor.value.uid.trim()) {
    payload.uid = teamEditor.value.uid.trim();
  }
  teamSaving.value = true;
  try {
    await post<TeamRecord>(endpoints.r3aktTeams, payload);
    teamEditorOpen.value = false;
    await loadTeamWorkspace();
    toastStore.push("Team saved", "success");
  } catch (error) {
    handleApiError(error, "Unable to save team");
  } finally {
    teamSaving.value = false;
  }
};

const deleteTeam = async (teamUid?: string) => {
  const uid = String(teamUid ?? "").trim();
  if (!uid) {
    return;
  }
  try {
    await deleteRequest<TeamRecord>(`${endpoints.r3aktTeams}/${encodeURIComponent(uid)}`);
    await loadTeamWorkspace();
    toastStore.push("Team deleted", "warning");
  } catch (error) {
    handleApiError(error, "Unable to delete team");
  }
};

const manageTeamMembers = (teamUid?: string) => {
  const uid = String(teamUid ?? "").trim();
  void router.push({
    path: "/users/teams/members",
    query: uid ? { team_uid: uid } : undefined
  });
};

const openTeamMemberEditor = (member?: TeamMemberRecord) => {
  if (!member) {
    teamMemberEditor.value = {
      uid: "",
      team_uid: "",
      user_identity: "",
      role: "TEAM_MEMBER",
      callsign: "",
      availability: "",
      freq: "",
      modulation: "",
      email: "",
      phone: "",
      certifications: ""
    };
    isCallsignAuto.value = true;
    teamMemberEditorOpen.value = true;
    return;
  }
  const linkedUserIdentity =
    toStringList(member.client_identities)[0] ??
    String(member.rns_identity ?? "");
  const derivedDisplayName =
    userDisplayNameByIdentity.value.get(linkedUserIdentity.toLowerCase()) ??
    String(member.display_name ?? linkedUserIdentity);
  teamMemberEditor.value = {
    uid: String(member.uid ?? ""),
    team_uid: String(member.team_uid ?? ""),
    user_identity: linkedUserIdentity,
    role: String(member.role ?? "TEAM_MEMBER"),
    callsign: String(member.callsign ?? ""),
    availability: String(member.availability ?? ""),
    freq: member.freq !== null && member.freq !== undefined ? String(member.freq) : "",
    modulation: String(member.modulation ?? ""),
    email: String(member.email ?? ""),
    phone: String(member.phone ?? ""),
    certifications: toCsv(member.certifications)
  };
  isCallsignAuto.value =
    !teamMemberEditor.value.callsign.trim() ||
    teamMemberEditor.value.callsign.trim() === derivedDisplayName.trim();
  if (isCallsignAuto.value) {
    teamMemberEditor.value.callsign = derivedDisplayName;
  }
  teamMemberEditorOpen.value = true;
};

const closeTeamMemberEditor = () => {
  teamMemberEditorOpen.value = false;
};

const onCallsignInput = () => {
  const callsign = teamMemberEditor.value.callsign.trim();
  const derived = teamMemberDerivedDisplayName.value.trim();
  isCallsignAuto.value = callsign.length === 0 || callsign === derived;
};

const syncTeamMemberClients = async (teamMemberUid: string, targetClientIdentities: string[], currentClients: string[]) => {
  const normalize = (value: string) => value.trim().toLowerCase();
  const desired = new Set(targetClientIdentities.map(normalize).filter((item) => item.length > 0));
  const current = new Set(currentClients.map(normalize).filter((item) => item.length > 0));

  const toAdd = [...desired].filter((item) => !current.has(item));
  const toRemove = [...current].filter((item) => !desired.has(item));

  const linkPath = (clientIdentity: string) =>
    `${endpoints.r3aktTeamMembers}/${encodeURIComponent(teamMemberUid)}/clients/${encodeURIComponent(clientIdentity)}`;

  await Promise.all([
    ...toAdd.map((clientIdentity) => put<TeamMemberRecord>(linkPath(clientIdentity))),
    ...toRemove.map((clientIdentity) => deleteRequest<TeamMemberRecord>(linkPath(clientIdentity)))
  ]);
};

const saveTeamMember = async () => {
  const selectedUserIdentity = teamMemberEditor.value.user_identity.trim();
  if (!selectedUserIdentity) {
    toastStore.push("A linked user is required", "warning");
    return;
  }
  const selectedUserKey = selectedUserIdentity.toLowerCase();
  if (linkedUserIdentitiesByOtherMembers.value.has(selectedUserKey)) {
    toastStore.push("Selected user is already linked to another team member", "warning");
    return;
  }
  const derivedDisplayName =
    userDisplayNameByIdentity.value.get(selectedUserKey) ??
    selectedUserIdentity;

  const payload: Record<string, unknown> = {
    team_uid: teamMemberEditor.value.team_uid.trim() || null,
    rns_identity: selectedUserIdentity,
    display_name: derivedDisplayName,
    role: teamMemberEditor.value.role.trim() || "TEAM_MEMBER",
    callsign: teamMemberEditor.value.callsign.trim() || derivedDisplayName,
    availability: teamMemberEditor.value.availability.trim() || null,
    modulation: teamMemberEditor.value.modulation.trim() || null,
    email: teamMemberEditor.value.email.trim() || null,
    phone: teamMemberEditor.value.phone.trim() || null,
    certifications: splitCsv(teamMemberEditor.value.certifications)
  };
  const freq = parseOptionalNumber(teamMemberEditor.value.freq);
  if (freq !== null) {
    payload.freq = freq;
  }
  if (teamMemberEditor.value.uid.trim()) {
    payload.uid = teamMemberEditor.value.uid.trim();
  }

  const clientIdentities = [selectedUserIdentity];

  teamMemberSaving.value = true;
  try {
    const saved = await post<TeamMemberRecord>(endpoints.r3aktTeamMembers, payload);
    const teamMemberUid = String(saved.uid ?? payload.uid ?? "").trim();
    if (teamMemberUid) {
      await syncTeamMemberClients(teamMemberUid, clientIdentities, toStringList(saved.client_identities));
    }
    teamMemberEditorOpen.value = false;
    await loadTeamWorkspace();
    toastStore.push("Team member saved", "success");
  } catch (error) {
    handleApiError(error, "Unable to save team member");
  } finally {
    teamMemberSaving.value = false;
  }
};

const deleteTeamMember = async (teamMemberUid?: string) => {
  const uid = String(teamMemberUid ?? "").trim();
  if (!uid) {
    return;
  }
  try {
    await deleteRequest<TeamMemberRecord>(`${endpoints.r3aktTeamMembers}/${encodeURIComponent(uid)}`);
    await loadTeamWorkspace();
    toastStore.push("Team member deleted", "warning");
  } catch (error) {
    handleApiError(error, "Unable to delete team member");
  }
};

const formatMetadata = (metadata?: Record<string, unknown>) => {
  if (!metadata) {
    return "-";
  }
  const parts = Object.entries(metadata)
    .slice(0, 3)
    .map(([key, value]) => `${key}:${String(value)}`);
  return parts.length ? parts.join(" / ") : "-";
};

const resolveClientDisplayName = (client: { id?: string; display_name?: string }) => {
  if (client.display_name) {
    return client.display_name;
  }
  if (!client.id) {
    return undefined;
  }
  return identityDisplayNameById.value.get(client.id) ?? identityDisplayNameById.value.get(client.id.toLowerCase());
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
  toastStore.push(fallback, "danger");
};

const clearNavigationIntentQuery = () => {
  const nextQuery = { ...route.query };
  delete nextQuery.tab;
  delete nextQuery.create_team_member;
  delete nextQuery.team_uid;
  void router.replace({ path: route.path, query: nextQuery });
};

const applyNavigationIntent = () => {
  const tabQuery = queryText(route.query.tab).toLowerCase();
  const createTeamMember = queryFlag(route.query.create_team_member);
  const requestedTeamUid = queryText(route.query.team_uid);

  const tabMap: Record<string, ActiveTab> = {
    clients: "clients",
    identities: "identities",
    routing: "routing",
    teams: "teams",
    "team-members": "team-members",
    teammembers: "team-members",
    members: "team-members"
  };
  if (tabMap[tabQuery]) {
    activeTab.value = tabMap[tabQuery];
  }

  if (createTeamMember) {
    activeTab.value = "team-members";
    openTeamMemberEditor();
    if (requestedTeamUid && teamRecords.value.some((team) => String(team.uid ?? "") === requestedTeamUid)) {
      teamMemberEditor.value.team_uid = requestedTeamUid;
    }
  }

  if (tabQuery || createTeamMember || requestedTeamUid) {
    clearNavigationIntentQuery();
  }
};

watch(clientPageCount, (count) => {
  if (clientsPage.value > count) {
    clientsPage.value = count;
  }
});

watch(clientFilter, () => {
  clientsPage.value = 1;
});

watch(identityPageCount, (count) => {
  if (identitiesPage.value > count) {
    identitiesPage.value = count;
  }
});

watch(identityFilter, () => {
  identitiesPage.value = 1;
});

watch(teamsPageCount, (count) => {
  if (teamsPage.value > count) {
    teamsPage.value = count;
  }
});

watch(teamFilter, () => {
  teamsPage.value = 1;
});

watch(teamMembersPageCount, (count) => {
  if (teamMembersPage.value > count) {
    teamMembersPage.value = count;
  }
});

watch(teamMemberFilter, () => {
  teamMembersPage.value = 1;
});

watch(
  () => teamMemberEditor.value.user_identity,
  (identity) => {
    if (!isCallsignAuto.value) {
      return;
    }
    if (!identity.trim()) {
      teamMemberEditor.value.callsign = "";
      return;
    }
    teamMemberEditor.value.callsign = teamMemberDerivedDisplayName.value || identity.trim();
  }
);

watch(
  () => [route.query.tab, route.query.create_team_member, route.query.team_uid],
  () => {
    applyNavigationIntent();
  }
);

watch(activeTab, (tab) => {
  if (tab === "clients") {
    clientsPage.value = 1;
  }
  if (tab === "identities") {
    identitiesPage.value = 1;
  }
  if (tab === "routing") {
    void loadRouting();
  }
  if (tab === "teams") {
    teamsPage.value = 1;
    if (!teamRecords.value.length) {
      void loadTeamWorkspace();
    }
  }
  if (tab === "team-members") {
    teamMembersPage.value = 1;
    if (!teamMemberRecords.value.length) {
      void loadTeamWorkspace();
    }
  }
});

onMounted(() => {
  loadTeamWorkspace()
    .then(() => {
      applyNavigationIntent();
    })
    .catch(() => undefined);
});
</script>

<style scoped>
.users-registry {
  --neon: #37f2ff;
  --panel-dark: rgba(4, 12, 22, 0.96);
  --panel-light: rgba(10, 30, 45, 0.94);
  --amber: #ffb35c;
  --danger: rgba(255, 104, 104, 0.8);
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

.registry-shell::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 65%, rgba(55, 242, 255, 0.12), transparent 85%);
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
  text-align: center;
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

.registry-grid {
  display: grid;
  grid-template-columns: minmax(240px, 320px) 1fr;
  gap: 18px;
  z-index: 1;
  position: relative;
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
  clip-path: polygon(
    1px 1px,
    calc(100% - 25px) 1px,
    calc(100% - 1px) 25px,
    calc(100% - 1px) calc(100% - 1px),
    25px calc(100% - 1px),
    1px calc(100% - 25px)
  );
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
  font-family: "Rajdhani", "Barlow", sans-serif;
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
  text-transform: uppercase;
  letter-spacing: 0.18em;
  background: rgba(18, 24, 30, 0.6);
}

.panel-tabs {
  display: inline-flex;
  flex-wrap: wrap;
  background: rgba(7, 18, 26, 0.8);
  border: 1px solid rgba(55, 242, 255, 0.25);
  border-radius: 999px;
  padding: 4px;
  gap: 4px;
}

.panel-tab {
  border: 1px solid transparent;
  background: transparent;
  color: rgba(209, 251, 255, 0.6);
  padding: 6px 14px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 11px;
  transition: all 0.2s ease;
}

.panel-tab.active {
  background: rgba(55, 242, 255, 0.12);
  border-color: rgba(55, 242, 255, 0.6);
  color: #e0feff;
  box-shadow: 0 0 14px rgba(55, 242, 255, 0.25);
}

.tree-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tree-item {
  display: grid;
  grid-template-columns: 12px 1fr auto;
  align-items: center;
  gap: 8px;
  border: 1px solid transparent;
  background: rgba(7, 18, 28, 0.6);
  color: rgba(213, 251, 255, 0.9);
  padding: 8px 10px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 11px;
  transition: all 0.2s ease;
}

.tree-item:hover {
  border-color: rgba(55, 242, 255, 0.35);
}

.tree-item.active {
  border-color: rgba(55, 242, 255, 0.65);
  background: rgba(55, 242, 255, 0.12);
  box-shadow: 0 0 16px rgba(55, 242, 255, 0.25);
}

.tree-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--neon);
  box-shadow: 0 0 10px var(--neon);
}

.tree-count {
  border: 1px solid var(--amber);
  color: var(--amber);
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  letter-spacing: 0.14em;
  background: rgba(10, 20, 30, 0.6);
}

.tree-search {
  margin-top: 14px;
}

.tree-search input {
  width: 100%;
  background: rgba(6, 16, 25, 0.85);
  border: 1px solid rgba(55, 242, 255, 0.3);
  color: #d8fbff;
  border-radius: 10px;
  padding: 8px 12px;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.tree-search input::placeholder {
  color: rgba(209, 251, 255, 0.4);
}

.tree-note {
  margin-top: 14px;
  padding: 12px;
  border: 1px dashed rgba(55, 242, 255, 0.3);
  border-radius: 10px;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.62);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
}

.registry-card {
  position: relative;
  padding: 16px 16px 12px;
  min-height: 220px;
}

.registry-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.registry-card-title {
  font-size: 16px;
  color: #e6feff;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.registry-card-subtitle {
  font-size: 11px;
  color: rgba(190, 246, 255, 0.7);
  margin-top: 4px;
}

.registry-card-tag {
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: rgba(227, 252, 255, 0.85);
  font-size: 10px;
  border-radius: 999px;
  padding: 4px 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
}

.registry-card-meta {
  margin-top: 12px;
  display: grid;
  gap: 8px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  color: rgba(220, 251, 255, 0.85);
}

.registry-card-meta div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.registry-card-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.registry-card-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.panel-empty {
  grid-column: 1 / -1;
  padding: 18px;
  border: 1px dashed rgba(55, 242, 255, 0.25);
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 12px;
  color: rgba(210, 251, 255, 0.65);
}

.panel-pagination {
  margin-top: 16px;
}

.panel-actions {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.editor-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.field-control {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-control span {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: rgba(209, 251, 255, 0.66);
}

.field-control.full {
  grid-column: 1 / -1;
}

.field-control input,
.field-control textarea {
  width: 100%;
  background: rgba(6, 16, 25, 0.9);
  border: 1px solid rgba(55, 242, 255, 0.26);
  color: #d8fbff;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 12px;
  letter-spacing: 0.08em;
}

.field-control textarea {
  resize: vertical;
  min-height: 84px;
}

.editor-actions {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 6px;
}

.routing-table-wrap {
  width: 100%;
  overflow-x: auto;
}

.routing-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 8px;
  table-layout: fixed;
}

.routing-table thead th {
  text-align: left;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 11px;
  color: rgba(209, 251, 255, 0.58);
  padding: 0 10px 6px;
}

.routing-table thead th.routing-cell--slot {
  text-align: right;
}

.routing-row td {
  background: rgba(7, 20, 30, 0.84);
  border-top: 1px solid rgba(55, 242, 255, 0.2);
  border-bottom: 1px solid rgba(55, 242, 255, 0.2);
  padding: 9px 10px;
  font-size: 12px;
  letter-spacing: 0.08em;
  color: rgba(221, 252, 255, 0.88);
}

.routing-row td:first-child {
  border-left: 1px solid rgba(55, 242, 255, 0.2);
  border-radius: 12px 0 0 12px;
}

.routing-row td:last-child {
  border-right: 1px solid rgba(55, 242, 255, 0.2);
  border-radius: 0 12px 12px 0;
}

.routing-cell--name {
  width: 20%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.routing-cell--destination {
  width: 42%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.routing-cell--identity {
  width: 16%;
  text-transform: uppercase;
}

.routing-cell--status {
  width: 12%;
}

.routing-cell--slot {
  width: 10%;
  text-align: right;
  color: rgba(210, 249, 255, 0.65);
}

.routing-tag {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  border: 1px solid rgba(255, 179, 92, 0.5);
  color: rgba(255, 183, 115, 0.88);
  padding: 3px 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 10px;
}

.routing-tag--active {
  border-color: rgba(55, 242, 255, 0.5);
  color: rgba(197, 251, 255, 0.9);
}

.mono {
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}

:deep(.users-registry .cui-btn) {
  background: linear-gradient(135deg, rgba(35, 130, 160, 0.45), rgba(6, 18, 28, 0.92));
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: #e5feff;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 10px;
  padding: 6px 12px;
  box-shadow: 0 0 12px rgba(55, 242, 255, 0.15);
}

:deep(.users-registry .cui-btn--secondary) {
  background: linear-gradient(135deg, rgba(14, 44, 60, 0.85), rgba(6, 14, 22, 0.92));
}

:deep(.users-registry .cui-btn--danger) {
  border-color: var(--danger);
  color: #ffd3d3;
}

:deep(.users-registry .cui-btn:disabled) {
  opacity: 0.45;
}

:deep(.users-registry .cui-modal) {
  border: 1px solid rgba(55, 242, 255, 0.28);
  box-shadow: 0 20px 60px rgba(1, 6, 12, 0.7), inset 0 0 0 1px rgba(55, 242, 255, 0.08);
}

:deep(.users-registry .cui-combobox) {
  width: 100%;
}

:deep(.users-registry .cui-combobox__label) {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.66);
}

@media (max-width: 1100px) {
  .registry-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .registry-top {
    grid-template-columns: 1fr;
    text-align: center;
  }

  .registry-status {
    justify-content: center;
  }

  .panel-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .panel-tabs {
    align-self: flex-start;
  }

  .editor-form {
    grid-template-columns: 1fr;
  }
}
</style>
