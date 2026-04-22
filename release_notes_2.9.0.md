# Release 2.9.0

## Overview
This release upgrades the transport baseline to Reticulum 1.1.7 and LXMF 0.9.5, aligns RCH announce handling with LXMF's evolving announce metadata layout, and keeps the minimum local runtime guards still required by the upstream 0.9.5 code.

## Compatibility warning
- RCH 2.9.0 changes the announce capability slot layout when upstream LXMF extension slots are present.
- Older RCH nodes that only inspect announce app-data slot `2` for the RCH capability payload will not discover capabilities from upgraded 2.9.0 peers in mixed-version deployments.
- Upgrade participating RCH nodes together if capability discovery continuity matters.

## Detailed improvements

### 1) Transport dependency upgrade
- Upgraded Python package pins and lock state to `rns ^1.1.7` and `lxmf ^0.9.5`.
- Updated packaged app versions to `2.9.0` across Python, UI, and Electron metadata.
- Verified that existing Reticulum info surfaces continue to report installed `RNS` and `LXMF` versions without introducing a new API contract.

### 2) Announce compatibility with evolving LXMF metadata
- Hardened RCH announce app-data composition so it preserves non-RCH extension slots instead of truncating announce payloads back to `[display_name, stamp_cost, ...]`.
- Updated inbound announce capability decoding to scan post-core announce slots for the RCH capability payload, keeping backward compatibility with the legacy third-slot layout while allowing LXMF functionality signaling to occupy its own slot.
- This keeps `/getAppInfo`, `/Reticulum/Interfaces/Capabilities`, and `/Reticulum/Discovery` behavior stable while reducing the risk of announce-format collisions as upstream LXMF evolves.

### 3) Minimal compatibility shim policy
- Re-audited local LXMF runtime shims after the upgrade.
- Kept the `LXMPeer.offer_response()` integer-response guard because upstream LXMF 0.9.5 still assumes iterable error payloads in that path.
- Kept the safe `LXStamper.generate_stamp()` speed calculation wrapper because upstream LXMF 0.9.5 can still divide by zero when the benchmark window collapses to zero duration.
- No new RCH-specific workaround layer was added on top of those existing guards.

### 4) Validation
- Expanded announce capability regression coverage for both legacy and functionality-slot announce layouts.
- Targeted backend regression runs and linting were used to validate the upgrade path.
