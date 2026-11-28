# German-200 source reservoir audit: D1–D2

This note reviews the frozen Random100/Interactive100 source frame and its
existing yield-reservoir witness. It is an availability and provenance audit,
not an admission decision. No source queue, gate, selector, map producer,
threshold, or protocol was changed. No conversion or planner binary ran.

## Reproduction and fingerprints

The replay ran from `overnight/reservoir-source-audit` at
`d21ff13013e65c59999bf4d06221d9644bd34f66`. It used the existing audit
producer and wrote into the ignored main-worktree output directory:

```bash
GEOTRANSFER_PROJECT=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD \
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/.venv/bin/python \
  -m geotransfer_gap.corpus.audit_german_200_yield_reservoir \
  --output-dir /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/reservoir/run_001
```

The queue input is `artifacts/german_200_v1/queues.json`, SHA-256
`33069002fe04000c0b6e35213f90a219554a1accba6c9bce8230bb990d779cba`. The
auditor, selector, identity helper, census, and map-preflight producer hashes
are recorded in the ignored machine receipt at
`runs/german_200_overnight/reservoir/reservoir_source_baseline_receipt.json`.
The prior `run_009` audit SHA-256 is
`31f98b21e61dd1dd096b4d9a16dbbac4e537387484aa3b8039e563621709ec94`. All
pinned audit inputs matched the current files. The replay directly checked
174 source-file/hash instances covering the 29 reconstructed recordings; all
matched the frozen source pins. The 5 generated catalogs, map receipts, and
ordered off-stride reservoir are byte-identical to `run_009`. Stable selected
row identities, rank fields, map verdicts, and arm/site/family distributions
also match. The full report differs in output path and runtime fields.

Fresh `yield_reservoir_audit.json` SHA-256:
`4ace2ce734d31b7959440b02a28b6b05c4b4f5c70c3bd1fadc5c94e8957f373b`.
The audit and receipt are in ignored output at
`runs/german_200_overnight/reservoir/run_001/` and
`runs/german_200_overnight/reservoir/reservoir_source_baseline_receipt.json`
(receipt SHA-256
`2d524de250909433efb00e9919fce9a26f14e88992aa2f3e3c1df46dd7d6bf2a`).
To verify the saved output digests:

```bash
sha256sum runs/german_200_overnight/reservoir/run_001/*.json \
  runs/german_200_overnight/reservoir/reservoir_source_baseline_receipt.json
```

## Frozen frame and split rules

The v1 queue contains 100 Interactive100 and 100 Random100 primary candidates.
It reserves 16 immutable anchor identities. The current baseline is therefore
216 rows, before the separate mandatory B fallback. All 200 primaries pass the
frozen source-map metadata predicate (complete ego source track, no sampled
center outside a road/bus lanelet, and a directed start-to-goal route). That
predicate is not a physical-source or semantic gate.

The exact sampling units are:

- **Random100:** one unique `(recording, ego_track_id)` unit. The source-map
  eligible stride-50 frame has 2,966 such units and 5,934 windows. Phase-level
  sampling would give egos with more windows extra weight, so the unit is
  selected first and its phases are ordered as alternatives.
- **Interactive100:** one unique `(recording, ego_track_id, actor_track_id)`
  source-positive task, not one phase. Seven selectors join to 764 eligible
  stride-50 tasks; 180 additional task identities are outside that pool. A
  task’s phases remain alternatives for that same unit.

Before independence constraints, the frozen raw draw probabilities were
100/2,966 for Random100 and 100/764 for Interactive100. Those are not final
inclusion probabilities after the greedy independence filter. The source
seed is `20261126`; canonical unit and phase identities are SHA-256 ranked.

The split label is exact: **every location-4 recording is
`heldout_location_4`**. At locations 1–3, recordings divisible by 5 are
`validation_recording`; all other recordings are `adaptation_recording`.
Location 4 remains represented in the queue, but must be analyzed separately
from adaptation and validation rows. There is no per-recording cap. The
independence rule instead requires non-overlapping inclusive source windows
and disjoint all-moving-track IDs within a recording. Windows are
`first_frame` through `first_frame + 225`, inclusive, with 91 evaluator samples
spaced 2.5 source frames apart.

## Source and map availability

The frozen stride-50 pool has the following site distribution. Family columns
are distinct Interactive task units; Random columns are distinct
`(recording, ego)` units.

| Location | Eligible windows | Cyclist tasks | Pedestrian tasks | Following tasks | Random units |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 675 | 28 | 15 | 21 | 469 |
| 2 | 3,884 | 213 | 345 | 80 | 1,802 |
| 3 | 182 | 1 | 1 | 13 | 130 |
| 4 | 1,193 | 5 | 25 | 17 | 565 |
| **Total** | **5,934** | **247** | **386** | **131** | **2,966** |

The seven selector files contain 6,649 raw selector rows and 1,553 exact
eligible selector rows in total; they deduplicate to 764 stride tasks. The
incremental off-stride pool adds 180 distinct tasks, 1,387 unique window
phases, and 1,411 task-window relations. In the reconstructed full converted
context, the referenced actor is present and moving for all 1,411 relations.

The fresh current map producer passed 727/1,387 off-stride windows (52.4%).
Its pass predicate is a complete ego track, all sampled ego centers inside
road/bus lanelets, and a directed start-to-goal route. Map failures had 119
outside-lanelet reason occurrences and 617 directed-route-false occurrences;
reason counts overlap. Incomplete-track failures were zero. By location, map
passes were 67/254 at site 1, 633/1,101 at site 2, 5/5 at site 3, and 22/27
at site 4.

The off-stride task progression below counts a task once when at least one
phase passes that stage; phase relations are not task counts.

| Location | Source-positive tasks | Actor-context-valid tasks | Map-passing tasks | Baseline-independent tasks | Greedy witness rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 38 | 38 | 25 | 10 | 8 |
| 2 | 128 | 128 | 109 | 28 | 20 |
| 3 | 4 | 4 | 4 | 0 | 0 |
| 4 | 10 | 10 | 9 | 3 | 3 |
| **Total** | **180** | **180** | **147** | **41** | **31** |

The 41 baseline-independent task count only asks whether a task has one
map-passing phase that does not conflict with the 216 fixed rows. Conflicts
between prospective tasks reduce the coverage-first greedy witness to 31. Its
family counts are 26 cyclist, four pedestrian, and one following. It is an
order-dependent witness, not a maximum independent set or a yield estimate.

Against all 216 fixed rows, the replay reproduced 31 off-stride Interactive,
80 stride-50 Interactive, and 272 Random source-only rows: 111 Interactive
plus 272 Random. A fresh current map preflight passed all 383 selected windows.
The combined site/family counts are:

| Location | Cyclist | Pedestrian | Following | Random | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 15 | 7 | 7 | 99 | 128 |
| 2 | 42 | 18 | 5 | 58 | 123 |
| 3 | 1 | 0 | 4 | 29 | 34 |
| 4 | 1 | 8 | 3 | 86 | 98 |

The saved sensitivity scenarios show how a changed retained baseline changes
the greedy supply. Only the 216-row witness and the identical 217-row
fallback reservation have a fresh current-map receipt for the selected set.

| Fixed baseline | Rows | Off-stride Interactive | Stride-50 Interactive | Interactive total | Random | Combined | Fresh selected-set map receipt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 16 anchors + 200 v1 primaries | 216 | 31 | 80 | 111 | 272 | 383 | Yes, 383/383 pass |
| Same + mandatory B fallback | 217 | 31 | 80 | 111 | 272 | 383 | Yes; selected windows unchanged |
| 16 anchors + 180 retained primaries + fallback | 197 | 38 | 90 | 128 | 277 | 405 | No separate post-selection replay |
| 16 anchors only | 16 | 99 | 174 | 273 | 304 | 577 | No separate post-selection replay |

This replay independently rechecked zero inclusive-window or moving-track
conflicts across the 216 fixed rows and all 383 witness rows. All 33 source
recordings occur in both the frozen 200-row queue and the 383-row witness;
the prospective witness uses at most 21 rows per recording. Reuse is permitted
because the rule is task/window/moving-track independence, not a recording cap.
The detailed per-recording matrices are in the machine receipt.

## Distribution effects and interpretation

The frozen v1 queue has site totals 36, 132, 10, and 22 for locations 1–4.
Interactive site totals are 10, 87, 2, and 1; Random totals are 26, 45, 8,
and 21. Interactive family totals are 33 cyclist, 47 pedestrian, and 20
following. Location 2 is 66% of the frozen candidates and 84% of the
stride-50 interaction task pool; the off-stride increment is also concentrated
there (128/180). That source concentration is visible in the selected v1
queue. The 216-baseline independent witness is more evenly distributed by
site after overlap constraints and its fixed ordering, but this does not make
it a probability sample.

Sites 3 and 4 are sparse in parts of the frozen frame: only 10 v1 candidates
are at site 3 and 22 at site 4. Family-by-site counts, particularly at site 3,
do not support precise standalone rate comparisons. Keep location 4 as its
own holdout; report site and recording counts before pooled summaries. Because
the greedy filter changes inclusion by order and recording clusters, use
descriptive cohort results unless inclusion probabilities can be recovered;
cluster uncertainty by recording/site when estimating cohort differences.

For source-context scale only, the 200 frozen primary windows contain 4,898
actor instances, of which 2,247 are moving under the converter-matched
`>=1.0 m` source-path rule. Of these actor instances, 1,275 have fewer than
91 valid source samples, including 1,224 moving instances. Their available
rows determine context membership and movement; motion outside the observed
source segment is unknown. These counts do not establish physical reviewability
or semantic correctness.

## Rank, reserve, and replacement behavior

The existing audit’s order is: coverage-first off-stride Interactive tasks,
then all stride-50 Interactive tasks, then Random units. Off-stride task order
starts with the best fixed-rank task in available location 1/3/4 by family,
then proceeds in a SHA-ranked order across locations 1–4. Selector phase
priority is frozen; event-fine phases rank by completeness, crossing-time gap,
distance of event midpoint from sample step 45, first frame, and selector row.
Other phases use first frame and selector row. Stride units use the frozen
SHA rank, and each unit’s phases have their own frozen SHA order.

For the final rank/reserve ledger, keep the unit and phase ranks separate and
publish every unit, stratum, phase, exclusion, and conflict before validation.
For Interactive, retain `(location, family)` stratum ranks and a fixed
coverage interleave: one rank-first task per nonempty location-1/3/4 family
stratum, ordered by location then cyclist/pedestrian/following, followed by
the remaining tasks in global SHA order across locations 1–4. This gives the
smaller sites explicit coverage while leaving location 2 in the shared
reserve. For Random, rank distinct `(recording, ego)` units globally; do not
rank windows as independent candidates. Keep location 4’s holdout ledger
separate. Do not add a recording cap: it would change the frame. Show
recording reuse and apply the frozen window/moving-track conflict rule. This
coverage order is descriptive; if population estimates are required, predeclare
proportional site/family allocations and recoverable probabilities instead of
using coverage counts as weights.

Use a same-task phase only for a pre-conversion source/map/task screen failure,
in that unit’s frozen phase order, after rechecking independence. A physical,
semantic, technical, or manual exclusion consumes an attempt and advances to
the next independently ranked unit; it does not authorize a better-looking
phase for the same task. Planner results must not change ranks or replacements.
If source-population estimates are needed, predeclare allocation probabilities
and keep all probabilities recoverable; otherwise label the outcome
descriptive.

## Reconciliation after the remaining batch chain

The B/C ledgers attempted 48 of the 200 primaries: 10 technical-gate passes
awaiting human review, six review-blocked, 17 source-physical rejections,
three source-geometry rejections, and 12 technical rejections. The other 152
are untested; no final manual admissions are recorded. The comparison baseline
for the next source-only reconciliation should remain all 16 anchors plus
**all 200 v1 primaries**, regardless of status, plus every fallback explicitly
marked retained by the completed chain. The present
additional reservation is the mandatory Interactive cyclist fallback
`r28/e105/a106, f5267`; it is review-blocked and still pending physical review.
The old audit’s 111+272 witness used the 216-row baseline. Adding this one
fallback yielded the same selected source-window set (217 baseline rows).
Alternative 405-row and 577-row sensitivity witnesses use different baselines;
they are not admission results, and the alternative selected sets were not
separately post-selection map-rechecked.

After the final chain, the minimum reconciliation inputs are:

1. The byte-pinned v1 queue and 16-anchor identities.
2. The completed primary/fallback disposition ledger, with immutable source
   window identity, arm, primary/fallback role, and explicit retained status.
3. The full set of retained fallback identities; do not infer retention from
   planner results or silently replace the 200 primary slots.
4. The pinned source selector/catalog/map-preflight inputs and current raw
   source-file hashes.
5. The fixed rank, phase, map, and inclusive-window/all-moving-track rules.

Hash the resulting baseline identity set, rerun source context and current map
checks, apply the same unit order, and publish the new baseline digest beside
the prior 216-row result. Report any baseline conflict explicitly rather than
silently deduplicating it. This keeps the all-200 comparison stable while
making later retained fallbacks visible as added reservations.

## Limits

The 111 Interactive plus 272 Random count is only this exact fixed-order greedy
source-only witness. No prospective row received a physical-overlap,
semantic/task, technical, manual, planner, rollout, or admission review. Map
pass is not physical clearance. No source-population yield or inclusion
probability is estimated here, and this note does not accept a candidate or
authorize a later freeze.
