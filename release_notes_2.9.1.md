# Release 2.9.1

## Overview
This release rolls the in-progress 2.9.0 transport work forward into a 2.9.1 security patch using Reticulum 1.1.9 and LXMF 0.9.6, keeps the current RCH announce-slot behavior, and preserves the minimum local runtime guards still required after the upstream 0.9.6 audit.

## Compatibility warning
- RCH 2.9.1 keeps the announce capability slot layout introduced in the in-progress 2.9.0 transport work when upstream LXMF extension slots are present.
- Older RCH nodes that only inspect announce app-data slot `2` for the RCH capability payload will not discover capabilities from upgraded 2.9.1 peers in mixed-version deployments.
- Upgrade participating RCH nodes together if capability discovery continuity matters.

## Detailed improvements

### 1) Transport dependency security upgrade
- Upgraded Python package pins and lock state to `rns ^1.1.9` and `lxmf ^0.9.6`.
- Updated packaged app versions to `2.9.1` across Python, UI, and Electron metadata.
- Verified that existing Reticulum info surfaces continue to report installed `RNS` and `LXMF` versions without introducing a new API contract.
- `RNS 1.1.9` includes the upstream fix for the BZ2 decompression-bomb issue affecting resource transfers and stream messages.

### 2) Announce compatibility with evolving LXMF metadata
- Hardened RCH announce app-data composition so it preserves non-RCH extension slots instead of truncating announce payloads back to `[display_name, stamp_cost, ...]`.
- Updated inbound announce capability decoding to scan post-core announce slots for the RCH capability payload, keeping backward compatibility with the legacy third-slot layout while allowing LXMF functionality signaling to occupy its own slot.
- This keeps `/getAppInfo`, `/Reticulum/Interfaces/Capabilities`, and `/Reticulum/Discovery` behavior stable while reducing the risk of announce-format collisions as upstream LXMF evolves.

### 3) Minimal compatibility shim policy
- Re-audited local LXMF runtime shims after the upgrade.
- Kept the `LXMPeer.offer_response()` integer-response guard because upstream LXMF 0.9.6 still assumes iterable error payloads in that path.
- Kept the safe `LXStamper.generate_stamp()` speed calculation wrapper because upstream LXMF 0.9.6 can still divide by zero when the benchmark window collapses to zero duration.
- No new RCH-specific workaround layer was added on top of those existing guards.

### 4) Validation
- Expanded announce capability regression coverage for both legacy and functionality-slot announce layouts.
- Targeted backend regression runs and linting were used to validate the upgrade path.
