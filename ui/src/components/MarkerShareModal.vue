<template>
  <BaseModal :open="true" title="Send marker" @close="close">
    <form class="space-y-4" @submit.prevent="send">
      <p>{{ markerName }}</p>
      <BaseInput id="marker-share-destination" v-model="destination" label="Recipient LXMF address"
        hint="Send this marker to a Sideband, REM, or Columba contact." :disabled="sending" />
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
import { onBeforeUnmount, ref } from "vue";
import BaseModal from "./BaseModal.vue";
import BaseInput from "./BaseInput.vue";
import BaseButton from "./BaseButton.vue";
import { shareMarker, type MarkerShareReceipt } from "../api/marker-share";

const props = defineProps<{ markerId: string; markerName: string }>();
const emit = defineEmits<{ (event: "close"): void }>();
const destination = ref("");
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
