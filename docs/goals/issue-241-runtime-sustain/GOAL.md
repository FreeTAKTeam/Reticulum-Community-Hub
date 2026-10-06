# Goal: repair sustained RCH issue 241

Execute PLAN.md in this directory using Krypton Execution. Preserve the full issue scope: sustained readiness, RPC announce and actual inbound traffic, not only the retained-window regression. The user authorizes the fix and release; the latest release request also authorizes a matching RCH prerelease for testing the daemon candidate. Change the daemon only from concrete evidence, preserve unrelated work, complete PRE/POST reviews and required gates, and verify published artifacts. Retention repair alone does not prove the production stall repaired.
