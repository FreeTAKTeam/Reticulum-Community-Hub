Below is a **reviewed and enhanced version** of your Codex task plan, with **finalized scope boundaries** and **explicit testing considerations** added per phase.
The intent is to make this **Codex-safe, audit-friendly, and regression-resistant**, while keeping scope controlled.

No functional scope is expanded beyond what was already agreed; what follows tightens definitions and removes ambiguity.

---

# Codex Tasks – Internal API Incremental Implementation (Final)

**Scope statement (authoritative)**
This task plan implements the **internal contract between processes** of the Reticulum Community Hub.
It does **not** define:

* External REST/OpenAPI schemas
* LXMF wire format
* Reticulum RNS internals
* UI behavior or UX

The Internal API is:

* Process-boundary safe
* Transport-agnostic
* Deterministic and testable
* Backward-compatible by versioning

---

## Phase 0 – Contract Baseline & Governance (FINAL)

**Goal:** Freeze authority and prevent drift.

* [x] read and Confirm `internal-api.md` as the **sole normative source**
* [x] Add a short **non-normative summary** to `README.md`
* [x] Add a versioned namespace:

  ```
  reticulum_telemetry_hub/internal_api/v1
  ```
* [x] Add an explicit **“Out of Scope”** section to `internal-api.md`

**Testing considerations**

* Static validation only
* CI check: changes to `internal_api/v1` require version bump
* Failing build if undocumented contract changes are detected

---

## Phase 1 – Schemas & Validation (FINAL)

**Goal:** Make the contract machine-verifiable.

### Implementation

* [x] Pydantic models for:

  * CommandEnvelope
  * EventEnvelope
  * QueryEnvelope
  * Result / Error objects
* [x] Explicit enums for:

  * CommandType
  * EventType
  * QueryType
  * ErrorCode
  * Severity
* [x] Strict payload typing (no free-form dicts)
* [x] Forbid unknown fields (`extra="forbid"`)

### Testing

* [x] Schema round-trip tests (serialize → deserialize)
* [x] Invalid field rejection
* [x] Missing mandatory field rejection
* [x] Version mismatch handling
* [x] Fuzz tests for malformed payloads

**Acceptance criteria**

* No handler logic exists yet
* Schemas alone can reject invalid messages deterministically

---

## Phase 2 – Transport-Agnostic Interfaces (FINAL)

**Goal:** Enforce architectural boundaries.

### Implementation

* [x] Define abstract interfaces:

  * `CommandBus`
  * `QueryBus`
  * `EventBus`
* [x] Define lifecycle semantics:

  * sync command handling
  * async event publication
* [x] Implement **in-process async queue transport**
* [x] No global state allowed

### Testing

* [x] Command dispatch ordering
* [x] Event fan-out to multiple subscribers
* [x] Backpressure behavior
* [x] Handler isolation (one handler failure ≠ bus failure)

**Acceptance criteria**

* Hub Core can be tested without API/UI or Reticulum
* Transport can be swapped without code changes

---

## Phase 3 – Command Handling (Hub Core) (FINAL)

**Goal:** Establish authoritative state transitions.

### Implementation

* [x] Implement handlers for:

  * `RegisterNode`
  * `CreateTopic`
  * `SubscribeTopic`
  * `PublishMessage`
* [x] Validation → Authorization → State Change → Event emission
* [x] Commands are **idempotent where applicable**
* [x] Reject commands with explicit error codes

### Testing

* [x] Happy-path command execution
* [x] Duplicate command replay
* [x] Authorization failure
* [x] Invalid state transitions
* [x] Event emission verification (exactly-once per command)

**Acceptance criteria**

* No command mutates state without emitting at least one event
* All rejections are explicit and typed

---

## Phase 4 – Query Handling (Hub Core) (FINAL)

**Goal:** Safe observability without side effects.

### Implementation

* [x] Implement:

  * `GetTopics`
  * `GetSubscribers`
  * `GetNodeStatus`
* [x] Queries must:

  * never emit events
  * never mutate state
* [x] Define cache hints (TTL, consistency level)

### Testing

* [x] Empty-state queries
* [x] Not-found behavior
* [x] Concurrency safety (queries during command execution)
* [x] Deterministic results for same state snapshot

**Acceptance criteria**

* Queries are replayable and side-effect free
* Query results are explicitly versioned

---

## Phase 5 – Gateway Adapter (API/UI) (FINAL)

**Goal:** Make the gateway a pure adapter.

### Implementation

* [x] REST → Command mapping
* [x] REST → Query mapping
* [x] Event → WebSocket streaming
* [x] Gateway owns **no business logic**

### Testing

* [x] API request → internal command translation
* [x] Event stream integrity
* [x] Backpressure handling (slow clients)
* [x] Gateway restart resilience

**Acceptance criteria**

* Gateway can be restarted without Hub Core restart
* No domain logic exists in the gateway

---

## Phase 6 – Reticulum Adapter (FINAL)

**Goal:** Make Reticulum a peer, not a special case.

### Implementation

* [x] LXMF / Reticulum inputs → Commands
* [x] Events → Reticulum outputs
* [x] Explicit mapping table (documented)

### Testing

* [x] One-to-one mapping verification
* [x] Unsupported message rejection
* [x] Network delay simulation
* [x] Duplicate LXMF delivery handling

**Acceptance criteria**

* Reticulum adapter is replaceable
* No Reticulum logic leaks into core

---

## Phase 7 – Compliance, Hardening & Non-Functional Tests (FINAL)

**Goal:** Lock architecture and prevent regression.

### Implementation

* [x] API version negotiation
* [x] Structured logging (command_id, event_id)
* [x] Correlation IDs across processes
* [x] Enforce “no shared memory” rule

### Testing

* [x] Contract compliance tests
* [x] Regression suite across all phases
* [x] Chaos tests (handler crashes, transport failures)
* [x] Performance baseline tests (command/sec)

**Acceptance criteria**

* Any architectural violation fails CI
* Logs allow full causal reconstruction

---

## Phase 8 – Documentation & Rollout (FINAL)

**Goal:** Make this sustainable.

### Implementation

* [x] Internal API overview
* [x] Sequence diagrams (command → event)
* [x] Example payloads per command/event/query
* [x] Dev defaults and transport configuration

### Testing

* [x] Documentation accuracy tests (examples validate against schemas)

**Acceptance criteria**

* A new developer can implement a compatible adapter without guidance






