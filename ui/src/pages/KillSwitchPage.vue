<template>
  <div class="kill-switch-hud" :class="{ 'is-deleting': isDeleting, 'is-ready': isReady }">
    <section class="kill-layout">
      <aside class="kill-panel kill-panel--arm">
        <div class="kill-panel-header">
          <div>
            <p class="kill-eyebrow">Operator lockout</p>
            <h1>KILL SWITCH</h1>
          </div>
          <span class="kill-accent-chip">Purge</span>
        </div>

        <div class="kill-arm-stack" aria-label="Kill switch arming controls">
          <div class="kill-arm-row">
            <div>
              <span>ARM A</span>
              <small>Primary operator gate</small>
            </div>
            <BaseSwitch
              :model-value="armA"
              :disabled="controlsLocked"
              :label="armA ? 'On' : 'Off'"
              @update:model-value="setArm('a', $event)"
            />
          </div>
          <div class="kill-arm-row">
            <div>
              <span>ARM B</span>
              <small>Independent confirm gate</small>
            </div>
            <BaseSwitch
              :model-value="armB"
              :disabled="controlsLocked"
              :label="armB ? 'On' : 'Off'"
              @update:model-value="setArm('b', $event)"
            />
          </div>
        </div>

        <form class="kill-pin" @submit.prevent="beginDeletion">
          <label id="kill-pin-label">PIN</label>
          <div class="kill-pin-digits" role="group" aria-labelledby="kill-pin-label" aria-describedby="kill-pin-help">
            <input
              v-for="index in pinLength"
              :key="index"
              :ref="(el) => setPinCellRef(el, index - 1)"
              :value="pinDigits[index - 1]"
              inputmode="numeric"
              type="password"
              maxlength="1"
              pattern="[0-9]*"
              autocomplete="off"
              :aria-label="`PIN digit ${index}`"
              :class="{ filled: Boolean(pinDigits[index - 1]) }"
              @focus="selectPinCell"
              @input="onPinDigitInput(index - 1, $event)"
              @keydown="onPinDigitKeydown(index - 1, $event)"
              @paste="onPinDigitPaste(index - 1, $event)"
            />
          </div>
          <p id="kill-pin-help">First-boot PIN enrolled. Entry remains masked.</p>
          <p v-if="initialPin" class="kill-initial-pin">
            <span>Initial PIN</span>
            <strong>{{ initialPin }}</strong>
          </p>
          <button class="kill-purge-button" type="submit" :disabled="!canSubmit">
            {{ actionButtonLabel }}
          </button>
        </form>

        <div class="kill-safety-strip">
          <span class="kill-warning-dot" aria-hidden="true"></span>
          <div>
            <strong>{{ safetyTitle }}</strong>
            <span>{{ safetyMessage }}</span>
          </div>
        </div>
      </aside>

      <main class="kill-panel kill-panel--visual">
        <div class="kill-panel-header kill-panel-header--center">
          <div>
            <p class="kill-eyebrow">Containment sequence</p>
            <h2>DATABASE PURGE</h2>
          </div>
          <span class="kill-progress-number">{{ progress }}%</span>
        </div>

        <div class="kill-orbit" aria-label="Deletion visualization">
          <div class="kill-orbit-grid" aria-hidden="true"></div>
          <svg class="kill-orbit-svg" viewBox="0 0 420 420" role="img" aria-label="Clock-inspired deletion scanner">
            <defs>
              <linearGradient id="kill-scan-gradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#37f2ff" stop-opacity="0" />
                <stop offset="60%" stop-color="#37f2ff" stop-opacity="0.85" />
                <stop offset="100%" stop-color="#37f2ff" stop-opacity="0.15" />
              </linearGradient>
            </defs>
            <circle class="kill-ring kill-ring--outer" cx="210" cy="210" r="184" />
            <circle class="kill-ring kill-ring--mid" cx="210" cy="210" r="146" />
            <circle class="kill-ring kill-ring--inner" cx="210" cy="210" r="96" />
            <circle class="kill-ring kill-ring--core" cx="210" cy="210" r="42" />
            <g class="kill-ticks">
              <line
                v-for="tick in orbitTicks"
                :key="tick.index"
                :x1="tick.x1"
                :y1="tick.y1"
                :x2="tick.x2"
                :y2="tick.y2"
                :class="{ major: tick.major }"
              />
            </g>
            <path class="kill-scan-wedge" d="M210 210 L210 26 A184 184 0 0 1 340 80 Z" />
            <path class="kill-wave kill-wave--cyan" :d="irregularOrbitPath" />
            <path class="kill-wave kill-wave--danger" :d="dangerOrbitPath" />
          </svg>
          <div class="kill-orbit-core">
            <span>{{ coreStateLabel }}</span>
            <strong>{{ progress }}%</strong>
          </div>
          <span
            v-for="particle in particles"
            :key="particle.id"
            class="kill-particle"
            :style="{ left: particle.left, top: particle.top, animationDelay: particle.delay }"
            aria-hidden="true"
          ></span>
        </div>

        <div class="kill-progress">
          <div class="kill-progress-copy">
            <span>DELETING</span>
            <small>{{ progressCopy }}</small>
          </div>
          <div class="kill-progress-track" role="progressbar" aria-label="Database purge progress" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100">
            <span class="kill-progress-fill" :style="{ width: `${progress}%` }"></span>
            <span class="kill-progress-cursor" :style="{ left: `${progress}%` }"></span>
          </div>
        </div>
      </main>

      <aside class="kill-panel kill-panel--targets">
        <div class="kill-panel-header">
          <div>
            <p class="kill-eyebrow">Purge targets</p>
            <h2>Erase manifest</h2>
          </div>
          <span class="kill-accent-chip kill-accent-chip--muted">{{ manifestStateLabel }}</span>
        </div>

        <div class="kill-target-list">
          <div v-for="target in targets" :key="target.label" class="kill-target-row">
            <div class="kill-target-icon" aria-hidden="true">{{ target.short }}</div>
            <div class="kill-target-body">
              <div class="kill-target-title">
                <span>{{ target.label }}</span>
                <small>{{ targetStateLabel(target.state) }}</small>
              </div>
              <div class="kill-target-meta">{{ targetValueLabel(target) }}</div>
              <div class="kill-target-track">
                <span :style="{ width: `${targetProgress(target)}%` }"></span>
              </div>
            </div>
          </div>
        </div>

        <div class="kill-mini-status">
          <div>
            <span>Operator</span>
            <strong>{{ armA && armB ? "Confirmed" : "Pending" }}</strong>
          </div>
          <div>
            <span>PIN state</span>
            <strong>{{ pinValue.length === pinLength ? "Masked entry" : `${pinValue.length}/${pinLength}` }}</strong>
          </div>
          <div>
            <span>Mode</span>
            <strong>{{ modeLabel }}</strong>
          </div>
        </div>
      </aside>
    </section>

    <div
      v-if="confirmDialogOpen"
      class="kill-confirm-backdrop"
      role="presentation"
      @click.self="cancelPurgeConfirmation"
    >
      <section
        class="kill-confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="kill-confirm-title"
        aria-describedby="kill-confirm-copy"
        @keydown.esc="cancelPurgeConfirmation"
      >
        <div class="kill-confirm-header">
          <p class="kill-eyebrow">Final authorization</p>
          <h2 id="kill-confirm-title">CONFIRM PURGE</h2>
        </div>
        <p id="kill-confirm-copy">
          This will delete all databases, configuration files, and Reticulum identity material known to this runtime.
        </p>
        <div class="kill-confirm-actions">
          <button class="kill-confirm-button kill-confirm-button--secondary" type="button" @click="cancelPurgeConfirmation">
            Cancel
          </button>
          <button class="kill-confirm-button kill-confirm-button--danger" type="button" @click="confirmPurge">
            Confirm
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { ComponentPublicInstance } from "vue";
import {
  authorizeKillSwitch,
  fetchKillSwitchStatus,
  setKillSwitchArms,
  startKillSwitchPurge
} from "../api/kill-switch";
import type { KillSwitchStatus, KillSwitchTarget, KillSwitchTargetState } from "../api/kill-switch";
import BaseSwitch from "../components/BaseSwitch.vue";
import "./styles/KillSwitchPage.css";

const pinLength = 6;
const armA = ref(false);
const armB = ref(false);
const pinDigits = ref(["", "", "", "", "", ""]);
const pinCellRefs = ref<HTMLInputElement[]>([]);
const pinValue = computed(() => pinDigits.value.join(""));
const status = ref<KillSwitchStatus | null>(null);
const statusBusy = ref(false);
const errorMessage = ref("");
const orbitPhase = ref(0);
const confirmDialogOpen = ref(false);
let statusPollTimer: ReturnType<typeof window.setInterval> | undefined;
let orbitFrame: number | undefined;

const progress = computed(() => status.value?.progress_percent ?? 0);
const initialPin = computed(() => status.value?.initial_pin ?? "");
const isDeleting = computed(() => status.value?.state === "deleting");
const isCompleted = computed(() => status.value?.state === "completed");
const isAuthorized = computed(() => status.value?.state === "authorized");
const controlsLocked = computed(() => statusBusy.value || isDeleting.value || isCompleted.value);
const targets = computed(() => status.value?.targets ?? []);
const isReady = computed(() => armA.value && armB.value && pinValue.value.length === pinLength);
const canSubmit = computed(() => isReady.value && !controlsLocked.value && !isCompleted.value);
const safetyTitle = computed(() => {
  if (statusBusy.value) {
    return "Core request pending";
  }
  if (isCompleted.value) {
    return "Purge complete";
  }
  if (isDeleting.value) {
    return "Purge active";
  }
  if (isAuthorized.value) {
    return "Authorized";
  }
  if (isReady.value) {
    return "Ready for final authorization";
  }
  return "Awaiting dual arm";
});
const safetyMessage = computed(() => {
  if (errorMessage.value) {
    return errorMessage.value;
  }
  if (statusBusy.value) {
    return "Waiting for the northbound core response.";
  }
  if (isCompleted.value) {
    return status.value?.message ?? "Purge completed.";
  }
  if (isDeleting.value) {
    return status.value?.message ?? "Purge in progress.";
  }
  if (!armA.value || !armB.value) {
    return "Both switches must be armed before final authorization.";
  }
  if (pinValue.value.length < pinLength) {
    return "Enter the masked first-boot PIN to enable authorization.";
  }
  return status.value?.message ?? "Controls are armed. Final action is available.";
});
const actionButtonLabel = computed(() => {
  if (statusBusy.value) {
    return "Core request...";
  }
  if (isDeleting.value) {
    return "Deletion running";
  }
  if (isCompleted.value) {
    return "Purge complete";
  }
  return "Authorize purge";
});
const coreStateLabel = computed(() => {
  if (isCompleted.value) {
    return "COMPLETE";
  }
  if (isDeleting.value) {
    return "DELETING";
  }
  if (isAuthorized.value) {
    return "AUTHORIZED";
  }
  if (armA.value && armB.value) {
    return "ARMED";
  }
  return "STANDBY";
});
const progressCopy = computed(() => {
  if (isCompleted.value) {
    return "Wipe sequence completed";
  }
  if (isDeleting.value) {
    return "Secure wipe sequence in progress";
  }
  if (isAuthorized.value) {
    return "Northbound authorization accepted";
  }
  return "Awaiting authorization";
});
const manifestStateLabel = computed(() => {
  if (isCompleted.value) {
    return "Erased";
  }
  if (isDeleting.value) {
    return "Active";
  }
  if (armA.value && armB.value) {
    return "Queued";
  }
  return "Locked";
});
const modeLabel = computed(() => {
  if (isCompleted.value) {
    return "Complete";
  }
  if (isDeleting.value) {
    return "Deleting";
  }
  if (isAuthorized.value) {
    return "Authorized";
  }
  if (armA.value && armB.value) {
    return "Armed";
  }
  return "Dry";
});

const particles = Array.from({ length: 28 }, (_, index) => ({
  id: index,
  left: `${34 + ((index * 17) % 34)}%`,
  top: `${30 + ((index * 23) % 42)}%`,
  delay: `${(index % 9) * 0.16}s`
}));

const orbitTicks = Array.from({ length: 60 }, (_, index) => {
  const angle = (index * 6 - 90) * (Math.PI / 180);
  const major = index % 5 === 0;
  const outer = 190;
  const inner = major ? 174 : 181;
  return {
    index,
    major,
    x1: 210 + outer * Math.cos(angle),
    y1: 210 + outer * Math.sin(angle),
    x2: 210 + inner * Math.cos(angle),
    y2: 210 + inner * Math.sin(angle)
  };
});

const setPinCellRef = (el: Element | ComponentPublicInstance | null, index: number) => {
  if (el instanceof HTMLInputElement) {
    pinCellRefs.value[index] = el;
  }
};

const focusPinCell = (index: number) => {
  pinCellRefs.value[Math.max(0, Math.min(pinLength - 1, index))]?.focus();
};

const selectPinCell = (event: FocusEvent) => {
  const target = event.target;
  if (target instanceof HTMLInputElement) {
    target.select();
  }
};

const applyPinDigits = (startIndex: number, value: string) => {
  const digits = value.replace(/\D+/g, "").slice(0, pinLength - startIndex).split("");
  if (digits.length === 0) {
    pinDigits.value[startIndex] = "";
    return;
  }
  const next = [...pinDigits.value];
  digits.forEach((digit, offset) => {
    next[startIndex + offset] = digit;
  });
  pinDigits.value = next;
  focusPinCell(Math.min(startIndex + digits.length, pinLength - 1));
};

const onPinDigitInput = (index: number, event: Event) => {
  const target = event.target as HTMLInputElement;
  applyPinDigits(index, target.value);
};

const onPinDigitPaste = (index: number, event: ClipboardEvent) => {
  event.preventDefault();
  applyPinDigits(index, event.clipboardData?.getData("text") ?? "");
};

const onPinDigitKeydown = (index: number, event: KeyboardEvent) => {
  if (event.key === "Backspace") {
    event.preventDefault();
    const next = [...pinDigits.value];
    if (next[index]) {
      next[index] = "";
      pinDigits.value = next;
      return;
    }
    if (index > 0) {
      next[index - 1] = "";
      pinDigits.value = next;
      focusPinCell(index - 1);
    }
  } else if (event.key === "ArrowLeft" && index > 0) {
    event.preventDefault();
    focusPinCell(index - 1);
  } else if (event.key === "ArrowRight" && index < pinLength - 1) {
    event.preventDefault();
    focusPinCell(index + 1);
  }
};

const applyStatus = (nextStatus: KillSwitchStatus) => {
  status.value = nextStatus;
  armA.value = nextStatus.arm_a;
  armB.value = nextStatus.arm_b;
};

const refreshStatus = async () => {
  try {
    applyStatus(await fetchKillSwitchStatus());
    errorMessage.value = "";
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Unable to refresh kill switch status.";
  }
};

const withCoreRequest = async (request: () => Promise<KillSwitchStatus>) => {
  statusBusy.value = true;
  try {
    applyStatus(await request());
    errorMessage.value = "";
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Kill switch request failed.";
  } finally {
    statusBusy.value = false;
  }
};

const setArm = (arm: "a" | "b", value: boolean) => {
  const nextArmA = arm === "a" ? value : armA.value;
  const nextArmB = arm === "b" ? value : armB.value;
  void withCoreRequest(() => setKillSwitchArms(nextArmA, nextArmB));
};

const targetProgress = (target: KillSwitchTarget) => {
  if (target.total <= 0) {
    return 0;
  }
  return Math.max(target.state === "erasing" ? 8 : 0, Math.round((target.erased / target.total) * 100));
};

const targetStateLabel = (state: KillSwitchTargetState) => {
  if (state === "erased") {
    return "Erased";
  }
  if (state === "erasing") {
    return "Erasing";
  }
  if (state === "failed") {
    return "Failed";
  }
  return "Queued";
};

const formatBytes = (value: number) => {
  if (value >= 1_000_000_000_000) {
    return `${(value / 1_000_000_000_000).toFixed(2)} TB`;
  }
  if (value >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)} GB`;
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)} MB`;
  }
  return `${value.toLocaleString()} B`;
};

const targetValueLabel = (target: KillSwitchTarget) => {
  if (target.unit === "bytes") {
    return `${formatBytes(target.erased)} / ${formatBytes(target.total)}`;
  }
  return `${target.erased.toLocaleString()} / ${target.total.toLocaleString()} ${target.unit}`;
};

const calculateIrregularOrbitPath = (radius: number, amplitude: number, points: number, phase: number) => {
  const values = Array.from({ length: points + 1 }, (_, index) => {
    const angle = (index / points) * Math.PI * 2;
    const jitter =
      Math.sin(index * 1.9 + phase) * amplitude +
      Math.cos(index * 0.7 - phase * 0.58) * (amplitude * 0.45) +
      Math.sin(index * 3.1 + phase * 0.38) * (amplitude * 0.22);
    const r = radius + jitter;
    const x = 210 + r * Math.cos(angle);
    const y = 210 + r * Math.sin(angle);
    return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  return `${values.join(" ")} Z`;
};

const irregularOrbitPath = computed(() => calculateIrregularOrbitPath(118, 11, 28, orbitPhase.value));
const dangerOrbitPath = computed(() => calculateIrregularOrbitPath(82, 7, 20, orbitPhase.value * 1.4 + 0.8));

const animateOrbit = () => {
  orbitPhase.value += 0.006;
  orbitFrame = window.requestAnimationFrame(animateOrbit);
};

const beginDeletion = () => {
  if (!isReady.value) {
    return;
  }
  confirmDialogOpen.value = true;
};

const cancelPurgeConfirmation = () => {
  confirmDialogOpen.value = false;
};

const confirmPurge = () => {
  if (!isReady.value || controlsLocked.value) {
    confirmDialogOpen.value = false;
    return;
  }
  confirmDialogOpen.value = false;
  void withCoreRequest(async () => {
    await authorizeKillSwitch(pinValue.value);
    return startKillSwitchPurge();
  });
};

onBeforeUnmount(() => {
  if (statusPollTimer) {
    window.clearInterval(statusPollTimer);
  }
  if (orbitFrame !== undefined) {
    window.cancelAnimationFrame(orbitFrame);
  }
});

onMounted(() => {
  void refreshStatus();
  statusPollTimer = window.setInterval(() => {
    void refreshStatus();
  }, 1000);
  orbitFrame = window.requestAnimationFrame(animateOrbit);
});
</script>
