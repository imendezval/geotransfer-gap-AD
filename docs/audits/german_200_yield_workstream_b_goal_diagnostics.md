# German-200 yield diagnostics: Workstream B

This report audits the eight primary diagnostics in
[`runs/german_200_yield_workstream_e/run_001`](../../runs/german_200_yield_workstream_e/run_001/)
and records a fresh capture/evaluation in the isolated B namespace. The original
E traces and scene files remain unchanged. The work found and corrected a
native goal-event evidence gap without changing simulator dynamics or trace
frames.

## Finding: terminal goal events were missing from the saved flag

The trace serializer records the SDC entity's `current_goal_reached` flag.
Under the configured `GOAL_REMOVE` behavior, the native SDC path increments
`goals_reached_this_episode` while removing the actor, but does not set the flag
that the trace serializer copies. The saved E captures therefore showed
`reached_goal:false` at all eight terminal observations, including six goal
removals. Removal by itself is not evidence of goal arrival.

The approved correction adds an optional schema-v2 evaluation-capture sidecar.
At each existing pre-step snapshot, the worker reads the cumulative native
counter through `get_agent_log(slot)` only after checking the slot against the
snapshot's active binary-index mapping. Captures bind source ID, binary index,
lifetime, slot, eligibility, counter value, and trace hash. Evaluation emits a
goal onset only for a positive integer counter delta across an adjacent,
applied transition with the same actor, lifetime, and verified slot. It rejects
fractional counts and increases larger than one per adjacent `GOAL_REMOVE`
transition. Missing reads remain unavailable; an initial nonzero count is
left-censored. Schema-v1 capture reading and legacy v1 interpretation remain
available.

The counter event remains separate from bounded-task completion. Completion
uses the existing source task only when the captured simulator navigation goal
matches the source goal. The six fresh events have no terminal pose; none is
reconstructed from proximity or from the removal reason. The controlled
fixture's unrelated off-road removal is a negative control: its counter stayed
at zero despite `ego_removed`.

## Fresh capture and source certificates

The B run matrix completed all eight rows. Its paired trace probe confirms that
all old and new JSON `frames` are exactly equal and every terminal reason is
unchanged. New schema-v2 sidecars are hash-bound and passed the shared saved
trace reader. Every counter observation was readable: 84/84, 91/91, 60/60,
91/91, 82/82, 86/86, 74/74, and 74/74. Six counters rose from 0 to 1 on the
terminal observation; both horizon runs stayed at zero. All eight terminal
legacy flags remain false.

The bounded task is valid in both scenes from the hash-bound evaluation
contract: ego source ID 39 / binary index 0 in r00 and source ID 35 / binary
index 0 in r16; source steps 0–85; completion radius 2 m; no task deadline.
The task goals are `[144.10134, -43.61995]` and
`[70.149935, -52.840485]`. The native navigation-goal binding matches the
source goal in all eight runs; the maximum observed difference is about
6.5 µm in r00 and 2.2 µm in r16, well inside the established 0.1 m binding
criterion.

The original scenes have no `source_route_sequence.json`. Two valid source-only
certificates were audited on isolated scene copies and supplied as in-memory
task-route context during the final offline evaluation. They bind the current
converted scene, binary, source recording metadata, source map, and current
route-audit/lane-change tool hashes. They use no planner rollout:

| Scene | Valid source route | Dense source samples | Certificate SHA-256 |
| --- | --- | ---: | --- |
| r00_e39_f3000 | 1015 → 1018 → 1021 → 1024 → 1028 → 1088 → 1149 → 1172 → 1130 → 1139 | 901 | `fd5e451f0735c18365d67f21ecef6ff2dfc52411316d9f49328dd035d44cf0c0` |
| r16_e35_f1521 | 2135 → 2134 | 901 | `53fd2ad9c4197546d0425367743d88d665888431ad377fc8da87888eabc7784d` |

Both source paths are legal, ordinary-road-only routes with no lane changes.
The final evaluation also used Shapely 2.1.1 from the isolated
`runs/german_200_research_verification/evaluation_geometry` directory. No
virtualenv or project dependency installation was made. With that optional
geometry dependency available, both source map contexts validate; map
completeness and legal access remain unassessed. Sparse task annotations are
absent. The original E evaluation had valid scene/map identities but marked
geometry unavailable because its environment lacked Shapely. Its route metrics
were independently unavailable because the source-route certificate was
absent from the immutable scenes. Supplying the isolated dependency and the
current source-only route certificates resolves those two context limits; it
does not make the four trajectory projections continuous.

## Per-run results

Progress is signed net advancement on the certified source task route, measured
only from observed ego poses. Completion time is shown as elapsed time after
policy start / after the first recorded observation. Stationary duration uses
the evaluator's sampled speed threshold of 0.2 m/s. `Outside` is the number of
sampled footprints outside the mapped road-surface union, with observed
outside duration. These map samples are not native off-road events and do not
establish road legality.

| Scene / controller | Terminal | Native goal / task | Route progress | Completion (policy / recording) | Stationary | Minimum TTC within 5 s | Outside mapped union |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| r00 / expert | ego_removed, step 83 | yes, step 83 / completed | 101.906 m / 97.3% | 7.3 / 8.3 s | 0.0 s | 4.89 s | 19/83; 1.9 s |
| r00 / IDM | horizon, step 90 | no / unresolved | unavailable: projection continuity support | — | 0.0 s | none predicted | 0/91; 0.0 s |
| r00 / PPO | ego_removed, step 59 | yes, step 59 / completed | unavailable: projection continuity support | 4.9 / 5.9 s | 0.0 s | 3.20 s | 3/59; 0.3 s |
| r00 / SMART | horizon, step 90 | no / unresolved | unavailable: projection continuity support | — | 0.0 s | none predicted | 24/81; 2.4 s |
| r16 / expert | ego_removed, step 81 | yes, step 81 / completed | 10.938 m / 83.6% | 7.1 / 8.1 s | 4.0 s | none predicted | 0/81; 0.0 s |
| r16 / IDM | ego_removed, step 85 | yes, step 85 / completed | 10.934 m / 83.6% | 7.5 / 8.5 s | 1.4 s | 3.83 s | 0/85; 0.0 s |
| r16 / PPO | ego_removed, step 73 | yes, step 73 / completed | unavailable: projection continuity support | 6.3 / 7.3 s | 2.1 s | 1.40 s | 0/73; 0.0 s |
| r16 / SMART | ego_removed, step 73 | yes, step 73 / completed | 10.558 m / 80.7% | 6.3 / 7.3 s | 1.9 s | 0.91 s | 0/73; 0.0 s |

The route certificate is valid in all rows, including the four with unavailable
progress. Those four measurements are unavailable because the observed
controller trajectory crosses missing or ambiguous route-projection support;
they are not rejected source routes. Progress stops at the last present pose
(one frame before the native goal event on the six removal rows). The goal
completion time can still be measured from the hash-bound native event at the
pose-less terminal observation.

The following geometry and source-fidelity values come from the same final
saved evaluation and trace. Distances to goal use the last supported present
ego pose: this is the terminal pose for the two horizon runs, and the prior
observation for the six removed egos. Observed distance sums consecutive
present ego-centre displacements over the full recorded trace. Reference ADE
uses exact timestamp matches on the 10 Hz source grid, without interpolation,
over the primary task window (76 expected observations). FDE is unavailable
where the primary endpoint was not reached or falls outside the source task
bounds. Sampled clearance is the minimum simultaneous oriented-footprint gap
across supported actor pairs in the full trace; it makes no claim about
between-sample contact. The full trace includes warmup replay and controller
observations where poses are present.

| Scene / controller | Last present pose: step / goal distance | Observed distance, full trace | Source ADE, primary window (matched / 76) | Source FDE | Minimum sampled footprint clearance, full trace |
| --- | ---: | ---: | ---: | --- | ---: |
| r00 / expert | 82 / 2.802 m | 101.906 m | 0.000003 m (73/76) | unavailable: requested endpoint not reached | 2.095 m; step 51, actor 40 |
| r00 / IDM | 90 / 48.597 m | 143.606 m | 12.999 m (76/76) | unavailable: endpoint outside task bounds | 5.076 m; step 18, actor 37 |
| r00 / PPO | 58 / 2.365 m | 103.305 m | 8.951 m (49/76) | unavailable: requested endpoint not reached | 5.346 m; step 18, actor 37 |
| r00 / SMART | 90 / 74.923 m | 171.482 m | 22.661 m (76/76) | unavailable: endpoint outside task bounds | 4.940 m; step 18, actor 37 |
| r16 / expert | 80 / 2.145 m | 10.938 m | 0.000002 m (71/76) | unavailable: requested endpoint not reached | 1.767 m; step 15, actor 33 |
| r16 / IDM | 84 / 2.182 m | 10.883 m | 0.902 m (75/76) | unavailable: requested endpoint not reached | 1.137 m; step 31, actor 33 |
| r16 / PPO | 72 / 2.293 m | 13.509 m | 1.047 m (63/76) | unavailable: requested endpoint not reached | 1.309 m; step 22, actor 37 |
| r16 / SMART | 72 / 2.337 m | 10.912 m | 1.500 m (63/76) | unavailable: requested endpoint not reached | 0.999 m; step 23, actor 33 |

The geometric goal distance is a straight-line measurement from an observed
pose; it does not establish a legal or continuous path to the goal. Route
progress instead projects a continuity-supported sequence of observed poses
onto the certified source route, which is why it can be unavailable while
straight-line distance and travelled distance remain measurable. The native
counter event records a simulator transition and completes the bound task, but
has no terminal pose for the six removals. These measures answer different
questions and are not substituted for one another.
Every last present pose remains outside the nominal 2 m radius. For the six
removed egos, that is expected: the native event is attached to the subsequent
terminal transition, which has no ego pose to measure. The two horizon runs
have a measured terminal pose and no native goal event.

All eight runs have complete `collision_state` and native counter coverage.
There are zero observed native vehicle-collision onsets and zero native
off-road onsets. Sampled rectangle overlaps are zero, but near-miss interval
coverage is partial. TTC values are fixed-heading, constant-velocity
predictions, not observed collisions. The map-footprint excursions in r00 are
reported separately from native off-road flags. The safe-completion composite
is `not_assessed` in every run: reviewed traffic-signal applicability is
missing, and the two horizon rows also lack bounded-task completion. No
failure deadline is defined.

r00 has no designated interaction obligation. In r16, the source certificate
supports a longitudinal-following opportunity with leader actor 33; actual
route-compatible leader observations were measured for all four controllers.
Interaction realization remains unresolved at recording end, with no reviewed
outcome criterion. r16 expert and IDM have low-progress candidate windows;
the evaluator explicitly does not call them deadlocks because opportunity to
proceed is unassessed. The sampled following measurements below use only
route-compatible, leader-ahead states from steps 10 onward. Following duration
sums supported applied intervals where that relation holds. Physical gap is
the oriented-box-to-box distance; directed route gap is the map-based centerline
distance. Moving time headway is physical gap divided by ego speed and is
reported only when speed exceeds the evaluator's 0.2 m/s stationary threshold.
Its count excludes standstill/undefined samples. Ranges and medians summarize
discrete samples, not a continuous following guarantee.

| r16 controller | Following samples; window | Following duration | Physical footprint gap, min / median / max | Directed route gap, min / max | Moving time headway, min / median / max (valid n) |
| --- | --- | ---: | ---: | ---: | ---: |
| expert | 71; steps 10–80 (1.0–8.0 s) | 7.0 s | 1.767 / 3.800 / 9.322 m | 1.622 / 10.866 m | 1.668 / 2.193 / 12.092 s (41) |
| IDM | 72; steps 10–81 (1.0–8.1 s) | 7.1 s | 1.137 / 2.583 / 11.193 m | 1.360 / 11.690 m | 1.835 / 2.994 / 7.785 s (68) |
| PPO | 48; steps 10–72 (1.0–7.2 s) | 4.7 s | 1.773 / 3.176 / 4.535 m | 1.281 / 8.950 m | 0.807 / 1.727 / 10.602 s (47) |
| SMART | 63; steps 10–72 (1.0–7.2 s) | 6.2 s | 0.999 / 1.735 / 4.639 m | 1.244 / 8.590 m | 0.756 / 1.269 / 7.043 s (54) |

## Run identity and checkpoint provenance

All eight fresh captures use immediate expert traffic, ten warmup replay
frames, and the same requested 91-observation horizon; six terminate early on
native goal removal and two reach the horizon. The saved result inputs and
run verification files agree on the ego and traffic roles. Expert and IDM use
no learned ego checkpoint. PPO and SMART have the same recorded, hash-bound
ego checkpoint in both scenes. No separate traffic checkpoint applies.

| Ego controller | Traffic controller / startup | Warmup replay frames | Ego checkpoint identity |
| --- | --- | ---: | --- |
| expert | expert / immediate | 10 | not applicable |
| IDM | expert / immediate | 10 | not applicable |
| PPO | expert / immediate | 10 | `50a9a580cca905fc3dae47b5847b4edf408de3b7fe7517bd4f3a781fa140e3b3` |
| SMART | expert / immediate | 10 | `b2cdeb31b0336588df1fc872e2f64dc6b24ec88472936068ec7e9501e9252616` |

The compact comparison preserves these per-run identities and adds the numeric
pose, source-deviation, clearance, and following summaries; each row remains
bound to its trace and evaluation hashes. The run protocol was diagnostic-only
and has no research-admission status, so these results audit the saved matrix
but do not establish broader controller claims.

All eight verification records also bind the same BehaviorBench commit
`805fe04c6977b60c41c92c31f1a5211fbd704f44`, runtime source digest
`beedf8f1b0e9c490`, runtime binary SHA-256
`bdf1a2cb70f4153a0283a45fe18920b09a545ecba15fdb335a87a31762b94d58`, and
evaluation configuration SHA-256
`afdf157a7b809e31700a49f977c46a7a4913c7e73546a5803d8635a9ae1f5e4e`.

## SMART divergence: evidence and hypotheses

The source inspection marks SMART's simulator-goal visibility as false; PPO's
is true. The native goal itself matches the bounded source goal in both scenes,
so this difference concerns what the controller receives, not how the task
was bound. SMART reaches the r16 goal but runs to the horizon without a native
goal event in r00. These two scenes cannot identify the cause.

Keep these explanation families separate for any next study: missing explicit
goal input to SMART; source-map or route-context representation; route
projection/control fidelity; and the r16 leader-following interaction. The
native terminal-event correction repairs outcome measurement but does not
explain controller divergence. No SMART-specific ablation was run because the
existing protocol does not provide a supported, precisely scoped causal
intervention for these families.

## Evidence and verification files

The tracked implementation is in commit `e13edca` and touches only capture,
episode evaluation, event attribution, and focused tests. It adds a read-only
counter capture path; it changes no trace frame, native dynamics, simulator
header, tolerance, or planner route source.

- [Fresh v2 run and evaluation index](../../runs/german_200_yield_workstream_b/run_001/evaluations_v2_final/index.json)
- [Per-run baseline comparison](../../runs/german_200_yield_workstream_b/run_001/per_run_comparison.json)
- [Frame equality and counter probe](../../runs/german_200_yield_workstream_b/run_001/native_v2_pairing_and_counter_probe.json)
- [Controlled positive and negative native fixture](../../runs/german_200_yield_workstream_b/run_001/native_probes/native_goal_counter_fixture_summary.json)
- [Source-route audit summary](../../runs/german_200_yield_workstream_b/run_001/source_route_audit_summary.json)
- [r00 route certificate](../../runs/german_200_yield_workstream_b/run_001/source_routes/r00_e39_f3000.json)
- [r16 route certificate](../../runs/german_200_yield_workstream_b/run_001/source_routes/r16_e35_f1521.json)

Validation: the full suite passes with **639 passed, 1 skipped**. After the
final counter hardening, focused capture, task, episode, and saved-evidence
tests pass with **91 passed**. The controlled off-road negative retained a zero
goal counter; the six positive events were obtained from native counter
readback, not removal or proximity.
