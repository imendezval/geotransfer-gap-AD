# Step 2 original feasibility expansion (historical)

> Superseded by the [third-family execution record](2_third_family_execution.md): current16 scenes/13 interactions/3 controls, runtimebeedf8f1b0e9c490 and dense-map SMARTv4. This page preserves the earlier13-scene baseline; its counts/protocols are historical. Evidence snapshots are in `pilot/audits/history/`.

Snapshot scope: runtime `9be6e6a3d09874d5`, SMART
`smart_all_actors_observed_history_v2`, traffic
`startup_sustained_departure_v1`. Historical results under other map,
expert-velocity or startup versions cannot contribute to these counts.

The fresh scene gates admit **13 independent scenes: ten interactions and
three controls**, across **locations1/3/4 and nine recording clusters**. All13 scenes reproduce their single-scene timelines exactly in fresh batch
subprocesses; the protocol freeze passed. Stages2.1–2.5 are complete within
the explicitly limited SMART scope. Consult
`pilot/audits/step2_frozen_protocol_baseline.json` for the completed verification,
not an old snapshot or a count without its hashes.

## Outcomes against stages 2.1–2.5

| Stage | Problem | Result and completion evidence |
| --- | --- | --- |
| 2.1 Reproducible baseline | Stock SMART does not include the required runtime/input fixes, and historical reports can appear current. | Isolated runtime fixes source-valid births/exits/re-entry, permanent collision removal and expert velocities at reset/every replay step. Native Lanelet2 comparison covers437 road/bus lanelets on five map variants, independent boundary-storage reversals and directed successors. Effective model/controller/runtime hashes and fresh gates are required by the protocol freeze. See reproduction commands. |
| 2.2 Source review and queue | Fitted aerial registration biased earlier judgments. | All30 earlier decisions are inventoried;25 historical/missing registrations are explicitly superseded pending re-review. Current admissions use provider factor12, zero translation and inspected source overlays. Candidate ledgers preserve source selection and every attempted failure; superseded decisions are not admissions. |
| 2.3 Genuine tasks | Proximity, braking and actor counts can falsely suggest a necessary interaction. | Source footprint/timing checks distinguish actual crossings from sidewalk/parallel traffic. Following goals must extend beyond the leader's complete collision interval, allowing the entire2m goal region and all ego orientations. Stop/restart and constrained creeping are distinct. A source same-route certificate can disprove a crossing heuristic but cannot waive explicit priority. |
| 2.4 Ten interactions | Controls and duplicate windows cannot fill the feasibility target; primary-actor fidelity can hide lost context. | Six pedestrian encounters and four longitudinal-following encounters pass fresh scene gates. Three controls remain separate. Source-order selection excludes one otherwise passing overlapping/shared-track scene. A new gate also requires essential preceding-vehicle context. Startup traffic now preserves all primary source-close encounter frames, including car390 in the pedestrian fixture. |
| 2.5 Scope and scalable execution | Unsupported rules, unmatched US diagnostics and scene-state leakage could invalidate later conclusions. | Applicable missing obligations remain excluded; ordinary-car access is separately checked for all13 ego source routes. Two US references exercise the same controller/actual SMART path. The canonical manifest runner isolates each scene in a fresh subprocess and checks identities at refresh. Matching fields, interface differences and claim limits are documented. All13 fresh-subprocess batch timelines exactly match the corresponding single-scene runs, and the protocol freeze passed. |

## Current feasibility set

| Scene | Source task | Interaction actor |
| --- | --- | --- |
| r00/e321/f21017 | Constrained following while leader creeps, then departs | Bus317 |
| r00/e366/f23240 | Pedestrian crossing approach |357 |
| r01/e252/f16915 | Pedestrian crossing approach |241 |
| r01/e301/f20017 | Leader stop/restart, then right turn |300 |
| r02/e206/f11598 | Pedestrian crossing approach |209 |
| r02/e347/f18595 | Pedestrian crossing encounter |330 |
| r06/e281/f20211 | Pedestrian clearing while ego approaches |272 |
| r12/e151/f12041 | Leader stop/restart |141 |
| r16/e35/f1521 | Leader stop/restart |33 |
| r32/e391/f21356 | Pedestrian crossing upstream of bounded stop-line task |379; essential leader390 also preserved |

Pedestrian approach scenes are not automatically examples of yielding or
pedestrian-caused braking. Following variants count as one family. Thus the set
has **two interaction families**, not three. Controls are r00/e39, r09/e196 and
r15/e332; the last can reach its goal before the stopped queue and is not a
restart benchmark.

All source primary-encounter close frames are preserved under the selected
hybrid traffic, using the existing thresholds. Across the13 scenes, maximum
expert replay position error is **0.0000153m**; actual SMART source-feature
position error is at most **0.00000382m**, with zero presence/class mismatches
and zero velocity-vector error. These numbers measure reconstruction of the
available source, not the accuracy of the source annotations or arbitrary
closed-loop background behavior.

## Generic repair exposed by the final audit

The former startup rule released a creeping leader too early. A diagnostic
that merely required sustained departure for vehicles stopped at birth still
missed car390, which begins at1.29m/s and brakes below1m/s during observed
warmup. The promoted rule includes this generic startup condition, without any
scene ID, ego route or per-scene threshold: at least one valid sample below1m/s
in the first eleven samples; then hold until at least1s after birth,1m
source displacement and five consecutive valid samples at >=2m/s. A vehicle
without such departure remains replayed through the window. Afterwards native
IDM controls it. The first13-scene diagnostic and the full refreshed technical
gates pass, including the prescribed ego perturbation.

The gate now rejects loss of an unclaimed preceding vehicle when its frozen
source box blocks the required ego source route before goal completion. This
applies to controls as well as interaction scenes. The r32 pedestrian review
explicitly retains leader390 as necessary context rather than attributing all
source braking to the pedestrian. The negative regression ensures this cannot
silently regress. Prior evidence is archived in
`pilot/audits/history/before_sustained_departure/`.

## Exclusions and candidate flow

The flow report records **495 attempted candidate rows across439 distinct source
windows**, grouped by producer hashes. These include revisits under older
versions; they are not a pooled current rejection-rate estimate. The selected
current audit has17 roots,14 per-scene research passes,one independence
exclusion and13 selected scenes. Full linked ledgers preserve semantic,
physical, task, technical and review failures. The moving-queue search has48
source-selected windows not attempted after reaching the feasibility task;
six alternative following phases are also deferred, not classified as failures.

The original intersection pilot is recording4/ego133/frame11749, rebuilt at
`pilot/oriented_v3/r04_e133_f11749`. Its bounded rule review finds no unresolved
applicable-rule flag, but the full counterfactual fails: background135 collides
with a parked car. It remains an explicit technical exclusion. It is not the
recording20 priority fixture. Recording20/ego416 remains excluded because
applicable priority relations are unsupported. The former recording31 turn-away
scene loses its technical admission after the expert-velocity repair; retaining
that old pass would preserve a simulator defect.

## Evidence and remaining scope

- `pilot/audits/step2_expanded_current_{manifest.json,manifest.csv,summary.json}`:
  selected scenes, independence decisions and recording/location splits.
- `pilot/audits/step2_candidate_flow.json`: linked attempt ledgers, version groups,
  current decisions, original-pilot exclusion and deferred candidates.
- `pilot/audits/step2_current_fidelity_metrics.json`: per-scene measured fidelity.
- `pilot/audits/step2_corpus_access.json`: source ego road-access audit.
- `pilot/audits/step2_smart_gate_regressions.json`:24 passing rejection/restoration
  cases, including essential leading context; helper restart/following/stop
  regressions remain required separately.
- `pilot/audits/step2_expanded_batch_parity.json` and
  `step2_frozen_protocol_baseline.json`: final execution/freeze evidence.

[Reproduction commands](2_reproduce_admission.md) describe the actual entrypoints
and mandatory manual inputs. [Protocol scope and matching](2_protocol_scope_and_matching.md)
documents nonreactive VRUs, source-held traffic intent, imputed dimensions,
unknown out-of-view motion, up to four ticks of between-refresh latency,
unsupported sign/priority meaning and SMART's lack of navigation-goal input.
The upstream BehaviorBench tree remains unchanged.

**Full Step2 is not complete.** This feasibility set is not the final50-scene,
three-family corpus, nor a matched US/German geographic-performance study.
PPO has no equivalent observability/admission proof yet. Full physical and
human-response faithfulness has not been established. The achieved scope is
source-faithful reconstruction and task-reviewed evaluation under an explicit,
limited, uniformly applied SMART traffic/interface protocol.
