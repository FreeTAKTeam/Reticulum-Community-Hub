<template>
  <div class="boot-screen" role="status" aria-live="polite">
    <div class="boot-screen__glow"></div>
    <div class="boot-screen__content">
      <div class="boot-screen__header">
        <div class="boot-screen__title">Initializing Reticulum Backend</div>
        <div class="boot-screen__status-row">
          <span class="boot-screen__pulse"></span>
          <span class="boot-screen__status-text">Polling WebSocket API</span>
          <span class="boot-screen__status-chip" :class="statusClass">[{{ statusText }}]</span>
        </div>
        <div class="boot-screen__detail">{{ detail }}</div>
      </div>

      <div class="boot-screen__logo-frame">
        <img
          class="boot-screen__logo cui-logo-spin"
          src="/RCH_vector.svg"
          alt="Reticulum Community Hub"
          loading="eager"
        />
        <div class="boot-screen__ring"></div>
      </div>

      <div class="boot-screen__progress" :style="{ '--progress': `${progress}` }">
        <div class="boot-screen__progress-track">
          <div class="boot-screen__progress-fill"></div>
          <div class="boot-screen__progress-scan"></div>
        </div>
        <div class="boot-screen__progress-label">Loading core services</div>
      </div>

      <div class="boot-screen__log">
        <div v-for="(line, index) in logs" :key="index" class="boot-screen__log-line">
          <span class="boot-screen__log-marker">›</span>
          <span>{{ line }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

type BootStatus = "pending" | "retrying" | "online";

const props = defineProps<{
  status: BootStatus;
  statusText: string;
  detail: string;
  progress: number;
  logs: string[];
}>();

const statusClass = computed(() => {
  if (props.status === "online") {
    return "boot-screen__status-chip--ok";
  }
  if (props.status === "retrying") {
    return "boot-screen__status-chip--warn";
  }
  return "boot-screen__status-chip--pending";
});
</script>

<style scoped>
.boot-screen {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px;
  color: #d9f6ff;
  background: radial-gradient(circle at 20% 20%, rgba(16, 40, 70, 0.7), transparent 55%),
    radial-gradient(circle at 80% 20%, rgba(8, 32, 60, 0.7), transparent 50%),
    linear-gradient(135deg, #060d16, #081a2b 45%, #06101b);
  overflow: hidden;
  animation: boot-fade-in 600ms ease;
}

.boot-screen::before {
  content: "";
  position: absolute;
  inset: -120px;
  background: radial-gradient(circle at 1px 1px, rgba(55, 242, 255, 0.16) 1px, transparent 0)
      0 0 / 18px 18px,
    radial-gradient(circle at 1px 1px, rgba(255, 255, 255, 0.08) 1px, transparent 0) 0 0 / 36px 36px;
  opacity: 0.55;
  pointer-events: none;
}

.boot-screen__glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 50% 30%, rgba(0, 180, 255, 0.22), transparent 60%);
  opacity: 0.7;
  pointer-events: none;
}

.boot-screen__content {
  position: relative;
  width: min(1100px, 96vw);
  min-height: min(720px, 88vh);
  display: grid;
  grid-template-rows: auto auto auto 1fr;
  padding: 40px 40px 36px;
  border: 1px solid rgba(0, 180, 255, 0.35);
  background: linear-gradient(180deg, rgba(7, 23, 38, 0.94), rgba(6, 18, 30, 0.98));
  box-shadow: inset 0 0 28px rgba(6, 12, 20, 0.65), 0 0 26px rgba(0, 180, 255, 0.15);
  clip-path: polygon(18px 0, calc(100% - 30px) 0, 100% 30px, 100% calc(100% - 18px),
      calc(100% - 18px) 100%, 0 100%, 0 18px);
  backdrop-filter: blur(6px);
  animation: boot-rise 700ms ease;
}

.boot-screen__content::before {
  content: "";
  position: absolute;
  inset: 8px;
  border: 1px solid rgba(0, 180, 255, 0.12);
  clip-path: polygon(14px 0, calc(100% - 24px) 0, 100% 24px, 100% calc(100% - 14px),
      calc(100% - 14px) 100%, 0 100%, 0 14px);
  pointer-events: none;
}

.boot-screen__header {
  display: grid;
  gap: 10px;
  text-align: left;
}

.boot-screen__title {
  font-size: 1.3rem;
  letter-spacing: 0.32em;
  text-transform: uppercase;
  font-weight: 600;
  color: #d5fbff;
  text-shadow: 0 0 16px rgba(55, 242, 255, 0.35);
}

.boot-screen__status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.9rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(211, 247, 255, 0.75);
}

.boot-screen__pulse {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #38f2ff;
  box-shadow: 0 0 10px rgba(55, 242, 255, 0.7);
  animation: boot-pulse 1.8s ease-in-out infinite;
}

.boot-screen__status-chip {
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.65rem;
  letter-spacing: 0.2em;
  border: 1px solid rgba(231, 243, 255, 0.15);
  background: rgba(7, 18, 26, 0.8);
}

.boot-screen__status-chip--pending {
  border-color: rgba(0, 180, 255, 0.55);
  color: #90e8ff;
}

.boot-screen__status-chip--warn {
  border-color: rgba(255, 122, 64, 0.7);
  color: #ffd1bf;
}

.boot-screen__status-chip--ok {
  border-color: rgba(0, 208, 176, 0.8);
  color: #9ff2e6;
}

.boot-screen__detail {
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  color: rgba(204, 230, 255, 0.6);
  word-break: break-all;
}

.boot-screen__logo-frame {
  position: relative;
  display: grid;
  place-items: center;
  margin: 32px 0 22px;
}

.boot-screen__logo {
  width: clamp(220px, 28vw, 320px);
  height: auto;
  filter: drop-shadow(0 0 18px rgba(55, 242, 255, 0.25));
}

.boot-screen__ring {
  position: absolute;
  width: clamp(280px, 34vw, 400px);
  height: clamp(280px, 34vw, 400px);
  border-radius: 999px;
  border: 1px dashed rgba(55, 242, 255, 0.35);
  opacity: 0.6;
  animation: boot-ring 12s linear infinite reverse;
}

.boot-screen__progress {
  display: grid;
  gap: 10px;
  margin-bottom: 20px;
}

.boot-screen__progress-track {
  position: relative;
  height: 12px;
  border-radius: 999px;
  border: 1px solid rgba(0, 180, 255, 0.35);
  background: linear-gradient(90deg, rgba(6, 20, 32, 0.96), rgba(10, 34, 52, 0.96));
  overflow: hidden;
}

.boot-screen__progress-fill {
  position: absolute;
  inset: 0;
  width: calc(var(--progress, 0) * 1%);
  background: linear-gradient(90deg, rgba(0, 180, 255, 0.25), rgba(55, 242, 255, 0.85));
  transition: width 300ms ease;
}

.boot-screen__progress-scan {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.45), transparent);
  transform: translateX(-60%);
  animation: boot-scan 2.4s ease-in-out infinite;
}

.boot-screen__progress-label {
  font-size: 0.78rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(183, 222, 255, 0.75);
}

.boot-screen__log {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border: 1px solid rgba(0, 180, 255, 0.2);
  background: rgba(7, 16, 26, 0.6);
  font-family: "JetBrains Mono", "Cascadia Mono", "Consolas", monospace;
  font-size: 0.8rem;
  color: rgba(200, 235, 255, 0.72);
  text-transform: uppercase;
  letter-spacing: 0.16em;
  min-height: 180px;
}

.boot-screen__log-line {
  display: flex;
  align-items: center;
  gap: 10px;
}

.boot-screen__log-marker {
  color: rgba(55, 242, 255, 0.8);
}

@keyframes boot-scan {
  0% {
    transform: translateX(-60%);
  }
  50% {
    transform: translateX(10%);
  }
  100% {
    transform: translateX(120%);
  }
}

@keyframes boot-pulse {
  0%,
  100% {
    opacity: 0.4;
    transform: scale(0.9);
  }
  50% {
    opacity: 1;
    transform: scale(1.15);
  }
}

@keyframes boot-ring {
  to {
    transform: rotate(360deg);
  }
}

@keyframes boot-fade-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes boot-rise {
  from {
    transform: translateY(12px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

@media (max-width: 720px) {
  .boot-screen__content {
    padding: 24px 20px;
    min-height: min(640px, 90vh);
  }

  .boot-screen__title {
    font-size: 1.05rem;
    letter-spacing: 0.22em;
  }

  .boot-screen__status-row {
    flex-wrap: wrap;
  }

  .boot-screen__log {
    font-size: 0.68rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .boot-screen,
  .boot-screen__content {
    animation: none;
  }

  .boot-screen__pulse,
  .boot-screen__ring,
  .boot-screen__progress-scan {
    animation: none;
  }
}
</style>
