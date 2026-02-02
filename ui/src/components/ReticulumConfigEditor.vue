<template>
  <div class="space-y-6">
    <div class="rounded border border-rth-border bg-rth-panel-muted p-4">
      <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Notice</div>
      <div class="text-sm font-semibold text-rth-text">Restart required after apply</div>
      <div class="text-xs text-rth-muted">
        Reticulum reads these settings on startup. Apply saves to the file resolved by
        <span class="text-rth-text">[hub].reticulum_config_path</span>, but changes take effect after the hub restarts.
      </div>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <div class="cui-panel p-4 space-y-4">
        <div>
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Reticulum</div>
          <div class="text-sm font-semibold text-rth-text">Core settings</div>
        </div>
        <div class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="text-xs font-semibold text-rth-text">Transport Mode</div>
              <div class="text-xs text-rth-muted">Route announces, respond to path requests, and forward traffic.</div>
            </div>
            <label class="cui-switch">
              <input
                v-model="enableTransport"
                type="checkbox"
                class="cui-switch__input"
                aria-label="Enable transport mode"
              />
              <span class="cui-switch__track">
                <span class="cui-switch__indicator" aria-hidden="true"></span>
              </span>
              <span class="cui-switch__label">{{ enableTransport ? "On" : "Off" }}</span>
            </label>
          </div>
        </div>
        <div class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="text-xs font-semibold text-rth-text">Shared Instance</div>
              <div class="text-xs text-rth-muted">Allow other local apps to use the shared Reticulum instance.</div>
            </div>
            <label class="cui-switch">
              <input
                v-model="shareInstance"
                type="checkbox"
                class="cui-switch__input"
                aria-label="Enable shared instance"
              />
              <span class="cui-switch__track">
                <span class="cui-switch__indicator" aria-hidden="true"></span>
              </span>
              <span class="cui-switch__label">{{ shareInstance ? "On" : "Off" }}</span>
            </label>
          </div>
        </div>
        <div>
          <div class="mb-2 text-[10px] uppercase tracking-[0.2em] text-rth-muted">Advanced reticulum settings</div>
          <KeyValueEditor v-model="reticulumExtras" />
        </div>
      </div>

      <div class="cui-panel p-4 space-y-4">
        <div>
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Logging</div>
          <div class="text-sm font-semibold text-rth-text">Telemetry verbosity</div>
        </div>
        <BaseSelect v-model="logLevel" label="Log level" :options="logLevelOptions" />
        <div>
          <div class="mb-2 text-[10px] uppercase tracking-[0.2em] text-rth-muted">Additional logging settings</div>
          <KeyValueEditor v-model="loggingExtras" />
        </div>
      </div>
    </div>

    <div class="cui-panel p-4 space-y-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Interfaces</div>
          <div class="text-sm font-semibold text-rth-text">Reticulum transports</div>
          <div class="text-xs text-rth-muted">Add, edit, and tune every interface property.</div>
        </div>
        <BaseButton variant="secondary" icon-left="plus" @click="addInterface">Add interface</BaseButton>
      </div>

      <div v-if="!config.interfaces.length" class="text-xs text-rth-muted">
        No interfaces configured yet.
      </div>

      <div class="space-y-3">
        <div
          v-for="(iface, index) in config.interfaces"
          :key="iface.id"
          class="rounded border border-rth-border bg-rth-panel-muted p-4 space-y-3"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="flex-1 space-y-2">
              <label class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Interface name</label>
              <input v-model="iface.name" type="text" class="cui-input w-full" placeholder="Interface name" />
            </div>
            <BaseButton variant="secondary" size="sm" icon-left="trash" @click="removeInterface(index)">
              Remove
            </BaseButton>
          </div>

          <div class="flex flex-wrap items-center gap-4">
            <ReticulumInterfaceTypeSelect v-model="iface.type" label="Type" />
            <label class="cui-switch">
              <input
                v-model="iface.enabled"
                type="checkbox"
                class="cui-switch__input"
                aria-label="Enable interface"
              />
              <span class="cui-switch__track">
                <span class="cui-switch__indicator" aria-hidden="true"></span>
              </span>
              <span class="cui-switch__label">{{ iface.enabled ? "Enabled" : "Disabled" }}</span>
            </label>
          </div>

          <div>
            <div class="mb-2 text-[10px] uppercase tracking-[0.2em] text-rth-muted">Interface settings</div>
            <KeyValueEditor v-model="iface.settings" empty-label="No interface properties yet." />
          </div>
        </div>
      </div>

      <div>
        <div class="mb-2 text-[10px] uppercase tracking-[0.2em] text-rth-muted">Interface defaults</div>
        <KeyValueEditor v-model="interfaceDefaults" empty-label="No global interface defaults." />
      </div>
    </div>

    <div class="space-y-3 text-xs text-rth-muted">
      <div v-if="error" class="text-[#fecaca]">Error: {{ error }}</div>
      <div v-if="validation">
        <div class="text-xs text-rth-muted">Validation</div>
        <BaseFormattedOutput class="mt-2" :value="validation" />
      </div>
      <div v-if="applyResult">
        <div class="text-xs text-rth-muted">Apply result</div>
        <BaseFormattedOutput class="mt-2" :value="applyResult" />
      </div>
      <div v-if="rollbackResult">
        <div class="text-xs text-rth-muted">Rollback result</div>
        <BaseFormattedOutput class="mt-2" :value="rollbackResult" />
      </div>
    </div>

    <div class="flex flex-wrap justify-end gap-2">
      <BaseButton variant="secondary" icon-left="refresh" :disabled="loading" @click="loadConfig">Reload</BaseButton>
      <BaseButton variant="secondary" icon-left="check" :disabled="loading" @click="validateConfig">Validate</BaseButton>
      <BaseButton icon-left="save" :disabled="loading" @click="applyConfig">Apply</BaseButton>
      <BaseButton variant="secondary" icon-left="undo" :disabled="loading" @click="rollbackConfig">
        Rollback
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { storeToRefs } from "pinia";
import BaseButton from "./BaseButton.vue";
import BaseFormattedOutput from "./BaseFormattedOutput.vue";
import BaseSelect from "./BaseSelect.vue";
import KeyValueEditor from "./KeyValueEditor.vue";
import ReticulumInterfaceTypeSelect from "./ReticulumInterfaceTypeSelect.vue";
import { useReticulumConfigStore } from "../stores/reticulum-config";
import { useToastStore } from "../stores/toasts";
import { createInterfaceId, type KeyValueItem } from "../utils/reticulum-config";

const configStore = useReticulumConfigStore();
const toastStore = useToastStore();
const { config, error, validation, applyResult, rollbackResult, loading } = storeToRefs(configStore);

const logLevelOptions = [
  { label: "0 - Critical only", value: "0" },
  { label: "1 - Errors", value: "1" },
  { label: "2 - Warnings", value: "2" },
  { label: "3 - Notices", value: "3" },
  { label: "4 - Info (default)", value: "4" },
  { label: "5 - Verbose", value: "5" },
  { label: "6 - Debug", value: "6" },
  { label: "7 - Extreme", value: "7" }
];

const getSection = (name: string) => {
  const key = name.trim().toLowerCase();
  if (!config.value.sections[key]) {
    config.value.sections[key] = [];
  }
  if (!config.value.sectionOrder.includes(key)) {
    config.value.sectionOrder.push(key);
  }
  return config.value.sections[key];
};

const findEntryIndex = (entries: KeyValueItem[], key: string) =>
  entries.findIndex((entry) => entry.key.trim().toLowerCase() === key);

const getEntryValue = (entries: KeyValueItem[], key: string) => {
  const index = findEntryIndex(entries, key);
  return index >= 0 ? entries[index].value : undefined;
};

const setEntryValue = (entries: KeyValueItem[], key: string, value: string) => {
  const index = findEntryIndex(entries, key);
  if (index >= 0) {
    entries[index].value = value;
    return;
  }
  entries.push({ key, value });
};

const removeEntry = (entries: KeyValueItem[], key: string) => {
  const index = findEntryIndex(entries, key);
  if (index >= 0) {
    entries.splice(index, 1);
  }
};

const parseBool = (value: string | undefined, fallback = false) => {
  if (!value) {
    return fallback;
  }
  const normalized = value.trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(normalized);
};

const reticulumSection = computed(() => getSection("reticulum"));
const loggingSection = computed(() => getSection("logging"));
const interfaceDefaultsSection = computed(() => getSection("interfaces"));

const enableTransport = computed({
  get: () => parseBool(getEntryValue(reticulumSection.value, "enable_transport"), false),
  set: (value: boolean) => {
    setEntryValue(reticulumSection.value, "enable_transport", value ? "yes" : "no");
  }
});

const shareInstance = computed({
  get: () => parseBool(getEntryValue(reticulumSection.value, "share_instance"), true),
  set: (value: boolean) => {
    setEntryValue(reticulumSection.value, "share_instance", value ? "yes" : "no");
  }
});

const logLevel = computed({
  get: () =>
    getEntryValue(loggingSection.value, "loglevel") ??
    getEntryValue(loggingSection.value, "log_level") ??
    "4",
  set: (value: string) => {
    setEntryValue(loggingSection.value, "loglevel", value);
    removeEntry(loggingSection.value, "log_level");
  }
});

const filterExtras = (entries: KeyValueItem[], reserved: string[]) =>
  entries.filter((entry) => !reserved.includes(entry.key.trim().toLowerCase()));

const mergeExtras = (entries: KeyValueItem[], reserved: string[], next: KeyValueItem[]) => {
  const reservedEntries = entries.filter((entry) => reserved.includes(entry.key.trim().toLowerCase()));
  const sanitized = next.filter((entry) => entry.key.trim().length > 0);
  entries.splice(0, entries.length, ...reservedEntries, ...sanitized);
};

const reticulumExtras = computed({
  get: () => filterExtras(reticulumSection.value, ["enable_transport", "share_instance"]),
  set: (next: KeyValueItem[]) => mergeExtras(reticulumSection.value, ["enable_transport", "share_instance"], next)
});

const loggingExtras = computed({
  get: () => filterExtras(loggingSection.value, ["loglevel", "log_level"]),
  set: (next: KeyValueItem[]) => mergeExtras(loggingSection.value, ["loglevel", "log_level"], next)
});

const interfaceDefaults = computed({
  get: () => interfaceDefaultsSection.value,
  set: (next: KeyValueItem[]) => {
    interfaceDefaultsSection.value.splice(0, interfaceDefaultsSection.value.length, ...next);
  }
});

const addInterface = () => {
  const baseName = "New Interface";
  const existingNames = new Set(config.value.interfaces.map((iface) => iface.name.trim()));
  let name = baseName;
  let counter = 1;
  while (existingNames.has(name)) {
    counter += 1;
    name = `${baseName} ${counter}`;
  }
  config.value.interfaces.push({
    id: createInterfaceId(),
    name,
    type: "TCPClientInterface",
    enabled: true,
    settings: []
  });
};

const removeInterface = (index: number) => {
  config.value.interfaces.splice(index, 1);
};

const loadConfig = async () => {
  try {
    await configStore.loadConfig();
    toastStore.push("Reticulum config loaded", "success");
  } catch (err) {
    toastStore.push("Unable to load Reticulum config", "danger");
  }
};

const validateConfig = async () => {
  try {
    await configStore.validateConfig();
    toastStore.push("Validation complete", "success");
  } catch (err) {
    toastStore.push("Validation failed", "danger");
  }
};

const applyConfig = async () => {
  try {
    await configStore.applyConfig();
    toastStore.push("Reticulum config applied", "success");
  } catch (err) {
    toastStore.push("Apply failed", "danger");
  }
};

const rollbackConfig = async () => {
  try {
    await configStore.rollbackConfig();
    toastStore.push("Rollback complete", "warning");
  } catch (err) {
    toastStore.push("Rollback failed", "danger");
  }
};

onMounted(async () => {
  await loadConfig();
});
</script>
