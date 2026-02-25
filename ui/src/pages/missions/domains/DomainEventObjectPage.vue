<template>
  <MissionDomainRecordPage
    title="Domain Event"
    subtitle="Domain event stream filtered by mission context"
    collection-key="events"
    legacy-path="/missions/logs"
  />
</template>

<script setup lang="ts">
import MissionDomainRecordPage from "../components/MissionDomainRecordPage.vue";
</script>
