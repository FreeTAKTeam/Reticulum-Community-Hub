<template>
  <div class="users-registry">
    <div class="registry-shell">
      <header class="registry-top">
        <div class="registry-title">User Registry</div>
        <div class="registry-status">
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
          </div>

          <div v-if="activeTab === 'clients'" class="tree-search">
            <input v-model="clientFilter" type="text" placeholder="Filter users by name/hash" />
          </div>
          <div v-else-if="activeTab === 'identities'" class="tree-search">
            <input v-model="identityFilter" type="text" placeholder="Filter identities by name/hash" />
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
            </div>
          </div>

          <LoadingSkeleton v-if="usersStore.loading && activeTab !== 'routing'" />
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

            <div v-else>
              <div v-if="routingLoading" class="panel-empty">Loading routing snapshot...</div>
              <div v-else-if="routingRows.length === 0" class="panel-empty">
                {{ routingError ?? "No routing destinations are currently connected." }}
              </div>
              <div v-else class="routing-table-wrap">
                <table class="routing-table">
                  <thead>
                    <tr>
                      <th>Destination</th>
                      <th>Identity</th>
                      <th>Status</th>
                      <th class="routing-cell--slot">Entry</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in routingRows" :key="row.id" class="routing-row">
                      <td class="routing-cell routing-cell--destination mono">{{ row.destination }}</td>
                      <td class="routing-cell routing-cell--identity">{{ row.label }}</td>
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
            <BaseButton v-if="activeTab !== 'routing'" variant="secondary" icon-left="refresh" @click="usersStore.fetchUsers()">
              Refresh
            </BaseButton>
            <BaseButton v-if="activeTab === 'routing'" variant="secondary" icon-left="refresh" @click="loadRouting">
              Reload
            </BaseButton>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { ref } from "vue";
import BaseBadge from "../components/BaseBadge.vue";
import BaseButton from "../components/BaseButton.vue";
import BasePagination from "../components/BasePagination.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import type { ApiError } from "../api/client";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { useConnectionStore } from "../stores/connection";
import { useUsersStore } from "../stores/users";
import { useToastStore } from "../stores/toasts";
import { formatTimestamp } from "../utils/format";
import { resolveIdentityLabel } from "../utils/identity";

const usersStore = useUsersStore();
const connectionStore = useConnectionStore();
const toastStore = useToastStore();
const routing = ref<unknown>(null);
const routingLoading = ref(false);
const routingError = ref<string | null>(null);
const activeTab = ref<"clients" | "identities" | "routing">("clients");
const clientsPage = ref(1);
const identitiesPage = ref(1);
const clientsPageSize = 6;
const identitiesPageSize = 6;
const identityFilter = ref("");
const clientFilter = ref("");

const baseUrl = computed(() => connectionStore.baseUrlDisplay);
const connectionLabel = computed(() => connectionStore.statusLabel);
const wsLabel = computed(() => connectionStore.wsLabel);
const totalRecords = computed(() => usersStore.clients.length + usersStore.identities.length);
const activeTabTitle = computed(() => {
  if (activeTab.value === "clients") {
    return "Users";
  }
  if (activeTab.value === "identities") {
    return "Identities";
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

const identityDisplayNameById = computed(() => {
  const map = new Map<string, string>();
  usersStore.identities.forEach((identity) => {
    if (identity.id && identity.display_name) {
      map.set(identity.id, identity.display_name);
    }
  });
  return map;
});

const clientPageCount = computed(() => Math.max(1, Math.ceil(filteredClients.value.length / clientsPageSize)));
const identityPageCount = computed(() => Math.max(1, Math.ceil(filteredIdentities.value.length / identitiesPageSize)));

const clientIdentitySet = computed(() => {
  const set = new Set<string>();
  usersStore.clients.forEach((client) => {
    if (client.id) {
      set.add(client.id);
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

const parseRoutingDestinations = (payload: unknown): string[] => {
  if (Array.isArray(payload)) {
    return payload.map((entry) => normalizeRoutingValue(entry)).filter((entry) => entry.length > 0);
  }
  if (!payload || typeof payload !== "object") {
    return [];
  }
  const source = payload as Record<string, unknown>;
  const candidates = [source.destinations, source.routes, source.items];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return candidate.map((entry) => normalizeRoutingValue(entry)).filter((entry) => entry.length > 0);
    }
  }
  return [];
};

const routingDestinations = computed(() => parseRoutingDestinations(routing.value));

const routingRows = computed(() =>
  routingDestinations.value.map((destination, index) => ({
    id: `${destination}-${index}`,
    destination,
    label: resolveIdentityLabel(identityDisplayNameById.value.get(destination), destination),
    connected: clientIdentitySet.value.has(destination),
    slot: index + 1
  }))
);

const clientTag = (lastSeenAt?: string) => {
  const seenTimestamp = lastSeenAt ? Date.parse(lastSeenAt) : Number.NaN;
  if (!Number.isNaN(seenTimestamp) && Date.now() - seenTimestamp <= 5 * 60 * 1000) {
    return "Active";
  }
  return "Seen";
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
  return clientIdentitySet.value.has(identityId);
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
  return identityDisplayNameById.value.get(client.id);
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
});

onMounted(() => {
  usersStore.fetchUsers();
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

.routing-cell--destination {
  width: 56%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.routing-cell--identity {
  width: 18%;
  text-transform: uppercase;
}

.routing-cell--status {
  width: 14%;
}

.routing-cell--slot {
  width: 12%;
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
}
</style>
