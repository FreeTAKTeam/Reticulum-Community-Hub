# Internal API Examples (Non-Normative)

These payloads are examples only. The authoritative contract is
`internal-api.md`. Each example is validated in tests.

## Command Envelopes

### RegisterNode

<!-- schema: CommandEnvelope -->
```json
{
  "api_version": "1.0",
  "command_id": "11111111-1111-1111-1111-111111111111",
  "command_type": "RegisterNode",
  "issued_at": "2026-01-14T12:00:00Z",
  "issuer": { "type": "reticulum", "id": "node-1" },
  "payload": {
    "node_id": "node-1",
    "node_type": "reticulum",
    "metadata": {
      "name": "Node One",
      "description": "Test node",
      "capabilities": ["telemetry"]
    }
  }
}
```

### CreateTopic

<!-- schema: CommandEnvelope -->
```json
{
  "api_version": "1.0",
  "command_id": "22222222-2222-2222-2222-222222222222",
  "command_type": "CreateTopic",
  "issued_at": "2026-01-14T12:01:00Z",
  "issuer": { "type": "api", "id": "gateway" },
  "payload": {
    "topic_path": "ops.alpha",
    "retention": "ephemeral",
    "visibility": "public"
  }
}
```

### SubscribeTopic

<!-- schema: CommandEnvelope -->
```json
{
  "api_version": "1.0",
  "command_id": "33333333-3333-3333-3333-333333333333",
  "command_type": "SubscribeTopic",
  "issued_at": "2026-01-14T12:02:00Z",
  "issuer": { "type": "api", "id": "gateway" },
  "payload": {
    "subscriber_id": "node-1",
    "topic_path": "ops.alpha"
  }
}
```

### PublishMessage (Text)

<!-- schema: CommandEnvelope -->
```json
{
  "api_version": "1.0",
  "command_id": "44444444-4444-4444-4444-444444444444",
  "command_type": "PublishMessage",
  "issued_at": "2026-01-14T12:03:00Z",
  "issuer": { "type": "api", "id": "gateway" },
  "payload": {
    "topic_path": "ops.alpha",
    "message_type": "text",
    "content": {
      "message_type": "text",
      "text": "Hello from the hub",
      "encoding": "utf-8"
    },
    "qos": "best_effort"
  }
}
```

### PublishMessage (Telemetry)

<!-- schema: CommandEnvelope -->
```json
{
  "api_version": "1.0",
  "command_id": "55555555-5555-5555-5555-555555555555",
  "command_type": "PublishMessage",
  "issued_at": "2026-01-14T12:04:00Z",
  "issuer": { "type": "reticulum", "id": "node-1" },
  "payload": {
    "topic_path": "ops.alpha",
    "message_type": "telemetry",
    "content": {
      "message_type": "telemetry",
      "telemetry_type": "position",
      "data": { "battery": 72, "rssi": -81 }
    },
    "qos": "best_effort"
  }
}
```

### PublishMessage (Event)

<!-- schema: CommandEnvelope -->
```json
{
  "api_version": "1.0",
  "command_id": "66666666-6666-6666-6666-666666666666",
  "command_type": "PublishMessage",
  "issued_at": "2026-01-14T12:05:00Z",
  "issuer": { "type": "api", "id": "gateway" },
  "payload": {
    "topic_path": "ops.alpha",
    "message_type": "event",
    "content": {
      "message_type": "event",
      "event_name": "alert",
      "attributes": { "level": "high", "active": true }
    },
    "qos": "best_effort"
  }
}
```

## Event Envelopes

### NodeRegistered

<!-- schema: EventEnvelope -->
```json
{
  "api_version": "1.0",
  "event_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "event_type": "NodeRegistered",
  "occurred_at": "2026-01-14T12:06:00Z",
  "origin": "hub-core",
  "payload": { "node_id": "node-1", "node_type": "reticulum" }
}
```

### TopicCreated

<!-- schema: EventEnvelope -->
```json
{
  "api_version": "1.0",
  "event_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  "event_type": "TopicCreated",
  "occurred_at": "2026-01-14T12:07:00Z",
  "origin": "hub-core",
  "payload": { "topic_path": "ops.alpha" }
}
```

### MessagePublished

<!-- schema: EventEnvelope -->
```json
{
  "api_version": "1.0",
  "event_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "event_type": "MessagePublished",
  "occurred_at": "2026-01-14T12:08:00Z",
  "origin": "hub-core",
  "payload": {
    "topic_path": "ops.alpha",
    "message_id": "44444444444444444444444444444444",
    "originator": "gateway"
  }
}
```

### SubscriberUpdated

<!-- schema: EventEnvelope -->
```json
{
  "api_version": "1.0",
  "event_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
  "event_type": "SubscriberUpdated",
  "occurred_at": "2026-01-14T12:09:00Z",
  "origin": "hub-core",
  "payload": {
    "subscriber_id": "node-1",
    "topic_path": "ops.alpha",
    "action": "subscribed"
  }
}
```

## Query Envelopes

### GetTopics

<!-- schema: QueryEnvelope -->
```json
{
  "api_version": "1.0",
  "query_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
  "query_type": "GetTopics",
  "issued_at": "2026-01-14T12:10:00Z",
  "payload": { "prefix": "ops" }
}
```

### GetSubscribers

<!-- schema: QueryEnvelope -->
```json
{
  "api_version": "1.0",
  "query_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
  "query_type": "GetSubscribers",
  "issued_at": "2026-01-14T12:11:00Z",
  "payload": { "topic_path": "ops.alpha" }
}
```

### GetNodeStatus

<!-- schema: QueryEnvelope -->
```json
{
  "api_version": "1.0",
  "query_id": "99999999-9999-9999-9999-999999999999",
  "query_type": "GetNodeStatus",
  "issued_at": "2026-01-14T12:12:00Z",
  "payload": { "node_id": "node-1" }
}
```

## Command Result

<!-- schema: CommandResult -->
```json
{
  "command_id": "44444444-4444-4444-4444-444444444444",
  "status": "accepted",
  "reason": null
}
```

## Query Results

### GetTopics Result

<!-- schema: QueryResult -->
```json
{
  "query_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
  "ok": true,
  "result": {
    "data": {
      "topics": [
        {
          "topic_id": "ops.alpha",
          "visibility": "public",
          "subscriber_count": 1,
          "message_rate": 0.5,
          "last_activity_ts": 1768333688,
          "created_ts": 1768330000
        }
      ]
    },
    "_cache": {
      "ttl_seconds": 5,
      "scope": "hub",
      "stale_while_revalidate": true
    }
  },
  "error": null
}
```

### GetSubscribers Result

<!-- schema: QueryResult -->
```json
{
  "query_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
  "ok": true,
  "result": {
    "data": {
      "topic_id": "ops.alpha",
      "subscribers": [
        {
          "node_id": "node-1",
          "first_seen_ts": 1768330000,
          "last_seen_ts": 1768333600,
          "status": "active"
        }
      ]
    },
    "_cache": {
      "ttl_seconds": 5,
      "scope": "hub",
      "stale_while_revalidate": true
    }
  },
  "error": null
}
```

### GetNodeStatus Result

<!-- schema: QueryResult -->
```json
{
  "query_id": "99999999-9999-9999-9999-999999999999",
  "ok": true,
  "result": {
    "data": {
      "node_id": "node-1",
      "status": "online",
      "topics": ["ops.alpha"],
      "last_seen_ts": 1768333600,
      "metrics": {
        "telemetry_rate": 1.2,
        "lxmf_rate": 0.6,
        "battery_pct": 72,
        "signal_quality": -81
      }
    },
    "_cache": {
      "ttl_seconds": 5,
      "scope": "node",
      "stale_while_revalidate": true
    }
  },
  "error": null
}
```

### Query Error (Topic Not Found)

<!-- schema: QueryResult -->
```json
{
  "query_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "ok": false,
  "result": null,
  "error": {
    "code": "TOPIC_NOT_FOUND",
    "message": "Topic does not exist"
  }
}
```
