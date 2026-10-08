# Goal: Sustained RCH and daemon resource stability

Use Krypton Execution to execute `docs/goals/resource-stability/PLAN.md`.

- Cover RCH issues #252, #253, #254, #255, #256, #257 and LXMF-rs #657.
- Preserve SQLite/domain/SDK ownership, delivery correctness, northbound contracts and unrelated work.
- Replace each displaced path rather than introducing another authoritative cache or delivery strategy.
- Respect the pending historical-collision and cache-budget policy gates; continue independent work.
- Capture final representative >=3-hour constrained real RCH/daemon memory-plus-swap plateau and reliable delivery, plus browser and lifecycle evidence.
- Tests or smoke alone do not complete this goal. If evidence is missing, say implemented but unproven and continue useful work.
