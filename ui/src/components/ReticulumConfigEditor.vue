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
              <div class="text-xs font-semibold text-rth-text">Transport mode</div>
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
              <div class="text-xs font-semibold text-rth-text">Shared instance</div>
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

        <div class="space-y-3 rounded border border-rth-border bg-rth-panel-muted p-3">
          <div>
            <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Discovery</div>
            <div class="text-xs text-rth-muted">Global settings for announce/listen discovery and autoconnect behavior.</div>
          </div>
          <div class="grid gap-3 md:grid-cols-2">
            <div v-for="field in globalDiscoveryFields" :key="field.key" class="space-y-1">
              <label class="text-[10px] uppercase tracking-[0.18em] text-rth-muted">
                {{ field.label }}
              </label>
              <div class="text-[11px] text-rth-muted" v-if="field.description">{{ field.description }}</div>
              <label v-if="field.kind === 'boolean'" class="cui-switch">
                <input
                  :checked="getReticulumFieldBoolValue(field)"
                  type="checkbox"
                  class="cui-switch__input"
                  :aria-label="field.label"
                  @change="setReticulumFieldValue(field, ($event.target as HTMLInputElement).checked)"
                />
                <span class="cui-switch__track">
                  <span class="cui-switch__indicator" aria-hidden="true"></span>
                </span>
                <span class="cui-switch__label">
                  {{ getReticulumFieldBoolValue(field) ? "Yes" : "No" }}
                </span>
              </label>
              <input
                v-else-if="field.kind === 'number'"
                :value="getReticulumFieldTextValue(field)"
                type="number"
                class="cui-input w-full"
                :min="field.min"
                :max="field.max"
                :step="field.step ?? 1"
                :placeholder="field.placeholder"
                @input="setReticulumFieldValue(field, ($event.target as HTMLInputElement).value)"
              />
              <input
                v-else
                :value="getReticulumFieldTextValue(field)"
                type="text"
                class="cui-input w-full"
                :placeholder="field.placeholder ?? 'Value'"
                @input="setReticulumFieldValue(field, ($event.target as HTMLInputElement).value)"
              />
            </div>
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
          <div class="text-xs text-rth-muted">Schema-driven forms with advanced fallback key/value editing.</div>
        </div>
        <BaseButton variant="secondary" icon-left="plus" @click="addInterface">Add interface</BaseButton>
      </div>

      <div class="grid gap-3 text-xs text-rth-muted md:grid-cols-3">
        <div class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Runtime</div>
          <div class="mt-1 text-sm font-semibold text-rth-text">
            {{ capabilities.runtime_active ? "Active" : "Unavailable" }}
          </div>
        </div>
        <div class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">RNS version</div>
          <div class="mt-1 text-sm font-semibold text-rth-text">{{ capabilities.rns_version }}</div>
        </div>
        <div class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Creatable types</div>
          <div class="mt-1 text-sm font-semibold text-rth-text">{{ creatableTypeCount }}</div>
        </div>
      </div>

      <div v-if="!config.interfaces.length" class="text-xs text-rth-muted">
        No interfaces configured yet.
      </div>

      <div class="space-y-3">
        <div
          v-for="(iface, index) in config.interfaces"
          :key="iface.id"
          class="rounded border border-rth-border bg-rth-panel-muted p-4 space-y-4"
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

          <div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
            <ReticulumInterfaceTypeSelect
              v-model="iface.type"
              label="Type"
              :capabilities="capabilities"
              :allow-unknown-current-value="true"
            />
            <label class="cui-switch self-end">
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

          <div class="grid gap-3 md:grid-cols-2">
            <div v-for="field in getInterfaceTypedFields(iface)" :key="`${iface.id}-${field.key}`" class="space-y-1">
              <label class="text-[10px] uppercase tracking-[0.18em] text-rth-muted">{{ field.label }}</label>
              <div class="text-[11px] text-rth-muted" v-if="field.description">{{ field.description }}</div>
              <label v-if="field.kind === 'boolean'" class="cui-switch">
                <input
                  :checked="getInterfaceFieldBoolValue(iface, field)"
                  type="checkbox"
                  class="cui-switch__input"
                  :aria-label="`${iface.name} ${field.label}`"
                  @change="setInterfaceFieldValue(iface, field, ($event.target as HTMLInputElement).checked)"
                />
                <span class="cui-switch__track">
                  <span class="cui-switch__indicator" aria-hidden="true"></span>
                </span>
                <span class="cui-switch__label">{{ getInterfaceFieldBoolValue(iface, field) ? "Yes" : "No" }}</span>
              </label>
              <select
                v-else-if="field.kind === 'select'"
                :value="getInterfaceFieldTextValue(iface, field)"
                class="cui-input w-full"
                @change="setInterfaceFieldValue(iface, field, ($event.target as HTMLSelectElement).value)"
              >
                <option value="">Not set</option>
                <option v-for="option in field.options ?? []" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <input
                v-else-if="field.kind === 'number'"
                :value="getInterfaceFieldTextValue(iface, field)"
                type="number"
                class="cui-input w-full"
                :min="field.min"
                :max="field.max"
                :step="field.step ?? 1"
                :placeholder="field.placeholder"
                @input="setInterfaceFieldValue(iface, field, ($event.target as HTMLInputElement).value)"
              />
              <input
                v-else
                :value="getInterfaceFieldTextValue(iface, field)"
                type="text"
                class="cui-input w-full"
                :placeholder="field.placeholder ?? 'Value'"
                @input="setInterfaceFieldValue(iface, field, ($event.target as HTMLInputElement).value)"
              />
            </div>
          </div>

          <div
            v-if="iface.type === 'RNodeMultiInterface'"
            class="space-y-3 rounded border border-rth-border bg-rth-panel p-3"
          >
            <div class="flex items-center justify-between gap-2">
              <div>
                <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">RNode subinterfaces</div>
                <div class="text-xs text-rth-muted">Manage virtual ports and radio parameters.</div>
              </div>
              <BaseButton variant="secondary" size="sm" icon-left="plus" @click="addRNodeSubinterface(iface)">
                Add subinterface
              </BaseButton>
            </div>

            <div v-if="!getRNodeSubinterfaces(iface).length" class="text-xs text-rth-muted">
              No subinterfaces configured.
            </div>

            <div class="space-y-2">
              <div
                v-for="(row, rowIndex) in getRNodeSubinterfaces(iface)"
                :key="`${iface.id}-sub-${rowIndex}`"
                class="rounded border border-rth-border bg-rth-panel-muted p-3 space-y-2"
              >
                <div class="grid gap-2 md:grid-cols-3">
                  <input
                    :value="row.vport"
                    type="number"
                    class="cui-input"
                    placeholder="vport"
                    @input="updateRNodeSubinterfaceValue(iface, rowIndex, 'vport', ($event.target as HTMLInputElement).value)"
                  />
                  <input
                    :value="row.frequency"
                    type="number"
                    class="cui-input"
                    placeholder="frequency"
                    @input="
                      updateRNodeSubinterfaceValue(iface, rowIndex, 'frequency', ($event.target as HTMLInputElement).value)
                    "
                  />
                  <input
                    :value="row.bandwidth"
                    type="number"
                    class="cui-input"
                    placeholder="bandwidth"
                    @input="
                      updateRNodeSubinterfaceValue(iface, rowIndex, 'bandwidth', ($event.target as HTMLInputElement).value)
                    "
                  />
                  <input
                    :value="row.txpower"
                    type="number"
                    class="cui-input"
                    placeholder="txpower"
                    @input="updateRNodeSubinterfaceValue(iface, rowIndex, 'txpower', ($event.target as HTMLInputElement).value)"
                  />
                  <input
                    :value="row.spreadingfactor"
                    type="number"
                    class="cui-input"
                    placeholder="spreadingfactor"
                    @input="
                      updateRNodeSubinterfaceValue(
                        iface,
                        rowIndex,
                        'spreadingfactor',
                        ($event.target as HTMLInputElement).value
                      )
                    "
                  />
                  <input
                    :value="row.codingrate"
                    type="number"
                    class="cui-input"
                    placeholder="codingrate"
                    @input="
                      updateRNodeSubinterfaceValue(iface, rowIndex, 'codingrate', ($event.target as HTMLInputElement).value)
                    "
                  />
                  <input
                    :value="row.airtime_limit_short"
                    type="number"
                    class="cui-input"
                    placeholder="airtime_limit_short"
                    @input="
                      updateRNodeSubinterfaceValue(
                        iface,
                        rowIndex,
                        'airtime_limit_short',
                        ($event.target as HTMLInputElement).value
                      )
                    "
                  />
                  <input
                    :value="row.airtime_limit_long"
                    type="number"
                    class="cui-input"
                    placeholder="airtime_limit_long"
                    @input="
                      updateRNodeSubinterfaceValue(
                        iface,
                        rowIndex,
                        'airtime_limit_long',
                        ($event.target as HTMLInputElement).value
                      )
                    "
                  />
                  <div class="flex items-center justify-end">
                    <BaseButton variant="secondary" size="sm" icon-left="trash" @click="removeRNodeSubinterface(iface, rowIndex)">
                      Remove
                    </BaseButton>
                  </div>
                </div>
                <div class="flex flex-wrap gap-4">
                  <label class="cui-switch">
                    <input
                      :checked="row.flow_control"
                      type="checkbox"
                      class="cui-switch__input"
                      aria-label="Flow control"
                      @change="
                        updateRNodeSubinterfaceValue(
                          iface,
                          rowIndex,
                          'flow_control',
                          ($event.target as HTMLInputElement).checked
                        )
                      "
                    />
                    <span class="cui-switch__track">
                      <span class="cui-switch__indicator" aria-hidden="true"></span>
                    </span>
                    <span class="cui-switch__label">Flow control</span>
                  </label>
                  <label class="cui-switch">
                    <input
                      :checked="row.outgoing"
                      type="checkbox"
                      class="cui-switch__input"
                      aria-label="Outgoing"
                      @change="
                        updateRNodeSubinterfaceValue(
                          iface,
                          rowIndex,
                          'outgoing',
                          ($event.target as HTMLInputElement).checked
                        )
                      "
                    />
                    <span class="cui-switch__track">
                      <span class="cui-switch__indicator" aria-hidden="true"></span>
                    </span>
                    <span class="cui-switch__label">Outgoing</span>
                  </label>
                  <label class="cui-switch">
                    <input
                      :checked="row.enabled"
                      type="checkbox"
                      class="cui-switch__input"
                      aria-label="Enabled"
                      @change="
                        updateRNodeSubinterfaceValue(
                          iface,
                          rowIndex,
                          'enabled',
                          ($event.target as HTMLInputElement).checked
                        )
                      "
                    />
                    <span class="cui-switch__track">
                      <span class="cui-switch__indicator" aria-hidden="true"></span>
                    </span>
                    <span class="cui-switch__label">Enabled</span>
                  </label>
                </div>
              </div>
            </div>
          </div>

          <div>
            <div class="mb-2 text-[10px] uppercase tracking-[0.2em] text-rth-muted">Advanced settings</div>
            <KeyValueEditor
              :model-value="getInterfaceAdvancedSettings(iface)"
              empty-label="No additional advanced keys."
              @update:model-value="setInterfaceAdvancedSettings(iface, $event)"
            />
          </div>
        </div>
      </div>

      <div>
        <div class="mb-2 text-[10px] uppercase tracking-[0.2em] text-rth-muted">Interface defaults</div>
        <KeyValueEditor v-model="interfaceDefaults" empty-label="No global interface defaults." />
      </div>
    </div>

    <div class="cui-panel p-4 space-y-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Discovery monitor</div>
          <div class="text-sm font-semibold text-rth-text">Live runtime snapshot</div>
          <div class="text-xs text-rth-muted">Polling every 15s while the Reticulum tab is active.</div>
        </div>
        <BaseButton variant="secondary" icon-left="refresh" :disabled="discoveryLoading" @click="refreshDiscovery(true)">
          Refresh
        </BaseButton>
      </div>

      <div class="grid gap-3 md:grid-cols-4 text-xs">
        <div class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Runtime</div>
          <div class="mt-1 text-sm font-semibold text-rth-text">
            {{ discovery.runtime_active ? "Active" : "Unavailable" }}
          </div>
        </div>
        <div class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Auto-connect</div>
          <div class="mt-1 text-sm font-semibold text-rth-text">{{ discovery.should_autoconnect ? "Enabled" : "Disabled" }}</div>
        </div>
        <div class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Auto-connect limit</div>
          <div class="mt-1 text-sm font-semibold text-rth-text">
            {{ discovery.max_autoconnected_interfaces ?? "Not set" }}
          </div>
        </div>
        <div class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Required value</div>
          <div class="mt-1 text-sm font-semibold text-rth-text">{{ discovery.required_discovery_value ?? "Not set" }}</div>
        </div>
      </div>

      <div class="text-xs text-[#fecaca]" v-if="discoveryError">Discovery error: {{ discoveryError }}</div>

      <div v-if="!discovery.discovered_interfaces.length" class="text-xs text-rth-muted">
        No discovered interfaces reported by runtime.
      </div>

      <div v-else class="overflow-x-auto rounded border border-rth-border">
        <table class="w-full text-left text-xs">
          <thead class="bg-rth-panel-muted text-rth-muted uppercase tracking-[0.16em]">
            <tr>
              <th class="px-3 py-2">Name</th>
              <th class="px-3 py-2">Type</th>
              <th class="px-3 py-2">Status</th>
              <th class="px-3 py-2">Transport</th>
              <th class="px-3 py-2">Last heard</th>
              <th class="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-rth-border">
            <tr v-for="entry in discovery.discovered_interfaces" :key="entry.discovery_hash ?? `${entry.type}-${entry.name}`">
              <td class="px-3 py-2 text-rth-text">{{ entry.name ?? "Unnamed" }}</td>
              <td class="px-3 py-2 text-rth-text">{{ entry.type ?? "-" }}</td>
              <td class="px-3 py-2">
                <BaseBadge :tone="statusTone(entry.status)">
                  {{ entry.status ?? "unknown" }}
                </BaseBadge>
              </td>
              <td class="px-3 py-2 text-rth-text">
                {{ entry.transport ?? "-" }}
                <span v-if="entry.reachable_on || entry.port">
                  ({{ entry.reachable_on ?? "-" }}{{ entry.port ? `:${entry.port}` : "" }})
                </span>
              </td>
              <td class="px-3 py-2 text-rth-text">{{ entry.last_heard ?? "-" }}</td>
              <td class="px-3 py-2 text-right">
                <BaseButton
                  size="sm"
                  variant="secondary"
                  :disabled="!entry.config_entry"
                  @click="addDiscoveredInterface(entry)"
                >
                  Add to config
                </BaseButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="cui-panel p-4 space-y-3 text-xs">
      <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Local validation</div>
      <div v-if="!localValidation.errors.length && !localValidation.warnings.length" class="text-rth-muted">
        No local validation issues.
      </div>
      <div v-if="localValidation.errors.length" class="space-y-1">
        <div class="font-semibold text-[#fecaca]">Blocking errors</div>
        <div v-for="issue in localValidation.errors" :key="`err-${issue.path}-${issue.message}`" class="text-[#fecaca]">
          {{ issue.path }}: {{ issue.message }}
        </div>
      </div>
      <div v-if="localValidation.warnings.length" class="space-y-1">
        <div class="font-semibold text-[#fcd34d]">Warnings</div>
        <div
          v-for="issue in localValidation.warnings"
          :key="`warn-${issue.path}-${issue.message}`"
          class="text-[#fcd34d]"
        >
          {{ issue.path }}: {{ issue.message }}
        </div>
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
import { computed, onMounted, onUnmounted } from "vue";
import { storeToRefs } from "pinia";
import BaseBadge from "./BaseBadge.vue";
import BaseButton from "./BaseButton.vue";
import BaseFormattedOutput from "./BaseFormattedOutput.vue";
import BaseSelect from "./BaseSelect.vue";
import KeyValueEditor from "./KeyValueEditor.vue";
import ReticulumInterfaceTypeSelect from "./ReticulumInterfaceTypeSelect.vue";
import { useReticulumConfigStore } from "../stores/reticulum-config";
import { useReticulumDiscoveryStore } from "../stores/reticulum-discovery";
import { useToastStore } from "../stores/toasts";
import {
  createInterfaceId,
  getEntryValue,
  parseBool,
  parseConfigList,
  parseReticulumInterfaceConfigEntry,
  removeEntry,
  serializeConfigList,
  setEntryValue,
  type KeyValueItem,
  type ReticulumInterfaceConfig,
} from "../utils/reticulum-config";
import { validateReticulumConfigState } from "../utils/reticulum-config-validation";
import {
  DEFAULT_INTERFACE_TYPE,
  getCreatableInterfaceTypeGroups,
  getVisibleTypedFieldsForInterface,
  RETICULUM_GLOBAL_DISCOVERY_FIELDS,
  type ReticulumFieldDefinition,
} from "../utils/reticulum-interface-schema";
import type { ReticulumDiscoveredInterfaceEntry } from "../api/types";

type SubinterfaceRow = {
  vport: string;
  frequency: string;
  bandwidth: string;
  txpower: string;
  spreadingfactor: string;
  codingrate: string;
  flow_control: boolean;
  airtime_limit_short: string;
  airtime_limit_long: string;
  outgoing: boolean;
  enabled: boolean;
};

const configStore = useReticulumConfigStore();
const discoveryStore = useReticulumDiscoveryStore();
const toastStore = useToastStore();
const { config, error, validation, applyResult, rollbackResult, loading } = storeToRefs(configStore);
const {
  capabilities,
  discovery,
  loading: discoveryLoading,
  error: discoveryError,
} = storeToRefs(discoveryStore);

const globalDiscoveryFields = RETICULUM_GLOBAL_DISCOVERY_FIELDS;

const logLevelOptions = [
  { label: "0 - Critical only", value: "0" },
  { label: "1 - Errors", value: "1" },
  { label: "2 - Warnings", value: "2" },
  { label: "3 - Notices", value: "3" },
  { label: "4 - Info (default)", value: "4" },
  { label: "5 - Verbose", value: "5" },
  { label: "6 - Debug", value: "6" },
  { label: "7 - Extreme", value: "7" },
];

const createEmptySubinterfaceRow = (): SubinterfaceRow => ({
  vport: "",
  frequency: "",
  bandwidth: "",
  txpower: "",
  spreadingfactor: "",
  codingrate: "",
  flow_control: false,
  airtime_limit_short: "",
  airtime_limit_long: "",
  outgoing: false,
  enabled: true,
});

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

const filterExtras = (entries: KeyValueItem[], reserved: string[]) =>
  entries.filter((entry) => !reserved.includes(entry.key.trim().toLowerCase()));

const mergeExtras = (entries: KeyValueItem[], reserved: string[], next: KeyValueItem[]) => {
  const reservedEntries = entries.filter((entry) => reserved.includes(entry.key.trim().toLowerCase()));
  const sanitized = next.filter((entry) => entry.key.trim().length > 0);
  entries.splice(0, entries.length, ...reservedEntries, ...sanitized);
};

const reticulumSection = computed(() => getSection("reticulum"));
const loggingSection = computed(() => getSection("logging"));
const interfaceDefaultsSection = computed(() => getSection("interfaces"));

const enableTransport = computed({
  get: () => parseBool(getEntryValue(reticulumSection.value, "enable_transport"), false),
  set: (value: boolean) => {
    setEntryValue(reticulumSection.value, "enable_transport", value ? "yes" : "no");
  },
});

const shareInstance = computed({
  get: () => parseBool(getEntryValue(reticulumSection.value, "share_instance"), true),
  set: (value: boolean) => {
    setEntryValue(reticulumSection.value, "share_instance", value ? "yes" : "no");
  },
});

const logLevel = computed({
  get: () =>
    getEntryValue(loggingSection.value, "loglevel") ??
    getEntryValue(loggingSection.value, "log_level") ??
    "4",
  set: (value: string) => {
    setEntryValue(loggingSection.value, "loglevel", value);
    removeEntry(loggingSection.value, "log_level");
  },
});

const reticulumReservedKeys = [
  "enable_transport",
  "share_instance",
  ...globalDiscoveryFields.map((field) => field.key.toLowerCase()),
];

const reticulumExtras = computed({
  get: () => filterExtras(reticulumSection.value, reticulumReservedKeys),
  set: (next: KeyValueItem[]) => mergeExtras(reticulumSection.value, reticulumReservedKeys, next),
});

const loggingExtras = computed({
  get: () => filterExtras(loggingSection.value, ["loglevel", "log_level"]),
  set: (next: KeyValueItem[]) => mergeExtras(loggingSection.value, ["loglevel", "log_level"], next),
});

const interfaceDefaults = computed({
  get: () => interfaceDefaultsSection.value,
  set: (next: KeyValueItem[]) => {
    interfaceDefaultsSection.value.splice(0, interfaceDefaultsSection.value.length, ...next);
  },
});

const resolveInterfaceFieldValue = (iface: ReticulumInterfaceConfig, field: ReticulumFieldDefinition) => {
  const keys = [field.key, ...(field.aliases ?? [])];
  for (const key of keys) {
    const value = getEntryValue(iface.settings, key);
    if (value !== undefined) {
      return value;
    }
  }
  return undefined;
};

const setInterfaceFieldValue = (
  iface: ReticulumInterfaceConfig,
  field: ReticulumFieldDefinition,
  nextValue: string | boolean
) => {
  const keys = [field.key, ...(field.aliases ?? [])];
  keys.forEach((key) => removeEntry(iface.settings, key));

  if (field.kind === "boolean") {
    const boolValue = typeof nextValue === "boolean" ? nextValue : parseBool(String(nextValue), false);
    setEntryValue(iface.settings, field.key, boolValue ? "yes" : "no");
    return;
  }

  if (field.kind === "list") {
    const serialized = serializeConfigList(parseConfigList(String(nextValue)));
    if (!serialized) {
      return;
    }
    setEntryValue(iface.settings, field.key, serialized);
    return;
  }

  const value = String(nextValue).trim();
  if (!value) {
    return;
  }
  setEntryValue(iface.settings, field.key, value);
};

const getInterfaceFieldTextValue = (iface: ReticulumInterfaceConfig, field: ReticulumFieldDefinition) => {
  const value = resolveInterfaceFieldValue(iface, field);
  if (value === undefined) {
    return "";
  }
  if (field.kind === "list") {
    return parseConfigList(value).join(", ");
  }
  return value;
};

const getInterfaceFieldBoolValue = (iface: ReticulumInterfaceConfig, field: ReticulumFieldDefinition) =>
  parseBool(resolveInterfaceFieldValue(iface, field), false);

const getReticulumFieldTextValue = (field: ReticulumFieldDefinition) => {
  const value = getEntryValue(reticulumSection.value, field.key);
  if (value === undefined) {
    return "";
  }
  if (field.kind === "list") {
    return parseConfigList(value).join(", ");
  }
  return value;
};

const getReticulumFieldBoolValue = (field: ReticulumFieldDefinition) =>
  parseBool(getEntryValue(reticulumSection.value, field.key), false);

const setReticulumFieldValue = (field: ReticulumFieldDefinition, nextValue: string | boolean) => {
  if (field.kind === "boolean") {
    const boolValue = typeof nextValue === "boolean" ? nextValue : parseBool(String(nextValue), false);
    setEntryValue(reticulumSection.value, field.key, boolValue ? "yes" : "no");
    return;
  }
  if (field.kind === "list") {
    const serialized = serializeConfigList(parseConfigList(String(nextValue)));
    if (!serialized) {
      removeEntry(reticulumSection.value, field.key);
      return;
    }
    setEntryValue(reticulumSection.value, field.key, serialized);
    return;
  }
  const value = String(nextValue).trim();
  if (!value) {
    removeEntry(reticulumSection.value, field.key);
    return;
  }
  setEntryValue(reticulumSection.value, field.key, value);
};

const getInterfaceTypedFields = (iface: ReticulumInterfaceConfig) => {
  return getVisibleTypedFieldsForInterface(iface.type, {
    capabilities: capabilities.value,
    discoveryEnabled: false,
  });
};

const knownInterfaceSettingKeys = (iface: ReticulumInterfaceConfig) => {
  const keys = new Set<string>(["enabled", "interface_enabled"]);
  getInterfaceTypedFields(iface).forEach((field) => {
    keys.add(field.key.toLowerCase());
    (field.aliases ?? []).forEach((alias) => keys.add(alias.toLowerCase()));
  });
  if (iface.type === "RNodeMultiInterface") {
    keys.add("subinterfaces");
  }
  return keys;
};

const getInterfaceAdvancedSettings = (iface: ReticulumInterfaceConfig) => {
  const knownKeys = knownInterfaceSettingKeys(iface);
  return iface.settings.filter((entry) => !knownKeys.has(entry.key.trim().toLowerCase()));
};

const setInterfaceAdvancedSettings = (iface: ReticulumInterfaceConfig, next: KeyValueItem[]) => {
  const knownKeys = knownInterfaceSettingKeys(iface);
  const retained = iface.settings.filter((entry) => knownKeys.has(entry.key.trim().toLowerCase()));
  const sanitized = next.filter((entry) => entry.key.trim().length > 0);
  iface.settings = [...retained, ...sanitized];
};

const parseSubinterfaceRows = (value: string | undefined): SubinterfaceRow[] => {
  if (!value || !value.trim()) {
    return [];
  }
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.map((item) => ({
      ...createEmptySubinterfaceRow(),
      ...(typeof item === "object" && item ? item : {}),
      flow_control: parseBool(String((item as Record<string, unknown>)?.flow_control ?? ""), false),
      outgoing: parseBool(String((item as Record<string, unknown>)?.outgoing ?? ""), false),
      enabled: parseBool(String((item as Record<string, unknown>)?.enabled ?? ""), true),
    }));
  } catch {
    return [];
  }
};

const getRNodeSubinterfaces = (iface: ReticulumInterfaceConfig) =>
  parseSubinterfaceRows(getEntryValue(iface.settings, "subinterfaces"));

const setRNodeSubinterfaces = (iface: ReticulumInterfaceConfig, rows: SubinterfaceRow[]) => {
  if (!rows.length) {
    removeEntry(iface.settings, "subinterfaces");
    return;
  }
  setEntryValue(iface.settings, "subinterfaces", JSON.stringify(rows));
};

const addRNodeSubinterface = (iface: ReticulumInterfaceConfig) => {
  const rows = getRNodeSubinterfaces(iface);
  rows.push(createEmptySubinterfaceRow());
  setRNodeSubinterfaces(iface, rows);
};

const removeRNodeSubinterface = (iface: ReticulumInterfaceConfig, index: number) => {
  const rows = getRNodeSubinterfaces(iface);
  rows.splice(index, 1);
  setRNodeSubinterfaces(iface, rows);
};

const updateRNodeSubinterfaceValue = (
  iface: ReticulumInterfaceConfig,
  index: number,
  key: keyof SubinterfaceRow,
  value: string | boolean
) => {
  const rows = getRNodeSubinterfaces(iface);
  if (!rows[index]) {
    return;
  }
  (rows[index] as Record<string, string | boolean>)[key] = value;
  setRNodeSubinterfaces(iface, rows);
};

const creatableTypeGroups = computed(() => getCreatableInterfaceTypeGroups(capabilities.value));
const creatableTypeCount = computed(() =>
  creatableTypeGroups.value.reduce((count, group) => count + group.options.length, 0)
);
const defaultCreatableType = computed(
  () => creatableTypeGroups.value[0]?.options[0]?.value ?? DEFAULT_INTERFACE_TYPE
);

const addInterface = () => {
  const baseName = "New Interface";
  const existingNames = new Set(config.value.interfaces.map((iface) => iface.name.trim().toLowerCase()));
  let name = baseName;
  let counter = 1;
  while (existingNames.has(name.toLowerCase())) {
    counter += 1;
    name = `${baseName} ${counter}`;
  }
  config.value.interfaces.push({
    id: createInterfaceId(),
    name,
    type: defaultCreatableType.value,
    enabled: true,
    enableKey: "enabled",
    settings: [],
  });
};

const removeInterface = (index: number) => {
  config.value.interfaces.splice(index, 1);
};

const resolveImportedInterfaceName = (baseName: string) => {
  const cleaned = baseName.trim() || "Discovered Interface";
  const existingNames = new Set(config.value.interfaces.map((iface) => iface.name.trim().toLowerCase()));
  if (!existingNames.has(cleaned.toLowerCase())) {
    return cleaned;
  }
  let counter = 2;
  while (existingNames.has(`${cleaned} ${counter}`.toLowerCase())) {
    counter += 1;
  }
  return `${cleaned} ${counter}`;
};

const addDiscoveredInterface = (entry: ReticulumDiscoveredInterfaceEntry) => {
  if (
    !entry.config_entry ||
    (typeof entry.config_entry !== "object" && typeof entry.config_entry !== "string")
  ) {
    toastStore.push("Discovered interface has no importable config entry", "warning");
    return;
  }
  const parsed = parseReticulumInterfaceConfigEntry(
    entry.config_entry,
    (entry.name ?? "Discovered Interface").trim() || "Discovered Interface"
  );
  if (!parsed) {
    toastStore.push("Unable to parse discovered config entry", "danger");
    return;
  }
  parsed.name = resolveImportedInterfaceName(parsed.name);
  parsed.type = parsed.type || DEFAULT_INTERFACE_TYPE;
  config.value.interfaces.push(parsed);
  toastStore.push(`Imported interface ${parsed.name}`, "success");
};

const statusTone = (status: string | null | undefined) => {
  const normalized = (status ?? "").trim().toLowerCase();
  if (normalized === "available" || normalized === "active") {
    return "success";
  }
  if (normalized === "stale" || normalized === "unknown") {
    return "warning";
  }
  if (!normalized) {
    return "neutral";
  }
  return "danger";
};

const localValidation = computed(() => validateReticulumConfigState(config.value));

const loadConfig = async () => {
  try {
    await configStore.loadConfig();
    toastStore.push("Reticulum config loaded", "success");
  } catch {
    toastStore.push("Unable to load Reticulum config", "danger");
  }
};

const validateConfig = async () => {
  if (!localValidation.value.valid) {
    toastStore.push("Fix local validation errors before backend validation", "danger");
    return;
  }
  try {
    await configStore.validateConfig();
    toastStore.push("Validation complete", "success");
  } catch {
    toastStore.push("Validation failed", "danger");
  }
};

const applyConfig = async () => {
  if (!localValidation.value.valid) {
    toastStore.push("Fix local validation errors before apply", "danger");
    return;
  }
  try {
    await configStore.applyConfig();
    toastStore.push("Reticulum config applied", "success");
  } catch {
    toastStore.push("Apply failed", "danger");
  }
};

const rollbackConfig = async () => {
  try {
    await configStore.rollbackConfig();
    toastStore.push("Rollback complete", "warning");
  } catch {
    toastStore.push("Rollback failed", "danger");
  }
};

const refreshDiscovery = async (showToast = false) => {
  try {
    await discoveryStore.refresh();
    if (showToast) {
      toastStore.push("Discovery snapshot refreshed", "success");
    }
  } catch {
    if (showToast) {
      toastStore.push("Unable to refresh discovery snapshot", "danger");
    }
  }
};

onMounted(async () => {
  await loadConfig();
  await refreshDiscovery(false);
  discoveryStore.startPolling();
});

onUnmounted(() => {
  discoveryStore.stopPolling();
});
</script>
