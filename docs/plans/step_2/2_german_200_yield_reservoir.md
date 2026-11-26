# German-200 yield reservoir and source-only audit

This is a planning audit, not a v2 freeze or admission result. The reusable
read-only tool is
[`audit_german_200_yield_reservoir.py`](../../../src/geotransfer_gap/corpus/audit_german_200_yield_reservoir.py).
It reads the frozen queue and B/C ledgers, uses the existing freeze/context
helpers, and runs the existing source-map producer on scratch catalogs. It
does not change queues or run prospective physical, semantic, technical,
planner, rollout, or manual-review gates.

## Frozen and retained scenarios

The frozen v1 cohort has 200 primary slots. B/C attempted 48: 10 technical
passes awaiting human review, six review-blocked, 12 technical rejections, 17
source-physical rejections, and three source-geometry rejections. The other
152 primaries are untested. The frozen source-map metadata passes for all 200;
that is not physical clearance. No manual review or final research admission
has been recorded.

Keep the mandatory B fallback for Interactive100 cyclist task r28/e105/a106,
f5267, as an additional reservation. It is review-blocked and pending physical
review. The frozen scenario therefore has **200 primary slots / 201 candidate
rows including the fallback**.

| Reservation scenario | Primary rows reserved | Candidate rows including fallback | Retained statuses |
| --- | ---: | ---: | --- |
| Frozen v1 | 200 | 201 | All 200, regardless of outcomes |
| Conservative retained-only | 180 | 181 | 152 untested, 10 technical passes pending review, six review-blocked, 12 technical rejections |
| Terminal-rejection sensitivity | 168 | 169 | 152 untested, 10 technical passes pending review, six review-blocked |

The conservative scenario releases only the 17 source-physical and three
source-geometry rejected primaries. Technical failures remain assigned because
they do not establish that the source task is unusable elsewhere. The labeled
sensitivity additionally treats all 12 technical rejections as reusable. Both
keep the fallback. Neither scenario changes the v1 queue or uses planner
outcomes.

## Baseline-dependent source-only witness counts

These are matched reruns of the same full-source, fixed-order greedy selection
using the same off-stride, stride-50 interaction, and random source pools. They
are availability witnesses, not maxima or expected admitted counts.

| Retained baseline | Baseline rows | Off-stride interaction | Stride-50 interaction | Interactive total | Random | Combined witness | Change from exact 216 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 anchors + 200 frozen primaries | 216 | 31 | 80 | 111 | 272 | **383** | — |
| Same 216 + protected B fallback | 217 | 31 | 80 | 111 | 272 | **383** | 0 |
| 16 anchors + 180 retained primaries + fallback | 197 | 38 | 90 | 128 | 277 | **405** | +22 |
| 16 anchors only, full current source | 16 | 99 | 174 | 273 | 304 | **577** | +194 |

The headline **383** is the prospective witness after the exact 216-row
baseline. The protected fallback adds one reservation (217 total) but its
selected source-window set is unchanged, so the same fresh current source-map
receipt applies: 383/383 pass. The 405 and 577 alternative-baseline counts use
the same fixed greedy functions, the fresh off-stride map preflight, and the
existing map-qualified stride-50 pools; those alternative selected sets did not
receive a separate post-selection current-map rerun. The earlier v1 stride-only
anchor reference was 249 interactive + 332 random = 581; it is a different
pool/order and is not the 577 full-source result.

The retained-only scenario reserves 197 rows: 16 anchors, 180 primaries, and
the fallback. It releases 20 rejected primaries for potential reuse. This does
not make the released rows planner outcomes or admissions, and does not create
a v2 queue.

## Prospective source-only supply

The seven frozen selectors join to 764 eligible stride-50 interaction tasks.
There are 180 incremental off-stride task keys outside that complete pool,
giving 944 source-positive interaction task keys in the union. The off-stride
pool has 1,387 deduplicated windows / 1,411 task-window relations. Its source
actors were present and moving in the reconstructed full converted context for
all 1,411 relations. All 29 recording input sets matched the frozen v1 hashes.

The current source-map producer was run over all 1,387 incremental off-stride
windows. It passed 727; 660 failed at least one source-map condition. The map
condition is a complete ego track, all sampled ego centers inside road/bus
lanelets, and a directed start-to-goal route. Reason occurrences overlap.

| Location | Incremental tasks: cyclist / pedestrian / following | Tasks with a map-passing phase | Fresh map windows pass / total |
| --- | ---: | ---: | ---: |
| 1 | 25 / 6 / 7 | 12 / 6 / 7 | 67 / 254 |
| 2 | 128 / 0 / 0 | 109 / 0 / 0 | 633 / 1,101 |
| 3 | 1 / 1 / 2 | 1 / 1 / 2 | 5 / 5 |
| 4 | 2 / 5 / 3 | 1 / 5 / 3 | 22 / 27 |

The order-independent task count after requiring at least one context- and
map-passing phase with no conflict against all 216 frozen anchors and primaries
is 41: location 1 has 6 cyclist, 3 pedestrian, and 1 following task; location
2 has 28 cyclist tasks; location 4 has 1 cyclist and 2 pedestrian tasks;
location 3 has none. A coverage-first, no-cap greedy pass selected a **31-task
off-stride witness** (8 at location 1, 20 at location 2, three at location 4;
26 cyclist, four pedestrian, one following). This is an order-dependent
witness, not a maximum independent set. It preserves the location-2 supply and
shows why source-map availability alone does not establish independence.

The full-source prospective witness additionally considers all 764 stride-50
interaction tasks and all 2,966 map-qualified random `(recording, ego)` units.
After reserving all 216 frozen rows, deterministic greedy selection found 80
additional stride-50 interaction rows and 272 random rows. With the 31
incremental off-stride rows, this gives **383 source-only rows after the full
216-row baseline**. A fresh current map preflight passed all 383 selected
windows, including 34 at location 3. The location/family counts are:

| Location | Cyclist | Pedestrian | Following | Random source candidates |
| --- | ---: | ---: | ---: | ---: |
| 1 | 15 | 7 | 7 | 99 |
| 2 | 42 | 18 | 5 | 58 |
| 3 | 1 | 0 | 4 | 29 |
| 4 | 1 | 8 | 3 | 86 |

The prior v1 stride-only greedy witness was 249 interaction plus 332 random,
581 total, **against the 16 anchors only**. It is not comparable to 383, which
reserves the 16 anchors and all 200 v1 primaries and includes off-stride tasks.
Neither count is a maximum or yield estimate. Random candidates remain
unreviewed source windows, not established controls. No prospective rows have
physical, semantic, technical, planner, or manual-review evidence.

## Validation design and effort

The prospective objective is 100 final eligible rows per arm, not 100
candidate attempts. Predeclare 12 rows per arm for the first validation
tranche, then fixed 12-row tranches. Use a maximum budget of 1,000 candidate
attempts per arm, which covers the 10% hypothetical-yield case. Stop when each
arm has 100 rows through the predeclared physical-source, semantic/task,
technical, and manual eligibility stages, at the 1,000-attempt limit, on
source-pool exhaustion, or at a protocol-integrity/safety stop. Do not extend
the budget or replace rows based on planner outcomes.

Before any prospective run, publish a deterministic source-only rank and
reserve ledger for each arm. Recheck inclusive source windows and all moving
track identities against every retained row. A source, map, task, physical,
semantic, technical, or manual exclusion consumes an attempt and advances to
the next independent source-ranked unit in its predeclared arm/site/family
order. A different phase of the same unit is allowed only for pre-conversion
source, map, or task-screen failure, using its frozen phase order. Do not tune
phase or rank order after planner results. The current source-only witness has
111 Interactive100 and 272 Random100 rows, so it is too shallow for the
predeclared attempt budget; expand and rank a deeper independent pool before a
v2 freeze or prospective execution.

Interactive sampling uses one
`(recording, ego, actor)` task per unit, with family/site strata. Random sampling
uses one equal-weight `(recording, ego)` unit from the 2,966 map-qualified
units, not uniform windows, which would over-weight longer tracks.

Only pre-conversion source-integrity, map, or task-screen failures can trigger
the next predeclared phase for that same task/unit. Recheck all moving context
actors and inclusive source intervals against every retained row. If phases
are exhausted, record the unit as unavailable; any reserve unit follows the
predeclared arm/site-family order. After a validation-stage exclusion, advance
to the next independent ranked unit. Never replace based on planner or outcome
evidence. Publish rank order and exclusions. The greedy
independence filter changes inclusion probabilities, so population estimates
need recoverable design weights; otherwise report descriptive cohort results
and cluster uncertainty by recording/site. Keep location 4 as the held-out
site and report site drift before pooled results.

The B/C pilot counts are descriptive only:

| Arm | B/C attempted | Awaiting human review | Review-blocked | Technical rejection | Source-physical rejection | Source-geometry rejection | Untested v1 rows | Current source-only witness | Later physical / semantic / technical / planner / manual yields |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Interactive100 | 24 | 6 | 4 | 4 | 9 | 1 | 76 | 111 (all passed current map preflight in the 216-row witness) | Unknown / not run |
| Random100 | 24 | 4 | 2 | 8 | 8 | 2 | 76 | 272 (all passed current map preflight in the 216-row witness) | Unknown / not run |

The 48 historical attempts produced zero final manual admissions. For 100 final
eligible rows per arm, the explicit hypothetical yields below imply 1,000,
400, or 250 candidate attempts. These are planning scenarios, not observed
rates or forecasts.

| Hypothetical final eligibility yield | Candidate attempts per arm | Serial worker minutes per arm at 14.994 s/attempt | Wall minutes with two evenly loaded workers | Reviewer hours if each attempt receives 15 min review |
| ---: | ---: | ---: | ---: | ---: |
| 10% | 1,000 | 249.9 | 124.95 | 250 |
| 25% | 400 | 99.96 | 49.98 | 100 |
| 40% | 250 | 62.475 | 31.2375 | 62.5 |

No safe exact cheaper substitute for the physical-source gate has been
validated. Lightweight overlap or source-map flags remain diagnostic only:
there is no demonstrated false-negative bound, equivalence study, or full
validator parity result that supports replacing the gate. No production
validator or queue was changed.

The B and C reports give mean primary runtimes of 15.785 and 14.202 seconds.
Their unweighted mean implies about 25 serial worker-minutes per 100-row arm,
or 12.5 minutes with two evenly loaded workers, excluding setup and map
preflight. For planning only, 15 reviewer-minutes per candidate gives three
reviewer-hours for a 12-row tranche or 25 hours for a 100-row arm. These are
throughput and effort assumptions, not yield forecasts. B/C were fixed,
stratified batches and are not used to project future pass rates.

## Reproduction and artifacts

```sh
PYTHONPATH=src MPLCONFIGDIR=/tmp/geotransfer_mpl OMP_NUM_THREADS=1 \
  .venv/bin/python -m geotransfer_gap.corpus.audit_german_200_yield_reservoir \
  --output-dir artifacts/german_200_yield_reservoir/run_009
```

The initial run_007 artifacts remain frozen. The corrected detailed scratch
report is
`artifacts/german_200_yield_reservoir/run_009/yield_reservoir_audit.json`
(SHA-256 `31f98b21e61dd1dd096b4d9a16dbbac4e537387484aa3b8039e563621709ec94`).
It records input hashes, source and stage counts by site/family, B/C statuses,
source versions, current map receipts, and selected witness rows. The complete
ordered 180-task / 1,411-phase off-stride reservoir with full moving-track
identities, phase evidence, map rows, source hashes, and selection decisions is
`run_009/ordered_incremental_offstride_reservoir.json`. The fresh off-stride
map receipt is `run_009/incremental_offstride_current_map_preflight.json`; the
fresh 383-window witness receipt is
`run_009/prospective_witness_current_map_preflight.json`. The report records
their hashes and the current preflight producer fingerprint.
