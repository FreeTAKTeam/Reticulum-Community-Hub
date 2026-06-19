# RCH Rust v3.0.0-preview.0 Release Notes

Draft status: prepared after green staging evidence from `rust-next` commit
`8dc69773af38ced251138c007c6f0bdc9543ea02`. The published prerelease tag and
its release workflow run are the authoritative artifact source.

This is the first Rust RCH preview package line. Python `2.9.x` maintenance
continues from the `rch-python` branch; this preview does not replace the Python
stable line.

## Scope

- Rust `r3akt-rch-server` server package with the shared UI bundle.
- Standalone `r3akt-tak-service` packaged beside the server.
- Mandatory ZeroMQ southbound command path through LXMF-rs `reticulumd`.
- Preview Tauri desktop bundles for Windows x64 NSIS and Linux x64 AppImage.

## Release Artifacts

The staging packaging run `26696071364` passed on commit
`8dc69773af38ced251138c007c6f0bdc9543ea02` and produced:

- `rch-rust-full-windows-x64-rust-next.zip`
- `rch-rust-full-linux-x64-rust-next.tar.gz`
- `rch-desktop-windows-x64-nsis`
- `rch-desktop-linux-x64-appimage`

For the published prerelease, create the release from a tag such as
`v3.0.0-preview.0`; the packaging workflow will then embed that tag in the
server archive names and `release-manifest.json`.

## Validation

- `Rust workspace` run `26696071362` passed the committed
  `scripts/release-readiness.ps1 -ServerOnlyAlpha` gate on Rust 1.85.
- `Build Rust Release Packages` run `26696071364` passed all server and desktop
  packaging jobs.
- Downloaded CI artifacts matched their SHA-256 sidecar files.
- Server archive manifests recorded the package name, release label, Git ref,
  Git SHA, and inclusion of the server, TAK service, and UI payloads.
- Local bridge tests passed with `cargo test -p r3akt-rch-bridge outbound_`,
  covering `auto` delivery mapping to direct send with propagation fallback.
- Live REM validation documented in `docs/release-live-stress-report.md` showed
  a Rust-created checklist delivered through Reticulum and visible on both
  connected REM phone UIs.

## Known Boundaries

- This is a preview/alpha release, not stable `v3.0.0`.
- Desktop bundles are preview artifacts while operator packaging and field
  feedback settle.
- External RMAP Reticulum validation should be refreshed if public testnet
  evidence is required in the final release announcement.
- Less common Python parity edge cases remain tracked in `README.md` and
  `docs/release-contract-matrix.json`.
