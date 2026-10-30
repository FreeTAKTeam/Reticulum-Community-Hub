# RCH v3.0.0-preview.32 — Linux AMD64 testing candidate

<!-- rch-release: linux-amd64-only -->

This test candidate pairs LXMF-rs SDK 0.16.0 at `c45a5113807fdf5618b55d4e6ba7f598c3eaafe7` with the exact daemon from [reticulumd-test-0.16.0-linux-c45a5113.1](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/reticulumd-test-0.16.0-linux-c45a5113.1). SDK contract 2/v2.6 and Tokio 1.53.3 remain the expected baseline. The upstream change targets indexed propagation expiry and maintenance read accounting for issue #663; an existing database builds the new index on first open.

The upstream archive SHA-256 is `2785ea8379fd2f565df2e16b3d0346a212dd3a284f15b1eecea057a13b4b0ba3`; the daemon SHA-256 is `b801218dba8c33f5edda421d54c990faea5b721af9bd81f8253756fec059a838`. The package workflow verifies the archive before staging that exact daemon. RCH and TAK are built on Debian 12 with Rust 1.88.

The planned Linux AMD64 assets are `rch-server_3.0.0.preview.32-1_amd64.deb`, `rch-rust-full-linux-amd64-v3.0.0-preview.32.tar.gz`, and their checksums.

Before upgrading, stop services and consistently back up configuration, databases, identities, attachments and other state. Preserve operator credentials, interfaces, paths, ownership and service overrides. See the [Debian package guide](../packaging/README.md#debian-amd64-installation); installation does not start services.

This is a testing candidate. Verify checksums, installed package behavior and daemon readiness before use. Real-peer delivery, sustained resource behavior, systemd PID 1 and deployment acceptance require separate testing. The upstream change does not address issue #709.
