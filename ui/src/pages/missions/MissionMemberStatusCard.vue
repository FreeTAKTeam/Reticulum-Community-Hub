<template>
  <article class="status-card" :class="[`tone-${toneClass}`, { expanded: isExpanded }]">
    <header class="status-card-header">
      <div class="status-card-identity">
        <p class="status-card-label">Call Sign</p>
        <h5>{{ member.callsign }}</h5>
        <p class="status-card-team">Team: {{ member.teamName || "Unassigned" }}</p>
        <p class="status-card-role">{{ member.role || "UNASSIGNED" }}</p>
      </div>
      <div v-if="member.capabilities.length" class="status-card-capabilities" aria-label="Capabilities">
        <span v-for="capability in member.capabilities" :key="`${member.uid}-${capability}`" class="status-card-capability">
          {{ capability }}
        </span>
      </div>
    </header>

    <section class="status-card-overview">
      <div class="status-ring" :style="ringStyle">
        <div class="status-ring-core"></div>
      </div>
      <div class="status-card-overview-copy">
        <p class="status-card-label">Overall</p>
        <p class="status-card-score">{{ member.scorePercent }}%</p>
        <p class="status-card-status">{{ member.overallStatus }}</p>
        <p v-if="statusMeta" class="status-card-meta">{{ statusMeta }}</p>
      </div>
    </section>

    <button type="button" class="status-card-toggle" :aria-expanded="isExpanded" @click="isExpanded = !isExpanded">
      <span>{{ isExpanded ? "Hide Statuses" : "Show Statuses" }}</span>
      <span class="status-card-chevron" :class="{ open: isExpanded }">^</span>
    </button>

    <transition name="status-details">
      <div v-if="isExpanded" class="status-card-details">
        <button
          v-for="dimension in dimensions"
          :key="`${member.uid}-${dimension.key}`"
          type="button"
          class="status-pill"
          :class="`tone-${getMissionMemberStatusTone(dimension.value)}`"
          :disabled="pendingDimensions.includes(dimension.key)"
          @click="emit('cycle-status', dimension.key)"
        >
          <span>{{ dimension.label }}</span>
          <strong>{{ pendingDimensions.includes(dimension.key) ? 'Saving...' : dimension.value }}</strong>
        </button>
      </div>
    </transition>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import {
  MISSION_MEMBER_STATUS_DIMENSIONS,
  getMissionMemberStatusTone
} from "./mission-member-status";
import type { EamStatus } from "./mission-member-status";
import type { MissionMemberStatusKey } from "./mission-member-status";

interface MissionMemberStatusCardMember {
  uid: string;
  callsign: string;
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

const props = defineProps<{
  member: MissionMemberStatusCardMember;
  pendingDimensions: MissionMemberStatusKey[];
}>();

const emit = defineEmits<{
  (event: "cycle-status", dimension: MissionMemberStatusKey): void;
}>();

const isExpanded = ref(false);

const toneClass = computed(() => getMissionMemberStatusTone(props.member.overallStatus));

const toneColor = computed(() => {
  if (toneClass.value === "green") {
    return "#19e38f";
  }
  if (toneClass.value === "yellow") {
    return "#f5c400";
  }
  if (toneClass.value === "red") {
    return "#ff4d4d";
  }
  return "#6f86b7";
});

const ringStyle = computed(() => {
  const percent = Math.max(0, Math.min(100, props.member.scorePercent));
  return {
    background: `conic-gradient(${toneColor.value} 0deg ${percent * 3.6}deg, rgba(50, 74, 119, 0.35) ${percent * 3.6}deg 360deg)`,
    boxShadow: `0 0 24px ${toneColor.value}33`
  };
});

const statusMeta = computed(() => {
  if (props.member.isExpired) {
    return "Report expired";
  }
  if (!props.member.reportedAt) {
    return "No recent report";
  }
  const reportedAtMs = Date.parse(props.member.reportedAt);
  if (Number.isNaN(reportedAtMs)) {
    return "";
  }
  const minutes = Math.max(0, Math.round((Date.now() - reportedAtMs) / 60000));
  if (minutes < 1) {
    return "Updated just now";
  }
  if (minutes < 60) {
    return `Updated ${minutes}m ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `Updated ${hours}h ago`;
  }
  const days = Math.round(hours / 24);
  return `Updated ${days}d ago`;
});

const dimensions = computed(() =>
  MISSION_MEMBER_STATUS_DIMENSIONS.map((dimension) => ({
    ...dimension,
    value: props.member[dimension.key]
  }))
);
</script>

<style scoped>
.status-card {
  border: 1px solid rgba(43, 217, 255, 0.2);
  border-radius: 24px;
  padding: 16px;
  display: grid;
  gap: 14px;
  background:
    radial-gradient(circle at top right, rgba(34, 116, 170, 0.16), transparent 42%),
    linear-gradient(180deg, rgba(7, 18, 34, 0.96), rgba(8, 19, 38, 0.92));
  box-shadow:
    inset 0 1px 0 rgba(92, 225, 255, 0.08),
    0 24px 40px rgba(1, 7, 15, 0.32);
}

.status-card.expanded {
  border-color: rgba(43, 217, 255, 0.28);
}

.status-card-header {
  display: grid;
  gap: 10px;
}

.status-card-identity {
  display: grid;
  gap: 4px;
}

.status-card-label {
  margin: 0;
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: rgba(165, 231, 255, 0.66);
}

.status-card h5 {
  margin: 0;
  font-size: clamp(1.35rem, 2vw, 1.9rem);
  line-height: 1.05;
  letter-spacing: 0.03em;
  color: #f1fbff;
}

.status-card-team,
.status-card-role,
.status-card-meta,
.status-card-status {
  margin: 0;
}

.status-card-team {
  font-size: 1.05rem;
  color: rgba(214, 240, 255, 0.86);
}

.status-card-role,
.status-card-meta {
  font-size: 0.75rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(150, 184, 220, 0.7);
}

.status-card-capabilities {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.status-card-capability {
  border: 1px solid rgba(43, 217, 255, 0.22);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 0.68rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(217, 245, 255, 0.9);
  background: rgba(7, 24, 42, 0.8);
}

.status-card-overview {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-ring {
  position: relative;
  width: 74px;
  height: 74px;
  border-radius: 50%;
  flex: 0 0 74px;
}

.status-ring-core {
  position: absolute;
  inset: 12px;
  border-radius: 50%;
  background: rgba(4, 12, 28, 0.94);
  border: 1px solid rgba(92, 225, 255, 0.08);
}

.status-card-overview-copy {
  display: grid;
  gap: 2px;
}

.status-card-score {
  margin: 0;
  font-size: clamp(2rem, 3vw, 2.5rem);
  line-height: 1;
  color: #edfaff;
}

.status-card-status {
  font-size: 1rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(223, 248, 255, 0.82);
}

.status-card-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  border: 1px solid rgba(43, 217, 255, 0.22);
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(7, 22, 42, 0.66);
  color: #d9f4ff;
  font-size: 0.86rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  cursor: pointer;
  transition:
    transform 140ms ease,
    border-color 140ms ease,
    background 140ms ease;
}

.status-card-toggle:hover {
  transform: translateY(-1px);
  border-color: rgba(43, 217, 255, 0.35);
  background: rgba(11, 34, 59, 0.74);
}

.status-card-chevron {
  display: inline-flex;
  line-height: 1;
  transform: rotate(180deg);
  transition: transform 140ms ease;
}

.status-card-chevron.open {
  transform: rotate(0deg);
}

.status-card-details {
  display: grid;
  gap: 12px;
}

.status-pill {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 54px;
  border-radius: 999px;
  padding: 0 20px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #04131d;
  border: none;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.18);
  cursor: pointer;
  transition:
    transform 140ms ease,
    filter 140ms ease;
}

.status-pill span,
.status-pill strong {
  font-size: 0.88rem;
}

.status-pill strong {
  font-weight: 700;
}

.status-pill:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.05);
}

.status-pill:disabled {
  cursor: progress;
  opacity: 0.84;
}

.tone-green .status-card-score,
.status-pill.tone-green {
  color: #0d2517;
}

.status-pill.tone-green {
  background: linear-gradient(90deg, #14c783, #1ce6a2);
}

.status-pill.tone-yellow {
  background: linear-gradient(90deg, #d7a600, #ffcd10);
}

.status-pill.tone-red {
  background: linear-gradient(90deg, #d53333, #ff6a6a);
}

.status-pill.tone-unknown {
  background: linear-gradient(90deg, #445d95, #7289bf);
  color: #e5eefc;
}

.tone-green .status-card-score {
  color: #1ee39b;
}

.tone-yellow .status-card-score {
  color: #ffd43d;
}

.tone-red .status-card-score {
  color: #ff7171;
}

.tone-unknown .status-card-score {
  color: #a3b7de;
}

.status-details-enter-active,
.status-details-leave-active {
  transition:
    opacity 160ms ease,
    transform 160ms ease;
}

.status-details-enter-from,
.status-details-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@media (max-width: 700px) {
  .status-card {
    border-radius: 20px;
    padding: 14px;
  }

  .status-card-overview {
    gap: 12px;
  }

  .status-card-score {
    font-size: 1.9rem;
  }

  .status-pill {
    min-height: 50px;
    padding: 0 16px;
  }

  .status-pill span,
  .status-pill strong,
  .status-card-toggle {
    font-size: 0.78rem;
  }
}
</style>
