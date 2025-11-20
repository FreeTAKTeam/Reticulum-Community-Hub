# TASKS

- 2025-02-14: ✅ Make messaging more robust by limiting telemetry broadcasts, suppressing echo replies, and listing commands for bad requests.
- 2025-11-19: ✅ Preserve `RejectTests=0` values when subscribing or patching subscribers.
- 2025-11-19: ✅ Decode announce metadata using LXMF helper and ensure identity labels follow msgpack names.
- 2025-11-19: ✅ Ensure create-subscriber commands preserve `RejectTests=0` values.
- 2025-11-19: ✅ Refresh topic subscriber cache after subscription changes to deliver messages immediately.
- 2025-11-19: ✅ Persist joined client list across Reticulum Telemetry Hub sessions.
- 2025-11-19: ✅ Handle string-wrapped LXMF commands and prompt for missing command parameters interactively.
- 2025-11-19: ✅ Accept snake_case command fields when prompting for missing data.
- 2025-11-20: ✅ Normalize Sideband-wrapped commands to preserve telemetry commands.
- 2025-11-20: ✅ Normalize Sideband-wrapped command payloads carrying JSON objects.
