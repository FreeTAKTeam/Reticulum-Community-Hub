<template>
  <div ref="scroller" class="message-scroller" tabindex="0" aria-label="Conversation messages" @scroll="onScroll">
    <div v-if="!messages.length" class="panel-empty">{{ loading ? 'Loading messages...' : 'No messages yet. Start a conversation.' }}</div>
    <div class="message-stack" :style="{ height: `${totalHeight}px` }">
      <article v-for="row in visible" :key="row.message.message_id" :ref="(element) => observeRow(element, row.message.message_id)"
        class="message-card" :class="{ outbound: row.message.direction === 'outbound' }" :data-message-id="row.message.message_id"
        :style="{ transform: `translateY(${row.top}px)` }">
        <div class="message-meta">
          <div class="message-source">{{ sourceLabel(row.message) }}</div>
          <div class="message-state"><span>{{ row.message.state || 'sent' }}</span><span>{{ timestamp(row.message.created_at) }}</span></div>
        </div>
        <div class="message-body">{{ row.message.content || 'Attachment delivered.' }}</div>
        <div v-if="row.message.attachments?.length" class="attachment-list">
          <div v-for="attachment in row.message.attachments" :key="`${attachment.file_id}-${attachment.name}`" class="attachment-card">
            <img v-if="attachment.category === 'image' && previews[attachmentPath(attachment)]" :src="previews[attachmentPath(attachment)]" :alt="attachment.name || 'Image attachment'" />
            <div class="attachment-name">{{ attachment.name }}</div>
            <div class="attachment-type">{{ attachment.media_type || 'File' }} · {{ size(attachment.size) }}</div>
            <BaseButton variant="secondary" icon-left="download" @click="$emit('download', attachment)">Download</BaseButton>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from "vue";
import type { ChatAttachment, ChatMessage } from "../../api/types";
import { endpoints } from "../../api/endpoints";
import BaseButton from "../BaseButton.vue";
import { useAttachmentPreviews } from "../../composables/useAttachmentPreviews";
import { resolveChatRetention } from "../../config/chat-retention";

const props = defineProps<{ messages: ChatMessage[]; loading: boolean; sourceLabel: (message: ChatMessage) => string }>();
defineEmits<{ download: [attachment: ChatAttachment] }>();
const scroller = ref<HTMLDivElement | null>(null);
const scrollTop = ref(0);
const viewportHeight = ref(600);
const measurements = ref(new Map<string, number>());
const mountedRows = new Map<string, Element>();
const overscan = resolveChatRetention().overscanRows;
const estimatedHeight = 128;
const gap = 12;
let observer: ResizeObserver | undefined;
let pinned = true;
const layout = (messages: ChatMessage[]) => {
  let top = 0;
  return messages.map((message) => {
    const height = Math.max(96, measurements.value.get(message.message_id ?? "") ?? estimatedHeight);
    const row = { message, top, height }; top += height + gap; return row;
  });
};
const rows = computed(() => layout(props.messages));
const captureAnchor = (messages = props.messages) => {
  const row = layout(messages).find((entry) => entry.top + entry.height >= scrollTop.value);
  return row ? { id: row.message.message_id, offset: scrollTop.value - row.top } : undefined;
};
const restoreAnchor = (anchor: ReturnType<typeof captureAnchor>) => {
  const row = anchor && rows.value.find((entry) => entry.message.message_id === anchor.id);
  if (row && scroller.value) { scroller.value.scrollTop = row.top + anchor.offset; onScroll(); }
};
const totalHeight = computed(() => { const last = rows.value.at(-1); return last ? last.top + last.height : 0; });
const visible = computed(() => {
  const all = rows.value;
  const first = all.findIndex((row) => row.top + row.height >= scrollTop.value);
  const last = all.findIndex((row) => row.top > scrollTop.value + viewportHeight.value);
  return all.slice(Math.max(0, (first < 0 ? all.length : first) - overscan), (last < 0 ? all.length : last) + overscan);
});
const onScroll = () => {
  const element = scroller.value;
  if (!element) { return; }
  scrollTop.value = element.scrollTop; viewportHeight.value = element.clientHeight || 600;
  pinned = element.scrollHeight - element.clientHeight - element.scrollTop < 48;
};
const scrollToLatest = async () => {
  pinned = true; await nextTick();
  if (scroller.value) { scroller.value.scrollTop = scroller.value.scrollHeight; onScroll(); }
};
const scrollToStart = async () => { pinned = false; await nextTick(); if (scroller.value) { scroller.value.scrollTop = 0; onScroll(); } };
const observeRow = (element: Element | ComponentPublicInstance | null, id?: string) => {
  if (!id) { return; }
  const previous = mountedRows.get(id);
  if (previous === element) { return; }
  if (previous) { observer?.unobserve(previous); mountedRows.delete(id); }
  if (element instanceof Element) { mountedRows.set(id, element); observer?.observe(element); }
};
watch(() => props.messages, async (messages, previous) => {
  if (messages.length === previous?.length && messages.every((message, index) => message === previous[index])) { return; }
  const anchor = captureAnchor(previous);
  const ids = new Set(messages.map((message) => message.message_id));
  measurements.value = new Map([...measurements.value].filter(([id]) => ids.has(id)));
  if (pinned) { await scrollToLatest(); }
  else { restoreAnchor(anchor); }
}, { flush: "post" });
onMounted(() => {
  if (typeof ResizeObserver !== "undefined") {
    observer = new ResizeObserver((entries) => {
      const anchor = captureAnchor();
      const next = new Map(measurements.value);
      let changed = false;
      for (const entry of entries) {
        if (entry.target === scroller.value) { viewportHeight.value = entry.contentRect.height; continue; }
        const id = entry.target.getAttribute("data-message-id");
        const height = entry.target.getBoundingClientRect().height;
        if (id && next.get(id) !== height) { next.set(id, height); changed = true; }
      }
      if (changed) { measurements.value = next; }
      if (changed && pinned) { void scrollToLatest(); }
      else if (changed) { restoreAnchor(anchor); }
    });
    if (scroller.value) { observer.observe(scroller.value); }
    mountedRows.forEach((element) => observer?.observe(element));
  }
  void scrollToLatest();
});
onBeforeUnmount(() => { observer?.disconnect(); mountedRows.clear(); measurements.value.clear(); });
const attachmentPath = (attachment: ChatAttachment) => attachment.file_id ? `${attachment.category === "image" ? endpoints.images : endpoints.files}/${attachment.file_id}/raw` : "";
const previewPaths = computed(() => visible.value.flatMap((row) => (row.message.attachments ?? []).filter((attachment) => attachment.category === "image").map(attachmentPath)).filter(Boolean));
const { urls: previews } = useAttachmentPreviews(previewPaths);
const timestamp = (value?: string) => value ? new Date(value).toLocaleTimeString() : "";
const size = (bytes = 0) => bytes < 1024 ? `${bytes}B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)}KB` : `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
defineExpose({ scrollToLatest, scrollToStart });
</script>
<style scoped>
.message-scroller { min-height: 0; overflow-y: auto; overflow-anchor: none; padding: 8px; border: 1px solid rgba(55,242,255,.2); border-radius: 12px; background: rgba(2,8,15,.5); }
.message-scroller:focus-visible { outline: 2px solid #37f2ff; outline-offset: -2px; }
.message-stack { position: relative; }
.message-card { position: absolute; top: 0; left: 0; right: 0; min-height: 96px; box-sizing: border-box; border: 1px solid rgba(55,242,255,.25); border-radius: 12px; padding: 12px; background: rgba(10,26,39,.9); }
.message-card.outbound { border-color: rgba(255,179,92,.4); background: rgba(37,26,21,.9); }
.message-meta { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 11px; color: #b9dbe5; }
.message-source { font-weight: 600; overflow-wrap: anywhere; }
.message-state { display: flex; gap: 12px; }
.message-body { white-space: pre-wrap; overflow-wrap: anywhere; font-family: "Rajdhani", "Barlow", sans-serif; font-size: 16px; line-height: 1.5; margin-top: 10px; }
.attachment-list { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
.attachment-card { border: 1px solid rgba(55,242,255,.2); border-radius: 8px; padding: 10px; max-width: 280px; overflow-wrap: anywhere; }
.attachment-card img { display: block; width: 180px; height: 120px; object-fit: contain; }
.attachment-name { font-size: 12px; }
.attachment-type { font-size: 11px; margin: 6px 0; }
.panel-empty { padding: 16px; color: #b9dbe5; }
</style>
