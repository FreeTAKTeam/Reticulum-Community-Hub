# Reticulum Adapter Mapping (Phase 6)

This document defines the LXMF-to-internal API mapping used by the Reticulum adapter.

## LXMF to Internal Commands

| LXMF input | Internal command | Notes |
| --- | --- | --- |
| `join` | `RegisterNode` | Emitted only on first-seen inbound LXMF. |
| `SubscribeTopic` | `SubscribeTopic` | Requires `TopicID`; uses sender hash as subscriber. |
| Text with `TopicID` | `PublishMessage` | Emits `message_type="text"` only when `TopicID` exists. |

Ignored LXMF inputs:

- `CreateTopic` (ignored; no internal command is emitted)

## Telemetry Mapping

When `FIELD_TELEMETRY` or `FIELD_TELEMETRY_STREAM` is present and `TopicID` exists:

- Emit `PublishMessage` with `message_type="telemetry"`.
- Content uses `telemetry_type` (optional) and `data` (raw payload).

## Internal Events to LXMF Outputs

| Internal event | LXMF output | Notes |
| --- | --- | --- |
| `MessagePublished` | Plain text | Format: `[topic:<topic_id>]` then message text. |

## De-duplication

- Key: LXMF `message_id` (SHA-256)
- Retention: 10 minutes
- Duplicates are dropped silently
