# Reticulum Community Hub Internal API Specification

Version: 1.1  
Status: Proposed (Normative)  
Audience: Core developers, Codex agents, future R3AKT integration

This document is the sole normative source for the internal API contract.

## 1. Architectural Positioning

This API defines the only allowed interaction surface with the Community Hub Core.

### 1.1 Out of Scope

- RNS internal APIs
- LXMF wire format
- External REST / WebSocket APIs

Design principles:
- Explicit contracts
- Message-driven
- No shared memory
- Transport-agnostic (in-proc, IPC, TCP, ZeroMQ)

## 2. Interaction Model

The Internal API is split into three channels:

| Channel     | Direction | Semantics                     |
| ----------- | --------- | ----------------------------- |
| Command API | Inbound   | Intent-driven, synchronous    |
| Event API   | Outbound  | Immutable facts, asynchronous |
| Query API   | Inbound   | Read-only, side-effect free   |

All envelopes include `api_version` using `major.minor`. Major versions must
match exactly. Minor versions may be greater or equal to the supported minor.

## 3. Command API (Inbound)

Commands request a state change. They are validated, authorized, and either accepted or rejected.

### 3.1 Command Envelope

```json
{
  "api_version": "1.0",
  "command_id": "uuid",
  "command_type": "string",
  "issued_at": "iso-8601",
  "issuer": {
    "type": "api|reticulum|internal",
    "id": "string"
  },
  "payload": {}
}
```

### 3.2 Command Types (Initial Set)

#### RegisterNode

Registers a logical node (Reticulum identity, gateway, or service).

```json
{
  "command_type": "RegisterNode",
  "payload": {
    "node_id": "hash",
    "node_type": "reticulum|gateway|service",
    "metadata": {
      "name": "string (optional, max 64)",
      "description": "string (optional, max 256)",
      "capabilities": ["string"],
      "location": {
        "lat": "float (optional)",
        "lon": "float (optional)"
      }
    }
  }
}
```

#### CreateTopic

Creates a hierarchical topic.

```json
{
  "command_type": "CreateTopic",
  "payload": {
    "topic_path": "northAmerica.can.ns.emergency",
    "retention": "ephemeral|persistent",
    "visibility": "public|restricted"
  }
}
```

#### SubscribeTopic

```json
{
  "command_type": "SubscribeTopic",
  "payload": {
    "subscriber_id": "hash",
    "topic_path": "string"
  }
}
```

#### PublishMessage

```json
{
  "command_type": "PublishMessage",
  "payload": {
    "topic_path": "string",
    "message_type": "telemetry|event|text",
    "content": {
      "message_type": "text",
      "text": "string (max 4096)",
      "encoding": "utf-8"
    },
    "qos": "best_effort|guaranteed"
  }
}
```

Message content variants:

```json
{
  "message_type": "telemetry",
  "telemetry_type": "string (optional)",
  "data": {
    "key": "value"
  },
  "timestamp": "iso-8601 (optional)"
}
```

```json
{
  "message_type": "event",
  "event_name": "string",
  "attributes": {
    "key": "string | number | boolean"
  }
}
```

### 3.4 Authorization (Initial)

| Command        | api | reticulum | internal |
| -------------- | --- | --------- | -------- |
| RegisterNode   | no  | yes       | yes      |
| CreateTopic    | yes | no        | yes      |
| SubscribeTopic | yes | yes       | yes      |
| PublishMessage | yes | yes       | yes      |

Unauthorized commands are rejected with:

```json
{
  "error_code": "UNAUTHORIZED_COMMAND",
  "severity": "error",
  "message": "string"
}
```

### 3.3 Command Result

```json
{
  "command_id": "uuid",
  "status": "accepted|rejected",
  "reason": "string|null"
}
```

## 4. Event API (Outbound)

Events are immutable facts emitted by the Hub Core. Consumers must not assume ordering across streams.

### 4.1 Event Envelope

```json
{
  "api_version": "1.0",
  "event_id": "uuid",
  "event_type": "string",
  "occurred_at": "iso-8601",
  "origin": "hub-core",
  "payload": {}
}
```

### 4.2 Event Types (Initial Set)

#### NodeRegistered

```json
{
  "event_type": "NodeRegistered",
  "payload": {
    "node_id": "hash",
    "node_type": "string"
  }
}
```

#### TopicCreated

```json
{
  "event_type": "TopicCreated",
  "payload": {
    "topic_path": "string"
  }
}
```

#### MessagePublished

```json
{
  "event_type": "MessagePublished",
  "payload": {
    "topic_path": "string",
    "message_id": "hash",
    "originator": "hash"
  }
}
```

#### SubscriberUpdated

```json
{
  "event_type": "SubscriberUpdated",
  "payload": {
    "subscriber_id": "hash",
    "topic_path": "string",
    "action": "subscribed|unsubscribed"
  }
}
```

## 5. Query API (Inbound, Read-Only)

Queries must not mutate state. They may be cached.

### 5.1 Query Envelope

```json
{
  "api_version": "1.0",
  "query_id": "uuid",
  "query_type": "string",
  "issued_at": "iso-8601",
  "payload": {}
}
```

### 5.2 Query Types

#### GetTopics

```json
{
  "query_type": "GetTopics",
  "payload": {
    "prefix": "optional.string"
  }
}
```

#### GetSubscribers

```json
{
  "query_type": "GetSubscribers",
  "payload": {
    "topic_path": "string"
  }
}
```

#### GetNodeStatus

```json
{
  "query_type": "GetNodeStatus",
  "payload": {
    "node_id": "hash"
  }
}
```

### 5.3 Query Result

```json
{
  "query_id": "uuid",
  "ok": true,
  "result": {
    "data": {},
    "_cache": {
      "ttl_seconds": 5,
      "scope": "node|hub|network",
      "stale_while_revalidate": true
    }
  },
  "error": null
}
```

Query errors return:

```json
{
  "query_id": "uuid",
  "ok": false,
  "result": null,
  "error": {
    "code": "TOPIC_NOT_FOUND",
    "message": "string"
  }
}
```

### 5.4 Query Result Shapes

#### GetTopics

```json
{
  "topics": [
    {
      "topic_id": "northAmerica.can.ns.sar",
      "visibility": "public|private",
      "subscriber_count": 12,
      "message_rate": 4.2,
      "last_activity_ts": 1768333688,
      "created_ts": 1768200000
    }
  ]
}
```

#### GetSubscribers

```json
{
  "topic_id": "northAmerica.can.ns.sar",
  "subscribers": [
    {
      "node_id": "rns:91fa3c…",
      "first_seen_ts": 1768201000,
      "last_seen_ts": 1768333600,
      "status": "active|stale|blackholed"
    }
  ]
}
```

#### GetNodeStatus

```json
{
  "node_id": "rns:91fa3c…",
  "status": "online|offline|stale|blackholed|unknown",
  "topics": [
    "northAmerica.can.ns.sar",
    "broadcast.alerts"
  ],
  "last_seen_ts": 1768333600,
  "metrics": {
    "telemetry_rate": 1.8,
    "lxmf_rate": 0.6,
    "battery_pct": 72,
    "signal_quality": -81
  }
}
```

## 6. Error Model

Errors are explicit and typed.

```json
{
  "error_code": "TOPIC_NOT_FOUND",
  "severity": "warning|error|fatal",
  "message": "string"
}
```

Version mismatch errors use:

```json
{
  "error_code": "API_VERSION_UNSUPPORTED",
  "severity": "error",
  "message": "string"
}
```

Query error codes:

- TOPIC_NOT_FOUND
- INVALID_QUERY
- UNAUTHORIZED
- INTERNAL_ERROR

## 7. Transport Binding (Non-Normative)

The API must not depend on a specific transport.

Allowed bindings:
- In-process async queue (dev)
- Unix socket / TCP (default)
- Reticulum LXMF (future)
- ZeroMQ  (future)
- NATS / Redis Streams (future)

## 8. Compliance Rules

- Hub Core MUST NOT import API/UI code.
- API/UI MUST NOT bypass this contract.
- All state changes MUST originate from Commands.
- All notifications MUST be Events.
- Queries MUST be side-effect free.

