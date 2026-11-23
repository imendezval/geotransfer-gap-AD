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
| `trajectory.lane_lateral_offset` | signed metres from the assigned source-mapped directed lane centreline; diagnostic only |
| `trajectory.lane_heading_deviation` | wrapped radians from the assigned source-mapped directed lane tangent; diagnostic only |
| `comfort.threshold_exposure` | supported seconds and samples exceeding each configured acceleration/jerk flag, separately named by quantity |
| `efficiency.stationary_duration` | sampled-approximation seconds below the configured speed threshold |
| `efficiency.low_progress_candidate` | boolean candidate plus assessed window and metres of route advancement; never a confirmed deadlock by itself |
| `efficiency.completion_time` | seconds from first observation and, when after warmup, from the primary policy start |
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

PE02 episode results report each continuous kinematic family as a finite distribution summary plus aligned observed samples. Each sample carries its trace step, recorded or inferred time, support stencil, lifetime, effective owner, and the exact left-interval or midpoint-separation exposure used for threshold-duration flags. Threshold duration sums each exceeded sample's own support; it is not a sample fraction multiplied by total duration. Missing samples stay null with an explicit assessment status. The four acceleration/jerk thresholds are operating flags, so results record exceedance counts and sampled duration without assigning a pass/fail verdict.

For legacy schema-2 expert/SMART traces, adjacent recorded observations support descriptive finite differences. When all timestamps are absent, their producer-guaranteed 10 Hz step index supplies an explicitly inferred timebase. No terminal observation creates a following interval. Because these traces do not record per-transition application or effective ownership, controlled duration and action attribution remain unavailable even when descriptive kinematics are measurable. Matrix intervals use the effective owner recorded at the interval's starting observation; second-difference stencils are excluded when their two adjacent intervals have different known owners. A source-validity change, lifetime-generation change, absence, or missing observation breaks the affected interval. When historical lifetime metadata is absent, only contiguous observations of the stable source ID are joined and the result records that limitation.

The PE02 event file contains compact observed ego collision-state, off-road-state, goal, and terminal-status records when those channels are present. It records initial active flags as left-censored observations, reports missing channel coverage separately, and assigns a controlled-transition label only when the prior flag is known clear and the preceding trace row records an applied ego-owned transition. It does not infer causal responsibility. A terminal native flag remains observable if the terminal pose is absent; it does not add post-removal pose, duration, or comfort support.

## 4. Collision, clearance, TTC, and road boundary

### Native event channel

The pinned Drive binding defines `VEHICLE_COLLISION = 1` and `OFFROAD = 2`. A vehicle-collision event is read from the native collision-state channel; native off-road is a separate event. In the native implementation, a vehicle collision takes precedence over the road-edge state, so one observed native classification cannot establish that simultaneous geometric conditions did not occur.

Count a collision onset once per ego/actor lifetime pair and transition, even when a flag remains latched or the terminal pose is null. Report any-collision independently of responsibility. If the old trace only establishes an event flag, report the observed count as a lower bound on distinct contacts where partner identity is unavailable. Use a captured native partner index only when it is bound to the exact trace and mapped through the recorded binary index/stable actor identity. Never name the nearest actor as the collision partner.

The binding exposes partner index and collision positions, but canonical `session.frame()` traces do not record them. PE03's optional capture sidecar preserves these fields only when it is bound to the exact trace. Old traces and unbound capture files degrade explicitly. Relative pre-impact speed is reported only from the observation before an identified onset, using supported same-lifetime motion, and is a severity proxy rather than an injury estimate. Detector centers are not exact physical impact points. Fault/responsibility remains unknown; no legal or upstream fault classifier is applied by PE04.

Native off-road means the native road-edge intersection event. It is not a full drivable-polygon membership calculation. Report it separately from sampled oriented-footprint membership in a supported physical-road polygon union. The latter preserves holes and connectivity and requires actual annotated road polygons. Do not close arbitrary road-edge polylines into invented surfaces or buffer lane centerlines into ground truth. Keep physical road area separate from legal access.

Reuse the existing Lanelet2 map selection/projection/topology and pure geometry helpers first. If those APIs cannot supply robust polygon union/difference, PE05 may add a single optional `evaluation-geometry` extra containing Shapely. That extra must remain unnecessary for imports and commands unrelated to map metrics.

### PE05 mapped-road and lane diagnostics

The PE05 map context is usable only when the saved scene root and binary match one row of the current portable scene manifest, the source recording metadata selects the same location, the provider map selector chooses the exact construction/standard OSM variant, the OSM bytes match that manifest row's `source_map_sha256`, and the scene's existing map-semantics certificate binds the same binary and OSM hashes. Contradictions make map context invalid; absent files or optional geometry support make it unavailable. No scene certificate or source review is regenerated.

The physical surface is the exact union of source OSM `lanelet` relations tagged `subtype=road`, `subtype=bus_lane`, or `subtype=crosswalk`, assembled from their left/right ways after the existing `orient_road_boundaries()` owner and `lanelet_polygon()` helper. Bus-lane inclusion describes physical pavement; legal access remains unassessed. The known map-surface coverage used to distinguish an unrepresented map gap is the union of those polygons plus explicit `walkway` lanelet polygons. Each geometric assessment requires the ego centre to lie in that mapped-surface coverage; otherwise the observation is unavailable and contributes no outside-area value. This coverage is only the mapped Lanelet surface set and does not attest that all paved or drivable space is mapped.

At a supported observation, `safety.map_footprint_outside` builds the ego rectangle using the same audited corner convention as PE04. Outside area is the exact area of `footprint.difference(road_union)`; an observation is outside when that area exceeds `1e-9 m²`. This preserves union seams, concavities and holes, including a hole enclosed by the footprint. Maximum excursion is the greatest distance to the road union among points on the footprint boundary that are outside it. The closed exterior and any interior rings are sampled along each segment at spacing no greater than `0.02 m`. Since distance to a set is 1-Lipschitz and every boundary point is within `0.01 m` of a sample, the sampled maximum can underestimate the exact boundary maximum by at most `0.01 m`. This is not a symmetric Hausdorff distance. Native `safety.native_offroad_onsets` remains an independent road-edge event channel.

Outside duration uses left-observation sampled state over consecutive present ego poses with valid increasing time, stable lifetime/source-validity, and no explicitly unapplied transition. The terminal observation has no outgoing interval. If the actor is removed or map coverage ends, the duration is censored; no post-terminal footprint or duration is imputed. Missing dimensions/heading, unsupported coverage, and malformed footprints remain unavailable or invalid per observation. When the selected window has no supported intervals, duration is `null` with an explicit unavailable status, not zero.

Lane centre lines and directed successors come from existing `maps.lanelet.make_roads()`. Lane assignment first uses nearest mapped lane geometry within half that lane's mapped width plus `1 m`; a distance tie within `0.25 m` is resolved only by a unique directed heading fit (at least `0.1 rad` better than the next candidate). Overlapping candidates with tangents within `0.05 rad` and signed offsets within `0.1 m` are treated as one diagnostic assignment and retain all lanelet IDs; contradictory direction candidates remain undefined. At speed `<=0.2 m/s`, heading cannot resolve an otherwise ambiguous assignment. Missing speed or heading is unavailable, while an observed low-speed heading is undefined. The lateral offset sign is positive to the directed lane's left. Heading deviation is the wrapped ego heading minus the local directed tangent, including possible values near `π`; this does not itself classify wrong-way travel. Neither lane metric establishes legality, access permission, or a rule violation.

### Sampled geometry and predictive TTC

At each observation, compute footprint-to-footprint separation between simultaneous present actors using their oriented rectangles and supported dimensions. Clearance is the minimum eligible pair gap in metres, with actor/lifetime, time, and dimension source/uncertainty. An imputed dimension is flagged. Sampled geometric overlap, native collision, and TTC are distinct channels.

PE04 reuses the repository's pure oriented-box overlap and distance helpers. It includes every simultaneous present actor, including parked and source-held actors. Direct positive length/width values are used as recorded. If one is missing, PE04 may fill only that dimension from constant positive values observed for the same source actor and verified lifetime generation; the result identifies the `same_actor_lifetime_constant_observations` source and the imputed fields. It uses no type-level or population default. Historical rows without a verified lifetime cannot borrow dimensions across observations. A supplied nonpositive or nonfinite dimension makes the affected geometry assessment `invalid`, while absent dimensions leave coverage incomplete or unavailable.

Predictive TTC uses fixed-heading oriented rectangles moving at constant observed world velocity. Compute the continuous first overlap using separating-axis time intervals over both rectangles' axes. Use a 5 s primary prediction horizon; retain 3 s and 8 s sensitivity variants. Do not use center-distance/closing-speed shortcuts for crossing traffic or actual future trajectories for prediction.

For a source-valid non-ego actor only, a missing velocity may use the backward position difference from the immediately preceding observation when both observations are present, have the same verified lifetime, retain source-valid status, and have a valid positive time interval. The result labels this method `observed_position_backward_difference_same_lifetime`. Ego velocity is never imputed, and a known/unknown generation boundary or explicitly unapplied transition blocks this fallback. The SAT solver intersects each rectangle-axis time interval; touching counts as overlap, and a first contact exactly at the horizon is included. Parallel, stationary, or separating configurations with complete data can yield `no_overlap_predicted_within_horizon`.

TTC quantity interpretation is one of:

- `overlap_now` (time-to-overlap is 0 s);
- `finite_future_overlap` (a supported first overlap exists within the horizon);
- `no_overlap_predicted_within_horizon` (all required counterpart coverage is complete for that claim);
- `undefined` (the quantity is not mathematically defined for the observed configuration);
- `unavailable` (required state, velocity, dimensions, or actor coverage is missing).

The minimum TTC over an eligible subset is not a full-scene safety certificate when other relevant actors lack usable data. Report expected and eligible pair samples plus missing-motion/dimension reasons. A finite prediction from a supported subset remains reportable with incomplete coverage; absence of a finite prediction is labeled partial rather than `no_overlap_predicted_within_horizon`. Near-miss exposure below the TTC threshold and below the clearance threshold are separate measures, accumulated from supported left-observation states over valid, same-lifetime intervals. Such durations are sampled approximations. A positive finding over a partial scene is a lower bound; a window-wide zero is reported only when all relevant pair coverage is complete. Missing counterpart evidence never becomes a zero or a safe result.

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

### PE06 task and route measurement choices

The bounded source task is resolved from a hash-bound `evaluation_contract_*.json`, its exact converted source-scene JSON, the scene validation record, the selected portable manifest row, and the recorded binary identity. The default bounds are the first valid source ego observation through the contract's `goal_sample`; the source route certificate must bind that same converted scene and binary and the exact selected source map before it supports route progress. Admission reports are not used to reconstruct task semantics. A task annotation can narrow or clarify these bounds only when its manifest hash and evidence references validate and the task-definition claim cites a reviewed record. No annotation means the existing source-owned task is used; it does not imply a new interaction criterion.

The existing runtime fixes `goal_radius=2.0 m`. Bounded-task completion is observed when the native `reached_goal` flag is active or an observed ego centre lies within that radius of the validated source goal. The native event, geometric observation, completion basis, and terminal reason remain separate. The first completion observation is retained even if a later native goal removal leaves no pose. Completion during observations 0–10 is labeled warmup/initial-condition and is not attributed to the controlled policy. Reaching this source goal says nothing about whether a PE07 encounter was presented or resolved. This source task has no implicit deadline; horizon or recording end without completion is `unresolved`. Only an explicitly supported task annotation may add a finite deadline, and that deadline produces `failed` only when the trace observes through it without completion.

Route projection uses the hash-bound source ego positions from task start through goal sample as the offline reference polyline. At each observation it finds nearest segment projections, then retains only candidates continuous with the preceding projection within observed ego displacement plus 0.5 m. Candidates within 0.1 m of the nearest geometric distance that differ by more than 0.5 m in arc position remain ambiguous. A 0.02 m direction guard rejects a projection whose signed arc change contradicts observed motion; backward travel therefore retains negative signed progress. These tolerances absorb adjacent-segment vertex ties while refusing to select a loop/branch by the amount of progress it would award. The result includes projection distances, raw signed metres and raw normalized fraction. A clipped `[0,1]` fraction is display-only. A window crossing an ambiguous/missing projection has no net progress value. The task span must be finite and positive before normalized progress is valid.

Completion time is the recorded or producer-guaranteed inferred observation time relative to the first observation, with a second elapsed value relative to observation 10 when completion occurs after policy start. Stationary duration is the left-observation approximation over supported present, same-lifetime intervals with increasing timestamps; an explicitly unapplied transition is excluded. Report the supported duration and speed-coverage gap rather than extending a terminal state. Low-progress candidates require at least 30 consecutive 10 Hz intervals spanning the configured 3 s, each with a finite positive interval no longer than 0.15 s and a continuous route projection. Candidates never establish opportunity to proceed. PE06 does not confirm deadlock.

Safe completion uses `safe_completion_core_v1`: any observed required native collision/off-road event is a failure; a no-event pass requires complete corresponding native event-field coverage. Missing fields remain `not_assessed`. PE06 leaves safe completion `not_assessed` unless all currently required criteria are known and passing; the applicable interaction/rule criteria remain unassessed until PE07/PE08. Neither task completion nor absence of recorded violations alone produces a safe-completion pass.

### PE07 actual encounter and interaction measurements

The fixed opportunity, family, subtype and actor IDs come from the selected hash-bound portable manifest row, checked against the task context's manifest, converted source scene and binary identities. The admission decision and its saved report are not read as encounter evidence. Existing source interaction-fidelity certificates are accepted only when their recorded binary/ego identities, rule-audit and lifecycle-trace hashes, internal source-evidence digest and selected actor IDs agree. An existing source body-path-conflict certificate is checked against the converted source-scene hash; a source following-scope certificate must also match its source scene, tracks and map hashes. These certificates remain fixed source context across planner conditions. A missing optional source certificate stays visible; it does not convert an actual rollout into a pass or exclude an episode.

PE07 reports `encounter.realization` separately from `interaction.outcome`, bounded-task completion and driving events. The source opportunity remains an explicit boolean plus its source subtype. A non-realized opportunity is `not_reached`; missing actor/time/conflict evidence is `indeterminate`; observed occupancy without a supportable complete passage is `encountered`/`unresolved`; and a supported, completed interaction is `encountered`/`resolved`. Controls have `not_applicable` interaction obligations while retaining all core task and safety metrics. No family receives a pass/fail interaction criterion without a separate hash-bound explicit criterion. In particular, after-ego cyclist crossings create no ego-yield obligation. No causal response, fault, human reaction or cooperation is inferred.

Crossing reference conflict regions are built from the union of positive-area intersections between the ego and designated actor's oriented footprints over their valid converted source paths, clipped to the source task bounds beginning at source sample 10. The intersection is geometric and asynchronous: it expresses where the two reference body-path corridors overlap, not that the source actors occupied the region simultaneously or that a planner must yield. Existing source conflict certificates corroborate this region when present. Actual occupancy requires the observed ego or actor oriented footprint to overlap this fixed region. PE07 uses saved observation poses and dimensions only; it does not interpolate missing states. PET is a sampled difference from an observed clear-region state to a later observed entry, and is emitted only for ordered, non-censored passages with supported time. Simultaneous occupancy, repeated runs, actor loss, missing entry/exit and horizon censoring remain explicit. Each interaction actor row links PE04's unchanged `safety.footprint_clearance` and `safety.ttc` results: it shows the clearance samples where that actor was the reported closest pair and the TTC samples for that actor pair. Missing actor-specific samples remain unavailable; PE07 does not recalculate or replace PE04 risk measures. Their proximity alone cannot establish yielding correctness.

Following route compatibility uses PE05's assigned directed lane centerlines and successor graph. A leader must be ahead along the same lane or a unique directed successor chain; ambiguous lane assignment, a wrong-direction leader, or an unconnected route does not count as a leader-ahead sample. PE07 reports physical oriented-footprint gap separately from route distance. Moving time headway is physical gap divided by observed ego speed only above the configured stationary threshold of 0.2 m/s; at or below that speed it is `undefined` with a null headway and any supported physical gap retained. Following duration sums valid primary-window left-observation intervals with a route-compatible leader ahead and continuous ego/leader identity. Stop/restart output records observed leader stop and motion resumption only; it does not say ego caused either event.

Encounter realization spans all recorded observations so an initial-condition encounter remains visible. Its timebase uses recorded observation times or the explicit schema-2 10 Hz producer step fallback. A state first occupied before observation 10 is labeled warmup/initial-condition in the supporting samples; primary following-duration exposure starts at observation 10's outgoing transition. Event and actor occupancy timing are observation-level evidence, not action causality. Gaps, known lifetime changes, unapplied transitions, actor removal and absent time are not bridged. When an ego failure prevents an encounter, its existing task/progress/safety result remains in the episode; encounter non-realization never filters the episode from later accounting.

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

PE06 accepts a `task_definition` decision only with `review.status = "reviewed"` and a hash-bound `review.evidence_ref`. Its decision object is limited to `task_id` (nonempty string), optional `start_source_step`, `goal_source_step`, `completion_radius_m`, and `deadline_s`; source step selectors still point into the converted source task and cannot exceed its validated goal sample. Each supplied bound/threshold must equal a value selected from one of the claim's hash-bound evidence references. Omitted values retain the existing contract bounds/radius and no-deadline semantics. A finite deadline is explicit task evidence, not the trace horizon. Each evidence reference is represented by `{"reference":{"root":"project|artifacts|source|bench|reference_data","path":"portable/relative/path"},"sha256":"<64 lowercase hex>","selector":"/json/pointer"}`. The selector must resolve in the hash-checked JSON owner. An unsupported field, unresolvable selector, stale hash, conflicting task claim, or invalid review binding cannot alter task bounds.

## Version changes

Change a substantive metric meaning, stencil, eligibility rule, threshold, or criterion set only with a recorded reason, a new definition/profile version, and affected known-case/sensitivity verification. Store both the definition version and effective parsed profile hash in every result. Historical results remain bound to their original versions.

## Offline reader and effective profile identity

PE01 exposes `runtime.trace_io.load_saved_trace()` for saved episode data. It checks the trace and sidecar identities, observation structure and available hash bindings. A valid passed parent attempt or a selected passing campaign slot can establish `archived_attested`. The caller supplies the campaign revision and scene identities from saved campaign records. Older standalone attempts may have no recorded Git revision. When the caller has local input files, it can supply them by input name for hash checks. The reader does not need the original runtime, planner or dataset. Parsing failures, unsupported schemas and contradictory evidence raise `SavedEvidenceError` or its `UnsupportedTraceSchema` subtype. These should enter downstream accounting as invalid evidence.

A coherent trace without a parent attestation supports `trace_only_diagnostic`. Hashes alone establish byte integrity. The scientific frame iterator joins verification metadata only when the verification bytes are paired with the trace by recorded hashes or name the exact trace hash. The viewer keeps its historical display behavior for a structurally coherent sidecar. Missing legacy metadata stays absent or null. `live_validated` remains a status supplied by the existing execution path, outside this reader.

`evaluation.profile.load_profile()` reads a complete TOML profile. Its raw SHA-256 identifies the file bytes. Its effective SHA-256 identifies the validated values, including profile ID and definition version. Schema-defined real numbers are normalized to floats. The hash input is UTF-8 JSON with lexically sorted keys, compact separators, unchanged array order, no newline and no nonfinite values. TOML comments, whitespace, key order and an integer spelling of a real field have no effect on the effective hash. The loader rejects unsupported versions, contradictory warmup and window settings, and sensitivity arrays that disagree with the primary thresholds. Version 1 fixes time and algorithm choices. Customized operating thresholds must remain within this contract.

`geotransfer evaluate episode --trace TRACE --output NEW_DIR [--profile PROFILE] [--scene ID_OR_ROOT]` reads one saved episode only. The resolved output must be a new directory beneath configured `runs`; existing outputs and paths overlapping the trace, its sidecars, profile, selected scene, or protected source/artifact roots are refused. `episode.json` binds the trace and available sidecar hashes, saved evidence level, recorded protocol/startup metadata, profile raw/effective hashes, and a dependency-light identity for the current reader/evaluator code. It does not rerun live validation; `live_validation_status` is `not_run_offline_evaluation`. A readable trace with no parent attestation remains `trace_only_diagnostic`. `events.json` is emitted only when observed event/terminal records exist, and its exact bytes are hash-bound from `episode.json`.

The primary post-warmup state window includes observation 10 as the initial state; its outgoing controlled transition begins at 10→11. Matrix owner labels apply to the outgoing interval from their observation. Second-difference stencils that cross two different known outgoing owners are excluded. A legacy trace can provide descriptive continuous samples, but missing owner/lifetime metadata remains explicit and cannot establish controller attribution or verifiable handover absence. Missing event channels produce an unavailable event count (`null`), while fully observed channels with no event support a known observed count of zero. A partial event channel is visibly lower-bound evidence.
