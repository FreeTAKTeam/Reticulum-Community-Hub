<template>
  <section class="identity-directory" aria-label="Identity directory">
    <div class="directory-controls">
      <label>Search identities <input v-model="search" type="search" placeholder="Name, identity or destination" /></label>
      <label>History <select v-model="view"><option value="recent">Recent</option><option value="all">All history</option></select></label>
      <label>Client type <select v-model="clientType"><option value="all">All</option><option value="rem">REM</option><option value="generic_lxmf">LXMF</option></select></label>
      <label>Order <select v-model="order"><option value="last_seen_desc">Recently heard</option><option value="identity_asc">Identity</option></select></label>
      <BaseButton variant="secondary" icon-left="refresh" @click="refresh">Refresh</BaseButton>
    </div>
    <p v-if="directory.settings" class="panel-empty">Recent: {{ directory.settings.recentHours }} hours, including joined, team-linked, REM and moderated identities. Recently heard describes discovery, not online presence. {{ directory.total ?? '—' }} matching identities.</p>
    <p v-if="directory.error" role="status" class="panel-empty">{{ directory.error }}</p>
    <LoadingSkeleton v-if="directory.loading" />
            <div class="card-grid">
              <div
                v-for="(identity, index) in directory.items"
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
                  <div><span>Recently Heard</span><span>{{ formatTimestamp(identity.recently_heard_at ?? identity.last_seen) }}</span></div>
                  <div><span>Status</span><span>{{ identity.status || "-" }}</span></div>
                  <div v-if="identity.is_announced">
                    <span>Announce Source</span>
                    <span>{{ identity.announce_source || "-" }}</span>
                  </div>
                  <div v-if="identity.is_announced">
                    <span>Destination</span>
                    <span class="mono" :title="identity.announce_destination_hash || '-'">
                      {{ identityAnnounceDestinationLabel(identity) }}
                    </span>
                  </div>
                  <div v-if="identityVoiceDestination(identity)">
                    <span>Voice</span>
                    <span class="mono" :title="identityVoiceDestination(identity)">
                      {{ identityVoiceDestinationLabel(identity) }}
                    </span>
                  </div>
                  <div v-if="identity.is_announced">
                    <span>First Announce</span>
                    <span>{{ formatTimestamp(identity.announce_first_seen) }}</span>
                  </div>
                </div>
                <div class="registry-card-badges">
                  <BaseBadge v-if="identity.is_announced" tone="success">Announce</BaseBadge>
                  <BaseBadge v-if="identityVoiceDestination(identity)" tone="warning">Voice</BaseBadge>
                  <BaseBadge :tone="identity.is_rem_capable ? 'success' : 'neutral'">
                    {{ clientTypeLabel(identity.client_type, identity.is_rem_capable) }}
                  </BaseBadge>
                  <BaseBadge v-if="identity.rem_mode" tone="warning">{{ identity.rem_mode }}</BaseBadge>
                  <BaseBadge v-if="identity.banned" tone="danger">Banned</BaseBadge>
                  <BaseBadge v-if="identity.blackholed" tone="warning">Blackholed</BaseBadge>
                </div>
                <div class="registry-card-actions">
                  <BaseButton variant="danger" icon-left="ban" @click="actOnIdentity(identity.id, 'Ban')">Ban</BaseButton>
                  <BaseButton variant="success" icon-left="unban" @click="actOnIdentity(identity.id, 'Unban')">Unban</BaseButton>
                  <BaseButton variant="secondary" icon-left="blackhole" @click="actOnIdentity(identity.id, 'Blackhole')">
                    Blackhole
                  </BaseButton>
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
              <div v-if="!directory.loading && !directory.error && directory.items.length === 0" class="panel-empty">No identities match the current filter.</div>
              <BasePagination
                v-if="directory.total !== null && directory.settings"
                v-model:page="identitiesPage"
                class="panel-pagination"
                :key="directory.settings.pageSize"
                :page-size="directory.settings.pageSize"
                :total="directory.total ?? 0"
              />
            </div>

  </section>
</template>
<script setup lang="ts">
import { ref, watch, onUnmounted } from "vue";
import BaseBadge from "../BaseBadge.vue";
import BaseButton from "../BaseButton.vue";
import BasePagination from "../BasePagination.vue";
import LoadingSkeleton from "../LoadingSkeleton.vue";
import { useIdentityDirectoryStore } from "../../stores/identity-directory";
import { useConnectionStore } from "../../stores/connection";
import { formatTimestamp } from "../../utils/format";
import { resolveIdentityLabel, shortHash } from "../../utils/identity";
import type { IdentityQuery } from "../../api/identity-directory";
const props = defineProps<{ joinedIds: Set<string> }>();
const emit = defineEmits<{ action: [identity: string | undefined, action: "Ban" | "Unban" | "Blackhole"]; join: [identity: string | undefined] }>();
const directory = useIdentityDirectoryStore();
const connection = useConnectionStore();
const search = ref("");
const view = ref<IdentityQuery["view"]>("recent");
const clientType = ref<IdentityQuery["clientType"]>("all");
const order = ref<IdentityQuery["order"]>("last_seen_desc");
const identitiesPage = ref(1);
let timer: ReturnType<typeof setTimeout> | undefined;
let resettingPage = false;
const load = () => directory.fetchPage({ page: identitiesPage.value, search: search.value.trim(), view: view.value, clientType: clientType.value, order: order.value });
const refresh = () => { directory.invalidate(); };
watch([search, view, clientType, order], () => {
  directory.cancelPage(); clearTimeout(timer);
  resettingPage = true; identitiesPage.value = 1; resettingPage = false;
  timer = setTimeout(() => { void load(); }, 250);
}, { flush: "sync" });
watch(identitiesPage, () => { if (!resettingPage) { clearTimeout(timer); void load(); } }, { flush: "sync" });
watch(() => directory.revision, () => { clearTimeout(timer); void load(); });
watch(() => connection.requestIdentity, () => { clearTimeout(timer); identitiesPage.value = 1; void load(); });
void load();
onUnmounted(() => { clearTimeout(timer); directory.cancelPage(); });
const actOnIdentity = (id: string | undefined, action: "Ban" | "Unban" | "Blackhole") => emit("action", id, action);
const joinIdentity = (id: string | undefined) => emit("join", id);
const isIdentityJoined = (id?: string) => Boolean(id && (props.joinedIds.has(id) || props.joinedIds.has(id.toLowerCase())));
const clientTypeLabel = (type?: string, rem?: boolean) => type === "rem" || rem ? "REM Client" : "Generic LXMF";
type IdentityWithAnnounce = {
  id?: string;
  announce_destination_hash?: string;
  metadata?: Record<string, unknown>;
};

const identityAnnounceDestinationLabel = (identity: IdentityWithAnnounce): string => {
  const destination = identity.announce_destination_hash;
  if (!destination) {
    return "-";
  }
  if (destination === identity.id) {
    return "same identity";
  }
  return shortHash(destination, 6, 6);
};

const identityVoiceDestination = (identity: IdentityWithAnnounce): string | undefined => {
  const voice = identity.metadata?.voice;
  if (!voice || typeof voice !== "object") {
    return undefined;
  }
  const destination = (voice as Record<string, unknown>).destination_hash;
  return typeof destination === "string" && destination.trim() ? destination : undefined;
};

const identityVoiceDestinationLabel = (identity: IdentityWithAnnounce): string => {
  const destination = identityVoiceDestination(identity);
  return destination ? shortHash(destination, 6, 6) : "-";
};

</script>
<style scoped src="../../pages/styles/UsersPage.css"></style>
<style scoped>
.identity-directory { min-width: 0; max-width: 100%; }
.directory-controls { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; margin-bottom: 1rem; }
.directory-controls label { display: flex; flex-direction: column; gap: .4rem; flex: 1 1 140px; min-width: 0; max-width: 100%; }
.directory-controls label:first-child { flex-basis: 240px; }
.directory-controls input, .directory-controls select { box-sizing: border-box; min-width: 0; width: 100%; max-width: 100%; padding: .6rem; background: var(--cui-panel, #111827); border: 1px solid #46546b; border-radius: .35rem; color: inherit; }
.card-grid { grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr)); }
.registry-card, .registry-card-header > div { min-width: 0; }
.registry-card-title, .registry-card-subtitle, .panel-empty { overflow-wrap: anywhere; }
.registry-card-meta div { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr); }
.registry-card-meta span { min-width: 0; overflow-wrap: anywhere; }
.registry-card-meta span:last-child { text-align: right; }
</style>
