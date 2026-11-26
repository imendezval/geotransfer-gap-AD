# German-200 v1 Workstream D: source supply census

## Reproduction and outputs

Rebuild the source-only census and the next deterministic queue with:

```bash
PYTHONPATH=src .venv/bin/python -m geotransfer_gap.corpus.census_german_200_v1
```

The command writes `artifacts/german_200_v1_workstream_d/supply_census.json`, `assessment.md`, `summary.json`, and `next_validation_queue.json`. The last file is directly consumable by `run_german_200_batch.py`: it has a top-level `candidates` array of 24 rows, with Interactive100's 12 rows followed by Random100's 12 rows. It also retains per-arm ordered identity lists as metadata. Within each arm, candidates are the next frozen ranks after excluding only identities in the immutable first batch. The source queue, first batch, and B ledger are read-only inputs.

The earlier envelope-form queue bytes are preserved at `artifacts/german_200_v1_workstream_d/next_validation_queue_v1_arm_envelopes.json` so the old serialization remains available. Flattening does not change either arm's ordered 12 identities.

## Source coverage and independence

The frozen source population contains 5,934 eligible stride-50 windows, 2,966 Random recording/ego units, and 764 Interactive task units. The selected 200 primaries are distributed across locations 1–4 as 36, 132, 10, and 22. Interactive family memberships are cyclist crossing 33, pedestrian crossing 47, and longitudinal following 20. Interactive rows span 21 recordings (largest recording contributes 11/100); Random rows span 33 (largest contributes 7/100). Combined, the 200 rows span 33 recordings.

The census rebuilds all 200 frozen source contexts from raw track CSVs using the frozen selector helpers. It found zero missing reconstructed rows, zero moving-actor list mismatches, and zero full-context mismatches. Inclusive interval and complete moving-actor checks against all 16 frozen anchors and every other primary found zero conflicts. The moving-actor rule has no cap.

No-cap greedy witnesses against the 16 anchors are 249 Interactive rows alone and 582 Random rows alone. With Interactive retained first, the cross-arm greedy witness is 249 Interactive plus 332 Random, or 581 rows. These order-dependent results establish witnesses, not maximum independent-set sizes. Pair-level rejections have no interval-only cases: all conflicting pairs share moving actors, with some also overlapping the inclusive source interval. Pair and phase counts are not additive distinct-unit losses.

The source task selectors are sampled against stride-50 catalogs. Among selector-positive actor references, 4,946 are off-stride (4,674 unique windows) and 107 on-stride references are absent from the catalogs. These are coverage gaps, not evidence of incompatibility. Missing source evidence is not treated as a rejection.

## Measured yield limits

Workstream B attempted 24 first-batch primaries: 9 source rejections, 6 technical rejections, 3 review-blocked, and 6 technical gate passes awaiting human review. No manual review was created and no final human-approved admission is recorded. Four of 11 prespecified alternates were attempted; their outcomes were two source-physical rejections, one source-geometry rejection, and one review-blocked, with no technical pass. The other 176 frozen primary rows remain unattempted.

For a descriptive, nonrepresentative first-batch scenario, technical gate passes were 4/12 Interactive and 2/12 Random. Scaling those rates to 100 frozen rows gives 33 and 17 gate passes, respectively; illustrative Wilson rate ranges are 14–61 and 5–45. These are uncertainty illustrations under a simplifying iid assumption, not yield forecasts. The first batch was deliberately stratified, and historical rates are not pooled. Technical gate passes remain distinct from final manual admissions.

The 200-row independence result establishes source supply. The technical and research yields remain uncertain. In location 2, none of the nine pilot primaries passed the technical gate and three are awaiting physical-overlap clearance. This matters because location 2 supplies 87 of the 100 frozen Interactive100 candidates. Report validation yields and evaluation uncertainty by recording and site. After the next batch, prioritize source checks on off-stride interaction windows and review the location-2 clearances. Additional German recordings would be useful if those searches still leave too few eligible tasks in the held-out site or too few recordings for clustered comparisons.

Workstream C protocol-specific results were unavailable when this census was produced. Outcomes for unrun candidates remain unknown.
