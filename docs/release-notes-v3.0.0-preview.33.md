# RCH v3.0.0-preview.33 — Linux AMD64 marker-sharing test

<!-- rch-release: linux-amd64-only -->

This testing candidate adds marker sharing using the Sideband Telemeter contract. RCH can encode and share independent map markers with compatible clients, without treating marker coordinates as the sender's location. The shared map-core codec and byte fixtures support RCH and REM; the UI exposes an explicit, permission-checked Send action. Automatic recipient selection remains in place.

The marker-sharing source was tested with connected REM phones, Sideband and Columba, including receipt and storage. Columba visual icon rendering and the full live GPS, altitude, speed, source-age and collector matrix remain unqualified; standard streams do not provide third-party deletion.

The candidate pairs LXMF-rs SDK 0.16.0 at `c45a5113807fdf5618b55d4e6ba7f598c3eaafe7` with the exact Linux x86-64 daemon from [reticulumd-test-0.16.0-linux-c45a5113.1](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/reticulumd-test-0.16.0-linux-c45a5113.1), SHA-256 `b801218dba8c33f5edda421d54c990faea5b721af9bd81f8253756fec059a838`. Its indexed propagation expiry change builds a database index on first open.

Planned assets are the Linux AMD64 Debian installer and server archive with checksums. Stop services and consistently back up configuration, databases, identities and attachments before upgrading. Preserve existing credentials, interfaces and systemd overrides; installation does not automatically start services. See the [Debian package guide](../packaging/README.md#debian-amd64-installation).

This is a test candidate. Verify package checksums and runtime readiness before use. Real-peer delivery under the new release, sustained resource behavior, systemd PID 1 and deployment acceptance require separate validation.
