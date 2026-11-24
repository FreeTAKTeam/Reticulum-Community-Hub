<template>
  <section class="auth-card" :class="{ 'auth-card--on': enabled }" aria-labelledby="authorization-setting-title">
    <div class="auth-kicker">Access</div>
    <div id="authorization-setting-title" class="auth-title">Authorization Required</div>
    <p class="auth-copy">
      When on, only registered members can chat with the hub or send it commands. Members are added by an operator
      in <RouterLink to="/users">Users</RouterLink>; <span class="mono">join</span> over LXMF no longer registers
      anyone. Mission data such as files, markers and checklists still needs mission rights from Users.
    </p>
    <p class="auth-copy auth-copy--note">
      Everyone already listed in Users is a member. Review the list before turning this on.
    </p>

    <p v-if="state.kind === 'loading'" class="auth-status" role="status">Loading current setting…</p>
    <p v-else-if="state.kind === 'failed'" class="auth-status auth-status--danger" role="alert">
      {{ state.message }}
      <button type="button" class="auth-retry" @click="load">Retry</button>
    </p>

    <label v-if="state.kind !== 'loading' && state.kind !== 'failed'" class="cui-switch">
      <input
        :checked="enabled"
        type="checkbox"
        class="cui-switch__input"
        :disabled="state.kind === 'saving'"
        aria-label="Only accept chat and commands from registered members"
        aria-describedby="authorization-setting-title"
        @change="onToggle"
      />
      <span class="cui-switch__track">
        <span class="cui-switch__indicator" aria-hidden="true"></span>
      </span>
      <span class="cui-switch__label">{{ switchLabel }}</span>
    </label>

    <BaseModal :open="confirmOpen" title="Require authorization?" size="sm" @close="confirmOpen = false">
      <p class="auth-modal-copy">
        Chat and commands from identities that are not listed in Users will be refused, and they will not be added
        to the list automatically. A <span class="mono">join</span> sent over LXMF will no longer register anyone;
        add new members from Users.
      </p>
      <p class="auth-modal-copy">
        Members can chat and use roster commands. Mission files, markers, checklists and mission changes also need
        mission rights, so give your members a team or mission role in Users first.
      </p>
      <p class="auth-modal-copy">Everyone currently listed in Users stays a member.</p>
      <template #footer>
        <div class="auth-modal-actions">
          <BaseButton variant="secondary" @click="confirmOpen = false">Cancel</BaseButton>
          <BaseButton @click="confirmEnable">Require authorization</BaseButton>
        </div>
      </template>
    </BaseModal>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import BaseButton from "./BaseButton.vue";
import BaseModal from "./BaseModal.vue";
import { fetchAuthorizationSetting, saveAuthorizationSetting } from "../api/authorization-setting";
import { useToastStore } from "../stores/toasts";

type CardState =
  | { kind: "loading" }
  | { kind: "ready"; required: boolean }
  | { kind: "saving"; required: boolean }
  | { kind: "failed"; message: string };

const toastStore = useToastStore();
const state = ref<CardState>({ kind: "loading" });
const confirmOpen = ref(false);

const enabled = computed(() =>
  state.value.kind === "ready" || state.value.kind === "saving" ? state.value.required : false
);
const switchLabel = computed(() => (state.value.kind === "saving" ? "Saving…" : enabled.value ? "On" : "Off"));

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error && error.message ? `${fallback}: ${error.message}` : fallback;

const load = async () => {
  state.value = { kind: "loading" };
  try {
    const setting = await fetchAuthorizationSetting();
    state.value = { kind: "ready", required: setting.authorization_required };
  } catch (error) {
    state.value = { kind: "failed", message: errorMessage(error, "Unable to load the authorization setting") };
  }
};

const save = async (required: boolean) => {
  if (state.value.kind !== "ready") {
    return;
  }
  const previous = state.value.required;
  state.value = { kind: "saving", required: previous };
  try {
    const setting = await saveAuthorizationSetting(required);
    state.value = { kind: "ready", required: setting.authorization_required };
    toastStore.push(
      setting.authorization_required ? "Authorization is now required" : "Authorization is no longer required",
      "success"
    );
  } catch (error) {
    state.value = { kind: "ready", required: previous };
    toastStore.push(errorMessage(error, "Unable to save the authorization setting"), "danger");
  }
};

const onToggle = (event: Event) => {
  const input = event.target as HTMLInputElement;
  const requested = input.checked;
  // The switch reflects the hub's value until the hub confirms a change.
  input.checked = enabled.value;
  if (requested) {
    confirmOpen.value = true;
    return;
  }
  void save(false);
};

const confirmEnable = () => {
  confirmOpen.value = false;
  void save(true);
};

onMounted(load);
</script>

<style scoped>
.auth-card {
  border: 1px solid rgba(55, 242, 255, 0.24);
  background: rgba(8, 20, 31, 0.76);
  border-radius: 12px;
  padding: 12px 14px;
  display: grid;
  gap: 5px;
}

.auth-card--on {
  border-color: rgba(255, 179, 92, 0.34);
}

.auth-kicker {
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(198, 246, 255, 0.62);
}

.auth-title {
  font-size: 14px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #e6feff;
}

.auth-copy,
.auth-status {
  margin: 0;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  line-height: 1.4;
  color: rgba(222, 251, 255, 0.75);
}

.auth-copy a {
  color: #37f2ff;
  text-decoration: underline;
}

.auth-copy--note {
  color: rgba(255, 210, 160, 0.85);
}

.auth-status--danger {
  color: rgba(255, 114, 114, 0.9);
}

.auth-retry {
  margin-left: 6px;
  text-decoration: underline;
}

.auth-modal-copy {
  margin: 0 0 10px;
  line-height: 1.45;
}

.auth-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
