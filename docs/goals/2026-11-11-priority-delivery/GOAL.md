# Goal: bounded SDK sessions and remaining authentication hardening

Use Krypton Execution to execute [PLAN.md](PLAN.md). The user authorized planning followed by execution, one SOL agent per issue, one PR per issue, independent review, CI repair and merge management.

- Preserve the plan's ownership, recovery contract, cutover and acceptance evidence.
- Assign LXMF #755, RCH #307 and RCH #231 to separate SOL agents in isolated worktrees.
- Merge the upstream session contract before pinning the final RCH runtime.
- Do not duplicate the already-merged #307 parser fix or erase durable state to reclaim sessions.
- Review exact PR heads and merge only after applicable checks pass under existing GitHub rules.
- Capture target-perspective evidence and distinguish local implementation from production and sustained resource qualification.
- Record outstanding operational gates honestly; say `implemented but unproven` for any acceptance claim whose required evidence is missing.
