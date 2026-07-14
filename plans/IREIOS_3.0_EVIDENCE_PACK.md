# IREIOS 3.0 — Evidence Pack (Gate G2)

Collected at **Step 19 / Task 10.4** to satisfy the Program final gate (G2) in
`IREIOS_3.0_STEP_BY_STEP_EXPANSION.md`. This file is the expansion parallel of the
Gate G1 evidence captured in `BUG_FIXES_CHANGELOG.md`.

> Status: SKELETON. Fill each section as the corresponding phase completes.

## Architecture & cutover
- [ ] Event Bus (Redis Streams) durable publish verified (Phase 1 exit gate output)
- [ ] Dual-path WhatsApp removed; only v3 path live (Task 10.2)
- [ ] `crm_sync` / `follow_up` direct usage decommissioned (Task 10.3)

## Data, graph, memory
- [ ] Neo4j reachable; schema v1 applied (Phase 7.2 migrate output)
- [ ] Graph API routes return 200 on smoke (Phase 7.3)
- [ ] Memory store/retrieve verified (Phase 7.6)

## APIs & realtime
- [ ] SSE contracts in `IREIOS_3.0_API_SSE_CONTRACTS.md` match live frames
- [ ] Frontend cutover complete: `MockSSEService` removed (Phase 9.4)
- [ ] AI chat real stream works end-to-end (Phase 9.5)

## Quality gates (commands)
Record the output of:
- [ ] `python -m pytest tests/test_p*.py` — bug-fix suite still green
- [ ] `python -m pytest tests/test_e*.py` — expansion suite green
- [ ] `python gate_isolation_test.py` — tenant isolation passes
- [ ] `python gate_dlq_drill.py` + `python dlq_replay.py` — DLQ recovers
- [ ] `python task3_runner.py --base-url http://localhost:8000 --api-key <KEY>` (when quota allows)

## Evidence (Task 10.4)
- [ ] Link/attach: final expansion test count + pass rate
- [ ] Link/attach: G1 + G2 gate outputs
- [ ] Link/attach: frontend cutover sign-off (Mayank)

*Append raw command outputs here as phases land.*
