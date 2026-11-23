# GeoTransfer performance evaluation — implementation milestones

**Companion specification:** `docs/plans/performance_metrics/geotransfer_performance_evaluation_plan.md`, reviewed version dated 22 November 2026.
**Companion execution prompts:** `docs/plans/performance_metrics/geotransfer_performance_milestone_prompts.md`.
**Executor:** Luna with xhigh reasoning in Codex. One implementation session implements one milestone.
**Repository inspected:** [`imendezval/geotransfer-gap-AD`](https://github.com/imendezval/geotransfer-gap-AD), `main` at **`504218cb9ecd7fd64d2952630b9f10f56d80f923`**, fetched and inspected on 22 November 2026.
**Pinned upstream inspected:** `boschresearch/behavior-bench` at **`805fe04c6977b60c41c92c31f1a5211fbd704f44`**, as required by the repository.

## 1. Architectural decision

Implement a **read-only performance evaluator over existing execution artifacts**. Add a small `src/geotransfer_gap/evaluation/` subsystem for genuinely new metric and analysis responsibilities, and a lazy `geotransfer evaluate` dispatch in the existing CLI. Reuse the existing runtime, controllers, manifests, artifact utilities, batch accounting, validation evidence, and offline viewer.

Evaluation must not run a simulator, regenerate admissions, mutate scenes, or produce new planner inputs. The only planned change to execution is an **optional evidence-capture sidecar**, using information already exposed at the existing pre-step capture point. Ordinary runs retain their behavior and historical trace format. Most metrics must work on saved traces without extra capture.

Keep original source admission, execution validity, metric validity, encounter realization, driving outcome, and geographic comparability as separate facts. A performance report cannot grant admission or promote a diagnostic controller pair to a research-admitted protocol.

These milestones are detailed engineering instructions accompanying the WHAT specification. They do not authorize changing that specification's scientific scope or quietly dropping requirements that prove difficult.

## 2. What the repository actually contains

All paths below are relative to the inspected repository. Recheck them in PE00 if HEAD has moved.

| Existing owner | Observed responsibility | Required reuse / extension |
|---|---|---|
| `cli.py` | Lazy command dispatch | Add one `evaluate` command; preserve all existing commands and selectors |
| `execution.py` | Immutable `RunProtocol`, legacy runners, matrix single/manifest execution | Keep orchestration here; extend only for optional capture |
| `runtime/episode_worker.py` | One controller-pair stepping loop; pre-step snapshot; at most `steps - 1` transitions | Reuse its existing `capture_lifecycle` hook; no second episode loop |
| `runtime/session.py` | Canonical environment construction and world-coordinate trace frames | Preserve this file unless an independently justified defect requires a separate change; it is in legacy SMART execution fingerprints |
| `runtime/actor_index.py`, `step_snapshot.py`, `scheduler.py` | Source ID/lifetime identity, live slot mapping, ownership and single action writer | Consume their recorded facts; do not rebuild identity from active batch positions |
| `runtime/run_trace.py` | Trace schema 3, verification schema 2, live pinned-runtime validation, exact canonical comparison | Keep existing validation strict and comparator semantics intact |
| `runtime/matrix_batch.py` | Schema-4 run ledger; durable attempts, logs, locks and resume | Read it for accounting; do not build another execution scheduler or retry system |
| `matrix_campaign.py`, `verification_matrix.py` | Frozen 504-slot acceptance campaign, single/batch parity, 16-scene input inventory | Consume persisted reports. Keep this fixed verification campaign fixed; it is not the general performance cohort builder |
| `artifacts.py`, `config.py` | Atomic finite JSON, hashes, configured roots, portable references, scene/manifest lookup | Reuse these; do not introduce another path/hash/config framework |
| `visualization/viewer.py`, `campaign_gallery.py`, `viewer.html` | Legacy/matrix playback, sidecar/hash checks, ownership/events, filtered saved-campaign galleries | Extend the existing viewer; share loading checks without using display labels as metric inputs |
| `maps/lanelet.py`, `audit_scene.py`, `audit_source_route_sequence.py` | Provider map choice, projection, geometry, orientation, directed-route evidence | Reuse map interpretation; do not invent another converter or routing graph |
| `maps/audit_rule_applicability.py`, `validation/audit_physical_source.py` | Existing oriented-box and polygon helpers; source physical/rule evidence | Reuse suitable pure geometry. Keep source validation independent of performance pass/fail decisions |
| `maps/audit_following_scope.py`, `audit_task_rule_scope.py`, `audit_directed_rule_scope.py` | Source-only following/stop-scope/directed-rule certificates | Read as scoped evidence; never apply a source-route waiver to arbitrary closed-loop behavior |
| `validation/audit_task_interactions.py`, `audit_interaction_fidelity.py` | Source body-path conflict and original IDM/hybrid timing-fidelity evidence | Reuse original source evidence; add actual-rollout encounter assessment instead of calling the old audit for every new controller pair |
| `validation/suite.py`, `migration.py`, `tests/` | Independent regression/migration gates and controller tests | Extend with focused performance tests; retain all existing gates |
| `planners/protocol.py`, `validation/scene_contract.py` | Established producer hashes and admission freshness | Do not change their definitions to make performance work inherit old admission |

### Verified corpus and execution facts

- The tracked portable manifest contains **16 scenes, 10 recording clusters, and three locations (1, 3, 4)**: six pedestrian crossings, four longitudinal-following cases, three cyclist crossings, and three controls.
- Cyclist subtypes include **one crossing after ego passage**. This must not become a mandatory-yielding failure criterion.
- Current matrix coverage is 28 configurations per scene: 16 immediate and 12 source-hold. The fixed acceptance inventory has 448 German slots, 32 immediate US slots, and 24 US source-hold slots blocked without authoritative source JSON. Repository documentation records acceptance evidence; this review did not rerun the native campaign.
- Matrix traces store nested pre-action frames, stable actor IDs, effective owners, movement modes and transitions. Legacy expert/SMART traces use flat schema-2 frames.
- `session.frame` stores pose, footprint dimensions, velocity, presence, collision state and ego goal flag. It omits native collision-partner/impact-position fields. Verification sidecars add lifecycle facts and **native-coordinate** navigation goals.
- The pinned upstream binding already exposes `collided_with_index` and collision positions. Native off-road is a road-edge collision signal, not a complete drivable-polygon excursion measurement. Native collision state is a single classification, so simultaneous physical conditions may need separate geometric diagnostics.
- Upstream `evaluation/metrics.py`, `evaluator.py`, and `collision_classifier.py` already contain benchmark metrics/classification logic. Their missing-value defaults and fault heuristics must not be adopted blindly. Prefer a narrow optional adapter over copied upstream evaluator code.
- SMART is not given a navigation goal in the inspected path; PPO observes the simulator goal. Goal misses need this context.

### Verification performed for this planning review

The checkout stayed clean. In an isolated Python environment, pytest produced **307 passed, 1 skipped, 2 failed**. Both failures were in `tests/test_core.py`: outside-project scene listing and real-scene viewer construction, because the ignored local manifest/scene artifacts were absent. Torch, Lanelet2, licensed data, checkpoints, the configured native environment and saved campaign artifacts were unavailable. Accordingly, native integration, migration and real rollout correctness are **not newly verified** here. PE00 must establish the baseline on the execution machine; do not treat this review as a clean full-suite pass.

## 3. Non-negotiable constraints for every session

1. Read applicable `AGENTS.md`, this plan, the specification, the selected prompt, and the preceding milestone's handoff. Inspect current implementations before editing.
2. Work on a feature branch. Preserve unrelated changes. Implement only the selected milestone and the smallest necessary fix for its own regressions. Do not silently start later milestones, rewrite controllers, expand the corpus, or train anything.
3. Reuse an existing owner before adding another implementation. New modules need a distinct responsibility and a named caller. No generic plugin system, duplicate registry, parallel manifest format, second viewer, second batch executor, catch-all utilities package, or permanent compatibility wrappers.
4. Keep `configs/scenes.json`, `configs/current_manifest.json`, existing semantic reviews, original converted JSON/binaries, upstream code/checkpoints/INI, native patches and model representations unchanged. Do not add licensed inputs, derived imagery, real traces or HTML to Git. Use synthetic fixtures for tracked tests.
5. Preserve `geotransfer run`, legacy SMART/expert/preset execution, fixed matrix acceptance, and viewer behavior without new options. Never weaken hash checks, admission checks or exact equality to get a green result.
6. New evaluation output goes into a **new directory under configured `runs`**. Refuse outputs overlapping source data, a scene's `testing/`, input traces, or frozen campaign directories. Evaluation should not overwrite its inputs or append derived metrics into an archived run.
7. Preserve historical evidence bytes. Never rewrite its code hashes to current HEAD. Distinguish archive integrity from live reproducibility, as specified below.
8. Use existing dependencies first. If robust polygon union/difference is needed, one optional `evaluation-geometry` extra containing Shapely is acceptable; it must not become necessary to import/run unrelated commands. Avoid adding pandas-like frameworks, databases or heavy simulation dependencies to offline analysis.
9. Add meaningful tests for the scientific calculation or compatibility risk. Prefer analytical expected values, invariances and independent fixtures over tests that recompute the implementation's formula.
10. Record exact commands, statuses and missing prerequisites. Never skip a required check silently, turn an asset failure into a pass, fabricate manual review, or call a milestone fully verified while a mandatory gate is blocked.
11. Each session updates **one shared** `docs/plans/performance_metrics/implementation_results.md` with its milestone section. Do not create a progress-file hierarchy. Record implemented behavior, files, reuse choices, tests, evidence paths, deviations, remaining blocks and the next milestone. Commit only milestone-owned source/tests/docs when appropriate; never push or publish automatically. A later frozen native campaign requires a clean committed implementation.

### Historical evidence versus current-runtime verification

`runtime.run_trace.code_fingerprints()` fingerprints **all package Python files**. Even adding an offline module changes current fingerprints. `matrix_campaign.report()` also insists that the full frozen revision/environment still matches. Therefore:

- For **new executions**, continue using existing strict parent validation at their actual producing revision.
- For **saved executions**, verify the saved attempt/campaign hashes, producer identity, recorded input identities and supported structural invariants. Record the evidence level as archived/attested, not freshly rerun against current software.
- Do not call the current `validate_run()` or regenerate a frozen campaign report as the mandatory entrypoint for reading an old campaign. Do not edit historical attestations or relax current validation.
- If historical evidence is incomplete, retain an explicit lower evidence level and exclude it from any analysis requiring stronger evidence. A bare trace can support limited diagnostics; it cannot acquire an execution attestation by being readable.

This distinction must be implemented once in the shared trace-loading boundary and tested with a producer revision different from evaluator HEAD.

## 4. Proposed ownership and data contracts

Use these names unless PE00 finds an existing equivalent. Small adjacent responsibilities can share a file; this is a boundary guide, not a requirement to create empty scaffolding.

| Location | Single responsibility |
|---|---|
| `runtime/trace_io.py` (new, narrowly extracted) | Saved bundle loading, existing viewer hash/coherence checks, shared raw frame access; no simulation and no metric verdicts |
| `evaluation/contracts.py`, `profile.py` | Typed result/status structures and metric profile loading/versioning |
| `evaluation/context.py` | Read-only joins to existing manifests/source/map/review evidence and sparse performance annotations |
| `evaluation/kinematics.py` | Exposure, continuous kinematics and comfort measurements |
| `evaluation/capture.py` | Optional native evidence capture/validation only |
| `evaluation/safety.py`, `map_metrics.py` | Collision/clearance/TTC and supported drivable-area/lane measurements |
| `evaluation/tasks.py`, `interactions.py`, `semantics.py` | Validated task outcomes, actual encounters, conditional rule assessment |
| `evaluation/episode.py`, `commands.py` | Compose episode results and existing-CLI handlers |
| `evaluation/reporting.py`, `aggregate.py`, `comparison.py`, `compatibility.py` | Offline run accounting/report rendering, statistical summaries, geographic comparisons, optional benchmark adapters |

Do not move protected validator or SMART producer logic merely to make the tree look symmetrical. Prefer importing a suitable pure helper over extracting it from a fingerprinted producer. The `trace_io` extraction is justified because viewer and evaluator need the same saved-evidence checks; preserve the existing public viewer entrypoints and rendering semantics.

### Result contract

Use one serializable metric-result shape: metric ID/definition version, value(s), units, assessment status/reason, optional criterion outcome, eligible samples/exposure/window, relevant actor/lifetime IDs, and evidence references. Separate:

- Assessment status: `valid`, `unavailable`, `not_applicable`, `undefined`, or `invalid`.
- Criterion outcome: `pass`, `fail`, or `not_assessed`.
- Quantity interpretation, when needed: e.g. finite TTC, overlap now, or no collision predicted within the prediction horizon.

No JSON NaN/Infinity or sentinel numeric defaults. A missing metric is not zero. A valid continuous measurement need not have a pass/fail threshold.

One episode result includes input/result schema versions, input content hashes and producing revision, evaluator/profile hashes, provenance/evidence level, metric results, observed events, task and encounter states, terminal outcome, exposure, and limitations. Performance annotations must bind to the specific input identity and task/review evidence; a filename match is insufficient.

**Proposed CLI:** `geotransfer evaluate episode`, `evaluate run`, `evaluate report`, `evaluate sensitivity`, and `evaluate compare`. These commands consume saved evidence; they do not launch models. `evaluate run` accepts either an existing run ledger or an existing campaign, plus the relevant existing manifest. Do not require the fixed 504-slot inventory for a custom cohort.

## 5. Measurement decisions to carry through implementation

PE00 finalizes these in one checked-in definition/profile document. Change a substantive decision only with a recorded reason, a definition/profile version change, and affected verification; never silently tune after seeing planner outcomes.

### Time, ownership and censoring

- A matrix request for 91 observations covers **90 transitions / 9 seconds**, not 91 transitions. Warmup transitions are 0–9. Primary planner exposure begins with the transition from observation 10 to 11, so a complete controlled rollout provides **80 transitions / 8 seconds**.
- State at observation 10 is the result of warmup. An event already present there is not attributed to the first policy action. Keep warmup diagnostics and initial-condition violations separately visible.
- For each measurement, use recorded timestamps and valid consecutive lifetimes. Do not differentiate across birth, disappearance, re-entry, missing data or protocol handover. Do not use an unrecorded final transition from a legacy producer.
- Terminal observations can retain a collision flag while position/velocity are absent. Detect the event without demanding a present footprint; use separately captured collision evidence if available. Do not impute post-removal zero speed or comfort.
- Duration metrics use valid intervals, not sample count times dt. State-based left-interval estimates must be labeled as sampled approximations with 0.1-second resolution; terminal events can be zero-duration observations. Truncation and unavailable post-event duration remain explicit.
- Source-held traffic remains physically relevant to ego safety. Its replay/hold duration is not learned-traffic behavior exposure. Missing source velocity for replayed VRUs needs an observed-position estimate within the same lifetime, labeled by method; it cannot be assumed to be zero.

### Initial research profile

The following are **provisional research operating choices**, not universal safety/legal limits or official benchmark equivalence:

| Measurement | Initial implementation choice | Sensitivity / boundary |
|---|---|---|
| TTC | Fixed-heading oriented footprints, constant world velocity; continuous first overlap within 5 s | Also 3 s and 8 s; no center-distance/closing-speed shortcut for crossing traffic |
| Near-miss exposure | TTC below 1.5 s and clearance below 0.5 m, reported separately | TTC 1.0/2.0 s; clearance 0.25/1.0 m; imputed dimensions flagged |
| Comfort operating flags | Absolute longitudinal/lateral acceleration above 3 m/s²; longitudinal/total jerk above 5 m/s³ | Scale limits by 0.8 and 1.2; report yaw quantities continuously until justified thresholds are chosen |
| Stationary state | Speed below 0.2 m/s | 0.1/0.3 m/s; report duration, not automatic deadlock |
| Low-progress candidate | Less than 1 m route advancement over an observed 3 s window | Diagnostic candidate only; legitimate waiting and truncated observation cannot become confirmed deadlock |
| Bootstrap summaries | Seed 0, 2,000 recording-cluster resamples, 95% intervals | Too few clusters/degenerate resamples require explicit uncertainty limits; never pretend repeated seeds are independent |

Use raw state-based kinematics as the initial primary measurement. Declare finite-difference stencils and timestamps, body-frame acceleration convention, unwrapped heading handling, longitudinal jerk versus world-vector jerk, and support at endpoints. No silent smoothing, padding, interpolation across gaps, or substitution of commanded acceleration for observed acceleration.

Native collision occurrence is the simulator event channel. Sampled footprint overlap and prospective TTC are separate geometric channels. Neither replaces the other. Native off-road and source-map drivable-area membership are also separate channels. A missing polygon model does not invalidate an observed native off-road event.

## 6. Milestone schedule

IDs deliberately use **PE** to avoid confusion with the completed controller-matrix M0–M9 work.

| Session | Milestone | Dependencies | Main result |
|---|---|---|---|
| PE00 | Baseline, reuse audit and frozen definitions | Specification | Confirmed starting state and implementation decisions |
| PE00.5 | Baseline repair and handoff cleanup | PE00 | Isolated admission regression and reproducible SMART fixture |
| PE01 | Shared saved-evidence reader and contracts | PE00.5 | Historical-compatible offline data boundary |
| PE02 | Exposure, kinematics and initial episode command | PE01 | Useful P0 measurements from existing traces |
| PE03 | Optional native evidence capture | PE01–02 | Collision evidence without changing canonical traces |
| PE04 | Collision, clearance and TTC | PE02–03 | Core safety measurement |
| PE05 | Map context, off-road extent and lane diagnostics | PE01, PE04 | Supported spatial metrics |
| PE06 | Route progress, task outcomes and efficiency | PE02, PE05 | Progress and completion without goal/horizon conflation |
| PE07 | Actual encounter and interaction outcomes | PE04–06 | Current three interaction families plus controls |
| PE08 | Conditional semantic compliance | PE05–07 | Honest rule coverage and supported assessments |
| PE09 | Offline run accounting and failure reports | PE02, PE04–08 | One reproducible evaluation dataset per saved cohort |
| PE10 | Aggregation, uncertainty and sensitivity | PE09 | Defensible rates and robustness evidence |
| PE11 | Integrate evidence into existing viewer | PE09–10 | Inspectable metrics/events in current playback |
| PE12 | Secondary / benchmark adapters | PE09 | P2 diagnostics; separate from P0 readiness |
| PE13 | Geographic comparison and baseline readiness | PE09–10 | Comparable-cohort analysis or explicit baseline block |
| PE14 | Final regression, pilot acceptance and handover | PE00–11; PE13 status recorded | Verified framework and evidence-limited pilot report |

PE12 may be deferred without blocking PE13/PE14 or P0 acceptance. Real geographic evaluation remains data-gated; PE13 must not quietly expand corpus acquisition/conversion into this implementation project. PE14 must distinguish implementation readiness, native verification, P1 coverage, P2 coverage, and geographic evidence readiness.

## PE00 — Confirm baseline, reuse boundaries and definitions

**Goal:** Establish the actual machine/revision baseline and remove implementation ambiguity before production code changes.

**Read:** README; architecture/workflows/migration; controller-matrix acceptance/verification; `docs/plans/step_2/2_protocol_scope_and_matching.md`; all owners in section 2; pinned upstream metric, collision and binding implementations.

**Work:**

1. Record current branch/commit, dirty state, configured assets, Python/dependency/runtime/checkpoint identities, and availability of archived campaign/admission evidence. If HEAD differs, list relevant architectural drift and update this plan's path assumptions rather than resetting the checkout.
2. Identify reusable calculations and annotate every proposed new file with its owner/caller. Specifically inspect geometry helpers, viewer loading checks, frame conventions, source certificates, run ledgers and upstream scoring.
3. Create `docs/performance_evaluation.md` as the **single technical definition document**. Specify metric IDs, units, timing/stencils, assumptions, statuses, task/encounter semantics, collision channels, source evidence scope and operational thresholds from section 5. Keep the high-level specification separate.
4. Define `configs/evaluation/default.toml` profile structure and sparse scenario-annotation requirements; record unknowns as unknown. Do not duplicate recording, source hashes or actor lists already provided by the manifest.
5. Run baseline pytest, `geotransfer doctor`, and available native/migration gates. Preserve outputs under a new run root. For artifact-writing legacy checks, use the documented copied-artifacts procedure. Capture source/binary/review/manifest hashes before checks.

**Constraints:** No metric implementation, asset regeneration, semantic-review fabrication, controller refactor or upstream edit. Missing research assets are a recorded verification block, not a reason to invent substitutes. Synthetic test design can proceed independently.

**Acceptance:** Reuse map and explicit measurement decisions exist; test baseline distinguishes pre-existing failures from new ones; protected-input fingerprints and available legacy trace oracles are recorded. Both source and evaluator evidence policies are understood. Update the shared results log with any data-dependent blocks.

## PE01 — Contracts and one shared saved-evidence reader

**Goal:** Load current and historical saved episodes without simulation or duplicated UI/evaluator checks.

**Touch:** New `evaluation/contracts.py`, `profile.py`, `runtime/trace_io.py`; narrowly refactor `visualization/viewer.py`; focused tests. Do not change live `run_trace.validate_run`, exact comparator rules or admission contracts.

**Work:**

1. Implement the result/status/profile contracts. Resolve profiles through existing config conventions; hash the effective profile and definition version. Serialize through existing `artifacts.write_json` with finite values only.
2. Extract existing saved-file hash and trace/verification coherence checks from the viewer into `trace_io`. Keep viewer signatures and public normalization behavior. Add one raw frame/actor iterator usable by metrics and viewer decoration; do not use owner-label strings or viewer event text as scientific inputs.
3. Support flat legacy expert/SMART traces and nested matrix schema-3 traces. Join lifecycle/ownership by step and stable source ID; retain lifetime generation. Identify the ego using recorded binary index and scene identity, never `actors[0]` or current slot 0.
4. Distinguish unsupported schemas, malformed records, missing optional evidence, valid archived attestations and bare diagnostics. Verify saved input/campaign/attempt hashes where supplied without requiring the original runtime to be installed. Do not falsely upgrade evidence if model or native reproduction is unavailable.
5. Bind results to actual trace and sidecar bytes. A sidecar from the same scene but different controller, startup, horizon or trace must fail coherence checks. Optional absent fields must remain explicitly absent.

**Tests:** Legacy and matrix fixtures; nonzero ego; actor reorder; missing/stale lifetime data; trace tampering; mismatched sidecar; changed current evaluator revision with intact historical attestation; unsupported schema. Existing viewer tests must retain their behavior. Imports must work without Torch, BB or Lanelet2.

**Acceptance:** One reusable loading boundary serves evaluator and existing viewer; historical bytes remain unchanged; no native import is required for data-only operations. A self-contained synthetic bundle demonstrates status serialization and lossless state access.

## PE02 — Exposure, kinematics and a useful episode command

**Goal:** Produce real P0 measurements from existing saved traces before optional native instrumentation.

**Touch:** `evaluation/kinematics.py`, `episode.py`, `commands.py`; one lazy branch in `cli.py`; tests and technical definitions.

**Work:**

1. Implement whole-recorded and primary post-warmup windows, effective-owner segments, present/lifetime masks, transition counts, elapsed exposure, observed distance and censoring. Distinguish pose exposure from event observation coverage.
2. Compute speed, longitudinal/lateral observed acceleration, yaw rate/acceleration, longitudinal jerk and total world-vector jerk with explicit time alignment and units. Exclude unsupported derivative samples, handover artifacts and removed states; include exclusion counts/reasons.
3. Produce maxima, relevant minima, distributions and operating-threshold exposure/flags without treating unknown comfort as a pass. Preserve braking sign; heading unwrap must handle ±π.
4. Add `geotransfer evaluate episode --trace PATH --output NEW_DIR [--profile PATH] [--scene ID_OR_ROOT]`. The scene context is optional for trace-only kinematics; missing map/task data produces unavailable assessments. Emit `episode.json`, a compact `events.json` when events exist, and no simulator activity.
5. Define optional source/replay velocity derivation from observed position differences. Label this separately from recorded native velocity, especially for VRUs; do not leak future source motion to controllers.

**Tests:** Constant velocity; known constant acceleration; constant-speed circular motion; analytically varying acceleration; yaw wrap; irregular/malformed time; insufficient frames; removal; gap/re-entry; handover; 91 observations = 90 transitions and 80 controlled transitions. Test no unobserved legacy last action is counted.

**Constraints:** No simulation calls or metric-specific duplicated loop over model execution. No smoothing or zero-padding by default. Add only implemented metrics to composed output; later capabilities are not fake zero-valued placeholders.

**Acceptance:** The episode CLI works on saved/synthetic traces in an environment without native/model assets, with correct primary exposure and scientifically distinguishable undefined/unavailable results. Existing commands remain lazily importable.

## PE03 — Optional native event-evidence capture

**Goal:** Make omitted native evidence available to future runs while preserving existing actions, states, trace bytes and default CLI behavior.

**Touch:** `evaluation/capture.py`; narrow additions to `execution.py` and `runtime/episode_worker.py`; affected execution/batch tests. Use the existing callback point rather than another stepping loop.

**Work:**

1. Add opt-in `--capture-evaluation` to the existing matrix run path and worker. Default remains off. Capture copied native collision-partner index and impact positions, supported goal/settings facts, and any demonstrably read-only per-agent logs needed for later compatibility diagnostics.
2. Write a separate `evaluation_capture.json` with its own version, exact trace hash, scene/binary/protocol identities, step/actor keys, coordinate-frame metadata and limitations. Preserve `trace.json`, `verification.json`, model provenance and legacy runner behavior. With capture off, do not introduce default fields that break schema-4 resume equality.
3. Capture terminal observations even if the canonical actor pose is absent. Convert positions through a documented native-to-world offset using existing frame conventions; do not combine native goals/impact coordinates with world-frame traces without transformation.
4. Parent-side validation must require and hash the sidecar only when requested. Extend the existing attempt evidence rather than adding an execution ledger. Resume must detect sidecar tampering/missing requested evidence and preserve failed attempts.
5. Before using upstream log reads, inspect their reset/index behavior and prove the chosen read is non-mutating. Do not call resetting aggregate log APIs or use a stale active slot. If safe capture is unavailable, record a limitation instead of patching the native engine.

**Tests:** Capture disabled output unchanged; capture enabled canonical action/state parity; nonzero ego and partner ID mapping; terminal collision after removal; false/stale sidecar rejected; default resume backward compatibility; requested-capture crash/log retention. Run representative fresh single/manifest parity in the configured native environment.

**Acceptance:** New capture can be requested through existing orchestration, is validated as additional evidence, and changes no control semantics. If real parity cannot run, record native acceptance BLOCKED; do not call instrumentation behavior verified from mocks alone.

## PE04 — Collision, footprint clearance and TTC

**Goal:** Implement core safety metrics with explicit event and predictive channels.

**Reuse:** Native collision flags, lifetime/ownership evidence, optional capture, existing oriented-box distance/overlap helpers, and pinned upstream classification functions where their inputs suffice.

**Work:**

1. Detect native collision onsets even when the ego is removed; deduplicate latched event flags by actor/lifetime and transition. Keep warmup events separate. Without complete evidence, collision count is an observed count/lower bound, not a guaranteed exhaustive contact catalog.
2. Report partner/source type when captured, collision geometry/type where supported, and pre-impact relative speed as an identified severity proxy. Never guess the closest actor as the contact partner. At-fault status stays unknown unless the selected heuristic's required evidence exists; distinguish a benchmark heuristic from legal responsibility.
3. Compute simultaneous oriented-footprint clearance over present actors, including replayed VRUs/parked actors. Record nearest actor, time, dimensions and dimension uncertainty. Keep sampled overlap separate from the native collision flag.
4. Implement continuous constant-velocity, fixed-heading oriented-box TTC using interval intersection over separating axes. Report overlap-now, finite future collision, no prediction within horizon, and unavailable/undefined cases separately. Use causal observed velocity or the labeled within-lifetime fallback; do not use actual future trajectories for predictive TTC.
5. Compute TTC/clearance threshold exposure on valid intervals and keep metric coverage visible when some relevant actors lack usable dimensions/velocity. An evaluated subset cannot silently certify the complete scene safe.

**Tests:** Head-on known impact time; parallel and separating vehicles; crossing paths with/without simultaneous collision; rotated footprints; already overlapping; stationary bodies; no counterpart; partial missing actor velocity; imputed VRU size; terminal flag with null pose; latched flags; horizon boundary; actor order and rigid-transform invariance. Independently checked analytical expected values must cover TTC, not just numerical self-consistency.

**Acceptance:** P0 collision occurrence, observed count, clearance and TTC are available with honest coverage. Partner/severity/fault measurements degrade explicitly for old traces. No geometry duplicate or copied upstream evaluator is introduced.

## PE05 — Map context, off-road extent and lane diagnostics

**Goal:** Add rollout spatial assessment without changing conversion or confusing lane alignment with legality.

**Touch:** `evaluation/context.py`, `map_metrics.py`; optional geometry extra if needed; synthetic geometry tests.

**Work:**

1. Read existing manifest/source/map metadata, correct recording-specific map variant, projection, lane boundaries and directed topology through existing owners. Cache only within the evaluation context and key any persisted derivative by input hashes.
2. Build a supported road-area union from actual annotated polygons, preserving holes and connectivity. Exclude bus/access-restricted areas from legal-compliance claims unless access is established; distinguish physical road area from legally permitted lane use. Do not close arbitrary binary edge polylines into invented road polygons or buffer centerlines into ground truth.
3. Report native off-road occurrence independently. For supported map coverage, compute full-footprint outside indicator, observed outside duration, outside area and maximum footprint-boundary excursion. Use robust polygon inclusion/difference rather than corner-only membership.
4. A practical excursion definition is maximum distance of the footprint boundary outside the road union, with perimeter samples spaced at most 0.02 m and a documented ≤0.01 m upper sampling-error bound. Keep the exact polygon outside test separate; do not call a corner-only or symmetric Hausdorff calculation equivalent.
5. Compute heading/lateral deviation only for defensible lane assignments. Keep ambiguity at intersections, contradictory directions, low speed, map coverage limits and unsupported US polygons explicit. A geometric departure from the recorded lane is not automatically wrong-way or illegal.

**Tests:** Adjacent polygon seam; holes; concave road; footprint crossing boundary with center inside; footprint enclosing a hole; reversed OSM way storage; overlapping opposite lanes; map gap versus road departure; missing source map; wrong construction variant; rigid transforms; time censoring after native removal. Existing map/orientation/route tests must stay unchanged.

**Acceptance:** Native off-road and map-based excursion are separately named and supported. Available geometry never silently substitutes for missing legal or map-coverage semantics. No converter/native/admission logic changes.

## PE06 — Route progress, tasks and efficiency

**Goal:** Measure meaningful progress and completion without interpreting every bounded goal/horizon as a full driving task.

**Reuse:** Existing source goal/window metadata, source route certificates, directed maps, scene IDs and goal reporting diagnostics. Source future geometry is permitted for offline reference measurement only.

**Work:**

1. Resolve validated bounded task and reference path from existing scene evidence. Sparse annotations may add endpoint/task meaning, route ambiguity, reviewed criteria and their evidence hashes, but must not copy the entire manifest or fabricate review.
2. Project the rollout onto the reference path using continuity/direction safeguards. Report signed net arc progress and observed traveled distance separately; normalized progress needs a positive validated task span. Preserve raw fractions and identify any clipped display variant. Avoid projection jumps on loops/intersections; unresolved ambiguity stays unavailable.
3. Separate native goal event, bounded-task completion, encounter completion and safe completion. Native goal removal must not erase observed success; a reached goal before the challenge must not count as interaction success. Record planner goal visibility and branch ambiguity.
4. Produce `completed`, `failed`, `unresolved` or `unassessable` with reason. A horizon alone is unresolved unless a validated task explicitly requires completion by that deadline. A measured collision can support a safety failure even if task completion remains unresolved.
5. Add completion time, stationary duration, timeout/truncation cause and low-progress candidates. Confirm stalling/deadlock only with sufficient opportunity-to-proceed evidence; otherwise retain a candidate/unassessed result. Safe completion needs known passing critical criteria, not absence of recorded violations alone.

**Tests:** Forward/reverse travel; loop or intersecting reference path; missing/zero-length route; goal before intended encounter; finite horizon before resolution; legitimate waiting behind stopped leader; observed restart opportunity; native goal terminal; SMART alternative legal branch; missing required safety assessment.

**Acceptance:** Progress and task/efficiency results work on admitted families without changing their stored goals or extending their 91-frame source visibility. No goal-success or horizon shortcuts remain.

## PE07 — Actual encounters and interaction-family outcomes

**Goal:** Determine what challenge the actual rollout presented and resolved, retaining failures that prevent an encounter.

**Initial scope:** `longitudinal_following`, `pedestrian_crossing`, `cyclist_crossing`, and the existing control cases. Preserve source subtypes, especially before/after-ego crossing. Defer roundabout/merge/overtake engines until those families are admitted.

**Work:**

1. Join existing source opportunity, actor IDs, source body-path conflicts and original fidelity certificates. Keep that source evidence fixed across planner conditions. It is not the verdict for a new rollout.
2. Report two separate dimensions: source/reference opportunity and actual realization (`not_reached`, `encountered`, `resolved`, `unresolved`, `indeterminate`, or `not_applicable`), with reasons. A planner's collision/deadlock before the encounter remains a driving outcome.
3. Following: assess current directed-route compatibility, leader-ahead relation, observed following duration, physical gap, moving time headway, and stop/restart resolution where enough observation exists. At standstill, report gap and an undefined speed-normalized headway rather than infinity/zero.
4. Crossing: use a documented reference conflict region/corridor and actual body occupancy/timing. Implement PET only where ordered occupancy/exit/entry can be established; simultaneous occupancy and incomplete exits need their own outcomes. Report clearance/TTC alongside PET; no single proximity cutoff proves yielding correctness.
5. Controls: mark interaction obligations not applicable while retaining core task/safety results. Do not demand unnecessary braking when a cyclist crosses after ego or the actor is no longer relevant.
6. Distinguish traffic-induced non-realization, ego failure, actor coverage loss and insufficient horizon where evidence supports it. Do not infer cooperation, causality or human-like reaction from a trajectory label.

**Tests:** Ego never reaches crossing; traffic disappears; safe ego-first and actor-first passage; simultaneous conflict occupancy; after-ego cyclist; repeated crossing occupancy; stopped leader then restart; wrong leader route; ambiguous encounter; all control subtypes. Test that a real progress failure remains in aggregate inputs.

**Acceptance:** Each admitted family has a documented measurement/assessment rule and coverage statement. A missing explicit source obligation can support geometric timing diagnostics while yielding compliance remains unassessable. No blanket scene exclusion based on failed encounter realization.

## PE08 — Conditional semantic compliance

**Goal:** Support rule assessment only where the actual maneuver and evidence make it meaningful.

**Touch:** `evaluation/semantics.py` and narrowly extended context/definitions; synthetic semantic fixtures. Existing reviews/certificates remain read-only.

**Work:**

1. Implement a capability/applicability assessment for direction, speed limit, stop sign, traffic signal and priority/yielding. Track evidence for the actual route/approach and its valid time range. A source certificate proving a rule outside the original task is not a waiver after the planner deviates onto that approach.
2. Implement wrong-way assessment with directed-lane assignment and temporal evidence, and speed-limit exceedance when a supported limit exists. Low-speed orientation alone is not moving wrong-way distance.
3. Implement the currently supported stop/priority cases using explicit, evidence-bound approach/line/conflict annotations and operational assessment criteria. Keep rule-obligation inference separate from whether a collision occurred. Missing/ambiguous obligation means unassessable, not compliant.
4. For red-light or other checks lacking authoritative dynamic state in the corpus, expose explicit unavailable capability/results and document the input contract. Do not implement a speculative signal reconstruction or claim complete rule coverage. Add a concrete evaluator only if valid data supports it in this milestone.
5. Reuse reviewed resolutions only within their recorded scope; do not rewrite them or infer new legal rules from sign proximity, source driver behavior or lane-center geometry.

**Tests:** Clear and ambiguous direction; supported overspeed; missing speed limit; correct stop approach versus adjacent lane; source-scope rule becomes relevant after deviation; applicable yielding with/without conflict; missing signal timeline; insufficient observation to establish compliance.

**Acceptance:** Per-family/per-rule coverage is explicit. Unsupported rules never silently pass, and any claimed supported evaluator has positive and negative scientific fixtures. Source admission remains unchanged and distinct from closed-loop compliance.

## PE09 — Offline run accounting, event taxonomy and reports

**Goal:** Turn saved runs into an auditable performance dataset without another execution system.

**Touch:** `evaluation/reporting.py`, composition/CLI handlers and tests; reuse run/campaign ledgers and shared reader.

**Work:**

1. Implement `evaluate run --run DIR --manifest PATH --output NEW_DIR` and the mutually exclusive saved `--campaign DIR` alternative. Read schema-4 matrix ledgers, supported legacy schema-2 result indexes, and persisted campaign reports. Snapshot the selected input inventory before calculating results.
2. Preserve all expected entries: not-run, blocked, interrupted, worker/evidence failure and usable trace. For campaigns, default to the saved single view as the primary observation; batch is replication evidence. Reject ambiguous/duplicate logical episodes rather than silently overwriting them.
3. Retain full attempt history. A usable retry can support explicitly labeled diagnostics, but cannot erase an earlier campaign failure or promote a failed slot to PASS. Failures before trace production still receive an accounting row.
4. Apply metric/event composition and non-exclusive failure labels. Preserve first event, subsequent/co-occurring events, actor IDs, severity evidence and limitations. Never label the first event as proven cause.
5. Emit one machine-readable evaluation index, per-episode result/event files, CSV summary and Markdown report under the new output root. `evaluate report` regenerates presentation from saved evaluation results without simulation or metric recomputation. Link raw evidence rather than copying real traces into each result.
6. Separate archive evidence level, metric validity, execution status, task/encounter result and driving outcome in every report. A run's `passed` flag and campaign PASS are integration judgments, never driving success.

**Tests:** Failed worker with no trace; blocked source hold; stale manifest; archived producer revision; tampered files; retry history; duplicate slot; legacy missing metadata; single+batch double-count prevention; incomplete output; output/input overlap; deterministic rerender; missing scene assets with usable trace-only metrics.

**Acceptance:** Every submitted logical entry is accounted for, none is silently dropped for missing metrics, and reports can be regenerated offline. No launch, resume or campaign-freeze mechanism is duplicated.

## PE10 — Aggregation, dependence and threshold sensitivity

**Goal:** Produce interpretable rates/distributions and robustness results while exposing selection/exposure limits.

**Touch:** `evaluation/aggregate.py`, report/sensitivity handlers, focused statistical tests.

**Work:**

1. Aggregate within explicit planner/checkpoint, traffic, startup, metric/profile, horizon and evidence strata. Use per-metric applicable/valid denominators, plus submitted/executed/failed/excluded totals. Do not average rates with incompatible units or quietly pool metric versions.
2. Report episode collision/off-road/completion rates separately from event/exposure rates. Distinguish total exposure ratios from average per-episode ratios. Preserve missingness and eligible cohort intersections for paired comparisons.
3. Use recording/sequence-cluster resampling; retain paired conditions within the same sampled block and weight according to the declared estimand. Missing cluster IDs prevent claimed independent uncertainty. Report cluster/location counts, not just episode count.
4. Implement seeded cluster bootstrap only where meaningful; explicitly flag few clusters, single-cluster cases and degenerate zero/all-event intervals. Never present a zero-width bootstrap interval as certainty. Avoid automatic significance or causal geographic claims.
5. Implement `evaluate sensitivity` using the frozen profile variants. Reuse stored continuous series/event evidence or recompute metrics from immutable saved traces as needed; never rerun simulation just to change a threshold. Align exactly the same episodes and report threshold-dependent assessability changes.
6. Report safety/progress/comfort trade-offs, family/location recurrence, stationary/low-progress outcomes and cross-startup/traffic differences without selecting only successful encounters.

**Tests:** Manual rates with different denominators; all unavailable; no exposure; clustered duplicated scenes; pairing preserved on resampling; single recording; zero events; missing clusters; incompatible versions; profile changes without new simulation; pooled-ratio versus mean-ratio distinction.

**Acceptance:** Aggregation is deterministic, denominators and evidence attrition are visible, repeated executions do not inflate independent sample size, and sensitivity findings are reproducible from saved evidence. Current tiny family strata must remain descriptive where inference is unsupported.

## PE11 — Extend existing playback with evaluation evidence

**Goal:** Let the researcher inspect the metric/event evidence in the current offline viewer.

**Touch:** `visualization/viewer.py`, `campaign_gallery.py`, `viewer.html` only as necessary; reuse shared loading and saved evaluation outputs.

**Work:**

1. Add optional evaluation attachment(s) bound to exact trace hashes, profile/version and scene/protocol. Show concise metric values/statuses, task/encounter outcome, exposure and limitations beside the existing actor/controller playback.
2. Add event selection that seeks to the recorded time, highlights relevant source actors and explains evidence status. Keep raw native events distinct from derived metric events.
3. Preserve current source/converted/legacy/matrix comparison menus, campaign filters, no-source US fallback, aerial registration, keyboard/time controls and standalone HTML behavior. A missing evaluation attachment is normal; the original viewer remains useful.
4. Keep campaign PASS explicitly labeled as integration/parity. Show driving failure independently. Filtered render output must remain isolated as in the current gallery fix; never modify frozen campaign artifacts.
5. Use one saved result source. Do not recompute scientific metrics in JavaScript, copy metrics into traces, add a second dashboard/server or import simulation during playback.

**Tests:** Existing viewer suite; old trace with no metrics; matching/mismatched attachments; early terminal event with absent pose; unavailable metric; conflicting profiles; filtered campaign isolation; escaping/script-injection fixture; self-contained output. On the real environment run the existing browser probe, extended for the metric panel and event seek.

**Acceptance:** A saved result can be traced visually to its episode/event, with no inference or network dependency. Original viewer workflows remain compatible. Browser verification is separately recorded if the browser runtime is unavailable.

## PE12 — Secondary metrics and benchmark compatibility

**Goal:** Complete P2 measurements without replacing P0/P1 outcomes or inventing benchmark equivalence.

**Touch:** `evaluation/compatibility.py`, limited composition/report changes, optional imports and tests.

**Work:**

1. Add timestamp/lifetime-aligned ADE/FDE/reference deviation with explicit reference coverage. Do not time-warp away behavior differences or equate deviation with unsafe behavior.
2. Add All-Core Pass Rate using a frozen named required-criterion set. Missing required criteria produce an indeterminate result and visible denominator; do not shrink the criterion set per scene to manufacture a pass.
3. Inspect the configured pinned upstream metrics/classifier and adapt only supported functions/observations. Import through a narrow optional adapter; do not vendor the upstream evaluator or subclass it into another runner. Reconcile the upstream fault heuristic, nearest-lane metrics, default values and inclusion of warmup explicitly.
4. Provide BehaviorBench component scores/native diagnostics where evidence allows, and a nuPlan-style adapted score only with its documented formula and required inputs. If a canonical composite/semantic requirement cannot be reproduced, label it unavailable/adapted and document differences. Do not invent a scalar merely because the specification names benchmark compatibility.
5. Add focused traffic diagnostics: observed speed/acceleration/gap distributions, visibility/lifetime coverage and actual replay/hold/learned exposure. Reference comparisons need matched context. These establish limited plausibility, not full human realism or a WOSAC score.

**Tests:** Partial reference coverage; missing FDE endpoint; safe alternative trajectory; unknown core criterion; missing upstream installation; missing native logs; warmup mismatch; unsupported fault evidence; score arithmetic against pinned reference cases where applicable.

**Acceptance:** Each secondary output states its provenance, coverage and compatibility level. No synthetic or imputed evidence is presented as an official score. This milestone is optional for P0/PE14 acceptance and may be marked deferred as a whole.

## PE13 — Geographic comparison and baseline-readiness gate

**Goal:** Implement comparison support and establish whether the available cohorts justify geographic conclusions.

**Reuse:** Existing protocol-scope/matching document, manifest metadata, recording/location split, source-only interaction labels, evaluation outputs and PE10 paired/cluster statistics.

**Work:**

1. Implement a readiness audit for source/target provenance, common metric definitions, exposure/protocol, task meaning, interaction coverage, dimensions, source-intent priors, legal semantics and planner information access.
2. Create only a sparse analysis/cohort selection config referencing existing scene manifests and frozen source-derived fields. Define matching strata before looking at outcomes: interaction/subtype, initial speed, route length/curvature, traffic composition/density, horizon and relevant geometry. No new universal corpus manifest or selection based on planner success.
3. Implement `evaluate compare` with comparable per-condition and within-stratum differences, balance/missingness/unmatched tables, clustered uncertainty, and a transparent direction of improvement for each metric. Use stratified standardization or explicit matched groups; avoid a complex learned propensity model for this small dataset.
4. Reject/limit comparisons across incompatible definitions/protocols; preserve unsupported strata rather than forcing matches. Keep SMART/PPO goal-information differences and source-hold priors visible.
5. With only the existing two US diagnostic fixtures, produce a **baseline-not-ready result** and a concrete source-only baseline acquisition/annotation list. Implement/test valid matching on synthetic cohorts, but do not pretend these fixtures complete a geographic benchmark.
6. State an eventual precision target in the technical report, number of independent recording/site units available and additional evidence needed. Do not equate the prospective 50-scene corpus target with sufficient statistical power.

**Tests:** Outcome-blind matching; changed labels after outcome inspection rejected by frozen config hash; unsupported source/target strata; missing clusters; protocol mismatch; matched synthetic gap; same scenes under paired conditions; diagnostic fixtures refused as automatic geographic evidence.

**Acceptance:** The comparison implementation is demonstrable. Scientific geographic acceptance is **separately conditional** on suitable real cohorts; without them record BLOCKED with an actionable input list. Do not silently start downloading/converting dozens of scenes or change existing admission policies in this session.

## PE14 — Final compatibility, real pilot and research handover

**Goal:** Verify the integrated framework, preserve the original project, and produce an honest initial failure-analysis report.

**Work:**

1. Review the entire diff for duplicate mechanisms, dead scaffolding, excessive dependencies, accidental public entrypoints, copied upstream logic and undocumented schema/metric changes. Check all P0/P1 requirements against code and evidence; list P2 status separately.
2. Run the full existing pytest suite plus new metric/reader/statistical/viewer tests. Run `geotransfer check all` and migration conversion/execution against copied artifacts in the configured native environment. Compare protected input hashes and original legacy SMART/hybrid oracles. For archived oracles use appropriate integrity/payload checks; do not demand equality of producing-code provenance after source changes.
3. Demonstrate capture on/off equality and representative fresh single/manifest parity, using existing helpers. Regenerate a full fixed 504-slot campaign only if changes affected scheduler/runtime/controller semantics or existing policy requires it; such semantic changes should normally be out of this project. Do not launch 1,008 fresh episodes just to recompute offline thresholds.
4. Evaluate all available 16-scene expert references and SMART/PPO rollouts under a **predeclared small protocol set**, using saved valid traces where possible. Suggested primary diagnostic comparison: each ego against expert traffic and SMART traffic under immediate startup; compare source-hold only for non-expert traffic as a separate sensitivity. Keep the original admitted SMART/hybrid baseline as a separate condition. Do not merge it with superficially similar matrix pairs.
5. If new rollouts are needed, launch through existing `geotransfer run` with fresh worker isolation. Account for expected runs, crashes and missing checkpoints before scoring; no substitute planner or fabricated evidence. A representative tiny capture/parity smoke gate must pass before the larger pilot starts.
6. Perform expert/reference sanity review, inspect representative failure and non-failure cases in the existing viewer, and report unexplained metric/reference violations. Do not change thresholds merely to make reference executions pass.
7. Produce a pilot report with per-condition metrics, exposures, encounter statuses, failure recurrence, safety/progress/comfort trade-offs, sensitivity and uncertainty limitations. Classify adaptation candidates as hypotheses supported by observed failures, not proven minimal-data solutions.
8. Update README/workflows/architecture and the shared results log with usage, versions, status and remaining work. Keep detailed metric definitions in the one technical document. Report readiness separately for code, native integration, supported interactions/rules, optional benchmark adapters and geographic comparison.

**Acceptance:** Required code checks pass and available real evidence is linked; original input identities and behavior are preserved; optional capture does not alter canonical behavior; reports and playback are reproducible offline. Missing native/data prerequisites leave the relevant acceptance gate BLOCKED, never passed. A blocked gate may coexist with completed implementation work, but the final report must name it.

## Specification coverage map

| Specification requirement | Primary implementation owner | Acceptance evidence |
|---|---|---|
| Collision occurrence, counts, partners and supported severity/fault | PE03–04 | Native sidecar parity plus analytical safety fixtures |
| Off-road occurrence, extent and duration | PE04–05 | Separate native and map channels; footprint/coverage cases |
| TTC, clearance and near-miss exposure | PE04 | Analytical continuous collision timing and missingness cases |
| Progress, tasks, safe completion and efficiency | PE06 | Route/horizon/goal and legitimate-waiting cases |
| Continuous comfort and violations | PE02 | Analytical state-based kinematics and exposure tests |
| Actual encounter and interaction outcomes | PE07 | Current family/subtype cases; non-realization retained |
| Direction, speed and supported rule compliance | PE05, PE08 | Capability matrix and evidence-bound positive/negative cases |
| Metric correctness, reference sanity, thresholds and attribution | PE00–10, PE14 | Versioned definitions, fixtures, sensitivity and real reference review |
| Episode/failure events, provenance and aggregate denominators | PE01, PE09–10 | Saved-evidence integrity and complete cohort accounting |
| Inspectable rollout evidence | PE11 | Existing viewer regressions and browser evidence |
| Benchmark scores, deviation, All-Core Pass and traffic diagnostics | PE12 | Optional adapter/reference arithmetic and honest compatibility labels |
| Geographic comparison and adaptation-priority evidence | PE13–14 | Baseline-readiness result, comparable-cohort tests and evidence-limited report |

## 7. Final readiness checklist and stopping rules

| Area | Required evidence at handover |
|---|---|
| Backward compatibility | Legacy/matrix saved traces and all original CLI/viewer behavior supported; protected inputs unchanged |
| Offline operation | Data-only evaluation/reporting imports and runs without BB/Torch/native inference |
| P0 metrics | Correctness cases, explicit units/windows/coverage, no missing-as-safe behavior |
| Optional capture | Exact original trace/action/state behavior plus validated additional sidecar |
| P1 interaction coverage | Following, pedestrian/cyclist crossing and control rules documented and tested; unsupported obligations explicit |
| Reporting | Every expected run accounted for; versions, denominators, failures and attempt history preserved |
| Uncertainty | Cluster dependence and small/degenerate-sample limits shown |
| Viewer | Existing standalone playback enhanced with hash-bound results, browser check status recorded |
| P2 | Implemented/adapted/unavailable/deferred distinctions visible |
| Geographic evidence | Matched real baseline or explicit baseline-not-ready result; no country-level causal claim from diagnostic fixtures |
| Clean implementation | One owner per responsibility, no duplicate runtimes/manifests/scorers/report stores, no tracked private artifacts |

Stop only the work that depends on a missing prerequisite. Continue independent code/synthetic verification within the milestone. Do not invent source evidence, weaken a gate, reset the repository, or cross into corpus expansion/training to make a blocked milestone look complete. Carry the exact block and required next action into the shared results log and the next session.

## 8. Repository references used for this plan

The repository commit above is the authoritative snapshot for these observations. Relevant entrypoints:

- [Architecture](https://github.com/imendezval/geotransfer-gap-AD/blob/504218cb9ecd7fd64d2952630b9f10f56d80f923/docs/architecture.md)
- [Execution](https://github.com/imendezval/geotransfer-gap-AD/blob/504218cb9ecd7fd64d2952630b9f10f56d80f923/src/geotransfer_gap/execution.py)
- [Episode worker](https://github.com/imendezval/geotransfer-gap-AD/blob/504218cb9ecd7fd64d2952630b9f10f56d80f923/src/geotransfer_gap/runtime/episode_worker.py)
- [Trace evidence and validation](https://github.com/imendezval/geotransfer-gap-AD/blob/504218cb9ecd7fd64d2952630b9f10f56d80f923/src/geotransfer_gap/runtime/run_trace.py)
- [Existing viewer](https://github.com/imendezval/geotransfer-gap-AD/blob/504218cb9ecd7fd64d2952630b9f10f56d80f923/src/geotransfer_gap/visualization/viewer.py)
- [Source protocol and matching requirements](https://github.com/imendezval/geotransfer-gap-AD/blob/504218cb9ecd7fd64d2952630b9f10f56d80f923/docs/plans/step_2/2_protocol_scope_and_matching.md)
- [Pinned upstream metric collection](https://github.com/boschresearch/behavior-bench/blob/805fe04c6977b60c41c92c31f1a5211fbd704f44/pufferlib/evaluation/metrics.py)
- [Pinned upstream collision classifier](https://github.com/boschresearch/behavior-bench/blob/805fe04c6977b60c41c92c31f1a5211fbd704f44/pufferlib/evaluation/collision_classifier.py)
