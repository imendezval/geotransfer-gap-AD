# Codex execution prompts — GeoTransfer 28-configuration controller matrix

Use this alongside [`GEOTRANSFER_CONTROLLER_MATRIX_PLAN.md`](./GEOTRANSFER_CONTROLLER_MATRIX_PLAN.md). The plan is authoritative for scope, architecture, acceptance and research validity. **All prompts assume Codex is running in the user's actual local repository with external datasets, BB checkout and checkpoints configured.** No prompt authorizes changing the external BB tree, regenerating research admissions, changing source scenes, hiding failures, or claiming execution results without actually running them.

## Recommended working method

**Use multiple bounded sessions**, not one enormous `lunaxhigh` session. The implementation has coupled correctness obligations (native modes, actor lifetimes, recurrent tensors, SMART multi-target prediction, hash-sensitive admissions). A single long session risks accumulating unjustified assumptions and merging many moving parts before test evidence. Use one or two stages per session **only after stage-gate reports are written**. The same conversation can be continued for small adjacent subtasks, but do not expect a 28×18 matrix acceptance test to be a useful debugging loop for unfinished PPO/SMART adapters.

Each stage prompt below is intentionally complete enough to start a **new** Codex session. At stage boundaries, maintain `runs/controller_matrix_work/handoff.md` (ignored output) with: current base SHA, new commits, changed files, verification commands/pass/fail/blocked counts, baseline comparison, unresolved risks and exact next stage. The *plan document itself* remains version-controlled if copied into `docs/` by the user; don't repeatedly rewrite it to make deviations look planned.

### Universal instruction (prefix for every stage)

Copy or reference this paragraph before the stage prompt if continuing in an unfamiliar chat:

> You are implementing the controller matrix in `geotransfer-gap-AD`. Read `GEOTRANSFER_CONTROLLER_MATRIX_PLAN.md`, `CODEX_STAGE_PROMPTS.md`, `README.md`, `docs/architecture.md`, `docs/migration.md`, and the relevant local Python/C source **before editing**. Inspect `git status` and the last stage handoff. Prefer extending existing modules through narrow, tested wrappers; do not duplicate source validation, SMART tokenization, release schedules, native environment setup, or trace parsing. Treat files hashed into scene/SMART admissions as frozen by default. Do not edit the external BehaviorBench checkout. Keep each commit small and backed by tests. Stop at this stage's exit gate. Distinguish VERIFIED, FAILED and BLOCKED (missing local data/assets); never infer passing from code review. Show exact files changed, commands executed, results, newly created commit SHAs and remaining risks. No changes to the 16 scene definitions, source evidence or time windows. Report any reason you must deviate from the spec *before* implementing the deviation.

---

## Session 0 / M0 — Inspect locally, freeze ground truth, no redesign

**Copy to Codex:**

> Start with a forensic, **read-only** audit of the current local checkout and the configured external BehaviorBench. Pin `git rev-parse HEAD`, dirty status, `python -V`, torch/numpy/BB hashes, runtime source hash, eval INI hash, the original 16 scene source JSON/binary/manifest hashes, 2 US reference roots, SMART checkpoint/codebooks and the `simple_ppo.pt` SHA. Inspect `execution.py`, `runtime/session.py`, `runtime/hybrid_traffic.py`, `runtime/late_spawn_runtime.py`, `planners/faithful_smart.py`, `planners/protocol.py`, `validation/scene_contract.py`, viewer and tests. Confirm all claims in the plan against the **local** revision; enumerate discrepancies without silently adapting the spec.
>
> Run existing `pytest -q`, `geotransfer check all`, migration conversion/execution checks, and appropriate SMART/hybrid 16-scene baseline commands where assets permit. Snapshot legacy single and manifest/batch SMART-hybrid actions, meaningful state, release schedule and original trace hashes **under `runs/`**, not in `artifacts/.../testing/`. For every baseline check, record the exact command, pass/fail/blocked status and artifact path. Make a durable baseline index with scene ID, binary hash, native runtime hash, checkpoint hashes, action sequence hash, meaningful-state hash, trace and controller configuration. Do not claim the baseline is frozen unless these records exist. Preserve the current legacy commands as an oracle for later parity.
>
> Also inspect local BB `pufferlib/planning/policy.py` and the checkpoint tensor keys/architecture without unsafe arbitrary pickle execution; use only trusted existing local checkpoints in this isolated research environment. Document any observed `.load_state_dict(strict=False)` behavior, recurrent tensor shapes, observation layout and action bounds. Do not yet implement the scheduler. Commit only small **test/provenance** artifacts that contain no licensed data and are appropriate to Git; keep run data ignored. Produce the handoff with a dependency/impact map of every hash-sensitive module.
>
> **Exit:** source inventory and baseline reproducibility are documented. If an expected asset/check fails, say precisely what is blocked. Do not continue automatically to M1.

**Review before proceeding:** Does baseline freeze actually reproduce the original SMART/hybrid behavior? Are there scene/admission hashes at risk? Does the local checkpoint differ from upstream assumptions?

## Session 1 / M1 — CLI selector contract and backward compatibility

**Copy to Codex:**

> Implement only the CLI protocol layer in `src/geotransfer_gap/execution.py` (plus focused pure helper module only if necessary). The spec is in §§2/4 of `GEOTRANSFER_CONTROLLER_MATRIX_PLAN.md`. Add new `--ego` and `--traffic` choices (`expert,idm,ppo,smart`) and `--traffic-startup` (`immediate,source_hold`; default immediate), preserving old `--planner smart` hybrid-startup default, `--planner expert` all-expert replay, `--planner smart --traffic idm` immediate and `--planner bb --diagnostic --bb-args` behavior. Legacy `--traffic hybrid_startup` maps to IDM+source_hold only in the legacy context. Add optional `--preset smart_hybrid_baseline` as an exact alias. Detect whether flags were explicitly provided; reject contradictions, unsupported hold-with-expert, and conflicting old/new selection rather than using silent precedence.
>
> Preserve current execution functions temporarily: do not implement an alternative simulator loop or change baseline routing. Introduce a typed, immutable `RunProtocol` that can later be passed to a child. Keep scene/manifest selection and `--diagnostic` semantics explicit. New pair requests may currently produce an honest `NotImplementedError` or clear "not yet integrated" error; **never** silently dispatch PPO/SMART traffic to the old SMART/hybrid runner. Tests should enumerate all 28 valid configurations and invalid combinations, legacy default behavior, named baseline, BB bridge passthrough, user-facing help, and no output directory creation on invalid CLI.
>
> Split into two reviewable commits: selector tests; protocol normalization/CLI implementation. Run unit tests and existing legacy invocation smoke checks. Do not modify `cli.py`, hash-sensitive files, checkpoint logic or viewer unless essential and explained. Write a handoff and stop.

**Review:** New `--ego smart --traffic idm` must differ intentionally from legacy `--planner smart` in startup default. Old expert must still mean full replay.

## Session 2 / M2 — Single identity model + snapshot, with adversarial fixtures

**Copy to Codex:**

> Implement `runtime/actor_index.py` and a minimal immutable pre-step snapshot type (in a new module), without altering `runtime/session.py`. The snapshot must copy the BB observation buffer and observe native entities/active indices **before each step**; identify `SourceActorID`, fixed binary index, current active slot, source-valid presence, controller eligibility, and `(source_id, lifetime_generation)` state. There is only one actor-ID→slot mapper, used by both roles, modes and tracing. Recompute active slots every tick; never use batch position as persistent identity.
>
> Create deterministic synthetic tests for: ego at binary index 4; missing or duplicated source IDs; late actor birth, absence, gap/re-entry, permanent physics removal versus temporary source-gap retire; a same-length swap of actor slots; count change; disappearance after collision; repeated episode reset; parked and VRUs as context. Check the corrected C runtime/source lifecycle logic if necessary, but do not modify it yet. Flag that `removed=True` may mean source-gap retirement, so use source-valid masks and native removal reasons rather than marking every removal permanent. Add snapshot immutability/mutation tests.
>
> Commit the identity type and tests separately. Run all fast tests plus the relevant re-entry existing checks. No learned-model integration yet. In the handoff, show exact slot mapping samples for the nonzero-ego and re-entry fixtures, and prove the original 16 binaries were not edited.

**Review:** Actor identity must survive even when the number of active vehicles stays constant but their slots swap.

## Session 3 / M3 — Side-effect-free expert/IDM adapters and one scheduler

**Copy to Codex:**

> Implement a small controller contract in `planners/controller_api.py`, `expert_controller.py` and `idm_controller.py`, and **one** native action/mode writer in `runtime/scheduler.py` plus one `episode_worker.py`. Reuse `runtime/session.evaluation_env`, `runtime/session.frame`, local BB binding and the new `actor_index`—do not copy their logic. Expert and IDM controllers return typed intents, and neither calls `vec_set_movement_mode` nor `env.step`. The scheduler derives warmup replay for every actor steps 0–9, applies per-actor modes every tick (including births), writes one neutral-initialized action matrix and calls `env.step` once. Keep replayed VRUs, parked, `mark_as_expert` vehicles passive and visible as context; traffic never controls ego.
>
> Test `expert/expert`, `expert/idm`, `idm/expert`, `idm/idm` with independent native fixtures, including source hold *disabled* for now. Verify no controller can overwrite a slot owned by another, every present controllable vehicle has a mode, IDM parameter initialization occurs, IDM and replay physics truly respond as intended, and an ego IDM does not inherit the source-informed background-only route. Inspect `vec_set_idm_params`/target-velocity global-versus-slot scope; if the BB checkout allows only global IDM dynamics parameters, enforce compatible settings instead of pretending independent per-role params work. Test the `t=9`/`t=10` takeover and 91-observation/90-transition boundary explicitly. Retain the legacy baseline runner as the oracle until exact parity is proven.
>
> Make 2–3 micro-commits: controller contract and adapters; scheduler worker; native fixtures. Run unit+native smoke; verify source/binary hashes unchanged. Stop and provide handoff before adding PPO.

**Review:** "One scheduler" means literally one place writing modes/slots and one `env.step` per observed action tick; no hidden side effect in adapters.

## Session 4 / M4 — Strict PPO checkpoint/interface/physics proof (ego only)

**Copy to Codex:**

> Implement the **PPO interface audit** against the exact local `weights/simple_ppo.pt` and BB revision first. Compare key names, shapes and total trainable weights against the intended `Drive + LSTMWrapper` (or the actual local architecture); check for prefixes, observation dimension/field order, any normalization, `reward_conditioning`, classic versus jerk dynamics, discrete logits (7 accel × 13 steer where applicable), and how continuous native actions are normalized. Never accept `strict=False` warnings as successful loading: strip only documented prefixes, exclude non-model metadata, then require complete compatible learned **and LSTM** weights. Add fixtures for missing LSTM key, unexpected learned key, shape mismatch, wrong observation width, non-finite obs, inconsistent action space. Every case must fail loudly with a useful error.
>
> Add `planners/ppo_controller.py` limited initially to ego stable actor. Advance its recurrent memory with every *observed* warmup frame, discard warmup actions, then use argmax from `t=10`. Compare intermediate PPO logits, recurrent h/c and decoded actions against a trusted local upstream implementation on identical fixed observations and initial hidden state. Verify action response on controlled straight-driving, braking and left/right steering native fixtures, distinguishing normalized action slots from physical m/s² and steering. Do not simply check a vehicle moved. Use CPU, seed 0. Log checkpoint and model/access identity to a sibling provenance file without modifying SMART admission producer files.
>
> Split commits: failing contract fixtures; strict load/obs/decode; verified PPO ego integration. Run tests after each. Do not implement PPO traffic yet. If actual checkpoint architecture does not match, **stop and report evidence**; do not invent a coercion or silently use random weights.

**Review:** Checkpoint *completeness*, *semantics*, and *physical action effect* are three separate proofs.

## Session 5 / M5 — PPO traffic, identity-safe recurrent state and mixed roles

**Copy to Codex:**

> Extend the already validated PPO adapter to traffic targets. Maintain LSTM `(h,c)` by `(source_actor_id,lifetime_generation)`, not row position, using ordered gather/forward/scatter each tick. Keep ego PPO state and traffic PPO state independent even if immutable weights can be shared. Do not instantiate a policy for every vehicle. For held or warmup PPO-designated traffic, advance recurrent state from actual observed frames but **discard** action proposals while replay is effective. On gap/removal retire old h/c; re-entry starts zeros and a new generation. Recomputing action slots each step is the scheduler's responsibility.
>
> Test same-size permutations with distinct actor histories and verify identical keyed logits, h/c and actions; test growing/shrinking batches, birth/death, gap/re-entry, permanent collision removal, stable-actor upstream reference comparison and missing/duplicate IDs. Test P/P (both ego+traffic PPO) and E/P, I/P, S/P when feasible without changing the frozen SMART ego proof path. Audit actual native mode after `env.step` to catch expert/IDM override. Per-actor PPO observation shapes and input access must be recorded. The first rollout may be unsatisfactory driving; **do not tune policy, rewrite scene selection, or treat collision as an implementation error**.
>
> Make separate commits for identity memory, adversarial lifecycle tests, then traffic/mixed integration. Run model and native fixtures and reproducible pair smoke tests; stop with handoff.

**Review:** Reordering tests must use different actor histories (so row-swapped hidden state is observable) and preserve batch **size**, not just exercise resizing.

## Session 6 / M6 — SMART traffic with explicit targets, preserved faithful ego

**Copy to Codex:**

> Implement `planners/smart_controller.py` as a **thin adapter around** the existing `FaithfulSMARTPlanner`. Do **not** copy or refactor `faithful_map.py`, `faithful_smart.py` or the old SMART closed-loop diagnostic without a demonstrated necessity and a controlled admission-hash impact review. The SMART traffic adapter must accept explicit target `ActorKey`s/binary indices and run **joint autoregressive prediction** over all represented actors as context. Use the existing map preprocessing, stable binary index, causal observed-birth velocity, past-only trajectory histories, greedy inference and original 5-step cadence. Convert predicted trajectories to actions **only** for target vehicles; ego, VRUs, parked, expert background and held/replayed traffic are context, not SMART-controlled.
>
> Build a lifecycle-aware prediction cache keyed by actor lifetime/generation and prediction timestamp. On gaps and removal, clear stale targets. A newly eligible actor (birth or source-hold release) must have a fresh usable forecast **before** its first SMART dynamics step; schedule an explicit inference refresh if needed, never silently return zero action and declare a pass. Maintain separate mutable SMART state for ego and traffic when S/S; share only immutable model weights/codebooks if proven equivalent. Do not give either learned model recorded future source data. Check future-mutation invariance of model inputs against modified *future* source traces, except the separately declared hold prior.
>
> Make a frozen-baseline comparison for SMART ego with hybrid/IDM before and after every change. Test explicit traffic target subset with context actors, nonzero ego index, multiple traffic targets, batch ordering, late birth, re-entry, held release, S/S and P/S; validate role and native movement modes. Do not weaken an existing SMART admission gate to make results appear admitted. Split commits: role-target wrapper; joint inference/target fixtures; lifecycle cache; mixed-role regression. Stop with handoff.

**Review:** Passing `obs.shape=(N,D)` to upstream `SMARTPlanner.plan` alone **does not** implement correct traffic ownership.

## Session 7 / M7 — Generalize original source-hold schedule to 3 traffic controllers

**Copy to Codex:**

> Create a small pure `runtime/startup_policy.py` that delegates to existing frozen `runtime/hybrid_traffic.release_schedule` and translates `immediate`/`source_hold` into per-tick effective replay-or-target ownership. **Do not rewrite the sustained-departure algorithm** or "fix" its thresholds as part of this task: its original semantics are the baseline oracle and source future information is an explicit traffic policy prior. Use the same release schedule for IDM, PPO and SMART. The learned controller must still observe every held present actor at each step; only its proposed action is discarded while replay movement mode is effective. On release, use the correct actor lifetime, pre-step observation, native route/mode and non-stale model state. Reject source-hold with traffic expert and log per-actor release or never-released reason. The original `--planner smart` / `hybrid_startup` stays exactly equivalent.
>
> Target all 12 hold configurations in unit-level enumeration, but use directed native fixtures for all three transition types: hold→IDM, hold→PPO, hold→SMART; late birth + hold; no sustained departure; source-valid gap; release when scene terminates early; parked/VRU exemption. Compare exact original baseline release steps, actions and meaningful-state traces. Verify learned histories advance while held and no action leaks into source replay. Avoid touching `hybrid_traffic.py`, `session.py` or C patch; if native route creation at late IDM release is wrong, isolate a minimal fix, **stop for impact review** and rerun all admission/baseline regressions.
>
> Split commits into policy reuse, transition tests, integration; stop with handoff.

**Review:** A hold release that is scheduled after the ego terminates was **not observed** and cannot count as native transition coverage.

## Session 8 / M8 — Fresh subprocess orchestration, provenance and exact parity machinery

**Copy to Codex:**

> Finish `execution.py` as an orchestrator: every scene, including legacy expert and new pairs, executes in its own fresh child process. Keep BB diagnostic execution separate. Build a deterministic enumerator for **16 immediate + 12 held = 28** configs; refuse invalid hold/expert. For German corpus use the original portable manifest with unchanged names/roots/hashes; separately add the two US interface roots. A failed subprocess must produce durable per-episode `status=failed` and its log/exception, and batch orchestration must not pretend the matrix is complete when one row is absent. Source JSON/binaries/admission evidence stay read-only.
>
> Define a versioned trace/provenance format with actual requested/effective owner per actor, slot/binary ID/lifetime, warmup, holds/releases, 2D actions and semantics, model/key/checkpoint hashes, native runtime, route prior, seed, CPU/thread mode and terminal reasons. Use existing `artifacts.py` read/hash/write and existing `session.frame` rather than duplicating them. Keep legacy viewer inputs readable. Make a canonical per-step comparison containing meaningful state, action and event fields; explicitly exclude only run ID, wall time and absolute paths. Seed 0, pinned CPU, PPO argmax, SMART greedy. Include a small deterministic two-scene single-versus-batch test and report exact mismatches at `(scene,config,tick,actor,field)`. Include a provenance test for no model/source future access and unchanged source hashes.
>
> Split commits: reliable worker/failure reporting; trace+provenance schema; deterministic matrix/permutation compare. Provide a machine-readable `verification_matrix.json` with 504 expected slots initialized **not-run**. Do not mark not-run as pass. Stop with handoff.

**Review:** A batch call must be 504 **fresh processes**, not one process cycling across scenes with contaminated model state.

## Session 9 / M9 — Viewer, full 504×2 matrix and final acceptance

**Copy to Codex:**

> Extend the existing offline HTML viewer (`visualization/viewer.py` and only necessary template edits) to consume old expert/SMART traces and new pair traces. Display `ego=X, traffic=Y, startup=Z`; show per-actor source ID, model-vs-effective ownership (e.g. `PPO target / expert held`), startup release events, collisions and terminal reasons. Do not infer reactivity from a label and do not expose private licensed sources in Git. Test old trace backward compatibility and new mixed traces using fixtures.
>
> Execute the full **28×18=504** deterministic matrix, one fresh process per episode; then invoke the batch/manifest path as **504 additional fresh-process executions**. Require exact equality for every configuration's canonical action, ownership/movement mode, event and meaningful-state trace under pinned CPU with seed 0. Preserve worker crashes as integration failures with logs. Compare frozen SMART/hybrid baseline actions/state and verify all 16 original JSON/binary source hashes unchanged. Run entire existing pytest suite, `geotransfer check all`, migration checks and new controller checks. Report missing asset/runtime failures honestly; never mark 504 passed based on a partial run.
>
> Produce `runs/<run>/verification_matrix.json` with exactly 504 rows, aggregate success/fail/blocked, per-controller/per-scene report, rerun parity, and a `summary.md` that **separates** integration validity, original source admission, independent encounter/task preservation, and driving outcomes. A collision/goal miss can be a valid simulated result; missing obs/misapplied action is not. Do not filter out bad traffic scenes or redefine success to salvage the matrix. Write reproduction instructions, exact environment and checkpoint hashes and a concise list of unresolved scientific limitations. Split commits: viewer; acceptance harness/corrections; reproduction docs. Keep all original scientific evidence untouched.
>
> Stop at final acceptance and give a checklist with each gate PASS/FAIL/BLOCKED and evidence paths. Do not assert scientific geographic generalization.

**Review:** If any of the 504 single or 504 repeat episodes is missing, the project may be partially implemented but the matrix is **not yet verified**.

---

## Optional shorter continuation prompt after an interruption

> Resume the controller matrix implementation **only from the next uncompleted stage**, not from scratch. Read `GEOTRANSFER_CONTROLLER_MATRIX_PLAN.md`, `CODEX_STAGE_PROMPTS.md`, `runs/controller_matrix_work/handoff.md`, current Git status/log and all changed source files. Confirm exactly which gate was last verified, do not assume previously reported passes remain current after later code changes, and read the canonical baseline oracle. First run the relevant regression suite. Then execute the next stage prompt verbatim with narrowly scoped commits. At the end state the exact new commits, failed/blocked tests, unchanged-source hashes, baseline comparison and next handoff. Never continue into a subsequent stage without its exit gate.

## When to stop Codex and review personally

There are **four high-risk human review points** that justify a fresh session before proceeding:

1. **After M0:** real local checkpoint/runtime/scene inventory; verify no unsupported BB assumptions.
2. **After M4:** PPO load + observation/action semantics and physical-response proof, *before* multi-agent rollout.
3. **After M6/M7:** SMART traffic identity/history and release transitions; verify old SMART ego parity before batch expansion.
4. **After M9:** inspect the actual 504×2 report, explicitly separating wrong driving from invalid integration.

If time is limited, first finish M0–M4 robustly. A few controllers with correct interfaces are more scientifically useful than a fully enumerated matrix implemented on incorrect PPO recurrence or SMART target ownership.
