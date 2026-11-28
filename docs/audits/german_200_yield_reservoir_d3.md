# German-200 source reservoir reconciliation: D3

This is an offline source-only reconciliation, not a v2 freeze or admission decision. It reads the accepted B1–B9 chain, preserves every frozen primary and retained fallback reservation, rebuilds the source candidate frame, and applies the existing deterministic selectors. No native run, physical gate, semantic review, technical gate, planner run, or human review was performed on the prospective rows.

## Result

The canonical B1–B9 chain resolves to **16 anchors + 200 v1 primaries + 6 retained fallbacks = 222 unique source-window identities**. The sorted identity-set SHA-256 is `aca19b77892050ad7b67497d6255a68016d1198242a6b1e7b18287eeb7f8b309`. The fallback counts by batch are `[1,0,0,1,0,0,3,1,0]`; the accepted B9 record digest is `05d898b174bccaebab6a1a804344e69d4eadef082254ad425a713530085c9aa6`, and the history-file digest is `27df52d6410f141c903e38a389e6dc746d13530241c7e39973ec810ec3e533d9`.

The 222-row reservation contains six internal source-independence conflicts. Each is exactly one retained fallback against its own replaced v1 primary phase; there are no other baseline conflicts. Both members remain reserved as mutually exclusive v1 alternatives. The selected new witness has **zero** window-overlap or shared-moving-track conflicts against all 222 reservations or among its own rows.

The deterministic source-only witness contains 31 off-stride Interactive rows, 80 stride-50 Interactive rows, and 272 Random rows: **111 Interactive + 272 Random**. Its selected-window-set SHA-256 is `f9b94266c53106ff2247e1943814720893deaddfe4bcc070bc7d1e9e382cacd3`. This exactly reproduces the accepted D1 217-row sensitivity result, and also the D1 216-row result. The five additional retained fallbacks did not change this greedy selected set.

All 383 selected windows passed the current source-map predicate: complete source ego track, zero sampled centers outside a road or bus lanelet, and a directed start-to-goal route. Counts by location were 128, 123, 34, and 98 for locations 1–4. These are map-qualified source candidates, not physically or technically cleared cases.

## Ordered witness distribution

Interactive family counts are row memberships; Random rows have no frozen task label and remain unclassified. Location 4 is a holdout and is excluded from the validation-attempt capacity below.

| Location | Interactive | Cyclist | Pedestrian | Following | Random | Total map-passing rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 29 | 15 | 7 | 7 | 99 | 128 |
| 2 | 65 | 42 | 18 | 5 | 58 | 123 |
| 3 | 5 | 1 | 0 | 4 | 29 | 34 |
| 4, holdout | 12 | 1 | 8 | 3 | 86 | 98 |
| **Total** | **111** | **59** | **33** | **19** | **272** | **383** |

The witness uses 33 recordings. Combined reuse ranges from 4 to 21 rows per recording; the per-arm maxima are 9 Interactive and 19 Random. This is permitted by the frozen rule: there is no per-recording cap, but inclusive source windows must not overlap and all moving context track IDs must be disjoint within a recording. Location 4 contributes 12 Interactive and 86 Random rows, all held out. Among locations 1–3, the selected rows split into 78 Interactive and 144 Random adaptation rows, plus 21 Interactive and 42 Random validation rows. Keep those splits separate in later analysis.

The ranked source pool has 5,934 stride-50 map-eligible windows, 764 unique Interactive `(recording, ego, actor)` tasks, and 2,966 Random `(recording, ego)` units. Seven existing selector catalogs add 180 off-stride Interactive task units across 1,387 window phases. The off-stride frame reconstructs full converter-matched moving context from 29 recordings; current raw source hashes matched every frozen queue pin available for those recordings. Source hashes for all 33 selected-witness recordings are recorded in the machine summary.

The selection order is fixed and outcome-blind: coverage-first off-stride Interactive tasks (one rank-first task for each available location-1/3/4 family stratum, then global deterministic task rank), all stride-50 Interactive task units ranked with their frozen phase order, then Random recording/ego units ranked globally with their frozen phase order. One unit contributes at most one selected phase. The independent rank/reserve artifacts enumerate the full unit and phase order, map eligibility, moving-track IDs, and each tested conflict. The off-stride artifact records every task and selector phase. These greedy witnesses are not maximum independent sets or probability samples; their counts do not imply physical, semantic, technical, or human-review yield.

## Validation capacity and pending reviews

The accepted chain contains 200 primary outcomes: 39 `awaiting_human_review`, 40 `review_blocked`, 8 source-geometry rejections, 77 source-physical rejections, and 36 technical rejections. The 39 primary technical passes pending human review are 13 Interactive and 26 Random. No manual approvals are recorded. All 200 primaries and all six fallbacks remain in the 222-row reservation regardless of status; these observations did not affect the source ordering.

| Arm | Source-only witness including location 4 | Location-4 holdout | Current non-holdout source capacity | Pending primary technical passes | New admissions needed if none pass review | If every pending primary pass is approved (upper-bound sensitivity) | Attempts at 10% yield, none / all pending | At 25%, none / all pending | At 40%, none / all pending |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Interactive | 111 | 12 | 99 | 13 | 100 | 87 | 1,000 / 870 | 400 / 348 | 250 / 218 |
| Random | 272 | 86 | 186 | 26 | 100 | 74 | 1,000 / 740 | 400 / 296 | 250 / 185 |

Yield percentages are hypothetical planning cases, not estimates. Even if all pending primary passes later receive human approval, the non-holdout witness is below both arms’ 10% attempt budget and below the 25% case. It is also below the 40% Interactive case; Random is only one row above the primary-pass-adjusted 40% attempt count. Separately, there is one additional Random alternate with technical-pass status. It is not included in the primary-pass table; if it eventually proves eligible and is approved, the Random pending-adjusted need would be 73 new admissions and 183 attempts at a hypothetical 40% yield. This is a sensitivity only, not an approval or eligibility claim. At the existing planning allowances of 14.994 technical-run seconds and 15 reviewer-minutes per candidate, reviewing every current non-holdout witness row would require about 24.7 worker-minutes and 24.75 reviewer-hours for Interactive, and 46.5 worker-minutes and 46.5 reviewer-hours for Random. The 39 pending primary rows add an assumed 9.75 reviewer-hours if all receive that review allowance. These are workload calculations, not measured reviewer throughput. Downstream eligibility for every new row remains unknown.

The witness count is a fixed-order simultaneous independent set, not an upper bound on all possible sequential attempts. A later attempt plan must keep the rank order fixed, preserve all 222 v1 reservations, and recheck independence against the retained cohort at the time of each attempt. It must not use planner outcomes to reorder candidates or replace a failed candidate with another phase of the same task after a physical, semantic, technical, or manual exclusion.

Location 2 has 123 witness rows (65 Interactive, 58 Random). The accepted E2 audit reports 7/132 L2 technical passes, 63 physical rejections, six geometry rejections, 40 review-blocked rows, and 16 technical rejections. In the 63 saved hybrid admission reports, 11 failed the `hybrid_counterfactual` check. These are observations on the existing L2 primary cohort, not a yield estimate for these 123 source-only candidates. See [the E2 location-2 follow-up](german_200_location2_followup_e2.md). No human-yield assumption is inferred from E2.

## Source-map and replay evidence

The 1,387-row off-stride current-map output was reused from the accepted D1 replay only after checking its SHA-256 against the D1 receipt, matching the producer and pinned input hashes, and rebuilding current source context. For the selected witness, a fresh current-map preflight was run in D3 run 003; run 005 reused that output only after the selected catalog bytes and producer fingerprint matched exactly. The preflight output SHA-256 is `96d33df6fc117205645d5f970e4a2f4f4c96bb2eae95df94de62503e355b9636`; it reports 383/383 pass with no metadata differences.

The D1 selected-set comparison reproduced SHA-256 `f9b94266c53106ff2247e1943814720893deaddfe4bcc070bc7d1e9e382cacd3` for the 216-row and 217-row baselines. The new 222-row baseline produces the same selected-set digest. This is an exact deterministic set comparison, not evidence that the three baselines have equal physical or technical yield.

The final run is in ignored output at `runs/german_200_overnight/reservoir_final/run_005/`. Key fingerprints:

- `d3_summary.json`: `230967202f4b051778fe2b4d73a11f404d8e7dc8c7decc4b0fbc6b7e3477b2f2`
- `d3_receipt.json`: `a82d4d54afdd49663e43d8c6db5d0e5a5efd8b042c15962e8c4b7215efb4c4e8`
- `replay_d3.py`: `aba834664d26ea642cc04b94aa0e4846ba5a078d72a1655ec19468b037de4e9e`
- `selected_witness.json.gz`: `cb2c9ad2d57a37ecdfb37966bd833b4b75db5815c909a957ffb0cccca3f8af57`
- `interactive_rank_reserve.json.gz`: `c00184a72094bde26114022e4fda4a294dd6b20cb8915092d6f10f8a77d5fe20`
- `random_rank_reserve.json.gz`: `c095c106d710f881d1f34bfc5475d61f3f5a29c8aadb09aa2babb0bd172f4de7`
- `ordered_incremental_offstride_reservoir.json.gz`: `990f6980a347ef1a68d421eee546f39e42221c7ae12776c263cfc36b7ae457cf`
- `prospective_witness_current_map_preflight.json`: `96d33df6fc117205645d5f970e4a2f4f4c96bb2eae95df94de62503e355b9636`
- `baseline_conflicts.json`: `6908b670397ee8f83e1de755c06a8f75434814f0b0f482b9fa5b59b2003764be`

The worktree was `overnight/reservoir-final` at `db8cbe7e594663c4481214e5fe6709967952a664`. The receipt pins the source, selector, identity, map, retention history, queue, review index, and prior D1 evidence hashes. To rerun into a fresh ignored directory, set `D3_OUTPUT` to a new path; the script refuses to overwrite a nonempty output. The run uses at most two numerical threads and performs no native execution:

```bash
D3_OUTPUT=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/reservoir_final/run_006 \
GEOTRANSFER_PROJECT=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD \
PYTHONPATH=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/reservoir-final/src \
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 MPLCONFIGDIR=/tmp/mpl_reservoir_final \
/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/.venv/bin/python \
/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/reservoir_final/run_005/replay_d3.py
```

## Other local datasets and readiness

Local `exiD` and `rounD` data include Lanelet2 and OpenDRIVE maps (seven mapped locations in exiD, three in rounD); local `highD` data has no `maps/` directory. The local exiD `tracksMeta` class tally is car 52,762, truck 12,651, van 3,940, and motorcycle 77. Treat exiD as a source of freeway entry/exit and merge opportunities with those observed motor-vehicle classes; this inventory does not support pedestrian or cyclist interaction evidence. Candidate future roles are rounD for roundabout interactions and highD for highway following. None is part of this inD source frame. Before supplementing inD, freeze per-dataset source-file hashes, conversion and actor-context rules, source-positive task units and phases, map coordinates and directed route checks, site/family sampling units, and independence against every retained row. The existing source-map preflight cannot be assumed to work on highD without a map/routing input.

**Readiness: not ready to freeze v2 or begin validation from this evidence alone.** The non-holdout source-only witness has 99 Interactive and 186 Random rows, includes no physical or semantic validation, and provides no measured human-review throughput or downstream yield. Keep the full rank/reserve evidence and the 222 reservations fixed; expand the independent source frame and specify the attempt/holdout design before a v2 freeze. No formal acceptance is implied by this report.
