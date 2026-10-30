# RCH v3.0.0-preview.31 — Linux AMD64 testing candidate

<!-- rch-release: linux-amd64-only -->

This test candidate pairs LXMF-rs SDK 0.16.0 at commit `45b5f5650b375ff418ec849cd9f99bf7f63a106c` with the exact Linux x86-64 daemon from the published [LXMF-rs v0.16.0 release](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/v0.16.0). SDK contract 2/v2.6 and Tokio 1.53.3 remain the expected baseline.

The upstream archive SHA-256 is `5bce62a02fcde924580819f8c5385638fb6a0380985f8ffbc36a10caacf67007`; the daemon SHA-256 is `cf04fb9ff0172f6c5b5c3da50ff7e4f76132c50736930ae60628b33ed4279fdc`. The release workflow verifies the archive before staging that daemon in both RCH packages. RCH and TAK are built on Debian 12 with Rust 1.88.

The planned Linux AMD64 assets are `rch-server_3.0.0.preview.31-1_amd64.deb`, `rch-rust-full-linux-amd64-v3.0.0-preview.31.tar.gz`, and their checksums. Desktop and other architectures are outside this candidate.

Before upgrading, stop services and back up configuration, databases, identities, attachments and other state consistently. Preserve operator credentials, interfaces, paths, ownership and service overrides. See the [Debian package guide](../packaging/README.md#debian-amd64-installation); installation does not start services.

Verify checksums, installed package behavior and actual daemon readiness before use. This is a testing release: real-peer delivery, sustained resource behavior, systemd PID 1 and deployment acceptance require separate testing.
