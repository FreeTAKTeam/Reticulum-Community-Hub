# Mission Library

[RCH #354](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/354) and the
metadata half of [RCH #355](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/355),
part of the [Mission Library sequence](https://github.com/FreeTAKTeam/rreticulum-package-protocol/issues/2).

## Shared contract: `r3akt-library-core`

A dependency-light crate (serde only) that RCH and REM both import:

- `LibraryItem`: metadata only. It keeps the identities apart: catalog `item_id`
  (`rch:<FileID>` on RCH), the legacy numeric `legacy_file_id`, the RPP reference
  (RDO Package and File Destinations, signed `manifest_hash`) and `content_sha256`.
- `kind` (`file` / `image`), `source` (`local` / `rch` / `peer`) and
  `availability` (`remote` / `downloading` / `local` / `failed`).
- `LibraryQuery`: `kind`, `source`, `mission_uid`, `search`, `page`, `per_page`
  (at most 50). `apply` authorizes **before** filtering, so hidden items never
  change totals.
- `Right::{Read, Publish, Forward}` map to `mission.content.read` /
  `mission.content.write`. An item linked to missions is visible if any of them
  grants the right; an item with no mission needs the global right. A hash or
  URL grants nothing.

## RCH storage

`rch_file_attachments` is unchanged. Two additive tables, created idempotently
with the marker-picture tables:

- `rch_library_mission_files(mission_uid, file_id, linked_ts_ms)`
- `rch_library_rpp_refs(file_id, package_destination, file_destination, manifest_hash, content_sha256)`

## LXMF commands (field 9 → field 10, answered to the sender only)

| Command | Args | Right |
|---|---|---|
| `mission.library.list` | `LibraryQuery` fields | read, per item mission |
| `mission.library.item.get` | `item_id` or `file_id` | read; unknown and unauthorized both answer `not_found` |
| `mission.library.item.link` | `item_id`/`file_id`, `mission_uid` | read on the item and publish on the target mission |

Each mission is authorized through RCH's own command rules (`mission_command_rejection`:
TEAM scope from field 11, capability, mission access roles), as the LXMF source
hash. FIELD_GROUP is echoed in the reply. Results carry no paths or bytes.

## HTTP

`GET /Library` is the operator view of the same projection and query parser.
`/File`, `/Image` and their raw routes keep their legacy output and the 8 MiB
upload limit.

Not yet here: RPP publication and serving (the second half of #355) fill
`rch_library_rpp_refs`.
