# GeoTransfer performance evaluation — Codex prompts per milestone

**Executor:** Luna with **xhigh** reasoning. **One new implementation session = one PE milestone.** These are execution prompts, not requests for another plan.

Use the tracked planning documents in `docs/plans/performance_metrics/`:

- `docs/plans/performance_metrics/geotransfer_performance_evaluation_plan.md` — scope specification.
- `docs/plans/performance_metrics/geotransfer_performance_implementation_milestones.md` — detailed implementation requirements and acceptance criteria.
- `docs/plans/performance_metrics/geotransfer_performance_milestone_prompts.md` — this prompt set.

Update the shared results log in the same directory. Each fenced block is independently copyable and includes the common constraints. Select the model/reasoning setting in Codex; the prompt does not change the model itself.

Run PE00–PE11 in order. PE12 is the optional P2 extension and may be deferred. PE13 adds comparison support and records the real baseline-readiness block. PE14 performs final acceptance. Do not start a dependent session while its required code contract is incomplete; carry native/data verification blocks explicitly without fabricating completion.

A session finishes by updating the same `implementation_results.md`, reporting tests/evidence/blocks, and handing off the next milestone. The detailed plan is authoritative for full requirements; these prompts emphasize the selected session's work and failure risks.

## Session index

| Session | Scope |
|---|---|
| PE00 | Baseline, reuse audit and frozen definitions |
| PE00.5 | Admission regression isolation and SMART fixture checkpoint |
| PE01 | Shared saved-evidence reader and contracts |
| PE02 | Exposure, kinematics and initial episode command |
| PE03 | Optional native evidence capture |
| PE04 | Collision, footprint clearance and TTC |
| PE05 | Map context, off-road extent and lane diagnostics |
| PE06 | Route progress, task outcomes and efficiency |
| PE07 | Actual encounter and interaction outcomes |
| PE08 | Conditional semantic compliance |
| PE09 | Offline run accounting and failure reports |
| PE10 | Aggregation, uncertainty and sensitivity |
| PE11 | Metrics and events in the existing offline viewer |
| PE12 | Secondary metrics and benchmark adapters |
| PE13 | Geographic comparison and baseline readiness |
| PE14 | Final regression, diagnostic pilot and handover |

## PE00 — Baseline, reuse audit and frozen definitions

```text
You are executing PE00 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE00 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Establish the real starting state without implementing metrics yet. Compare current HEAD with the inspected 504218cb9ecd7fd64d2952630b9f10f56d80f923 snapshot and record relevant drift. Inspect the existing CLI, runtime/session/episode worker, actor identity, run_trace fingerprints/validation, batch/campaign ledgers, artifact/config helpers, viewer loading, source/map/interaction certificates, and pinned BehaviorBench metric/classifier/binding code. Read the protocol-scope/matching document and the existing controller acceptance instructions.

Produce a repository-specific reuse map and baseline section in the shared implementation_results.md. Create docs/performance_evaluation.md as the single operational metric-definition document; finalize the profile/annotation contracts and section 5 measurement choices with reasons. Explicitly settle observation-versus-transition timing, warmup attribution, derivative support, collision/TTC channels, task/horizon semantics, unknown statuses and archive integrity versus live reproducibility. Do not leave routine engineering decisions for the next model to guess.

Run baseline pytest and doctor, then available required native/migration checks on copied artifacts. Retain exact statuses and protected-input hashes. Missing assets stay BLOCKED; no fabricated source/campaign evidence. The planning audit observed 307 passed, 1 skipped and 2 asset-dependent test failures, not a full green baseline. Do not fix unrelated baseline issues or modify production behavior in this milestone.

Acceptance: concrete reuse/definition decisions, known environment baseline, protected identities, native-verification availability and a precise PE01 handoff.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE00.5 — Baseline repair and handoff cleanup

Reconcile the PE00 protected hashes against retained evidence. Preserve changed reports and recover pinned bytes only from a verified original copy. Run the admission regression on an isolated artifact tree. Run the SMART joint-input probe with its synthetic re-entry fixture. Record inventory and representative parity separately. Record unresolved gates in the shared results log before proceeding to the saved-evidence reader.

## PE01 — Shared saved-evidence reader and contracts

```text
You are executing PE01 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE01 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement the contracts and shared saved-evidence loading boundary from PE01. Reuse artifacts.py/config.py. Narrowly extract the existing viewer hash/coherence checks into runtime/trace_io.py so viewer and evaluator share them; preserve the current viewer API/rendering behavior. Add one raw frame/actor access path for legacy schema-2 expert/SMART and nested schema-3 matrix traces. Resolve ego from its recorded binary index and stable source ID, retaining lifetime identity and missing metadata.

Implement finite JSON result/status/profile structures and version/hash the effective profile. Separate assessment status, criterion outcome and special quantity interpretation. Never encode missing values as zero, -1, Infinity or pass. Do not add fake future metric implementations.

Support archived saved attestations independently of the evaluator's current code fingerprints. Validate the recorded hashes, identities and supported structural facts; keep live run_trace.validate_run and exact canonical comparison strict and unchanged. A bare readable trace remains lower-evidence diagnostics. Do not require Torch, BehaviorBench or the native runtime just to read/inspect saved evidence.

Test old and new layouts, nonzero ego, actor reorder, missing lifetimes, incompatible/tampered sidecars, old producing revision versus new evaluator HEAD, unsupported schemas and finite serialization. Run existing viewer tests and import checks. Acceptance: one reusable loading boundary, no historical byte changes, no duplicated display-derived scientific interpretation and a working synthetic saved bundle.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE02 — Exposure, kinematics and initial episode command

```text
You are executing PE02 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE02 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement PE02 only: exposure/kinematics composition and the first useful offline episode CLI. Add the evaluate dispatch lazily to the existing geotransfer CLI; implement evaluate episode --trace PATH --output NEW_DIR with optional profile and scene context. It must never launch models or regenerate evidence.

Compute full-recorded and primary post-warmup exposure using timestamps, applied transitions, presence and lifetime/ownership segments. A complete matrix trace has 91 observations, 90 transitions, 9 seconds recorded, and 80 controlled transitions/8 seconds after replay warmup. State at observation 10 precedes the first policy action; do not attribute an existing warmup event to that action.

Compute observed speed, longitudinal/lateral acceleration, yaw rate/acceleration, longitudinal jerk and total world-vector jerk using the frozen definition's timing/stencils. Preserve signed braking and distinguish these quantities. No zero padding, silent filtering, derivatives across gaps/re-entry/handover, post-removal zeros or commanded-action substitutes. Report eligible samples, exclusions, operating flags and exposure. Label observed-position VRU/replay velocity estimates separately if needed.

Test constant speed, analytical acceleration and circular motion, changing acceleration, yaw wrap, irregular timestamps, short traces, terminal removal, gap/re-entry/handover and legacy unrecorded final action. Output finite versioned episode results and available events. Missing scene/map/task context must not prevent trace-only kinematics. Acceptance: scientifically correct offline measurements and all existing command/import behavior preserved.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE03 — Optional native evidence capture

```text
You are executing PE03 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE03 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement the optional evidence-capture path from PE03 using the existing episode_worker capture point and existing execution/batch machinery. Add --capture-evaluation to matrix run/worker selection with default off. Do not add another simulation loop or change session.frame, actions, scheduler, controller inputs, native patches or upstream files.

Capture copied native collision-partner/impact-position evidence and justified read-only settings/log fields into evaluation_capture.json. Bind the sidecar to the exact trace hash, scene/binary/controller/startup/horizon and actor/lifetime identities. Preserve coordinates explicitly: native impact/goals must be translated consistently before combining with world trace coordinates. Capture terminal events whose canonical pose is absent. Inspect log readers for indexing/reset side effects before using them; do not call resetting aggregate logging APIs.

With capture off, preserve existing canonical files and default schema-4 resume expectations. With capture requested, parent validation must require/check/hash the sidecar through the existing attempt evidence; missing or stale requested evidence fails visibly. Preserve retries/logs and default legacy SMART/expert behavior.

Test off/on action/state/trace equality, terminal collision/partner identity, nonzero ego, coordinate transforms, tampering/missing sidecars and default resume compatibility. Run representative fresh single/manifest parity in the configured research environment. Acceptance requires real parity evidence; without native assets finish independent implementation/tests and mark native acceptance BLOCKED rather than claiming verification from mocks.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE04 — Collision, footprint clearance and TTC

```text
You are executing PE04 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE04 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement PE04 safety metrics on the saved-evidence/context contracts. Reuse suitable existing oriented-box distance/overlap helpers. Keep native event occurrence, sampled physical overlap and constant-velocity predictive TTC as separate named channels.

Detect collision onsets even when the terminal actor pose is null. Deduplicate latched flags, distinguish warmup/controlled attribution, and call event counts observed/lower-bound when evidence is incomplete. Use captured partner IDs/impact positions where available; do not guess a nearest actor as partner. Report pre-impact relative speed as a proxy and only supported type/fault classifications, with unknown responsibility otherwise. Optional pinned upstream heuristics must not become legal truth or require the whole upstream evaluator.

Compute simultaneous footprint clearance including replayed VRUs and parked actors. Implement continuous fixed-heading, constant-world-velocity oriented-box TTC through separating-axis time intervals, using the frozen horizon/profile. Distinguish overlap now, finite collision time, no predicted collision within horizon, and missing/undefined data. Compute threshold exposure only on supported intervals; missing counterpart motion/dimensions must remain visible rather than certifying the full scene safe.

Tests must include analytical head-on and crossing times, rotated shapes, separating/parallel/stationary bodies, already-overlapping bodies, horizon limits, missing VRU velocity, dimension imputation, terminal collision without pose, latched flags, actor-order and rigid-transform invariance. Acceptance: meaningful validated core safety outputs on old/new traces with honest degradation when optional evidence is absent.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE05 — Map context, off-road extent and lane diagnostics

```text
You are executing PE05 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE05 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement PE05 with existing provider-map interpretation and immutable source context. Reuse recording-specific map selection, projection, Lanelet2 boundary orientation and directed topology. Do not implement another converter/router or mutate reviews/admissions. If robust polygon union/difference requires Shapely, add only the optional evaluation-geometry extra and preserve dependency-light unrelated commands.

Keep native road-edge offroad occurrence separate from footprint membership in a supported physical-road polygon union. Preserve holes/connectivity, distinguish physical area from legal access, and report unsupported coverage/US geometry honestly. Do not invent polygon closures from binary road-edge lines or infer ground-truth road width by buffering centerlines.

Implement exact polygon outside tests, sampled observed duration/outside area, and maximum footprint-boundary excursion under the PE05 definition/error bound. Corner-only membership and symmetric Hausdorff distance are not substitutes. Add conditional lane offset/heading diagnostics with ambiguous intersections/directions/low-speed states explicit; lane deviation is not automatically a rule violation.

Test adjacent lane seams, concavity/holes, a footprint enclosing a hole, boundary crossing with center inside, opposite OSM way storage, overlapping directions, map coverage gaps, the construction-map variant, missing source maps, transforms and censored offroad duration after removal. Run existing map/orientation tests as applicable. Acceptance: independently named native and map-based metrics, correct geometric support and unchanged converter/native/admission behavior.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE06 — Route progress, task outcomes and efficiency

```text
You are executing PE06 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE06 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement PE06 using existing source goals/windows/routes and read-only sparse evaluation annotations bound to input/review evidence. Do not edit scene goals, extend source visibility or duplicate manifest metadata. Offline source reference geometry must never enter planner observations.

Measure signed net arc progress along a validated reference route with continuity/direction safeguards; distinguish distance traveled and normalized task progress. Require a positive validated task span and expose ambiguous projection at loops/branches instead of selecting a progress-maximizing match.

Separate simulator goal event, bounded-task completion, encounter completion, safe completion and terminal outcome. Handle goal removal correctly. Reaching a source goal before the challenge is not interaction success. A horizon is unresolved unless an explicit validated deadline makes it a failure. Preserve SMART's lack of goal input and alternative legal branch ambiguity. Safe completion requires known passing critical criteria, not just no observed violation.

Add completion time, stationary duration, timeout/truncation cause and low-progress candidates. Confirm deadlock only with sufficient opportunity-to-proceed evidence; legal waiting/short observation stays unassessed or a diagnostic candidate.

Test reverse/forward travel, intersecting routes, zero/missing task span, goal before encounter, incomplete horizon, stopped leader and restart, native goal terminal, SMART legal branch divergence and missing critical safety evidence. Acceptance: useful route/task/efficiency results without false goal/horizon success/failure or changed source task semantics.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE07 — Actual encounter and interaction outcomes

```text
You are executing PE07 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE07 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement PE07 for exactly the existing following, pedestrian-crossing, cyclist-crossing and control families. Preserve the source subtypes, including cyclist crossing after ego. Do not add unsupported merge/roundabout/overtake engines.

Reuse source opportunity/actor/conflict/fidelity evidence as fixed context, then assess actual rollout realization independently. Report source opportunity, not-reached/encountered/resolved/unresolved/indeterminate/not-applicable states, and supported reasons. A planner that never reaches the challenge has not passed it; retain any driving/progress failure rather than excluding the scene.

For following, assess actual route compatibility, leader-ahead relation, physical gap, moving headway and supported stop/restart resolution. Standstill headway is undefined, with finite physical gap still available. For crossings, define the conflict region/corridor and actual footprint occupancy; compute ordered PET only when entry/exit is observed. Simultaneous/repeated occupancy, missing exits and insufficient horizon need explicit handling. Keep clearance/TTC alongside PET and yielding compliance dependent on a supported obligation.

Controls retain core evaluation but no invented interaction obligation. Never require unnecessary braking for the after-ego cyclist or infer cooperation/human reaction/causality from a label.

Test ego non-approach, disappearing actor, safe ego-first/actor-first crossing, simultaneous and repeated occupancy, after-ego cyclist, leader stop/restart and route mismatch, ambiguous realization and all control subtypes. Acceptance: documented operational criteria and coverage per admitted family, with actual failure retention and no automatic admission claims.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE08 — Conditional semantic compliance

```text
You are executing PE08 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE08 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement PE08 semantic applicability and supported checks on actual closed-loop routes. Reuse existing map/rule/review certificates without modifying them. Source-route proof of irrelevance is not a waiver if the planner later drives onto a different approach.

Cover direction, speed limit, stop sign, traffic signal and priority/yielding in a capability matrix. Implement moving wrong-way distance/duration only with reliable directed-lane assignment; low-speed heading alone is insufficient. Compute overspeed only with an authoritative applicable limit. Implement supported stop/priority cases from evidence-bound approach/line/conflict criteria; absence of collision alone does not prove compliance.

If the corpus lacks authoritative traffic-signal state or another obligation, emit explicit unavailable/unassessable results and document the required input contract. Do not reconstruct imagined signals, claim exhaustive German traffic-law coverage, infer rules from sign distance/source-driver behavior, or fabricate reviewed annotations. Add a concrete evaluator only where evidence supports it and fixtures can verify it.

Test supported and ambiguous direction/limits, correct stop approach versus adjacent lane, source-irrelevant rule becoming applicable after deviation, supported priority with/without relevant conflict, missing signal timeline and insufficient observation. Every implemented assessment requires positive/negative scientific cases. Acceptance: explicit per-rule/per-family coverage, no missing-as-compliant cases and source admission untouched.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE09 — Offline run accounting and failure reports

```text
You are executing PE09 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE09 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement PE09 offline cohort processing and reports; reuse existing run/campaign accounting rather than launching or scheduling simulation. Add evaluate run for an existing run ledger or saved campaign plus its existing manifest, with output in a new directory. Support relevant schema-4 matrix, legacy schema-2 and persisted campaign layouts through the shared reader.

Snapshot expected input selection and account for every logical entry, including blocked, not-run, interrupted, worker failure and invalid evidence with no trace. Use the saved single campaign view as primary; batch is replication evidence, not another independent driving sample. Reject duplicate/ambiguous identities. Preserve attempt history; a successful retry does not erase an earlier failed campaign status.

Compose per-episode metrics/events and non-exclusive failure labels. Separate integration status, archive evidence, metric eligibility, task/encounter result and driving outcome; campaign PASS is not safe driving. Keep first and co-occurring events without calling the first proven root cause.

Emit one machine-readable index, per-episode results/events, CSV and Markdown summary. Add evaluate report to rerender those saved results without recomputing metrics or running models. Hash/reference original evidence rather than copying traces into another store. Refuse output/input/scene/frozen-campaign overlap.

Test no-trace crashes, blocks, stale manifests/sidecars, archived code revision, retries, duplicates, legacy missing fields, single/batch deduplication, partial output, no-source trace-only evaluation and deterministic rendering. Acceptance: complete transparent accounting, reproducible offline outputs and no parallel execution/resume framework.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE10 — Aggregation, uncertainty and sensitivity

```text
You are executing PE10 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE10 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement PE10 statistical summaries and threshold sensitivity from saved PE09 results/evidence. Keep planner/checkpoint, traffic, startup, horizon, evidence and metric/profile versions explicit; do not pool incompatible definitions or silently select only realized/successful encounters.

Compute per-metric valid/applicable denominators together with submitted/executed/failed/excluded counts. Distinguish episode rates, event/exposure rates, total exposure ratios and means of episode ratios. Preserve cohort intersections and missingness for paired conditions.

Implement seeded recording/sequence-cluster bootstrap with pairing retained inside resampled blocks and the declared estimand/weights. Missing clusters, one/few clusters and degenerate zero/all-event samples need explicit limits, never false independent precision or certain zero-width intervals. Report recording and location counts.

Implement evaluate sensitivity with frozen alternative profiles, reusing continuous evidence or recomputing offline from immutable traces when needed. Never rerun simulation just to adjust TTC/comfort thresholds. Align the same logical episodes and disclose changed applicability. Report safety/progress/comfort trade-offs, family/location recurrence and traffic/startup dependence.

Test hand-calculated mixed denominators, all-unavailable/no-exposure groups, repeated scenes in one cluster, paired block resampling, missing/single cluster, zero events, incompatible profiles and deterministic threshold-only recomputation. Acceptance: defensible reproducible aggregate outputs and sensitivity results, with small-corpus inference limits visible.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE11 — Metrics and events in the existing offline viewer

```text
You are executing PE11 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE11 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement PE11 in the existing viewer/gallery/template, not a second dashboard. Consume saved evaluation results bound to the exact trace hash, scene/protocol and profile/version. Preserve PE01 shared loading rather than duplicating integrity checks.

Show compact values/statuses, task/encounter state, exposure and limitations alongside the existing actor/controller playback. Add event selection that seeks to recorded time and identifies involved source actors. Keep native and derived metric events distinct and support terminal events with absent pose. Campaign PASS remains an integration/parity label separate from driving failure.

Preserve original source/converted/legacy/matrix comparisons, scene/controller/startup filters, US no-source fallback, aerial registration, time/keyboard controls, standalone no-server HTML and filtered-output isolation. Missing metric attachments are normal. Do not recompute scientific formulas in JavaScript, copy metrics into traces, run simulation or mutate campaigns.

Run existing viewer tests and add old/no-metric, stale/hash-mismatched attachments, terminal event, unavailable metric, conflicting profile, filter isolation and HTML-escaping cases. On the configured browser environment extend/run the existing probe_matrix_viewer browser check for the panel and event seek; record browser verification BLOCKED if unavailable.

Acceptance: inspectable hash-bound results in original playback with zero inference/network dependency and unchanged baseline viewing workflows.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE12 — Secondary metrics and benchmark adapters

```text
You are executing PE12 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE12 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Execute PE12, the separate P2 extension. It must not hold P0 readiness hostage. Reuse completed core results, existing upstream metrics/classifier and context, with lazy optional imports; do not copy/vendor the upstream evaluator or create another runner.

Implement timestamp/lifetime-aligned ADE/FDE/reference deviation with honest endpoint/coverage requirements. Add All-Core Pass Rate over one frozen named criterion set; unknown required criteria cannot be silently removed to produce pass.

Inspect the configured pinned BehaviorBench implementation before exposing compatibility scores. Adapt supported components/native diagnostics and classification functions only with sufficient captured inputs, explicit warmup/window alignment and documented heuristic/default-value differences. A nuPlan-style adapted score requires an explicit formula and valid inputs. Do not invent a canonical composite or call an adapted score official.

Add focused traffic speed/acceleration/gap and replay/hold/learned exposure diagnostics, with source/reference comparability limits. These are limited plausibility diagnostics, not demonstrated human realism or WOSAC equivalence.

Test partial/missing reference endpoints, alternative safe paths, unknown required core checks, missing BB/native logs, window mismatch, unsupported fault evidence and arithmetic against pinned supported cases. Acceptance: all secondary outputs state validity/provenance/compatibility level; unsupported official scores remain unavailable. If this optional milestone is deferred, record that clearly without blocking the core milestone chain.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE13 — Geographic comparison and baseline readiness

```text
You are executing PE13 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE13 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Implement PE13 geographic-comparison support and the real-data readiness gate. Read the existing step_2 protocol-scope/matching requirements; reuse manifests/metadata, existing evaluation outputs and PE10 cluster statistics. Do not treat the two US interface fixtures as a matched benchmark.

Audit common metric versions/protocols/exposure, task and interaction coverage, source/map/dimension provenance, traffic priors, legal semantics and planner goal information. Define an outcome-blind sparse cohort/matching config referencing existing manifests. Use transparent strata for family/subtype, initial speed, route length/curvature, traffic composition/density, horizon and geometry; no new general manifest format or learned matching machinery for this tiny corpus.

Add evaluate compare with balance/missingness/unmatched tables, within-stratum/matched or standardized differences, declared metric direction and clustered uncertainty. Reject or explicitly limit incompatible comparisons; preserve unsupported strata instead of forcing matches. Freeze selection before outcome inspection and detect changed config identity.

Test on synthetic comparable cohorts, known gaps, unsupported strata, missing clusters, protocol mismatch and paired conditions. For the actual current diagnostic-only US set, emit baseline-not-ready plus a concrete source-only input/acquisition/annotation list and independent-sample precision limitations. Do not quietly download/convert a new corpus, change admission or claim geographic causality.

Acceptance: working comparison code demonstrated independently of data readiness; real geographic scientific acceptance remains BLOCKED until suitable real cohorts exist.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```

## PE14 — Final regression, diagnostic pilot and handover

```text
You are executing PE14 only for the existing geotransfer-gap-AD repository. Use Luna/xhigh. Read applicable AGENTS.md and these files under docs/plans/performance_metrics/: geotransfer_performance_evaluation_plan.md, geotransfer_performance_implementation_milestones.md (especially PE14 and global constraints), and the prior entries in implementation_results.md. If paths/HEAD differ, inspect and adapt narrowly; do not reset unrelated work. Implement the selected milestone concretely and stop before later milestone work.

Build on existing owners. No second simulator loop, batch executor, manifest system, scorer registry, viewer or generic framework. Keep converted sources/binaries, existing reviews/manifests, SMART/PPO inputs, checkpoints, native patches and upstream BB unchanged. Preserve old run/view behavior, strict validation and historical evidence bytes. New evaluation outputs belong in a new directory under configured runs, outside all inputs/frozen artifacts. Use synthetic tracked fixtures; never commit licensed or real derived data. Keep missing evidence distinct from zero/pass. Read all requirements and acceptance tests for this milestone in the detailed plan.

Execute PE14 integrated acceptance and research handover. Audit the full diff for duplicate loaders/scorers/configs/runtimes/viewers, dead scaffolding, heavy imports, accidental public tools and tracked private artifacts. Cross-check all P0/P1 requirements; record PE12/P2 and PE13 geographic readiness separately.

Run full old/new pytest; required check all and migration conversion/execution on copied artifacts in the configured native environment; protected source/binary/review/manifest hash checks; and legacy SMART/hybrid behavior-oracle checks. Use appropriate historical-integrity versus fresh-runtime checks, never rewrite producer hashes. Demonstrate capture on/off canonical equality and representative fresh single/manifest parity through existing helpers. A full 504-slot rerun is required only for changed runtime/controller semantics or existing explicit policy, not merely offline metric additions.

After smoke/parity gates, evaluate available expert, SMART and PPO evidence for all 16 scenes under a predeclared small protocol set. Reuse saved valid traces; launch missing rollouts only through the existing CLI/fresh worker. Keep original SMART/hybrid admission conditions separate from matrix conditions and preserve all failed/blocked attempts. No substitute weights/planners or fabricated data.

Perform reference sanity checks and inspect representative failures/non-failures in the existing viewer. Produce the diagnostic report covering metrics/exposure, encounters, recurring failures, trade-offs, sensitivity, uncertainty and adaptation hypotheses. Do not tune thresholds just to make humans pass or claim minimal-data adaptation is proven.

Update README/workflows/architecture and the one shared results log with exact usage, evidence, readiness and remaining blocks. Acceptance must separately state code, native, family/rule, P2 and geographic status. Missing mandatory assets mean BLOCKED verification, not a green completion claim. Do not start training, corpus expansion or publishing.

Before finishing, review the diff for redundancy and compatibility, run the milestone's meaningful checks and relevant old tests, and update only this milestone's section in docs/plans/performance_metrics/implementation_results.md. Record exact commands/results, evidence paths, deviations and blocked prerequisites; a blocked mandatory gate is not a pass. Continue independent work if assets are missing. Commit only milestone-owned code/tests/docs when the repository workflow permits; do not push/publish. Return implemented behavior, verification, remaining blocks and the next handoff. Do not end with merely a proposed plan.
```
