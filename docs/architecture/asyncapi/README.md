# R3AKT AsyncAPI Contracts

This directory is the canonical home for Reticulum/LXMF interaction contracts.

## Scope

- Commands and events exchanged over LXMF
- Message schemas for control-plane and data-plane interactions
- Version compatibility notes for mesh deployments

## LXMF Field Semantics (Normative)

All AsyncAPI contracts in this directory use the same field-level message class profile:

| Message class | LXMF field | Hex |
|---|---|---|
| Command request | `FIELD_COMMANDS` | `0x09` |
| Command outcome (`accepted`/`rejected`/`result`) | `FIELD_RESULTS` | `0x0A` |
| Event/fact publication | `FIELD_EVENT` | `0x0D` |
| Optional group/topic scope metadata | `FIELD_GROUP` | `0x0B` |

`FIELD_GROUP` scopes fan-out and topic delivery but does not define whether a message is a command or an event.

## Authority Model

- AsyncAPI in this directory is authoritative for Reticulum/LXMF interactions.
- OpenAPI in `docs/architecture/openapi/` is authoritative for northbound HTTP APIs.
- Any HTTP command endpoint that triggers LXMF behavior must map to an AsyncAPI-defined message.

## Artifacts

- `r3akt-core-lxmf.asyncapi.yaml`
- `r3akt-analytics-lxmf.asyncapi.yaml`
- `r3akt-gateway-lxmf.asyncapi.yaml`
- `r3akt-agent-runtime-lxmf.asyncapi.yaml`
- `r3akt-checklist-lxmf.asyncapi.yaml`
- `r3akt-mission-sync-lxmf.asyncapi.yaml`
