<template>
  <BaseModal :open="true" title="Send marker" @close="close">
    <form class="space-y-4" @submit.prevent="send">
      <p>{{ markerName }}</p>
      <RecipientPicker id="marker-share-destination" v-model="destination" label="Recipient"
        :options="recipientOptions" :loading="usersStore.resourceLoading.clients" :accept-typed="parseAddress"
        placeholder="Search users by name or address"
        hint="Send this marker to a Sideband, REM, or Columba user, or paste an LXMF address." :disabled="sending" />
      <p v-if="usersStore.errors.clients" class="text-amber-300">
        Users could not be loaded ({{ usersStore.errors.clients }}). You can still paste an LXMF address.
      </p>
      <p v-if="error" role="alert" class="text-red-400">{{ error }}</p>
      <p v-if="receipt" role="status">Marker queued. Delivery status is available in Messages.</p>
      <div class="flex justify-end gap-2">
        <BaseButton type="button" variant="ghost" :disabled="sending" @click="close">Close</BaseButton>
        <BaseButton type="submit" :disabled="sending || !destination.trim() || !!receipt">
          {{ sending ? "Sending…" : "Send marker" }}
        </BaseButton>
      </div>
    </form>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import BaseModal from "./BaseModal.vue";
import BaseButton from "./BaseButton.vue";
import RecipientPicker, { type RecipientOption } from "./RecipientPicker.vue";
import { shareMarker, type MarkerShareReceipt } from "../api/marker-share";
import { useUsersStore } from "../stores/users";

const props = defineProps<{ markerId: string; markerName: string }>();
const emit = defineEmits<{ (event: "close"): void }>();
const destination = ref("");
const usersStore = useUsersStore();

const LXMF_ADDRESS = /^[0-9a-f]{32}$/;
const parseAddress = (text: string) => {
  const candidate = text.trim().toLowerCase();
  return LXMF_ADDRESS.test(candidate) ? candidate : null;
};

const recipientOptions = computed<RecipientOption[]>(() => {
  const seen = new Set<string>();
  const options: (RecipientOption & { unnamed: boolean })[] = [];
  for (const client of usersStore.clients) {
    const address = parseAddress(client.id ?? "");
    if (!address || seen.has(address)) continue;
    seen.add(address);
    const name = client.display_name?.trim();
    options.push({
      value: address,
      label: name || `${address.slice(0, 8)}…`,
      detail: address,
      tag: client.is_rem_capable ? "REM" : "LXMF",
      unnamed: !name
    });
  }
  // Named users first, alphabetically; users known only by address after them.
  return options
    .sort((left, right) => Number(left.unnamed) - Number(right.unnamed) ||
      left.label.localeCompare(right.label, undefined, { sensitivity: "base" }))
    .map(({ unnamed: _unnamed, ...option }) => option);
});

onMounted(() => {
  if (!usersStore.clients.length) void usersStore.fetchClients();
});
const sending = ref(false);
const error = ref("");
const receipt = ref<MarkerShareReceipt | null>(null);
const controller = new AbortController();
onBeforeUnmount(() => controller.abort());
const close = () => { if (!sending.value) emit("close"); };
const send = async () => {
  if (sending.value || receipt.value) return;
  sending.value = true;
  error.value = "";
  try {
    receipt.value = await shareMarker(props.markerId, destination.value, controller.signal);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : "Unable to send marker.";
  } finally {
    sending.value = false;
  }
};
</script>
