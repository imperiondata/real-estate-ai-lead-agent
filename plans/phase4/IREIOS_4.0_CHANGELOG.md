# IREIOS 4.0 — Expansion changelog (living)

| This doc owns | Does not own |
|---|---|
| What shipped in Product Phase 4 + test evidence | Task specs → `IREIOS_4.0_STEP_BY_STEP.md` |

**Status legend:** `[ ]` · `[~]` · `[x]` · `[-]` · `[?]`

**Test naming:** `tests/test_f4_*.py` (Phase 4). Do not reuse `test_e*` (3.0) or `test_p*` (bugs) IDs for new work.

---

## Status table

| ID | Status | Summary | Tests |
|---|---|---|---|
| P4-0 | `[ ]` | Baseline audit vs sprint | doc |
| P4-1 | `[ ]` | API contract freeze | smoke curls |
| P4-2 | `[?]` | Graph neighborhood API | `test_f4_graph*` |
| P4-3 | `[?]` | Twin inventory API | `test_f4_twin*` |
| P4-4 | `[?]` | HubSpot track | drill / inbound TBD |
| P4-5 | `[ ]` | FE Sales AI button | lint + manual |
| P4-6 | `[ ]` | FE Forecast live | lint + manual |
| P4-7 | `[?]` | FE Graph wire | lint + manual |
| P4-8 | `[?]` | FE Twin wire | lint + manual |
| P4-9 | `[ ]` | FE SSE/JWT harden | grep + manual |
| P4-10 | `[?]` | n8n deltas | smoke |
| G5 | `[ ]` | MVP gate | full suite |
| Plans layout | `[x]` | `plans/phase3` archive + `plans/phase4` skeletons | n/a |

---

## Entries

### 2026-08-07 — Plans folder restructure + Phase 4 skeletons

- **Files:** `plans/README.md`, `plans/phase3/*` (moved 3.0 artifacts), `plans/phase4/*` (new), `AGENTS.md` pointers, root sprint header note
- **Behavior:** No runtime code change. Active queue is `plans/phase4/`. Phase 3 docs frozen under `plans/phase3/`.
- **Tests:** n/a
- **Notes:** Implementation blocked on `TEAM_LEAD_QUESTIONNAIRE.md` answers. Recommended defaults documented in Implementation Plan.
