<template>
  <Teleport to="body">
    <div class="setup-wizard" role="dialog" aria-modal="true" aria-labelledby="setup-wizard-title">
      <section class="setup-wizard__panel">
        <header class="setup-wizard__header">
          <div>
            <p class="setup-wizard__eyebrow">First-run configuration</p>
            <h1 id="setup-wizard-title">Initialize RCH</h1>
          </div>
          <div class="setup-wizard__status">
            <span>{{ currentStep + 1 }}</span>
            <span>/</span>
            <span>{{ steps.length }}</span>
          </div>
        </header>

        <nav class="setup-wizard__map" aria-label="Setup steps">
          <ol class="setup-wizard__map-list">
            <li
              v-for="(step, index) in stepMap"
              :key="step.id"
              :class="[
                'setup-wizard__map-step',
                {
                  'is-active': index === currentStep,
                  'is-complete': index < currentStep
                }
              ]"
              :aria-current="index === currentStep ? 'step' : undefined"
            >
              <span class="setup-wizard__map-index">{{ index + 1 }}</span>
              <span class="setup-wizard__map-copy">
                <strong>{{ step.label }}</strong>
                <small>{{ step.detail }}</small>
              </span>
            </li>
          </ol>
        </nav>

        <form class="setup-wizard__body" @submit.prevent="submitCurrentStep">
          <section v-if="currentStep === 0" class="setup-wizard__step">
            <p class="setup-wizard__eyebrow">Hub identity</p>
            <BaseInput
              v-model="hubName"
              label="Hub name"
              placeholder="RCH Field Hub"
              required
              :error="fieldError('hubName')"
            />
            <div class="setup-wizard__identity-card">
              <span class="setup-wizard__identity-label">Reticulum identity hash</span>
              <strong>{{ reticulumIdentityHash || "Generating identity..." }}</strong>
              <small>
                {{ reticulumIdentityCaption }}
              </small>
            </div>
          </section>

          <section v-else-if="currentStep === 1" class="setup-wizard__step">
            <div class="setup-wizard__step-head">
              <div>
                <p class="setup-wizard__eyebrow">Reticulum TCP</p>
                <h2>Interfaces</h2>
              </div>
              <div class="setup-wizard__selected-count">
                <strong>{{ selectedTcpEndpoints.length }}</strong>
                <span>selected</span>
              </div>
            </div>

            <div class="setup-wizard__server-list">
              <label
                v-for="server in tcpServerOptions"
                :key="server.endpoint"
                class="setup-wizard__server-option"
              >
                <input
                  type="checkbox"
                  :checked="selectedTcpEndpointSet.has(server.endpoint)"
                  @change="setTcpEndpoint(server.endpoint, ($event.target as HTMLInputElement).checked)"
                />
                <span class="setup-wizard__server-copy">
                  <strong>{{ server.name }}</strong>
                  <span>{{ server.endpoint }}</span>
                </span>
                <span v-if="server.isBootstrap" class="setup-wizard__bootstrap-badge">Bootstrap</span>
              </label>
            </div>

            <div class="setup-wizard__custom-row">
              <input
                v-model="customTcpEndpoint"
                type="text"
                class="cui-input"
                placeholder="Add custom endpoint (host:port or tcp://host:port)"
                @keyup.enter.prevent="addCustomTcpEndpoint"
              />
              <BaseButton variant="secondary" icon-left="plus" @click="addCustomTcpEndpoint">Add</BaseButton>
            </div>

            <div class="setup-wizard__active-endpoints">
              <span
                v-for="endpoint in selectedTcpEndpoints"
                :key="endpoint"
                class="setup-wizard__active-endpoint"
              >
                {{ endpoint }}
                <button type="button" @click="removeTcpEndpoint(endpoint)">Remove</button>
              </span>
            </div>
          </section>

          <section v-else-if="currentStep === 2" class="setup-wizard__step">
            <p class="setup-wizard__eyebrow">Remote access</p>
            <div class="setup-wizard__field-grid">
              <BaseInput
                v-model="remotePassword"
                label="Password"
                type="password"
                required
                :error="fieldError('remotePassword')"
              />
              <BaseInput
                v-model="remotePasswordConfirm"
                label="Confirm password"
                type="password"
                required
                :error="fieldError('remotePasswordConfirm')"
              />
            </div>
          </section>

          <section v-else class="setup-wizard__step">
            <p class="setup-wizard__eyebrow">Kill switch</p>
            <div class="setup-wizard__field-grid">
              <BaseInput
                v-model="killSwitchPin"
                label="Kill switch PIN"
                type="password"
                placeholder="Six digits"
                required
                :error="fieldError('killSwitchPin')"
              />
              <BaseInput
                v-model="killSwitchPinConfirm"
                label="Confirm PIN"
                type="password"
                placeholder="Six digits"
                required
                :error="fieldError('killSwitchPinConfirm')"
              />
            </div>
          </section>

          <p v-if="submitError" class="setup-wizard__error">{{ submitError }}</p>

          <footer class="setup-wizard__footer">
            <BaseButton variant="ghost" :disabled="currentStep === 0 || saving" @click="currentStep -= 1">
              Back
            </BaseButton>
            <BaseButton type="submit" icon-right="chevron-right" :loading="saving">
              {{ currentStep === steps.length - 1 ? "Complete setup" : "Next" }}
            </BaseButton>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BaseButton from "./BaseButton.vue";
import BaseInput from "./BaseInput.vue";
import { completeSetup, fetchSetupStatus } from "../api/setup";
import type { ApiError } from "../api/client";
import { createEmptyReticulumConfig, serializeReticulumConfig } from "../utils/reticulum-config";
import type { ReticulumInterfaceConfig } from "../utils/reticulum-config";
import {
  DEFAULT_TCP_COMMUNITY_ENDPOINT,
  TCP_COMMUNITY_SERVERS,
  endpointHostPort,
  normalizeTcpEndpoint,
  toTcpEndpoint
} from "../utils/tcp-community-servers";

type FieldName =
  | "hubName"
  | "remotePassword"
  | "remotePasswordConfirm"
  | "killSwitchPin"
  | "killSwitchPinConfirm";

const emit = defineEmits<{ (event: "completed", remotePassword: string): void }>();

const stepMap = [
  { id: "hub", label: "Hub", detail: "Identity" },
  { id: "tcp", label: "TCP", detail: "Interfaces" },
  { id: "remote", label: "Remote", detail: "Password" },
  { id: "pin", label: "PIN", detail: "Purge guard" }
] as const;
const steps = stepMap.map((step) => step.label);
const currentStep = ref(0);
const hubName = ref("RCH Field Hub");
const customTcpEndpoint = ref("");
const selectedTcpEndpoints = ref<string[]>([DEFAULT_TCP_COMMUNITY_ENDPOINT]);
const remotePassword = ref("");
const remotePasswordConfirm = ref("");
const killSwitchPin = ref("");
const killSwitchPinConfirm = ref("");
const reticulumIdentityHash = ref("");
const reticulumIdentityCreated = ref<boolean | null>(null);
const reticulumIdentityPath = ref("");
const saving = ref(false);
const validationActive = ref<Record<FieldName, boolean>>({
  hubName: false,
  remotePassword: false,
  remotePasswordConfirm: false,
  killSwitchPin: false,
  killSwitchPinConfirm: false
});
const submitError = ref("");

const tcpServerOptions = TCP_COMMUNITY_SERVERS.map((server) => ({
  name: server.name,
  endpoint: toTcpEndpoint(server),
  isBootstrap: Boolean(server.isBootstrap)
}));

const reticulumIdentityCaption = computed(() => {
  if (!reticulumIdentityHash.value) {
    return "RCH is creating local Reticulum identity material for this hub.";
  }
  const origin =
    reticulumIdentityCreated.value === true ? "Created for this hub." : "Loaded from existing identity material.";
  return reticulumIdentityPath.value ? `${origin} ${reticulumIdentityPath.value}` : origin;
});

const activateValidation = (...fields: FieldName[]) => {
  validationActive.value = fields.reduce(
    (next, field) => ({ ...next, [field]: true }),
    { ...validationActive.value }
  );
};

const fieldError = (name: FieldName) => {
  if (!validationActive.value[name]) {
    return "";
  }
  if (name === "hubName" && !hubName.value.trim()) {
    return "Hub name is required.";
  }
  if (name === "remotePassword" && remotePassword.value.trim().length < 8) {
    return "Use at least eight characters.";
  }
  if (name === "remotePasswordConfirm") {
    if (!remotePasswordConfirm.value.trim()) {
      return "Confirm the password.";
    }
    if (remotePassword.value.trim() !== remotePasswordConfirm.value.trim()) {
      return "Passwords do not match.";
    }
  }
  if (name === "killSwitchPin" && !/^\d{6}$/.test(killSwitchPin.value.trim())) {
    return "Use exactly six digits.";
  }
  if (name === "killSwitchPinConfirm") {
    if (!killSwitchPinConfirm.value.trim()) {
      return "Confirm the PIN.";
    }
    if (killSwitchPin.value.trim() !== killSwitchPinConfirm.value.trim()) {
      return "PINs do not match.";
    }
  }
  return "";
};

const hasFieldErrors = (...fields: FieldName[]) => fields.some((field) => Boolean(fieldError(field)));

const selectedTcpEndpointSet = computed(() => new Set(selectedTcpEndpoints.value));

const setTcpEndpoint = (endpoint: string, selected: boolean) => {
  const normalized = normalizeTcpEndpoint(endpoint);
  if (!normalized) {
    return;
  }
  if (selected) {
    selectedTcpEndpoints.value = [...new Set([...selectedTcpEndpoints.value, normalized])];
    return;
  }
  selectedTcpEndpoints.value = selectedTcpEndpoints.value.filter((item) => item !== normalized);
};

const removeTcpEndpoint = (endpoint: string) => {
  setTcpEndpoint(endpoint, false);
};

const addCustomTcpEndpoint = () => {
  const normalized = normalizeTcpEndpoint(customTcpEndpoint.value);
  if (!normalized) {
    submitError.value = "Enter a TCP endpoint as host:port.";
    return;
  }
  setTcpEndpoint(normalized, true);
  customTcpEndpoint.value = "";
  submitError.value = "";
};

const tcpInterfaceName = (endpoint: string) => {
  const known = tcpServerOptions.find((server) => server.endpoint === endpoint);
  return known?.name ?? `TCP ${endpoint}`;
};

const validateCurrentStep = () => {
  submitError.value = "";
  if (currentStep.value === 0) {
    activateValidation("hubName");
    return !hasFieldErrors("hubName");
  }
  if (currentStep.value === 1 && selectedTcpEndpoints.value.length === 0) {
    submitError.value = "Select at least one TCP server.";
    return false;
  }
  if (currentStep.value === 2) {
    activateValidation("remotePassword", "remotePasswordConfirm");
    return !hasFieldErrors("remotePassword", "remotePasswordConfirm");
  }
  if (currentStep.value === 3) {
    activateValidation("killSwitchPin", "killSwitchPinConfirm");
    return !hasFieldErrors("killSwitchPin", "killSwitchPinConfirm");
  }
  return !submitError.value;
};

const reticulumConfigText = computed(() => {
  const config = createEmptyReticulumConfig();
  config.sectionOrder = ["reticulum", "logging", "interfaces"];
  config.sections.reticulum = [
    { key: "enable_transport", value: "yes" },
    { key: "share_instance", value: "yes" }
  ];
  config.sections.logging = [{ key: "loglevel", value: "4" }];
  config.interfaces = selectedTcpEndpoints.value
    .map((endpoint, index): ReticulumInterfaceConfig | null => {
      const parsed = endpointHostPort(endpoint);
      if (!parsed) {
        return null;
      }
      return {
        id: `tcp-community-${index}`,
        name: tcpInterfaceName(endpoint),
        type: "TCPClientInterface",
        enabled: true,
        enableKey: "interface_enabled",
        settings: [
          { key: "target_host", value: parsed.host },
          { key: "target_port", value: parsed.port }
        ]
      };
    })
    .filter((iface): iface is ReticulumInterfaceConfig => Boolean(iface));
  return serializeReticulumConfig(config);
});

const complete = async () => {
  saving.value = true;
  submitError.value = "";
  try {
    await completeSetup({
      hub_name: hubName.value.trim(),
      remote_password: remotePassword.value.trim(),
      kill_switch_pin: killSwitchPin.value.trim(),
      reticulum_config_text: reticulumConfigText.value
    });
    emit("completed", remotePassword.value.trim());
  } catch (error) {
    const apiError = error as ApiError;
    const body = apiError.body as { detail?: string; message?: string } | undefined;
    submitError.value = body?.detail ?? body?.message ?? apiError.message ?? "Setup failed.";
  } finally {
    saving.value = false;
  }
};

const submitCurrentStep = () => {
  if (!validateCurrentStep()) {
    return;
  }
  if (currentStep.value < steps.length - 1) {
    currentStep.value += 1;
    return;
  }
  void complete();
};

onMounted(async () => {
  try {
    const status = await fetchSetupStatus();
    reticulumIdentityHash.value = status.reticulum_identity_hash ?? "";
    reticulumIdentityCreated.value = status.reticulum_identity_created ?? null;
    reticulumIdentityPath.value = status.reticulum_identity_path ?? "";
  } catch {
    reticulumIdentityHash.value = "";
    reticulumIdentityCreated.value = null;
    reticulumIdentityPath.value = "";
  }
});
</script>

<style scoped>
@import "./FirstRunSetupWizard.css";
</style>
