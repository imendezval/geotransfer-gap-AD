# GeoTransfer performance evaluation definitions

**Definition version:** `1.0.0`
**Initial profile:** [`configs/evaluation/default.toml`](../configs/evaluation/default.toml)
**Scope:** the WHAT requirements remain in [`geotransfer_performance_evaluation_plan.md`](plans/performance_metrics/geotransfer_performance_evaluation_plan.md). This is the single operational definition document for metric meaning, input eligibility, timing, task/encounter interpretation, status semantics, and initial research thresholds.

The thresholds below are versioned research operating choices for this corpus. They are not legal limits, universal safety standards, injury estimates, or official benchmark thresholds. Results must retain the underlying measurements and must not turn them into an arbitrary weighted score.

## 1. Evaluation boundary and evidence

The evaluator reads saved execution artifacts. It does not launch a simulator, alter scenes, create admissions, or change planner inputs. Existing admission, execution, trace, run-ledger, and campaign evidence remains owned by its current producer.

Every episode keeps these facts separate:

1. **Source admission:** the original scene/review decision and the evidence it covered.
2. **Execution validity:** whether the saved attempt or campaign attests to the rollout under its producing protocol.
3. **Metric assessment:** whether a particular measurement has sufficient, valid inputs.
4. **Encounter realization:** whether the intended challenge was presented and reached in this actual rollout.
5. **Task and driving outcome:** whether the validated task was completed, failed, or remained unresolved, plus observed driving events.
6. **Geographic comparability:** whether the cohort supports a German/US comparison under compatible protocols and scenario coverage.

### Evidence levels

- `live_validated`: a newly produced run passed the existing strict parent validation at its producing revision.
- `archived_attested`: saved attempt/campaign records and their referenced hashes are internally coherent and structurally supported. The report records the producer revision and labels this as archived evidence; it does not rerun current code fingerprints or require an old runtime to be installed.
- `trace_only_diagnostic`: the trace is readable and its own integrity checks pass, but there is no sufficient execution attestation. It can support limited trace-derived diagnostics only.
- `invalid`: required hashes, identity, schema, or coherence checks fail. Invalid evidence is retained in accounting, not scored as a pass or silently discarded.

For new execution, retain `runtime.run_trace.validate_run()` and exact trace comparison unchanged. For saved campaigns, do not use current `validate_run()` or `matrix_campaign`'s live freeze check as a gate for reading historical evidence. Verify the saved attempt/campaign hashes and recorded identities at the shared saved-evidence reader. Never rewrite an old producer hash to current HEAD. A readable trace cannot acquire an execution attestation merely by being parsed.

### Metric-result contract

Each serialized metric result records:

- stable `metric_id` and `definition_version`;
- value(s) and units when defined;
- assessment status and reason;
- criterion outcome when the metric has a predeclared criterion;
- eligible samples, eligible duration/exposure, and the evaluated window;
- relevant stable actor IDs and lifetime generations;
- evidence references and material limitations.

Assessment status is one of `valid`, `unavailable`, `not_applicable`, `undefined`, or `invalid`. Criterion outcome is independently `pass`, `fail`, or `not_assessed`. A valid continuous value need not have a pass/fail criterion. A mathematically undefined quantity, missing input, unsupported rule, and invalid record are different cases.

Use JSON `null` for an absent quantity with an explicit status/reason. Do not encode missingness as zero, `-1`, infinity, a safe value, or pass. No JSON NaN/Infinity is allowed. Special quantities such as TTC also carry an interpretation state; an absent finite TTC is not sufficient to infer “no collision.”

### Stable metric IDs and units

Metric IDs below are the version-1 namespace. A result may contain several statistics (for example minimum, maximum, and threshold exposure) under a family ID with explicit statistic names; do not create a new ID for a display label. Preserve IDs when only the display wording changes. A substantive meaning or eligibility change requires a new definition/profile version.

| Metric ID | Value/unit and scope |
|---|---|
| `exposure.recorded_duration` | seconds of valid recorded observation interval |
| `exposure.controlled_duration` | seconds of valid post-warmup, policy-controlled interval |
| `exposure.pose_duration` | seconds with supported present ego pose; report full and primary windows |
| `trajectory.observed_distance` | metres travelled by valid consecutive ego-centre displacements |
| `trajectory.route_progress` | signed metres along a validated task reference route |
| `trajectory.normalized_route_progress` | dimensionless fraction, only for a validated positive route span and task bounds |
| `trajectory.speed` | m/s at observations |
| `trajectory.acceleration_longitudinal`, `trajectory.acceleration_lateral` | m/s² on supported transition intervals |
| `trajectory.yaw_rate`, `trajectory.yaw_acceleration` | rad/s and rad/s² on their supported interval/midpoint stencils |
| `trajectory.jerk_longitudinal`, `trajectory.jerk_world_norm` | m/s³ on adjacent supported transition stencils |
| `safety.native_vehicle_collision_onsets` | observed count of distinct supported ego/actor-lifetime collision onsets; include lower-bound flag when partner coverage is incomplete |
| `safety.native_offroad_onsets` | observed native road-edge event count |
| `safety.footprint_clearance` | minimum oriented-footprint gap in metres, with pair/time and dimension support |
| `safety.footprint_overlap` | count/duration of sampled geometric overlap, separate from native collision |
| `safety.ttc` | seconds and interpretation over the declared prediction horizon, with eligible-pair and scene-coverage counts |
| `safety.near_miss_exposure` | seconds below the configured TTC threshold and below the clearance threshold, reported separately |
| `safety.map_footprint_outside` | supported footprint outside area in m², duration in seconds, and maximum excursion in metres; unavailable without supported polygon coverage |
| `comfort.threshold_exposure` | supported seconds and samples exceeding each configured acceleration/jerk flag, separately named by quantity |
| `efficiency.stationary_duration` | sampled-approximation seconds below the configured speed threshold |
| `efficiency.low_progress_candidate` | boolean candidate plus assessed window and metres of route advancement; never a confirmed deadlock by itself |
| `task.outcome`, `task.safe_completion` | categorical outcome/status contracts, not numeric scores |
| `encounter.realization`, `interaction.outcome` | categorical state/reason per validated intended encounter/family |
| `semantics.rule_assessment` | categorical applicable/assessment/outcome with rule-specific evidence references |

Every aggregate retains the corresponding episode IDs, eligible numerator/denominator and exposure; a rate never replaces its counts or assessor status. The namespace lists the initial core families, not permission to emit an unimplemented field as a placeholder.

## 2. Trace timing, exposure, and attribution

Current matrix traces contain pre-action **observations**. The transition, when present, advances from observation `i` to `i+1` and is recorded on observation `i` as `transition_applied`. Do not interpret `requested_observation_frames` as a transition count.

For the standard 91-observation rollout:

- observations are indexed `0..90`;
- there are at most 90 transitions and 9.0 recorded seconds at 10 Hz;
- warmup transitions are `0→1` through `9→10` (10 transitions / 1.0 s);
- the primary controlled window starts with the transition from observation 10 to 11 and ends at 89 to 90 (80 transitions / 8.0 s when complete);
- observation 10 is the post-warmup initial state, before the first policy action. A condition already present there is a warmup/initial-condition event, not a consequence of the first policy action.

Report the full recorded window and the primary controlled window separately. Also retain warmup diagnostics, effective-owner segments, applied transitions, observed pose exposure, event-observation coverage, elapsed time, and observed distance. Exposure is the sum of valid observed intervals, not sample count times a nominal time step. A source-held actor remains physically relevant to ego collision/clearance metrics, but its replay/hold interval is not learned-traffic behavior exposure.

Use recorded `time_s` values when available. Current `runtime.session.frame()` stores `time_s = step × 0.1`; for supported older traces with only a producer-guaranteed 10 Hz step index, derive the time from that producer contract and identify the timebase as inferred. Otherwise time-dependent quantities are unavailable. Never create an unrecorded final transition from a legacy trace.

An event observed at observation `j` is assigned to the interval ending at `j` only when that interval is recorded as applied and its controller/ownership is known. An event already present at observation 10 stays in the warmup/initial-condition channel. Event timing is an observation, not proof of root cause. A first violation is not automatically the cause of later events.

Only use intervals with finite, increasing timestamps and consecutive valid observations of the same source actor and lifetime. Split exposure at births, disappearance, source gaps/re-entry, missing samples, and controller/startup handovers. Do not differentiate through those boundaries, interpolate across them, or replace removed-state values with zero. Terminal flags may establish an event even when the terminal pose/velocity is absent; they cannot establish post-removal comfort or duration.

For state-based duration thresholds, use left-interval estimates: a supported state at observation `i` represents the interval `i→i+1`, at the trace's sampling resolution. Label such durations as sampled approximations. A terminal-only threshold event is a zero-duration observation unless another source establishes duration. Missing post-event time is censored, not assumed safe.

## 3. Kinematics and comfort

The primary ego kinematics use raw observed world-coordinate state and recorded timestamps. They are descriptive measurements of the realized trajectory, not commanded-action or controller-request values.

For a present actor with recorded world velocity `(vx, vy)` at observations `i` and `i+1`, define `dt = t[i+1] - t[i]` and world acceleration on that interval as:

`a_world[i] = (v[i+1] - v[i]) / dt`.

Unwrap heading only within a continuous lifetime. Let `theta_mid` be the arithmetic midpoint of the two unwrapped endpoint headings. The longitudinal unit vector is `(cos(theta_mid), sin(theta_mid))`; the left lateral unit vector is `(-sin(theta_mid), cos(theta_mid))`. Longitudinal acceleration is the projection of `a_world` onto the longitudinal vector; lateral acceleration is its projection onto the left lateral vector. Negative longitudinal acceleration retains its braking sign.

Speed is `hypot(vx, vy)` at an observation. Yaw rate is the unwrapped heading difference divided by `dt`, assigned to the transition midpoint. Yaw acceleration is the difference between adjacent supported yaw-rate intervals divided by the difference between their midpoint times. Longitudinal jerk is the corresponding difference of adjacent longitudinal-acceleration intervals. Total jerk is the norm of the difference between adjacent world-acceleration vectors divided by their midpoint-time separation. These are finite differences; no smoothing, endpoint padding, commanded acceleration, or extrapolation is used.

Acceleration and yaw-rate support one valid transition. Yaw acceleration and jerk need two adjacent valid transitions. Every stencil must remain within one lifetime and one effective-owner segment; the derivative spanning a handover is excluded. Report sample counts and exclusions for each quantity. If a fallback velocity is required for a replayed/source actor, use only a backward position difference within the same observed lifetime and label it `observed_position_backward_difference`. Do not assume missing source velocity is zero or use future source motion as predictive TTC input.

The initial comfort operating flags are:

- `abs(longitudinal_acceleration) > 3 m/s²`;
- `abs(lateral_acceleration) > 3 m/s²`;
- `abs(longitudinal_jerk) > 5 m/s³`;
- `total_world_jerk > 5 m/s³`.

Report continuous longitudinal/lateral acceleration, yaw rate, yaw acceleration, both jerk measures, supported threshold-exceedance samples, and time exposure. Yaw quantities remain continuous diagnostics without an initial threshold. Comfort flags are not a substitute for route progress, collision safety, or task outcome.

These values are transparent initial screening cut points, not estimated vehicle-specific comfort boundaries. Scaling all four limits by 0.8 and 1.2 tests whether a conclusion depends on a modest threshold change. Keeping yaw continuous avoids adding another criterion without a reviewed basis.

## 4. Collision, clearance, TTC, and road boundary

### Native event channel

The pinned Drive binding defines `VEHICLE_COLLISION = 1` and `OFFROAD = 2`. A vehicle-collision event is read from the native collision-state channel; native off-road is a separate event. In the native implementation, a vehicle collision takes precedence over the road-edge state, so one observed native classification cannot establish that simultaneous geometric conditions did not occur.

Count a collision onset once per ego/actor lifetime pair and transition, even when a flag remains latched or the terminal pose is null. Report any-collision independently of responsibility. If the old trace only establishes an event flag, report the observed count as a lower bound on distinct contacts where partner identity is unavailable. Use a captured native partner index only when it is bound to the exact trace and mapped through the recorded binary index/stable actor identity. Never name the nearest actor as the collision partner.

The binding exposes partner index and collision positions, but current canonical `session.frame()` traces do not record them. A later optional evidence-capture sidecar may preserve these fields. Old traces must degrade explicitly. Relative pre-impact speed is a severity proxy only when both actors and collision timing/identity are supported. It is not an injury estimate. Fault/responsibility remains unknown without the required evidence; any adopted benchmark heuristic is labeled as a heuristic, not legal responsibility.

Native off-road means the native road-edge intersection event. It is not a full drivable-polygon membership calculation. Report it separately from sampled oriented-footprint membership in a supported physical-road polygon union. The latter preserves holes and connectivity and requires actual annotated road polygons. Do not close arbitrary road-edge polylines into invented surfaces or buffer lane centerlines into ground truth. Keep physical road area separate from legal access.

Reuse the existing Lanelet2 map selection/projection/topology and pure geometry helpers first. If those APIs cannot supply robust polygon union/difference, PE05 may add a single optional `evaluation-geometry` extra containing Shapely. That extra must remain unnecessary for imports and commands unrelated to map metrics.

### Sampled geometry and predictive TTC

At each observation, compute footprint-to-footprint separation between simultaneous present actors using their oriented rectangles and supported dimensions. Clearance is the minimum eligible pair gap in metres, with actor/lifetime, time, and dimension source/uncertainty. An imputed dimension is flagged. Sampled geometric overlap, native collision, and TTC are distinct channels.

Predictive TTC uses fixed-heading oriented rectangles moving at constant observed world velocity. Compute the continuous first overlap using separating-axis time intervals over both rectangles' axes. Use a 5 s primary prediction horizon; retain 3 s and 8 s sensitivity variants. Do not use center-distance/closing-speed shortcuts for crossing traffic or actual future trajectories for prediction.

TTC quantity interpretation is one of:

- `overlap_now` (time-to-overlap is 0 s);
- `finite_future_overlap` (a supported first overlap exists within the horizon);
- `no_overlap_predicted_within_horizon` (all required counterpart coverage is complete for that claim);
- `undefined` (the quantity is not mathematically defined for the observed configuration);
- `unavailable` (required state, velocity, dimensions, or actor coverage is missing).

The minimum TTC over an eligible subset is not a full-scene safety certificate when other relevant actors lack usable data. Report coverage and eligible pair counts. Near-miss exposure below the TTC threshold and below the clearance threshold are separate measures, accumulated only over supported intervals.

The primary near-miss thresholds are TTC `< 1.5 s` and footprint clearance `< 0.5 m`, reported separately. Sensitivity values are TTC `< 1.0/2.0 s` and clearance `< 0.25/1.0 m`. These are initial screening cut points from the reviewed implementation plan; the bracketing variants expose threshold dependence, and separate channels prevent a predicted future conflict from being conflated with a currently small physical gap. TTC is a model-based conflict diagnostic, not a finding of fault or interaction failure by itself.

The 5 s prediction horizon is a finite, readable near-term window for the fixed-velocity model; 3 s and 8 s variants show horizon dependence. It is not borrowed as an upstream planner horizon or treated as a safety guarantee.

## 5. Route progress, task, interaction, and efficiency

Distance travelled is the sum of valid consecutive ego centre displacements. Route progress is the signed net arc-length advancement along a validated reference route. These are separate values. Normalized route progress is available only when the task has a validated positive route span and unambiguous task boundaries. Keep the raw fraction; any clipped display value is supplemental. Do not choose a route projection that maximizes progress at a loop or branch.

Source/reference route and goal evidence is offline-only and must never enter SMART/PPO observations. Record whether the planner could observe a navigation goal: the inspected SMART path does not receive the simulator navigation goal, while PPO does. A goal miss by SMART at an ambiguous branch cannot alone establish an unfamiliar-local-rule explanation.

Keep the native goal event, bounded-task completion, interaction completion, safe completion, and terminal reason separate. Use task outcomes `completed`, `failed`, `unresolved`, or `unassessable`, with a reason. A horizon/recording end is `unresolved` unless an independently validated task definition imposes that deadline. An observed collision can establish a safety failure while task completion remains unresolved. A goal event or actor removal does not erase prior observed completion evidence; a goal reached before the intended encounter is not encounter completion.

`safe_completion_core_v1` requires a validated task completion and known passing results for all applicable, predesignated critical criteria: complete native vehicle-collision observation; complete native off-road observation; supported map-footprint boundary criteria when explicitly applicable; and all validated must-pass interaction/rule criteria designated for that task. TTC/clearance remain risk diagnostics unless a reviewed family-specific criterion explicitly makes one critical. Any required failure makes safe completion fail. Missing required evidence leaves it `not_assessed`; absence of a recorded violation is not a pass. Report task success and safe-completion denominators independently.

Encounter opportunity comes from validated source/task evidence; actual realization is assessed from the rollout. Use `not_reached`, `encountered`, `resolved`, `unresolved`, `indeterminate`, or `not_applicable`, with reasons. A non-realized encounter is not an invalid scene and is not a successful interaction. Retain any planner progress/task failure that prevented reaching it. Source fidelity evidence is fixed context, not the new controller's encounter verdict.

Initial admitted interaction coverage is longitudinal following, pedestrian crossing, cyclist crossing, and control scenes. Preserve source subtypes, especially a cyclist crossing after ego passage; it is not automatically a yielding/braking obligation. For following, use supported same-route leader relation, observed following duration, physical gap, moving headway, and stop/restart evidence. Headway at standstill is `undefined`; retain physical gap. For crossings, use validated conflict-region/corridor evidence and actual footprint occupancy. Compute PET only when entry/exit order is observed; simultaneous occupancy, repeated occupancy, incomplete exits, or insufficient horizon receive distinct outcomes. Keep TTC/clearance alongside PET. A yielding criterion needs an explicit supported obligation; proximity alone does not establish it. Controls retain core metrics with interaction obligations not applicable.

Stationary state is speed `< 0.2 m/s`; report its duration independently. Sensitivity is `< 0.1/0.3 m/s`. This labels low-speed occupancy at the corpus's 10 Hz sampling resolution; it is not a stall definition. Less than 1 m of route advancement over an observed 3 s window is a low-progress **candidate** only. The finite window makes a candidate inspectable while requiring sustained low progress; the threshold does not establish that progress was possible. Do not call legitimate yielding/waiting deadlock. Confirmed stalling/deadlock needs sufficient evidence that progress was possible and appropriate; otherwise retain a candidate/unassessed state. Keep completion time, stationary duration, timeout, truncation, and other terminal reasons separate.

## 6. Conditional semantics, aggregation, and geography

Rule metrics are applicable only when the actual route/approach, relevant time interval, and rule evidence are supported. Wrong-way distance/duration needs a directed-lane assignment and moving ego; low-speed heading alone is not wrong-way travel. Speed-limit exceedance needs a supported applicable limit. Stop/yield assessment needs an evidence-bound approach/line/conflict criterion. Red-light compliance is unavailable without authoritative signal state over the observed interval. A source certificate proves only its recorded source scope; it is not a waiver after the rollout deviates. Missing or ambiguous semantics are unassessable, not compliant. Lane-centre/heading alignment is diagnostic unless a maneuver-aware reviewed criterion says otherwise.

Aggregates expose submitted, executed, failed, excluded, valid, applicable, assessable, and metric-specific denominators. Report episode rates separately from event/exposure rates; state the unit, exposure, missingness, recording and location counts. Do not pool metric/profile/protocol versions. Bootstrap by independent recording/sequence cluster with paired conditions kept together. The initial operating bootstrap is seed 0, 2,000 cluster resamples, 95% intervals. The fixed seed/resample count makes reports reproducible, while recording/sequence clustering respects shared source dependence. With one/few clusters, missing cluster IDs, or degenerate all-zero/all-event resamples, show the uncertainty limitation; a zero-width interval is not certainty. Do not count repeated seeds/overlapping windows as new independent geography.

German-only output is failure characterization on the tested German corpus. The two US diagnostic fixtures do not constitute a matched geographic baseline, even where exact source JSON now qualifies their source-hold protocol. Geographic degradation remains unestablished until cohorts have compatible definitions, task/interaction coverage, exposure, traffic/startup protocol, observation limits, and relevant geometry/traffic composition. If those conditions fail, retain descriptive differences or hypotheses and state the baseline-not-ready reason.

## 7. Secondary metrics and compatibility boundary

ADE/FDE/reference deviation, All-Core Pass Rate, BehaviorBench/nuPlan-style composites, and traffic-realism summaries are P2 outputs. Deviation from an expert/reference path is descriptive, not automatically unsafe or incorrect. All-Core Pass Rate uses one frozen criterion set; a missing required criterion makes the result indeterminate rather than shrinking the set. Any benchmark output states whether it is faithful, adapted, unavailable, or deferred and lists coverage/differences. Do not adopt upstream default sentinels or missing-to-zero behavior, and do not call an adapted composite official. Individual P0/P1 metrics remain visible.

The pinned upstream evaluator consumes live environment/log data. Its `MapMetrics` defaults include `-1`/infinity sentinels and zero defaults; its collision classifier uses an approach/stopped/lane-drift heuristic and its fallback partner finder chooses a nearest projected entity. Those behaviors are not GeoTransfer evidence or ground truth. Any future adapter must be narrow, lazy, and tested against supported inputs; do not vendor or recreate the evaluator.

## 8. Sparse annotation contract

Store only decisions that cannot be derived safely from existing source, map, review, and admission evidence. A per-scene annotation, if needed, is `configs/evaluation/annotations/<scene_id>.json` with this contract:

| Field | Contract |
|---|---|
| `schema_version` | Integer `1`; unknown versions are unsupported, not guessed. |
| `scene_id` | Must equal the manifest-selected scene ID. |
| `manifest_sha256` | Exact SHA-256 of the portable manifest used for scene selection. |
| `claims` | Array of sparse claim objects; empty means no added claim, not an implicit pass. |
| `claims[].claim_id` | Stable unique identifier within the annotation. |
| `claims[].claim_type` | `task_definition`, `interaction_criterion`, `rule_applicability`, or `physical_map_coverage`. |
| `claims[].scope` | Specific claim scope and selectors into existing owner data; do not embed a duplicate actor/map/route inventory. |
| `claims[].decision_status` | `supported`, `explicitly_unassessable`, or `rejected`; ambiguous or unknown evidence uses `explicitly_unassessable` with a reason. |
| `claims[].decision` | Explicit typed value/criterion when supported; `null` for an unassessable/rejected decision, with `reason` present. |
| `claims[].evidence_refs[]` | Portable relative owner path, SHA-256 of exact bytes, and selector (for example JSON Pointer); at least one is required for `supported`. |
| `claims[].review` | `status` is `reviewed`, `unreviewed`, or `not_required`; a human-reviewed criterion must be `reviewed` and cite a hash-bound review record. |

Malformed fields, unsupported schemas, or mismatched manifest/evidence hashes make the affected annotation/claim `invalid`. An absent annotation or unreviewed required criterion is `unavailable`; an explicit unassessable decision remains recorded as such. A claim with all identities/hashes verified and a supported decision may be used only within its declared scope. Do not copy recording IDs, source hashes, full actor lists, map geometry, or full task routes already owned by the manifest/source/map evidence. Point to the existing owner and hash it. Filename agreement alone is insufficient. PE00 creates no scene annotations and makes no new semantic review decisions.

## Version changes

Change a substantive metric meaning, stencil, eligibility rule, threshold, or criterion set only with a recorded reason, a new definition/profile version, and affected known-case/sensitivity verification. Store both the definition version and effective parsed profile hash in every result. Historical results remain bound to their original versions.

## Offline reader and effective profile identity

PE01 exposes `runtime.trace_io.load_saved_trace()` for saved episode data. It checks the trace and sidecar identities, observation structure and available hash bindings. A valid passed parent attempt or a selected passing campaign slot can establish `archived_attested`. The caller supplies the campaign revision and scene identities from saved campaign records. Older standalone attempts may have no recorded Git revision. When the caller has local input files, it can supply them by input name for hash checks. The reader does not need the original runtime, planner or dataset. Parsing failures, unsupported schemas and contradictory evidence raise `SavedEvidenceError` or its `UnsupportedTraceSchema` subtype. These should enter downstream accounting as invalid evidence.

A coherent trace without a parent attestation supports `trace_only_diagnostic`. Hashes alone establish byte integrity. The scientific frame iterator joins verification metadata only when the verification bytes are paired with the trace by recorded hashes or name the exact trace hash. The viewer keeps its historical display behavior for a structurally coherent sidecar. Missing legacy metadata stays absent or null. `live_validated` remains a status supplied by the existing execution path, outside this reader.

`evaluation.profile.load_profile()` reads a complete TOML profile. Its raw SHA-256 identifies the file bytes. Its effective SHA-256 identifies the validated values, including profile ID and definition version. Schema-defined real numbers are normalized to floats. The hash input is UTF-8 JSON with lexically sorted keys, compact separators, unchanged array order, no newline and no nonfinite values. TOML comments, whitespace, key order and an integer spelling of a real field have no effect on the effective hash. The loader rejects unsupported versions, contradictory warmup and window settings, and sensitivity arrays that disagree with the primary thresholds. Version 1 fixes time and algorithm choices. Customized operating thresholds must remain within this contract.
