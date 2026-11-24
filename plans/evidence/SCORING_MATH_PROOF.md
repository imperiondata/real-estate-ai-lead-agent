# Scoring math proof — blend caps at 80, floor is loaded

**Date:** 24 November 2026
**Owner:** Maitri
**Scope:** v3 `score_lead` only. Not staging. Not Render.

`score_lead` returns a dict. It does not persist the row. The caller writes the columns.

## Why the old blend could not reach 82

Published `real_estate` v1, `Industry_Profile_Schema.json` `examples[0].scoring_rules`:

- `engagement.points_per_field` = 16
- `engagement.opt_in_points` = 4
- `engagement.cap` = 100
- `probability.engagement_weight` = 0.5
- `probability.temperature_weight` = 0.5
- `probability.temperature_weights.hot` = 60
- `probability.cap` = 98
- `temperature.hot_min_probability` = 82
- `temperature.full_qualify_floor` = 88
- `temperature.field_floors.visit_date` = 82

A fully filled lead with WhatsApp opt-in and temperature `hot`:

1. Engagement = `6 * 16 + 4 = 100`, then `min(100, 100) = 100`.
2. Blend = `int(100 * 0.5 + 60 * 0.5) = int(50 + 30) = 80`.
3. The probability cap is 98, so the cap does not raise 80.
4. 80 is below the hot cut of 82. Without a floor, 82 is unreachable. The old literal cutoff of 70 classified that 80 as hot. That cutoff is not the current function.

## Why the profile scorer returns 88

`app/industry/profile_loader.py` `load_profile("real_estate", 1)` reads that example. `score_lead` still computes the blend, then:

```text
qualify_floor = temperature_rules.get("full_qualify_floor")
if all(core):
    if qualify_floor is not None:
        prob = max(prob, qualify_floor)
elif lead.visit_date:
    prob = max(prob, loaded visit floor)
```

For the published profile, `qualify_floor` is 88, so `max(80, 88) = 88`, then classified hot because `88 >= 82`.

88 is not a literal in `score_lead`. The source check asserts `"88" not in` the function. A test that loads `full_qualify_floor = 90` returns 90, not 88. Deleting the key leaves the blend at 80, which is warm at the 82 cut.

## Boundaries

| Input | Result |
|---|---|
| Probability 81 at hot cut 82 | warm |
| Probability 82 at hot cut 82 | hot |
| Visit date only | loaded `field_floors.visit_date` (82) and hot |
| Five fields, opt-in, no visit date | blend 72, warm |
| Fully qualified, published profile | blend 80, then loaded floor 88, hot |
| Fully qualified, loaded floor 90 | 90, hot |
| Fully qualified, floor key removed | 80, warm |

## Tests

`tests/test_v2_industry_profile_scorer.py`

- `test_note_boundaries_for_the_82_cut_and_floors`
- `test_full_qualify_floor_is_loaded_not_hardcoded`
- `test_score_lead_no_longer_contains_the_literal_70_threshold` also asserts the function source has no `88`

Raw output: `plans/evidence/SCORING_MATH_PROOF.log`.

This does not replace `plans/evidence/NOV4_SCORER_RCA.md`. That file is the November root-cause note. This file is the calculation proof.
