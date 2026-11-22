# GeoTransfer Gap AD — Controller Matrix Implementation and Verification Plan

**Status:** implementation specification for Codex; **not** a claim of completed implementation or verified runs.  
**Target:** [`imendezval/geotransfer-gap-AD`](https://github.com/imendezval/geotransfer-gap-AD), current `main` as inspected 2026-11-17.  
**Execution environment:** user's existing local `bb_pufferdrive`, external BehaviorBench checkout, licensed inD/WOMD scenes and weights. Pin exact local Git SHA and dependencies before changing code.

## 0. Decision summary

Implement a **single episode scheduler** and **four role-independent controller adapters** while preserving the current source -> conversion -> admission -> execution -> offline-viewing pipeline. Keep source evidence and previously admitted scenes untouched. Controller correctness and research admission remain separate. Deliver **16 immediate** ego×traffic pairs plus **12 source-hold** variants (no source-hold with expert traffic), across **16 existing German scenes and two US interface references**, yielding **28 × 18 = 504 deterministic episodes** for the acceptance matrix. Repeat all 504 independently in fresh processes for batch-versus-single parity (**1,008 episode executions minimum**, not counting diagnostic and fixtures). Do not describe these as 504 independent scenarios or 504 geographic evidence points.

**Recommendation:** incremental execution with verification-backed micro-commits and external review gates. Do not ask one coding agent to implement all 28 combinations and self-certify in one uninterrupted pass. Use `CODEX_STAGE_PROMPTS.md` alongside this file.

### Non-negotiable design constraints

1. **No parallel engine:** preserve the existing validated native-runtime path and `evaluation_env`; do not create a second simulator, duplicate actor-state extraction, or transplant upstream BB evaluator wholesale.
2. **One action writer:** exactly one component maps owners/actions to native movement modes and action slots, then calls `env.step()` once per tick. Controllers never mutate `env` movement modes or action buffers directly.
3. **One authority for each rule:** reuse `hybrid_traffic.release_schedule` unchanged as the source-hold rule; reuse `faithful_smart`/`faithful_map` for SMART feature extraction; reuse `artifacts` for references/hashes/atomic JSON. New code must *call* these producers, not clone their algorithms.
4. **Freeze provenance-sensitive producers by default.** The current `validation/scene_contract.py` fingerprints `runtime/session.py`, `runtime/hybrid_traffic.py`, `runtime/late_spawn_runtime.py`, `runtime/background_route_intent.py`, `planners/faithful_smart.py` (through SMART proof), config/artifact helpers and other validation components. `planners/protocol.py` independently fingerprints SMART input/execution code. Avoid editing them; extend using new files/wrappers. If a modification is unavoidable, stop, record why, regenerate/revalidate affected evidence explicitly and compare legacy equivalence before proceeding. Never silently carry forward a stale admission.
5. **Preserve the baseline as an oracle:** capture pre-change `geotransfer run --planner smart` / SMART + `hybrid_startup` on all accessible scenes with code hashes, actions and meaningful state. Keep legacy output generation intact until the new scheduler proves exact semantic parity. The legacy baseline trace format should remain byte-stable where possible; new provenance may live in sibling files. A new-format trace need not have identical JSON metadata, but action arrays, ownership, release events and meaningful states must match the frozen reference exactly.
6. **No outcome-based scene filtering.** Preserve the 16 scene definitions, time windows, source admission and their independence groups. Poor execution or changed encounters are research observations, not integration failures.
7. **External BB is read-only.** Adapt in `src/geotransfer_gap`; changes to the project's isolated runtime must be exceptional and independently proved. Do not modify the external BB checkout or its weight files.
8. **Small commits:** commit at each tested, coherent change (target about 22–26 commits). Never combine a large refactor, learned-model integration, validation redesign and viewer redesign into one commit.

## 1. Repository audit / concrete findings

These are source-level findings from the public repository, **not** local runtime verification:

| Current source | Observed implementation | Implication |
|---|---|---|
| [`src/geotransfer_gap/execution.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/execution.py) | Three diverging run paths: expert replay inline; SMART via `probe_faithful_smart_closed_loop.py` child; BB via diagnostic subprocess. Manifest freshness check is specifically SMART/traffic-protocol admission. | Convert it into CLI normalization plus per-scene subprocess orchestration; move common stepping into a *single new episode worker*. Preserve the BB diagnostic route separately. |
| [`src/geotransfer_gap/cli.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/cli.py) | Dispatches `run` to `execution.main`; no top-level CLI redesign is needed. | Add new selectors within `execution.py`, not a second public entrypoint. |
| [`runtime/session.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/runtime/session.py) | Canonical `evaluation_env`, scene alias and `frame` state extraction. `control_evaluation`, continuous 2D action, 0.1-s timestep, 91-frame scenes. | Import rather than copy; place trace *extensions* in separate module. |
| [`runtime/hybrid_traffic.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/runtime/hybrid_traffic.py) | A deterministic `release_schedule` with source speed/displacement/5-sample sustained departure. `apply` currently also writes native modes. | Reuse `release_schedule`, **do not call `apply` inside the new scheduler**, since ownership/mode writing must have one authority. Preserve its original semantics, including edge cases, for baseline parity. |
| [`runtime/background_route_intent.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/runtime/background_route_intent.py) | Native background-only source-informed IDM route prior, subject to a coverage guard. | Report as privileged traffic information. Verify it is never applied to ego as a source future or passed into PPO/SMART features. Don't call all traffic variants information-equivalent. |
| [`planners/faithful_smart.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/planners/faithful_smart.py) | `FaithfulSMARTPlanner` preserves all binary-order actors as context, map tokenization and causal source-velocity *at observed birth*. | Build role-specific wrapper/extension, with explicit target IDs, around this code. Do not rewrite representation or alter frozen ego output. |
| [`planners/probe_faithful_smart_closed_loop.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/planners/probe_faithful_smart_closed_loop.py) | Existing ego SMART baseline: steps 0–9 replay, append observed histories; step 10 onward SMART controls ego; traffic uses IDM/hold. | Freeze as oracle. New SMART wrapper must match history append, inference cadence, actions and event order. |
| [`planners/protocol.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/planners/protocol.py) | SMART producer/path and execution fingerprint registry. | Do not change old hashes just to add new controllers. Add separate controller-matrix execution provenance/fingerprint registry. |
| [`visualization/viewer.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/visualization/viewer.py) | Offline HTML viewer accepts saved traces, labels them by `report['planner']`, compares source/converted and rollout. | Extend trace metadata and viewer to show **ego and traffic controller** and per-actor ownership. Preserve existing trace readability and no-server design. |
| [`validation/scene_contract.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/validation/scene_contract.py) | Fingerprints audit dependencies and currently assumes the manifest's ego index is zero. | All production admitted scenes must remain unchanged. Test **nonzero ego indices with synthetic/US interface fixtures**, not by changing admitted scenes or weakening this gate. |
| [`validation/suite.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/validation/suite.py) | Isolated regression commands; already tests admission, re-entry, background routes/startup. | Add independent controller-matrix checks under `validation` and tests; don't replace source-admission checks with rollout checks. |
| [`artifacts.py`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/artifacts.py) | Portable schema-2 scene references, hashes, atomic JSON writing. | Reuse for all new run provenance. |
| [`tool_registry.json`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/src/geotransfer_gap/tool_registry.json) | Registry for 92 legacy tools and their destinations. | Do not force every new private module into historical registry; add only if it is an actual retained/public tool. |

### Upstream BehaviorBench-specific audit

- [`pufferlib/planning/policy.py`](https://github.com/boschresearch/behavior-bench/blob/master/pufferlib/planning/policy.py) defines `PPOPlanner`. It creates `Drive` + `LSTMWrapper`, handles checkpoint prefixes, calls `load_state_dict(..., strict=False)` with warnings, decodes discrete logits through 7 acceleration × 13 steering bins into normalized continuous outputs, and stores recurrent tensors at batch positions. Its batch behavior is **not actor-ID-safe** across reorderings or batch resizing; load success is **not proof of complete compatible weights**.
- [`pufferlib/planning/smart.py`](https://github.com/boschresearch/behavior-bench/blob/master/pufferlib/planning/smart.py) supports joint prediction but determines target actor indices using whether `obs` is 1-D or 2-D, assuming all non-ego actors in traffic mode. That violates explicit traffic ownership. It maps model predictions to binary-ordered actors and uses proportional control for normalized acceleration/steering; its current `HistoryBuffer` is per binary row and its forecasts may span births/gaps unless guarded.
- [`pufferlib/planning/idm.py`](https://github.com/boschresearch/behavior-bench/blob/master/pufferlib/planning/idm.py) directly sets native modes and IDM parameters. **Do not instantiate and use its mutating side effects** inside the new ownership contract; instead use its documented native binding semantics in the centralized action writer. `vec_set_idm_params` is environment-level while `vec_set_idm_target_velocity` is slot-based: use one compatible parameter set per episode, or explicitly reject contradictory role-specific global IDM parameters.
- [`pufferlib/ocean/drive/drive.py`](https://github.com/boschresearch/behavior-bench/blob/master/pufferlib/ocean/drive/drive.py) forwards raw arrays to the native environment; it does not establish that every policy output uses the correct dynamics. Validate action semantics against the **locally pinned C source/runtime**; no unverified acceleration/jerk assumptions.
- The upstream docs/README and weights have changed names across revisions. Use **the actual configured local checkout and `weights/simple_ppo.pt`**; pin its SHA-256 and inspect its checkpoint content before assuming architecture, action type, or normalization. Do not copy inference assumptions from an arbitrary upstream `master` revision.

## 2. Scope, combinatorics, and no-go boundaries

**Ego:** expert, idm, ppo, smart. **Vehicle traffic:** expert, idm, ppo, smart. Pedestrians, cyclists and parked/`mark_as_expert` actors remain replayed regardless of pair, and are context only for learned traffic. The ego must never be included in traffic targets.

| Ego \ Traffic | expert | idm | ppo | smart |
|---|---|---|---|---|
| expert | E/E | E/I | E/P | E/S |
| idm | I/E | I/I | I/P | I/S |
| ppo | P/E | P/I | P/P | P/S |
| smart | S/E | S/I | S/P | S/S |

These are the **16 immediate** cases. The **12 source_hold** cases are E/I, E/P, E/S; I/I, I/P, I/S; P/I, P/P, P/S; S/I, S/P, S/S. Source-hold with `traffic=expert` is a validation error. Source-hold describes a *source-informed controller startup policy*, not a fifth controller.

**Not in scope:** new data collection/conversion, admissions, conditioned PPO variants, a matched US-DE study, planner safety optimization, goal conditioning of SMART, source-future information in learned inputs, changing frame windows, retraining, or proving every encounter is preserved.

**US tests:** use the two existing reference roots by stable configured/artifact lookup, identified in `validation/probe_us_reference_parity.py` as `us_hybrid_1002fdc9826fc6d1` and `us_smart_negative_world_739e0513c6f7cfe8`; they are **interface references only**, not geographic-study controls. Preflight must verify that both exist locally and are the intended binaries.

## 3. Architecture: narrow additions, not a redesign

Preferred provisional files (names may be adjusted if a demonstrably better layout already exists in local checkout):

```text
src/geotransfer_gap/
  execution.py                     # Existing public run CLI; normalization and subprocess dispatch
  runtime/
    actor_index.py                 # NEW pure ID <-> binary <-> active slot and lifetime tracking
    startup_policy.py              # NEW pure immediate/source_hold policy; calls frozen release_schedule
    scheduler.py                   # NEW only writer of native modes/action slots; one env.step per tick
    episode_worker.py              # NEW isolated single-scene loop using session.evaluation_env/frame
    run_trace.py                   # NEW common trace/provenance/event schema and canonical comparisons
    # session.py, hybrid_traffic.py, late_spawn_runtime.py remain frozen by default
  planners/
    controller_api.py              # NEW Controller and action intent/observation contracts
    expert_controller.py           # NEW replay intent, no native side effects
    idm_controller.py              # NEW IDM intent/params, no native side effects
    ppo_controller.py              # NEW strict checkpoint/obs/decode + identity-indexed LSTM
    smart_controller.py            # NEW explicit target wrapper over FaithfulSMARTPlanner
    # faithful_smart.py, faithful_map.py, protocol.py remain frozen by default
  validation/
    controller_matrix.py           # NEW verification runner/report, independent of source admissions
  visualization/
    viewer.py, viewer.html         # Extend existing offline viewer, keep old traces readable
tests/
  unit/test_controller_*.py        # Pure synthetic, fast, no external BB needed where possible
  integration/test_controller_*.py # Controlled native fixtures and actual local models/scenes
```

Avoid `src/geotransfer_gap/execution/` unless migrating existing `execution.py` deliberately; a same-name module/package would be needless ambiguity. Avoid creating a new copy of `session.frame`, `hybrid_traffic.release_schedule`, SMART tokenizer, checkpoint wrapper or registry. New private modules need no legacy tool registry entry.

### Immutable observed `StepSnapshot`

Capture **one pre-step world state**, the corresponding observation matrix, the source-ID/binary mapping, current active slots, source-valid flags, and observed removal/collision/terminal status. Freeze or defensively copy observation buffers that the C engine overwrites on stepping. `snapshot.step` is the **pre-action observation frame**. Do not use future scene state from this snapshot except in an **explicit source-startup schedule** or preexisting **background-only IDM route prior** that is separately disclosed.

Keep two distinct identifiers:

- `SourceActorID`: stable source/Waymo track ID, unique in scene.
- `ActorKey = (SourceActorID, lifetime_generation)`: actual controlled lifetime. A later source-valid re-entry starts a new generation. Mapping to a current native slot is **recomputed every tick** from the state's `active_agent_indices`; never persist slots as actor identities.

The registry exposes `eligible_present_vehicle_ids`, `ego_id`, `replayed_context_ids`, `lifetime_begin/end` and `slot_for(key)` only for present/active controlled actors. Fail closed on duplicate IDs, duplicate active slots, out-of-range entity indices, non-ego traffic action, missing slot for a vehicle that is contractually controllable, orphan action, or overlapping owners. Distinguish source gap/removal from physics-permanent removal using native flags and source validity: **`removed=True` alone is insufficient**, because the corrected runtime retires source-gap actors and can respawn them. Never resurrect an actor permanently removed by physics.

### Controller contract

Implement small protocol(s) analogous to:

```python
class Controller(Protocol):
    role: Literal['ego', 'traffic']
    name: Literal['expert', 'idm', 'ppo', 'smart']
    def reset(self, episode_info): ...
    def observe(self, snapshot: StepSnapshot, visible_targets: frozenset[ActorKey]): ...
    def act(self, snapshot: StepSnapshot,
            eligible_targets: frozenset[ActorKey]) -> Mapping[ActorKey, ActionIntent]: ...
    def retire(self, actor: ActorKey, reason: str): ...
```

`observe` advances model state/history **once per observed tick** for actor lifetimes it owns, even during warmup and source hold; `act` produces intents **without writing to native arrays**. Do not call SMART `plan` and then separately append history for the same frame. Keep SMART ego and SMART traffic histories/forecast caches separate when both are selected; optionally share **immutable** loaded weights/codebooks. Use `ActionIntent` as a typed discriminated union: replay mode, IDM mode with config, or normalized two-component dynamics action with declared semantics. A replay/IDM controller returns no fake learning action. Explicit validation rejects unhandled targets.

### One tick, exactly one application

At pre-step frame `t`:

1. Read and snapshot native state/observations; resolve `ActorKey` and present controllable roster. Capture initial trace frame **once**, including status when terminal.
2. Determine effective owner for ego and each vehicle: warmup replay (`t<10`), source-hold replay (`t<release_t` for qualifying background traffic), otherwise the requested adapter; VRUs, parked/marked-expert actors always replay. The **declared adapter** stays configured while *effective movement owner* is temporarily replay; record both.
3. Notify each learned adapter of current observed state **once**. For PPO, pass the correct observation for every owned actor during replay warmup/hold to advance LSTM. For SMART, accumulate the actual observed history in the same cadence as the baseline; its warmup need not manufacture or execute predictions.
4. From this same snapshot, compute eligible ego and traffic actions. Explicitly include only assigned traffic vehicle `ActorKey`s. For SMART joint prediction, include represented context actors in the model, but filter the **output** by declared target IDs. For `ppo/ppo` maintain ego and traffic recurrent namespaces separately (shared immutable weights permissible).
5. Check every action key and value (finite, shape/units/range, source ID, generation). Build *one* native action array initialized neutral and a complete per-slot movement-mode plan (`dynamics=0`, `IDM=1`, `replay=2`, subject to local native confirmation). Apply native modes and IDM setup centrally, then do **one** `env.step(actions)`.
6. Record proposed/applied actions, modes, owner transitions, held/released events, survival/collision status, terminal reason. Repeat until source-horizon exhaustion or explicit terminal. No model updates from post-step state until the **next snapshot**.

**Off-by-one test:** source traces have 91 observations at 10 Hz, with 90 transitions between frames 0 and 90. Define CLI `--steps` unambiguously as observation frames or transitions and preserve historical public behavior; verify takeover at the action applied from `t=10` to `t=11` rather than inadvertently at `t=9` or after `t=10`. Record the last observation even if no further `env.step` is valid. Never step past the source recording merely to reach an arbitrary loop count.

### Actor lifecycles

- For a new source-valid episode/lifetime: fresh PPO h/c and SMART target/history eligibility, no inherited action/forecast; source velocity at **observed birth** may be used as in `FaithfulSMARTPlanner`.
- For any source validity gap, exit, collision removal or permanent disappearance: close the lifetime, remove PPO memory, invalidate SMART target cache/predictions; distinguish re-entry from forbidden resurrection.
- SMART history remains indexed by **stable binary actor index** for context, but per-actor discontinuities must have invalid masks and no stale trajectory tokens. If upstream history memory cannot clear one actor without disturbing context, use a targeted wrapper/invalidation mechanism and prove it with a gap/re-entry fixture; do **not** reset the entire SMART predictor on every birth.
- Reordering and batch resizing cannot change PPO actor memory or action in otherwise identical actor histories. Test both same-size reorder (the critical hidden bug) and different-size batches.
- When moving a vehicle from source replay to IDM, verify correct route creation after hold release. For PPO/SMART, verify `movement_mode=0` is not overridden by `idm_others`, source-expert flags or a birth-path native branch; test physical response, not only the flag setter.

### SMART and PPO behavior details

**PPO:** initial checkpoint `weights/simple_ppo.pt` resolved relative to configured local BB unless explicitly overridden. Fail if missing or inconsistent. Inspect checkpoint format, architecture `Drive + LSTMWrapper`, observation width/layout, 7×13 discrete action decomposition, any normalizers, reward-conditioning flags, and runtime dynamics from local BB source. Permit *documented* prefix normalization (`module.`, etc.), then require complete compatible learned policy + recurrent weights: assert all expected trainable parameters loaded, no unexpected learned keys or shape mismatch; strict load after normalization where possible. Treat non-model optimizer/metadata separately. Document expected/matched key counts, tensors, hashes and sizes. Use deterministic argmax. Decode to the native **normalized** acceleration/steering interface only after an independent physical action test; do not confuse 4 m/s² acceleration bounds with an already normalized action buffer or assume jerk-based dynamics. Compare logits, LSTM h/c and final actions for one stable actor against the pinned compatible upstream implementation; a tolerance may be used for *independent model calculations*, but acceptance process/episode parity is exact on the pinned environment. Use a batched forward with gather/scatter by `ActorKey`; no full-model instance per traffic actor and no batch-row-indexed persistent memory.

**SMART:** preserve `FaithfulSMARTPlanner` map/state adapter as the feature producer. Implement an explicit `target_keys`/binary-index mapping and **one joint inference over represented actors** per traffic controller/scene when prediction is due. Never infer the targets from observation-array dimensionality. Exclude ego from traffic actuation even in S/S. Make a usable forecast available **before** a newly eligible actor's first learned action; if the normal 5-step reprediction interval would skip a new actor, force a prediction refresh for that newly eligible actor (not a hidden neutral-action fallback). When target presence changes, invalidate stale forecasts without discarding valid histories for unrelated actors. Predictions for replayed VRUs/context are not written back to native actions. In S/S, keep role-specific mutable histories/cache separate and freeze greedy seed 0 on CPU for acceptance; optional shared weights must not couple mutable planner state. Add a future-mutation invariance probe for learned inputs.

**IDM:** use native mode. Log actual effective global IDM `min_gap`, `headway_time`, `accel_max`, `decel_max`, per-actor target velocity and source-informed background route flag/coverage. An **ego IDM** must not receive a source-informed background route; native ego routing differences are part of protocol. If ego/traffic both use IDM, assert their global IDM settings are compatible before execution.

**Expert:** role-independent native replay. `expert` ego with interactive traffic is required; all-expert is complete replay. Keep VRUs, parked and other `mark_as_expert` tracks as replayed context and report exemptions from eligible traffic target counts.

## 4. CLI and backward compatibility

New commands:

```bash
geotransfer run --scene SCENE --ego ppo --traffic smart
geotransfer run --manifest MANIFEST --ego expert --traffic idm
geotransfer run --scene SCENE --ego smart --traffic ppo --traffic-startup source_hold
geotransfer run --scene SCENE --preset smart_hybrid_baseline
```

- New `--ego` and `--traffic`: each `expert|idm|ppo|smart`.
- `--traffic-startup immediate|source_hold` (default `immediate`). `expert + source_hold` for traffic is invalid.
- Optional explicit `--ppo-weights`, `--smart-weights`, `--seed`, `--device` only if cleanly integrated with existing config; defaults pin CPU/seed 0 for acceptance. Do not add unneeded selectors.
- `--planner smart` (legacy) defaults to the original SMART+hybrid startup, even though the **new** `--ego smart --traffic idm` defaults to **immediate**. Legacy `--planner smart --traffic idm` stays immediate; `--traffic hybrid_startup` translates to IDM + `source_hold` in the legacy selector context.
- `--planner expert` remains all-actor replay; do not silently accept an explicitly contradictory new traffic selection. `--planner bb --diagnostic --bb-args ...` remains a distinct bridge.
- Distinguish omission from explicit flags when detecting conflicts. Reject conflicting selector combinations instead of allowing option-order wins. A preset must reject incompatible explicit overrides. Parse/validate **before** creating output directories and launching models.
- Keep `--scene` and `--manifest` mutually exclusive. Preflight manifest/binary hashes; source admission and SMART admission are **labels/evidence**, not a carte-blanche integration grant for new traffic controller pairs.

Add CLI parse/normalization tests for default new/legacy behavior, explicit alias, all invalid combinations, `--bb-args`, manifest path and missing checkpoint errors. The legacy baseline should still use the same original runner path until parity has been demonstrated; on migration, preserve its trace contract.

## 5. Verification ladder — integration correctness, not safe driving

### Gate 0 — provenance freeze and preflight

- Save Git head/dirty status, local BB head/dirty status, C runtime source hash, config ini, Python/PyTorch/Numpy, model/device, CPU thread settings, data/codebook/checkpoint hashes, original 16 scene refs and both US roots. Do not modify inputs during run/view.
- Run existing pytest + `geotransfer check all`, migration conversion/execution, SMART input and baseline as locally available. Capture legacy SMART/hybrid action and meaningful-state traces, release schedules, source admission statuses and a clean baseline manifest under `runs/` (do not write into `testing/`).
- For fresh-process baseline, hash/canonicalize each sequence and state; include missing data status rather than inventing a successful pass.
- Check that local assets really exist; user says they do, but public repository cannot establish local state.

**Pass:** documented pinned baseline; all source inputs unmodified; missing or failing checks explicit. Failure blocks any claim of unchanged baseline, but not all isolated unit development.

### Gate A — interface/controller fixtures

Use bounded non-model and independent-reference fixtures for: mapping (nonzero ego, same-size slot reorder), native 0/1/2 modes, expert replay, IDM braking/headway and route initialization, acceleration/steering direction/scale/saturation vs jerk, finite observation/action, snapshot immutability, neutral action handling, PPO strict load, upstream PPO logits + recurrent state, SMART map/state token equality, SMART explicit traffic-only outputs and context isolation, no future inputs. Test model weight mismatch by deleting a recurrent key and corrupting one shape; **both must fail**.

**Pass:** correct execution and physical interpretation. Unsafe or wrong-way driving alone does not fail.

### Gate B — startup / birth / re-entry / ownership

Cover warmup boundary 9→10, late birth during warmup and after, source gaps/re-entry, permanent collision removals, no resurrection, late new active slot, identical-sized slot reorder, count changes, all-role reset/reuse, terminal-on-warmup, held release, never-release-before-source-horizon, move from replay→IDM/PPO/SMART, and mixed S/S + P/P ownership. Assert exactly one effective owner per present controllable actor, exactly one native step per tick and zero actions to context-only actors. Test held PPO memory advances; held SMART histories advance. No action from a stale prediction on first release.

**Pass:** no leaks, stale target IDs, unintended IDM/expert override or ownership misapplication.

### Gate C — 28 configurations × 18 roots

For **each** selected scene/reference, generate all valid matrix entries *programmatically from the protocol spec*, not a hand-picked success list. Seed 0; pinned CPU; PPO argmax; SMART greedy; no stochastic traffic. Individual 504 runs **each in a fresh scene subprocess**. Repeat the same 504 as a manifest/batch invocation that *also spawns one fresh process per scene*. Compare per-episode canonical action/mode/event/meaningful-state sequences with **exact equality**, excluding only non-semantic run names, wall time and absolute output paths. Use a stable comparison schema and deterministic JSON serialization; never mask meaningful physics differences via rounding. Verify the 16 original scene definitions' source and binary hashes before and after.

If an ego is terminal before a held traffic vehicle's scheduled departure, record `release_not_observed_due_to_terminal` rather than misreporting the transition as tested. Separate dedicated fixtures must prove every release path. Each run records complete trace and an explicit terminal reason (collision, offroad, ego gone, horizon, etc.). Worker crashes / OOM / exception / missing trace are integration failures, with partial logs preserved. Continue through the whole matrix for diagnosis unless an explicit fatal setup error invalidates all work.

**Pass:** exactly 504 valid episode records, 504 matching repeat records, no integration failures or unexplained nondeterminism. Planner crashes are failures; collisions, poor progress and goal misses are behavioral outcomes, not failures.

### Gate D — inspectability and claims

Viewer source/converted/expert/SMART files remain readable. For new traces show `ego=...`, `traffic=...`, `startup=...`, per-actor declared/effective ownership, source ID, held/released events, dynamics modes and termination; never show just `planner=SMART` for PPO ego. Display four distinct validity dimensions:

1. **Integration validity:** compatible loaded model + correct inputs/memory/actions/lifecycle.
2. **Original source admission:** independent source/technical/semantic/SMART evidence, with exact gate hash and original scope (do not manufacture approvals).
3. **Task preservation:** whether the particular traffic run retains its task-defining event, judged using outcome-independent pre-specified interaction criteria; **do not filter by ego planner success**. Some task assessments may remain indeterminate.
4. **Driving outcomes:** collision type/partner, wrong-way, offroad, progress and goal, with no implicit failure-to-integrate classification.

**Pass:** every configuration inspectable, uncertain evidence marked unknown, counterfactual traffic changes visible; no overclaim of cross-geography performance.

## 6. Expected machine-readable artifacts

Use `runs/` only; scene inputs and admission/evidence under `artifacts/.../testing/` stay immutable. Example outline (adapt exact fields to existing schema):

```text
runs/<run_id>/
  run.json                          # top-level requests, statuses, results, completed/failed summary
  matrix.json                       # protocol and exactly 28 configuration definitions
  verification_matrix.json          # exactly 28 × 18 rows with gate statuses + repeat parity
  environment.json                  # code/runtime/BB/dependency versions and hashes
  <scene>/<config_id>/
    provenance.json                 # controller/checkpoint identities, info access, route prior, startup, seed
    trace.json                      # state frames and per-actor ownership (backward-readable with viewer)
    actions.json                    # keyed proposed/applied native actions, modes, actor lifetimes
    events.json                     # births, gaps, holds/releases, terminations, collisions
    execution.log                   # stdout/stderr and diagnostic failures
    verification.json               # interface/lifecycle/execution results, missing/unknown evidence
  summary.md                        # integration / source admission / task / outcomes separated
```

Use stable scene ID + config ID: `e-smart__t-ppo__startup-source_hold`. Each report distinguishes `controller_requested`, `controller_effective`, `source_actor_id`, `binary_index`, `slot`, `lifetime_generation`, `action_semantics`, `held_release_step`, `source_future_prior` and `learned_observation_access`. Document model hashes/architecture/normalization/strict-load key counts, C runtime hash, ini and BB SHA, GPU/CPU, thread count, seed, inference mode, warmup. Do not retain proprietary scene content in Git.

`verification_matrix.json` row fields should include: scene/ref ID, source domain label (German or US interface reference), pair/startup, passed interface/lifecycle/execution checks, single/batch hash equality, observed release fixture coverage, termination, behavioral outcome summary, task suitability (yes/no/unknown with independent reason), original source admission/ref, file paths and exception/missing evidence. `passed` cannot be true with an unexecuted mandatory test.

## 7. Ordered implementation and **micro-commit** milestones

**All commits** should include appropriate tests/doc updates and a succinct verification note; run fast unit tests after each, relevant integration after each adapter, full regressions at milestone boundaries. Commit only when tested; if local assets block a test, report it as blocked, do not label passing and do not commit a false certification.

| Stage | Suggested micro-commits (short, reviewable) | Exit gate |
|---|---|---|
| M0 — Freeze | `test: record legacy SMART hybrid execution oracle`; `docs: pin runtime and controller protocol inventory` | Baseline hashes, CLI/source audit, 16 scene identities unchanged |
| M1 — Public contract | `test: specify new and legacy run CLI selections`; `feat: normalize run protocols and reject conflicts` | CLI protocol unit tests, old invocation intact |
| M2 — Actor identity | `feat: add immutable step and lifetime identity mapping`; `test: cover source gaps slot reorder and removal` | Pure mapping and snapshots tested, no native changes |
| M3 — Scheduler skeleton | `feat: add controller intents and replay IDM adapters`; `feat: add single-writer episode scheduler`; `test: verify expert IDM all-role combinations` | One step/action writer, warmup, E/I pairs, native checks |
| M4 — PPO compatibility | `test: specify checkpoint/observation/action reference fixtures`; `feat: implement strict PPO loader and normalization`; `test: verify native actuation and upstream PPO parity` | Mandatory A/PPO gate |
| M5 — PPO multi-actor | `feat: add identity-lifetime indexed PPO recurrence`; `test: cover reorders reentry and held memory`; `feat: enable PPO traffic and PPO mixed roles` | PPO traffic and P/P correct, B gate |
| M6 — SMART traffic | `feat: add explicit-role SMART traffic target adapter`; `test: verify context-only and joint-target forecasts`; `fix: handle new eligibility and stale SMART forecasts` | SMART ego unchanged, traffic joint identity, S/S and P/S |
| M7 — Holds | `feat: reuse source hold policy for IDM PPO SMART traffic`; `test: cover three hold release paths and no-departure` | 12 variants implemented, legacy schedule untouched |
| M8 — Batch/provenance | `feat: isolate all scene runs and persist failed attempts`; `feat: write typed controller provenance and common traces`; `test: verify 28-case enumeration and repeat parity` | 28 enumerated, full preflight and canonical comparison |
| M9 — Viewer/acceptance | `feat: show ego traffic owners and release events in offline viewer`; `test: run 504 plus 504 acceptance executions`; `docs: publish reproduction and four-tier validity report` | Matrix complete, exact parity, baseline identical |

Aim **22–26** narrow commits if necessary; table is minimum guidance, not a quota. Never merge a stage that fails its gate. Add small fix commits instead of hiding failures in a huge final cleanup. At each milestone print SHA, changed files, verification commands/results, baseline status, next known risks. Never rewrite published history or amend old commits unless expressly requested.

## 8. Specific regression hazards and resolution rules

1. **Audited-file drift:** if touching `session.py`, `faithful_smart.py`, `hybrid_traffic.py`, `protocol.py`, `scene_contract.py` or native build, first quantify which admission/SMART proofs fingerprint it. Changing a filename/producer hash may make admission stale even if behavior is identical. Prefer wrappers. Do **not** "fix" the gate by removing file checks.
2. **PPO batch memory:** upstream batch of equal size can swap cars without changing tensor shape. A batch-size-only reset test is insufficient; identity permutation tests are mandatory.
3. **PPO loading:** upstream `strict=False` logs missing recurrent keys. A policy yielding finite logits with omitted LSTM weights is not a validated PPO policy.
4. **Action units:** upstream PPO emits normalized values; SMART P controller emits normalized acceleration/steer. Native classic vs jerk and C limits must be independently measured in fixtures. A car moving forward is not enough.
5. **SMART target ambiguity:** array-shape-based targeting can control unintended context including the ego. Pass explicit target identities, not implicit `N-1` indices.
6. **SMART re-entry:** old forecasts may remain valid for the binary row while the source actor has a new lifetime; force fresh forecast before actuation, clear target-specific prediction/historical validity.
7. **IDM native overrides:** verify effective movement modes before and *after* C stepping; `idm_others` and native birth/expert path can supersede a learned action. Surface all such mismatches.
8. **Native hold release:** when a held actor switches to IDM, route construction/params may be missing if native route initialization occurred only at birth. Test transition physics.
9. **Actor classification:** `mark_as_expert` may include non-VRU vehicles; keep them replayed, report exemptions, and do not silently score them as SMART/PPO controlled.
10. **Original admission vs tested pair:** a scene SMART-admitted for old `hybrid_startup` cannot be declared scientifically admitted for PPO/SMART traffic because the new loop ran correctly.
11. **Preservation vs traffic realism:** reactive traffic can destroy the original task; evaluate preservation independently from ego planner outcome and retain result as inspectable.
12. **Terminal-aware coverage:** running a configuration is not the same as observing each lifecycle or hold transition; prove transitions with targeted fixtures even if a scene ends early.
13. **Run completion:** current `execution.py` stops on failed child (`check=True`) and may lack complete failed-attempt metadata. The new batch executor must preserve failure status/logs per episode and keep aggregate counts trustworthy.
14. **Historical expert semantics:** original all-expert `execution.replay` used parent-process stepping and a special trace format. New role-independent expert must be verified against that oracle, not simply assumed equivalent.
15. **Warmup inconsistency:** do not feed SMART future-source trajectories to generate warmup actions; preserving append-only observed history may be essential for exact SMART baseline equivalence, while PPO consumes warmup observations to initialize recurrence.

## 9. Final acceptance checklist

- [ ] Public CLI implements all selectors/aliases and preserves `--planner bb` diagnostic bridge.
- [ ] Four adapters are reusable for either role; one scheduler owns all movement-mode/action writes and one step per tick.
- [ ] All controller inputs are pre-step/causal except explicitly logged route/hold priors, never learned-model future leakage.
- [ ] All PPO learned and recurrent weights load compatibly, exact upstream reference tested, action interpretation verified, actor identity recurrence tested.
- [ ] SMART traffic controls only explicit targets, shares scene context, handles births/gaps, and preserves old faithful ego execution.
- [ ] Source hold works for IDM/PPO/SMART traffic, and replay-to-learned transitions are observed in fixtures.
- [ ] Nonzero ego indices, slot changes, same-size swaps, gaps, re-entry and permanent removals have direct tests.
- [ ] 16 German scene files unchanged; two US interface roots pinned; all 28 case definitions exactly enumerated.
- [ ] 504 single executions and 504 fresh-process batch repeats completed with exact meaningful parity; failures/outcomes explicitly classified.
- [ ] Frozen SMART+hybrid baseline action/state/trace contract preserved; previous checks/admissions are current or explicitly marked stale and revalidated.
- [ ] Viewer labels true ego×traffic roles, hold/release events and source/learned context correctly.
- [ ] Machine-readable matrix, reproduction instructions, pinned source/checkpoint/runtime hashes and four separate validity fields delivered.
- [ ] No model's unsafe driving silently marked an implementation failure; no failed implementation incorrectly passed; no overclaim of geographic transfer.
- [ ] Small reviewable commits, each with tests/evidence, no unnecessary code duplication and no edits to external BB.

## 10. Source reading list for Codex (locally installed versions take precedence)

- Project [`README.md`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/README.md), [`docs/architecture.md`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/docs/architecture.md), [`docs/migration.md`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/docs/migration.md), [`docs/commands.md`](https://github.com/imendezval/geotransfer-gap-AD/blob/main/docs/commands.md).
- Project `src/geotransfer_gap/{execution.py,cli.py,artifacts.py,config.py}`; `runtime/{session.py,hybrid_traffic.py,background_route_intent.py,late_spawn_runtime.py}`; `planners/{faithful_smart.py,protocol.py,probe_faithful_smart_closed_loop.py}`; `validation/{scene_contract.py,suite.py,probe_us_reference_parity.py}`; `visualization/{viewer.py,viewer.html}`; unit/integration tests and `configs/example.toml`.
- Actual local external BehaviorBench commit: `pufferlib/planning/{policy.py,smart.py,idm.py,registry.py}`; `pufferlib/ocean/drive/{drive.py,drive.h,binding.*}`; `pufferlib/ocean/torch.py`; `pufferlib/models.py`; `pufferlib/config/evaluation.ini`; `pufferlib/evaluation/evaluator.py`; checkpoint dictionaries/keys.

**Important epistemic boundary:** this plan is based on inspected public code. It cannot prove the user's private checked-out BB revision, binary scene set, checkpoint tensor format or native test results. Codex must validate those **locally** in M0/M4 and truthfully report any mismatch. No acceptance box may be checked merely because the task appears in this document.
