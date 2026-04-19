# Reticulum Community Hub User Manual

This manual is the screen-by-screen operator guide for the Reticulum Community Hub (RCH) UI.
It uses the built-in online help content as its baseline, then expands that help into
practical instructions for each screen currently available in the application.

This guide focuses on using the interface. For lower-level runtime, API, and LXMF details,
keep `docs/userManual.md`, `docs/supportedCommands.md`, and `docs/southbound.md` nearby.

## Introduction

Reticulum Community Hub (RCH) is a coordination hub for Reticulum and LXMF-based communications.
It is designed to give operators a shared working space for messaging, telemetry, files, map
objects, missions, and team coordination without depending on conventional centralized internet
services. In practice, it sits between field clients, operators, and supporting systems so that
traffic can be routed, stored, reviewed, and acted on from a single operational interface.

RCH is made for environments where communications may be intermittent, bandwidth may be limited,
and operators still need a reliable way to maintain shared awareness. Instead of treating messages,
telemetry, mission data, and attachments as separate tools, RCH brings them together so a team can
track people, distribute information, manage work, and maintain a common operating picture.

Common use cases include:

- Mesh-based team coordination where field users exchange direct messages, topic traffic, and broadcast updates.
- Situational awareness for distributed teams using live telemetry, operator markers, and operational zones.
- Mission management where operators assign teams, assets, checklists, and log entries to a specific mission.
- Attachment handling for field-delivered images, files, and other artifacts that need to be stored and retrieved later.
- Identity and routing control where administrators need to see who is connected, moderate access, and inspect routing state.
- Bridging into TAK-oriented workflows where chat, position, and mission context need to coexist with Reticulum traffic.

In short, RCH is intended to act as the shared coordination point for small to medium operational
networks that need resilient communications, mission tracking, and operator oversight in one place.

## Who This Manual Is For

- Operators running the RCH gateway and web UI
- Team leads managing missions, users, files, and routing
- Administrators configuring Reticulum, hub policies, and mission permissions

## Before You Start

### Startup behavior

When the application starts, it may show a full-screen boot panel while it waits for the backend
and WebSocket API to respond. That screen is informational only. Once the backend is reachable,
the normal UI loads.

### Main navigation

The left sidebar is the primary way to move through the application:

- `Home`
- `Missions`
- `Checklists`
- `WebMap`
- `Topics`
- `Files`
- `Chat`
- `Users`
- `Configure`
- `Connect`
- `About`

The sidebar can be collapsed to save space or pinned so it stays open.

### Global status elements

Most screens include shared status elements:

- `?` help button: Opens the online help entry for the current screen.
- Connection pill: Shows whether the UI can reach the selected hub.
- WebSocket pill: Shows whether live event streams are connected.
- Base URL label: Shows which backend the UI is pointed at.
- Connection banner: Appears when the hub is offline, login is required, or credentials are rejected.

### Recommended first-run sequence

1. Open `Connect` and point the UI at the correct backend.
2. Confirm the connection is live.
3. Check `Home` for overall health.
4. Use `Configure` if the node needs tuning.
5. Move to `Users`, `Topics`, `Missions`, `Checklists`, `WebMap`, `Files`, or `Chat` for operational work.

## Screen Reference

The sections below follow the operator-facing screens in the current UI. Where the application
still exposes both canonical mission-domain routes and older editable mission views, both are
described so the workflow remains understandable.

## Connect

Route: `/connect`

Purpose:
Use this screen before operations to set the API target, set the WebSocket target, and authenticate
against remote hubs.

How to use it:

- Enter the REST base URL in `Base URL`.
- Enter the WebSocket root in `WebSocket Base URL`.
- If the target is remote, choose an auth mode and provide a bearer token, API key, or both.
- Enable `Remember credentials on this device` only on trusted systems.
- Select `Save` to persist the settings locally.
- Select `Log in` for remote targets to validate credentials and establish an authenticated session.
- Select `Test Connection` for local targets to verify the app info and status endpoints.

What to watch for:

- Remote targets require authentication.
- Local loopback targets can usually be used without credentials.
- If login succeeds, the UI returns to the originally requested screen.

## Home

Route: `/`

Purpose:
The Dashboard is the operational overview. It combines backend control, telemetry health, event flow,
connection state, and uptime in one place.

Main areas:

- `Backend Control`: Start, stop, query status, or send an announce from the gateway.
- `Global Telemetry Stream`: 24-hour visualization of telemetry ingest, motion, transport load, and marker activity.
- `Event Feed`: Real-time event table with expandable metadata details.
- `Time`: Local node clock and gateway uptime.
- Vital cards: High-level counts for users, topics, and active missions.

Typical workflow:

1. Confirm the connection and WebSocket pills are healthy.
2. Check whether the backend is running.
3. Review recent event activity.
4. Use the telemetry graph to spot stale or quiet systems.
5. Jump into more detailed screens only after the dashboard looks healthy.

## Missions

Primary route: `/missions`

Canonical workspace route: `/missions/:mission_uid/...`

Purpose:
This is the main mission operations area. The `/missions` entry route resolves the selected mission
and redirects into the canonical mission workspace. Most mission-specific routes live under
`/missions/:mission_uid/...`.

Important behavior:

- `/missions` is the entry point, not the final working screen.
- `/missions/assets` and `/missions/logs` are compatibility routes that redirect into the canonical mission routes.
- The mission workspace keeps the selected mission in the URL query and local UI state.
- Many canonical mission-domain routes are inspection-oriented tables and expose an `Open Legacy Workspace`
  action when you need editable mission workflows.

### Mission Workspace Shell

Route: `/missions/:mission_uid`

Purpose:
The shell provides mission selection, mission KPIs, and the navigation tabs for the mission-domain views.

How to use it:

- Choose a mission from the `Mission Directory` on the left.
- Use the domain tabs across the top of the main panel to move between mission records.
- Use `Refresh` to reload the mission workspace data.
- Use `Legacy Workspace` when you need one of the older editable mission flows.

### Legacy Mission Editing Views

These views are still part of the real operator workflow even though the application now prefers
canonical mission-domain routes.

You may encounter them when:

- Opening the legacy workspace directly
- Selecting `Open Legacy Workspace` from a mission-domain table
- Using older links or bookmarks

The main legacy mission views are:

- `Mission Registry`: Summary table of missions, status, checklist count, and open-task count.
- `Mission Create`: Full mission-creation form for new missions.
- `Mission Edit`: Editable mission metadata form for the selected mission.
- `Mission Overview`: Operational summary with KPIs, excheck snapshot, and mission audit feed.
- `Mission Excheck Board`: Pending, late, and complete task lanes for quick excheck review.
- `Mission Team Members`: Team summaries plus the member status board.
- `Asset Registry`: Mission-linked assets and related assignment context.
- `Task Assignment Workspace`: Assignment review and assignment actions.
- `Assign Zones`: Zone selection and mission coverage review.
- `Checklist Import CSV`: Mission-scoped CSV upload and preview for checklist generation.

Use the legacy views when you need guided editing actions rather than read-only record inspection.

### Mission Overview

Route: `/missions/:mission_uid/overview`

Purpose:
Read-only summary of the selected mission. This is the best first stop after selecting a mission.

Use it to:

- Review mission status and description.
- See counts for checklists, teams, members, assets, assignments, and zones.
- Review the compact excheck board.
- Read the unified audit stream built from events, mission changes, and log entries.
- Export the audit log or snapshot data.

### Mission

Route: `/missions/:mission_uid/mission`

Purpose:
Mission metadata table for the selected mission.

Use it to:

- Inspect the mission record fields exactly as stored.
- Refresh the table.
- Jump back to the legacy editable mission form when you need to create or update mission metadata.

### Topic

Route: `/missions/:mission_uid/topic`

Purpose:
Mission topic scope and taxonomy records.

Use it to:

- Check which topic records are available in mission context.
- Confirm how the mission is scoped for message routing.
- Jump back to the legacy workspace for topic-oriented editing if needed.

### Checklist

Route: `/missions/:mission_uid/checklists`

Purpose:
Mission-scoped checklist instances.

Use it to:

- Review which checklist runs are attached to the mission.
- Refresh the list.
- Jump back into the checklist workspace when you need active checklist editing instead of record inspection.

### Checklist Task

Route: `/missions/:mission_uid/checklist-tasks`

Purpose:
Flattened task table for all mission-scoped checklist tasks.

Use it to:

- See task numbers, status, due time, completion time, and assignee in one list.
- Quickly identify open or overdue work across all checklist runs.
- Open the checklist workspace for task-level operations.

### Checklist Template

Route: `/missions/:mission_uid/checklist-templates`

Purpose:
Checklist template records, including templates created from CSV imports.

Use it to:

- Review available templates in mission context.
- Refresh template data.
- Open the editable checklist template workspace when you need to create, clone, archive, or convert templates.

### Team

Route: `/missions/:mission_uid/teams`

Purpose:
Mission-linked team records.

Use it to:

- Inspect which teams are attached to the mission.
- Review mission/team linkage fields.
- Jump to the legacy mission team-management workflow when you need edits.

### Team Member

Route: `/missions/:mission_uid/team-members`

Purpose:
Mission team member records and roles.

Use it to:

- Review team member assignments, roles, identities, and related mission membership data.
- Refresh the mission-scoped member set.
- Open the legacy mission workspace or Users pages if you need to change team membership.

### Skill

Route: `/missions/:mission_uid/skills`

Purpose:
Skill registry records used by mission assignments.

Use it to:

- Audit which skills exist in the mission workspace.
- Compare skill records to team member capabilities.

### Team Member Skill

Route: `/missions/:mission_uid/team-member-skills`

Purpose:
Member-to-skill capability links.

Use it to:

- Inspect capability links between members and skills.
- Verify qualification or specialization coverage for a mission.

### Task Skill Requirement

Route: `/missions/:mission_uid/task-skill-requirements`

Purpose:
Task capability requirement records.

Use it to:

- Compare task requirements against available mission members and skills.
- Audit whether tasks are supported by qualified people.

### Asset

Route: `/missions/:mission_uid/assets`

Purpose:
Mission asset registry and mission-linked equipment views.

Use it to:

- Review assets available to the selected mission.
- Check asset type and status.
- Open the legacy asset inventory for create, update, assignment, or retirement workflows.

### Assignment

Route: `/missions/:mission_uid/assignments`

Purpose:
Task-to-member assignment records.

Use it to:

- Inspect assignment state for tasks in mission scope.
- Review who owns each task and which assets are attached.
- Open the legacy assignment workflow to create, change, or revoke assignments.

### Zone

Route: `/missions/:mission_uid/zones`

Purpose:
Mission operational zone links.

Use it to:

- Review which zones are linked to the mission.
- Confirm mission boundary scope from a record view.
- Open the legacy zone-assignment workflow or `WebMap` for geometry work.

### Domain Event

Route: `/missions/:mission_uid/domain-events`

Purpose:
Mission-filtered domain event stream.

Use it to:

- Review mission-domain events without opening the larger audit view.
- Confirm event presence for a specific mission aggregate.

### Mission Change

Route: `/missions/:mission_uid/mission-changes`

Purpose:
Mission change records and broadcast-style change entries.

Use it to:

- Review mission change history.
- Confirm which structured changes were recorded for the selected mission.

### Log Entry

Route: `/missions/:mission_uid/log-entries`

Purpose:
Mission logbook view.

Use it to:

- Review log entry history for the mission.
- Open the legacy logbook when you need to create or edit mission log entries.

### Snapshot

Route: `/missions/:mission_uid/snapshots`

Purpose:
Mission aggregate snapshots.

Use it to:

- Review saved mission state snapshots by aggregate UID and type.
- Refresh snapshot data.
- Cross-check exported snapshot captures from the overview screen.

### Audit Event

Route: `/missions/:mission_uid/audit-events`

Purpose:
Unified mission audit timeline combining events, mission changes, and log entries.

Use it to:

- Review the full mission activity timeline in one table.
- Sort mentally by time and source.
- Open the legacy logbook when you need to work on the editable source records.

## Checklists

Route: `/checklists`

Purpose:
This is the full checklist operations workspace. Use it for active checklist runs, templates, CSV imports,
task completion, and mission linking.

Main areas:

- `Active Checklists`: Browse live checklist runs.
- Checklist detail view: Review progress, task rows, due offsets, and completion state.
- `Templates`: Manage saved templates and CSV-derived templates.
- `Template Builder`: Create, clone, archive, convert, or save templates.
- `Import from CSV`: Upload CSV or CVF content and preview the resulting columns and tasks.

Typical workflow:

1. Search for the checklist or template you need.
2. Choose `Active Checklists` for live work or `Templates` for design work.
3. Open a checklist detail page to toggle tasks done, add tasks, link the checklist to a mission, or delete it.
4. Use the template area to create new reusable checklist structures.
5. Use CSV import when building checklists from an existing spreadsheet-style source.

## WebMap

Route: `/webmap`

Purpose:
The WebMap is the spatial operations console for live telemetry, operator markers, and zones.

Main areas:

- Map canvas with telemetry and operator layers
- Marker toolbar for symbol selection and marker placement
- Zone drawing controls
- Coordinate readout
- Right-side `Marker Registry` with `Operator`, `Telemetry`, and `Zones` tabs
- Inspector and radial menus for focused actions

How to use it:

- Select a marker symbol from the toolbar, then place a marker on the map.
- Use zone mode to draw polygons; finish the zone and name it when complete.
- Use radial menus or list actions to rename, move, delete, or assign markers and zones to missions.
- Use the registry sidebar to filter by topic or search by identity.
- Use the telemetry tab to jump to live telemetry positions.
- Use the zones tab to focus, rename, or edit saved polygons.

Good practice:

- Do geometry work on the map and mission-linking work from the assignment prompts.
- Use the marker label toggle from `Configure` if the map becomes visually crowded.

## Topics

Route: `/topics`

Purpose:
This screen manages topic hierarchy, subscriber routing, and topic-linked file or image assets.

Main areas:

- `Topic Hierarchy Tree`: Branch selection and filtering
- `Topics` tab: Topic records and linked asset summaries
- `Subscribers` tab: Subscriber route records
- Topic asset modal: Link and unlink files or images from a topic

How to use it:

- Select a branch from the hierarchy tree to narrow the working set.
- Use `New Topic` to create a topic with a name, path, and description.
- Use `Edit` or `Delete` on topic cards to maintain topic definitions.
- Open `Manage Assets` on a topic card to link or detach files and images.
- Switch to the `Subscribers` tab to add or remove routes for a topic.

Use this screen when you need to control how messages fan out through the hub.

## Files

Route: `/files`

Purpose:
The asset library for binary attachments stored by the hub.

Main areas:

- `Files` tab: Non-image attachments
- `Images` tab: Image attachments with preview support
- Upload controls for both categories
- Pagination for larger inventories

How to use it:

- Browse the library by category.
- Use `Download` to retrieve an attachment from hub storage.
- Use `Preview` on image records to inspect the image before downloading it.
- Use `Delete` to remove the attachment from the database and disk.
- Use `Upload File` or `Upload Image` to add new library items.

Important limits:

- Uploads are limited to 8 MB per file.
- Image uploads must have an image content type.

## Chat

Route: `/chat`

Purpose:
The live communications plane for direct messages, topic messages, broadcasts, and attachments.

Main areas:

- `Directory` with `Users`, `Topics`, and a `Broadcast` lane
- Conversation panel with message history and delivery state
- Composer with scope selector, target selector, text area, and attachment picker

How to use it:

- Select a user for a direct message, a topic for channel traffic, or `Broadcast` for all joined users.
- Review the message history for that lane.
- Choose the same scope in the composer.
- Add text, attach files, then select `Send`.

Attachment behavior:

- Queued attachments are shown before sending.
- Images display inline in message history.
- The application uploads attachments first, then queues the message.

## Users

Route: `/users`

Purpose:
Identity governance, moderation, routing inspection, REM peer visibility, team management, and rights management.

Tabs:

- `Users`: Connected clients currently known to the hub
- `Identities`: Identity records, join state, ban state, blackhole state, and client type
- `REM Peers`: Remote edge mode peers and their capabilities
- `Routing`: Current routing snapshot and destination table
- `Teams`: Team records and mission linkage
- `Team Members`: Team member records
- `Rights`: Team rights matrix with mission/global scope controls

How to use the main tabs:

### Users tab

- Review active or recent clients.
- Use `Ban`, `Unban`, `Blackhole`, or `Leave` for moderation and hub membership control.

### Identities tab

- Review identity records even when they are not currently joined.
- Use `Join` to join an identity to the hub.
- Use moderation controls on the identity record itself.

### REM Peers tab

- Review REM-capable peers, mode registration, and capabilities.
- Confirm whether the system is in connected or passive REM mode.

### Routing tab

- Inspect destination, identity, and joined/routed state.
- Use this when diagnosing delivery or routing issues.

### Teams tab

- Create, edit, or delete teams.
- Use `Members` to jump into the team roster assignment screen.

### Team Members tab

- Create, edit, or delete team member records.
- Link a team member to an existing user identity.
- Maintain callsign, role, availability, contact fields, and certifications.

### Rights tab

- Filter by team, scope, member, and operation.
- In mission scope, select a mission and mission access bundle.
- Toggle individual operations to allow or deny rights.
- Use `Apply Changes` to persist the current draft.
- Use `Reset Draft` or `Revoke Visible` when cleaning up broad permission sets.

## Team Roster

Route: `/users/teams/members`

Purpose:
Focused team assignment workspace for assigning existing team members to a selected team or removing them from that team.

How to use it:

- Select a team from the top filter row.
- Review the team properties panel on the left.
- Use the `Member` selector to add an existing team member to the selected team.
- Use `Remove` in the member table to unassign a member from that team.
- Use the back button to return to the main Users screen.

This screen is narrower in scope than the main `Users` page. Use it when you need fast roster assignment work.

## Configure

Route: `/configure`

Purpose:
Node tuning, configuration management, Reticulum interface editing, and live command diagnostics.

Tabs:

- `Config`: Hub configuration file editing
- `Reticulum`: Reticulum engine and interface profile editing
- `Tools`: Live diagnostics against the connected hub

### Config tab

Use it to:

- Load the hub configuration text.
- Validate the current payload.
- Apply changes to the hub configuration file.
- Roll back to a backup if needed.
- Toggle WebMap marker labels globally for the UI.

Recommended sequence:

1. Load
2. Edit
3. Validate
4. Apply
5. Roll back only if the node degrades

### Reticulum tab

Use it to:

- Toggle transport mode and shared-instance mode.
- Edit global discovery and logging settings.
- Add, remove, or modify interfaces.
- Configure schema-driven interface fields for supported transport types.
- Add discovered interfaces to the config from the live discovery snapshot.
- Review local validation errors and warnings before applying changes.

Important note:

Reticulum configuration changes are saved immediately to file when applied, but they do not take effect until the hub restarts.

### Tools tab

Use it to run live probes:

- `Ping`
- `Dump Routing`
- `List Clients`

The output is shown in the tool response panel.

## About

Route: `/about`

Purpose:
System identity, build metadata, storage paths, and documentation entry points.

Main areas:

- Identity rail with destination hash and basic metadata
- Runtime profile cards with engine versions and status flags
- Storage path inventory
- `Help` tab with links into the screen-specific help system
- `Examples` tab with command and example loaders

How to use it:

- Verify the running version and destination hash.
- Confirm whether transport and shared-instance modes are enabled.
- Review storage paths for the hub database, files, images, and config.
- Open help links for any screen.
- Load `Commands` and `Examples` to inspect current backend help output.

## Common Workflows

### Bring a node online

1. Open `Connect` and set the target.
2. Log in if the target is remote.
3. Open `Home` and confirm backend status.
4. Open `Configure` if transport or interface changes are needed.

### Create and manage a mission

1. Open `Missions`.
2. Select or create a mission from the mission workflow.
3. Review `Overview`.
4. Use `Teams`, `Team Members`, `Assets`, `Assignments`, and `Zones` to verify the mission is operationally complete.
5. Use `Checklists` for live checklist execution.

### Manage message routing

1. Open `Topics`.
2. Create or edit the topic hierarchy.
3. Add subscribers to the correct topic branch.
4. Open `Chat` and send to the topic to validate behavior.

### Work with attachments

1. Upload to `Files` for general library management.
2. Link files or images to a topic from `Topics`.
3. Send attachments in `Chat`.
4. Review mission-linked assets from `Missions` or spatial assignment from `WebMap`.

### Diagnose delivery or membership problems

1. Check `Home` for connection and event errors.
2. Check `Users` for moderation state, join state, or REM capability.
3. Check `Users > Routing` for destination visibility.
4. Check `Configure > Tools > Dump Routing`.

## Using The Built-In Help System

Each major screen exposes context-sensitive help through the `?` button in the header or dashboard banner.
The help content is short and intended for quick lookup. This manual is the expanded reference. When in doubt:

1. Use the in-app help to orient yourself quickly.
2. Use this manual for full workflow guidance.
3. Use `docs/userManual.md` and the API documents for protocol and backend details.
