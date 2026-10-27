# RCH v3.0.0-preview.30 — Linux AMD64 testing candidate

<!-- rch-release: linux-amd64-only -->

This server testing candidate pairs LXMF-rs SDK 0.15.0 at commit `eee8b2c64b11424f15619d180c28880f7748ff81` with the exact static Linux x86-64 daemon from [reticulumd-test-0.15.0-linux-eee8b2c6.1](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/reticulumd-test-0.15.0-linux-eee8b2c6.1). The daemon includes LXMF-rs #700, which triggers WAL maintenance at its size threshold, and Tokio 1.53.3. The SDK contract remains 2/v2.6.

The upstream archive SHA-256 is `eadb00c607372b71aeb574a17bc733711078e7759022fae2ec608699fbd27e50`; the daemon SHA-256 is `09c1ef129d765a972a4b15018bf2ff59ad5daa47ff4d83a4954f65615260eed2`. The release workflow checks the archive hash and uses that daemon in the RCH archive and Debian package. RCH and TAK are built on Debian 12 with Rust 1.88. The manifest records the source and daemon checksum.

The planned assets are `rch-server_3.0.0.preview.30-1_amd64.deb`, `rch-rust-full-linux-amd64-v3.0.0-preview.30.tar.gz`, and their checksum files. Desktop and other architectures are outside this candidate.

Before upgrading, stop services and back up configuration, databases, identities, attachments and other state consistently. Preserve operator credentials, interfaces, paths, ownership and service overrides. See the [Debian package guide](../packaging/README.md#debian-amd64-installation); installation does not start the services.

This is a testing candidate. Verify the published assets, installed package, daemon readiness, `/Status` and `/diagnostics/runtime` before use. A successful HTTP check alone does not establish message delivery. DigitalOcean deployment, real-peer receipt and sustained resource behavior require separate testing.
