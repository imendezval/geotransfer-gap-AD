# Performance evaluation implementation results

This is the single handoff log for PE00–PE14. Normative metric definitions live in [`docs/performance_evaluation.md`](../../performance_evaluation.md). The scope, milestone, and prompt documents remain at their existing single-copy location under `docs/plans/performance_metrics/`; the initial prompts' `performance_evaluation/` location assumption did not match this checkout.

## PE00 — Baseline, reuse audit, and frozen definitions

**Status:** Definition/profile baseline complete. Native smoke has one failing probe; current admission inventory is blocked by stale evidence. No metric implementation or production-code change was made.

### Starting state and drift from planning review

- No applicable `AGENTS.md` and no prior `implementation_results.md` were present. This file establishes the shared handoff location.
- The planning review commit `504218cb9ecd7fd64d2952630b9f10f56d80f923` was the starting HEAD. I created branch `pe00/performance-evaluation-baseline`. Two owner-authored commits appeared on that branch during the session and were preserved: `658a279` adds regression cases for the US source-hold inputs; `0beb7d8` qualifies the exact original WOMD sources for the two US diagnostic fixtures. The final baseline HEAD is `0beb7d84d6b61357d6bbfa7b28c83cb72e08f95c`.
- The code drift is narrow: `runtime/matrix_inputs.py` now accepts the two US fixtures only when one exact original WOMD v1.3 source is found, its pinned hash matches, and the pinned upstream writer recreates the existing binary hash. `verification_matrix.py` imports those pinned identities from `matrix_inputs.py`. No evaluator, metric, runner, viewer, schema, or controller owner changed in these commits.
- Both WOMD source JSONs are available and hash-match the new constants. The committed parametrized source-hold tests passed in the final full pytest run (the fixtures yield 9 and 2 release entries). This expands source-hold protocol availability for two US **diagnostic** fixtures; it does not make them a matched geographic baseline.
- The three requested plan files are physically under `docs/plans/performance_metrics/`, not `docs/plans/performance_evaluation/`. They remain there without duplicate copies. New operational definitions and this results log link to their actual locations.
- Pre-existing untracked `.codex-attachments/` and `docs/plans/performance_metrics/` were preserved. No unrelated changes were staged or discarded.

### Repository-specific reuse map

| Existing owner | PE reuse decision |
|---|---|
| `cli.py` | Keep its lazy command dispatch; add evaluation dispatch only in its selected implementation milestone. |
| `execution.py`, `runtime/episode_worker.py` | Keep all orchestration and the single stepping loop. The worker already exposes a pre-step lifecycle capture callback; any future optional evidence capture extends it. |
| `runtime/session.py` | Keep the canonical environment and world-coordinate `frame()` representation. It records `time_s = step × 0.1`, present pose/velocity/footprint, native collision state, and ego goal state. It does not serialize partner/impact positions. Preserve this fingerprinted execution owner. |
| `runtime/actor_index.py`, `step_snapshot.py`, `scheduler.py` | Consume stable source IDs, lifetime generations, fixed binary indices, effective ownership, movement modes, and the per-step slot mapping. Never infer identity from active slot order. |
| `runtime/run_trace.py` | Preserve schema-3 matrix validation, schema-2 verification, strict live `validate_run()`, exact comparison, and all-package-Python fingerprints. Historical artifacts must be handled at a separate saved-evidence boundary, not by weakening this validator. |
| `runtime/matrix_batch.py`, `matrix_campaign.py`, `verification_matrix.py` | Read schema-4 durable run/attempt accounting and persisted campaign views. Do not add a scheduler/retry ledger. The fixed campaign inventory is not the general evaluation cohort builder; campaign freeze/report checks require a live matching revision/environment. |
| `artifacts.py`, `config.py` | Reuse finite atomic JSON writing, SHA-256, configured roots, portable references, scene lookup, and manifest resolution. Do not add another artifact/path framework. |
| `visualization/viewer.py`, `campaign_gallery.py`, `viewer.html` | Keep the existing viewer and gallery. Current viewer loading already checks attempt/campaign trace and verification hashes plus sidecar coherence. PE01 should extract those checks once for viewer/evaluator reuse and preserve viewer APIs/rendering. |
| `maps/lanelet.py`, `audit_scene.py`, `audit_rule_applicability.py`, `validation/audit_physical_source.py` | Reuse recording-specific map selection, projection/orientation/topology, pure polygon/oriented-box helpers, and supported source physical evidence. `box_distance()` already computes polygon gap. Keep source admission separate from rollout results. |
| `audit_following_scope.py`, `audit_task_rule_scope.py`, `audit_directed_rule_scope.py`, `audit_task_interactions.py`, `audit_interaction_fidelity.py` | Read source-only task/rule/following/conflict/fidelity certificates within their recorded scope. Assess encounter realization from each actual rollout; do not treat a source certificate as its verdict or as a waiver after route deviation. |
| Pinned BehaviorBench `evaluation/metrics.py`, `evaluator.py`, `collision_classifier.py`, `ocean/drive/binding.c` | Do not vendor the runner. Its metrics operate on live environment logs and contain `-1`/infinity sentinels and zero defaults. Its responsibility heuristic uses stopped/approach/lane-drift rules; its fallback partner search selects a projected nearest entity. These are not automatic GeoTransfer truth. The binding exposes `collided_with_index` and collision positions, but canonical traces omit them. Native `VEHICLE_COLLISION=1` and `OFFROAD=2` are distinct; native off-road is road-edge intersection, and the single collision state cannot prove simultaneous geometry. A later narrow optional adapter/capture path must state evidence limits. |

### Operational decisions fixed for PE01 onward

The normative decisions and profile are in [`docs/performance_evaluation.md`](../../performance_evaluation.md) and [`configs/evaluation/default.toml`](../../../configs/evaluation/default.toml), profile `geotransfer_p0_v1`, definition `1.0.0` (profile file SHA-256 `8e5a6dfc329b0c71f75ac4aca41000efea6699acc5726ac7cfc61863139fba55`). They settle:

- observation versus transition counts, 10 warmup transitions, attribution boundary at observation 10, and the full 80-transition/8-second primary window for a complete 91-observation rollout;
- raw state-based kinematics with explicit interval and adjacent-interval finite-difference stencils, support exclusions, owner/lifetime boundaries, and no smoothing/padding/interpolation;
- native collision/off-road events versus sampled footprint geometry and constant-velocity SAT TTC, partner/severity limitations, and explicit pair/coverage status;
- route progress versus travelled distance, separate native goal/task/encounter/safe-completion outcomes, horizon censoring, and nonconfirmed low-progress candidates;
- `valid`/`unavailable`/`not_applicable`/`undefined`/`invalid` assessment states, separate criterion outcomes, and archived-attested versus trace-only evidence;
- initial TTC, near-miss, comfort, stationary, low-progress, and cluster-bootstrap operating choices, including sensitivity values and their research-only status;
- sparse evidence-bound annotation requirements without copied manifest actor lists, source hashes, routes, or map geometry.

No real annotation was created. Shapely is not installed in the current environment. PE05 should reuse current Lanelet2/pure geometry helpers first; if robust polygon union/difference needs it, the definition allows only an optional `evaluation-geometry` extra, lazy and unrelated-command-safe.

### Baseline and verification

All generated verification output is local and ignored under `runs/pe00_baseline_20261122/`. The 896 MB artifact tree was copied to `recheck/artifacts/`; `check all` and both migration commands used that copy with `GEOTRANSFER_ARTIFACTS` and `GEOTRANSFER_RUNS` redirected beneath the PE00 run root.

| Command / check | Result |
|---|---|
| `.venv/bin/pytest -q` at HEAD `0beb7d8` | **PASS**, 328 passed, 1 upstream PyG deprecation warning, 36.69 s. Final-head output: `runs/pe00_baseline_20261122/pytest_current_head.stdout.txt`. An earlier run overlapped the two commits and is not used as the final baseline. |
| `.venv/bin/geotransfer doctor` at HEAD `0beb7d8` | **PASS**, exit 0, no configured source/BB/weight paths missing. Output: `doctor_current_head.stdout.txt`. |
| `GEOTRANSFER_ARTIFACTS=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/pe00_baseline_20261122/recheck/artifacts GEOTRANSFER_RUNS=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/pe00_baseline_20261122/recheck/runs .venv/bin/geotransfer check all` | **PASS**, all 13 checks: orientation, lane changes, background, map, route, directed rule, restart, following, task rule, queue, admission, re-entry, startup. Exact command/root summary: `check_all.status.json`; per-check log: `check_all.log`; result summary: `recheck/runs/checks/summary.json`. |
| `GEOTRANSFER_ARTIFACTS=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/pe00_baseline_20261122/recheck/artifacts GEOTRANSFER_RUNS=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/pe00_baseline_20261122/recheck/runs .venv/bin/geotransfer check migration conversion` | **PASS**, byte-identical JSON/binary/manifest conversions for all 16 scenes. Exact command/root/status: `migration_conversion.status.json`; output: `migration_conversion.log`. |
| `GEOTRANSFER_ARTIFACTS=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/pe00_baseline_20261122/recheck/artifacts GEOTRANSFER_RUNS=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/pe00_baseline_20261122/recheck/runs .venv/bin/geotransfer check migration execution` | **PASS**, exact legacy/new execution comparisons for all 16 scenes (actions, meaningful states, actor identity, prediction-input hashes). Exact command/root/status: `migration_execution.status.json`; output: `migration_execution.log`. |
| `matrix_campaign.fingerprint_environment()` | **PASS** at HEAD `0beb7d8`; BB `805fe04c6977b60c41c92c31f1a5211fbd704f44` clean; runtime source `beedf8f1b0e9c490`, native binary SHA-256 `bdf1a2cb70f4153a0283a45fe18920b09a545ecba15fdb335a87a31762b94d58`; SMART/PPO checkpoint and both codebook hashes match their pinned identities. Python 3.11.18, NumPy 1.26.4, Torch 2.5.1+cu121, Lanelet2 1.2.3. Full fingerprint: `matrix_environment_fingerprint.json`. |
| `.venv/bin/python tests/integration/probe_ppo_native.py --root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/artifacts/oriented_v3/r07_e200_f25439` | **PASS**. |
| `.venv/bin/python tests/integration/probe_ppo_traffic_physics.py --root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/artifacts/oriented_v3/r07_e200_f25439 --target-index 7` | **PASS**. |
| `.venv/bin/python tests/integration/probe_smart_controller.py --root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/artifacts/oriented_v3/r07_e200_f25439` | **FAIL** at `tests/integration/probe_smart_controller.py:94`, `StopIteration`: no traffic refresh at expected step 14. No code/input change was made to mask this probe failure. |
| `.venv/bin/python tests/integration/probe_smart_ego_reference.py --root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/artifacts/oriented_v3/r07_e200_f25439` | **PASS**. |
| `.venv/bin/python tests/integration/probe_smart_ego_reference.py --root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/artifacts/oriented_v3/r32_e391_f21356 --steps 4 --require-birth` | **PASS**, causal birth check. |
| `.venv/bin/python tests/integration/probe_source_hold_models.py --root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/artifacts/oriented_v3/r12_e151_f12041 --actor 137` | **PASS** for PPO/SMART hold and release readback. The `check all` startup regression also passed on the copied artifacts. All exact argv, exit codes, and per-probe log paths: `native_probes/summary.json`. |
| `.venv/bin/python -m geotransfer_gap.verification_matrix --output runs/pe00_baseline_20261122/current_matrix_inventory.json` | **BLOCKED**, exit 1 at `r00_e321_f21017`: current admission SHA differs from the pinned portable manifest. No inventory output was written. A final audit found 7 of 16 admission records differ; precise old/current hashes are in `current_matrix_inventory_status.json`. The 7 scene IDs are `r00_e321_f21017`, `r01_e280_f18833`, `r01_e301_f20017`, `r09_e136_f11030`, `r32_e391_f21356`, `r09_e196_f16232`, and `r15_e332_f25626`. No admission was regenerated or restored. |
| Fresh representative single/manifest matrix parity | **BLOCKED / not launched** because its required `build_matrix()` rejects the same stale admission hashes. No fresh episode or fixed 504-slot campaign was started. |

The pre-check protected-input snapshot contains 577 fingerprints (portable manifest, scene recipes, reviews, 555 files in the 16 scene `testing/` trees, SMART/PPO checkpoints, and SMART codebooks). The final comparison has 7 changed paths and no missing files; every changed path is one of the seven admission JSONs listed above. The other 570 fingerprinted inputs match the pre-check snapshot. The source/binary/review/config/checkpoint/codebook hashes are unchanged. Because the admission differences were observed in the shared artifact tree during this session and their cause is not established, the “protected admission inputs unchanged” gate remains **BLOCKED**; they were not edited by this implementation and were not repaired. Snapshots: `protected_inputs_before.json` and `protected_inputs_after.json`.

Existing archived evidence is present: `runs/m9_acceptance/campaign.json` (504 slots, frozen at `4706b42a0d6ea5a97b3e149dd32ddfdaeebeb804`) and `runs/post_m9_hardening/us_generation/campaign.json` (24 slots, frozen at `0beb7d84d6b61357d6bbfa7b28c83cb72e08f95c`), plus migration acceptance/conversion/execution reports under `artifacts/audits/`. These are availability observations, not a fresh live campaign validation. The source-hold files and exact hashes are recorded in `protected_inputs_after.json` and `current_matrix_inventory_status.json`.

### PE01 handoff

1. Implement the finite result/status contracts and parse/hash the effective default profile, without adding placeholder metrics or importing Torch/BehaviorBench/Lanelet2 for trace-only reads.
2. Add the single `runtime/trace_io.py` saved-evidence boundary and narrowly extract the viewer's existing file-hash/coherence checks. Preserve `run_trace.validate_run()`, exact comparison, viewer API, historical bytes, and display semantics.
3. Cover flat legacy schema-2 expert/SMART traces and nested matrix schema-3 traces. Resolve ego through recorded binary index and stable source ID; retain lifetime/ownership and absent metadata. Support producer revision `504218c` (and older archived producers) independently of evaluator HEAD `0beb7d8`.
4. Test synthetic archived-attested and trace-only bundles, tampering, sidecar mismatch, actor reorder/nonzero ego, finite serialization, and old viewer behavior. The stale live admission records do not authorize re-admission or weakening the saved-evidence hash boundary; carry them as a source-context limitation.

## PE00.5 — Baseline repair and handoff cleanup

Started at `683f7ae86a28c87688740cb6298440be16bda66c` on `pe00/performance-evaluation-baseline`. The visible process list showed no competing test processes at startup. Other worktrees and untracked attachments were preserved. All four planning documents now live here. The PE00 entry above records the historical layout.

**Admission attribution.** The archived PE00 copied probe completed at 20:39:28 CET on November 22. The seven original admission reports were written at 20:46:12–20:46:32 in precisely the order of the old probe's final gate calls. The original-tree `step2_smart_gate_regressions.json` appeared at 20:46:34 and records that probe's exact file hash and all final restoration cases. The copied tree had separate inodes and no symlinks. Taken together, this evidence points to a separate original-tree invocation of the regression probe. There is no retained process record identifying its launcher or exact command line. The probe restores its deliberate input mutations but the unchanged producer rewrites admission and source certificates on each gate call.

The seven changed bytes are retained in `runs/pe005/quarantine/`. The PE00 copied check also rewrote its own reports. Comparing its post-check reports and the original-tree replacements shows differences in `contract` (scene root and file provenance), `evidence_sha256`, and `evidence_files`. All seven pairs agree on checks and admission decisions. This compares two post-check versions. A local search across artifact and run admission reports found no copy matching any of the seven expected hashes, so the exact pre-check field diff and recovery remain blocked. The manifest and the shared reports were left in place. Do not use the seven replacements as the original admission evidence.

**Isolation and fixture.** The admission regression now copies its configured artifact tree into a unique directory below configured runs and binds the existing probe and subprocesses to the resolved copy. The original fixtures and reports are never the mutation targets. The SMART joint probe uses the existing binary writer to generate three separated vehicle paths and bounding road edges. It checks the source validity sequence and initial native slot before model inference. The historical M6 result at `runs/controller_matrix_work/m6/joint_gate.json` confirms the intended re-entry assertion. Two early minimal-map attempts aborted in native teardown with exit 134. The bounded fixture passed with normal teardown and preserved the causal graph, independent history, off-cadence refresh and action assertions. Logs for both attempts and the debugger stack are retained.

Commands below use the checkout root. Evidence is under `runs/pe005/`, with exact resolved roots and starting Git revision in `session.json`.

| Check | Result |
|---|---|
| `.venv/bin/geotransfer doctor` | Exit 0, `doctor.json`. |
| `cp -a --reflink=auto artifacts runs/pe005/artifacts`, resolved root and recursive symlink check | Separate tree, no links (`symlinks.txt`). `protected_before.json` and `protected_after.json` cover 577 original paths. No original or outer-copy protected hash changed in PE00.5. |
| `GEOTRANSFER_ARTIFACTS="$PWD/runs/pe005/artifacts" GEOTRANSFER_RUNS="$PWD/runs/pe005" .venv/bin/geotransfer check admission` | Exit 0, 34 cases. Command output in `admission.log`. Private producer outputs under `admission-regression-cb4jnl4d/artifacts`. The same seven reports differ from the original replacements on path and evidence provenance fields, with identical decisions. |
| `OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/geotransfer_mpl .venv/bin/python tests/integration/probe_smart_controller.py --fixture-dir runs/pe005/smart_final_fixture` | Exit 0, `smart_final.log`. Traffic refresh at step 14 with `new_target`, actor 1035, generation 1, slot 2, SMART ownership and a dynamics action. |
| `GEOTRANSFER_ARTIFACTS="$PWD/runs/pe005/artifacts" GEOTRANSFER_RUNS="$PWD/runs/pe005/pytest" .venv/bin/pytest -q` | Exit 0, 328 passed, 1 warning in 34.42s. |
| `GEOTRANSFER_ARTIFACTS="$PWD/runs/pe005/artifacts" GEOTRANSFER_RUNS="$PWD/runs/pe005" .venv/bin/python -m geotransfer_gap.verification_matrix --output runs/pe005/inventory.json` | **BLOCKED**, exit 1, first mismatch `r00_e321_f21017`. Full inventory requires all seven pinned admissions. |
| `geotransfer run --manifest runs/controller_matrix_work/m9_preflight/representative_final/scenes_r07_e200_f25439_r12_e151_f12041.json --ego smart --traffic smart --steps 24` and the same options with `--scene "$GEOTRANSFER_ARTIFACTS/oriented_v3/$scene"` | Exit 0 for batch and both singles with copied artifacts, `GEOTRANSFER_RUNS="$PWD/runs/pe005/parity"`, `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLCONFIGDIR=/tmp/geotransfer_mpl`. Both native runs passed existing parent validation. `.venv/bin/python -m geotransfer_gap.runtime.run_trace BATCH_DIR SINGLE_DIR --output runs/pe005/parity_$scene.json` reported exact equality for each scene. Run directories are in `parity_*.log`. |

PE01 can proceed on synthetic bundles. The missing pinned admission bytes remain a source-context block and confer no execution attestation.

## PE01 — Contracts and shared saved-evidence reader

Started from the PE00.5 checkpoint `1001d7a`. Added `evaluation/contracts.py`, `evaluation/profile.py`, and `runtime/trace_io.py`. The existing viewer delegates file binding, sidecar coherence and actor joins to the shared reader. It retains display labels, legacy actions, source fallback, and campaign selection. The evaluator uses the stricter saved-evidence entry point. It reads schema-2 legacy and schema-3 matrix observations by source ID and recorded binary index, with no inference from list or slot position. Missing historical lifetimes and transition metadata remain unknown. Verification metadata needs an exact trace binding before it enters scientific frames.

A passed parent attempt or a selected passing campaign slot can establish archived attestation. The reader exposes checked hashes, validates saved scene/protocol/input/horizon identities and structural actor coherence, and can hash supplied local input files. Producer Git revision is optional for standalone attempts that never recorded it. The campaign caller supplies its recorded revision and selected scene identities. A readable or hash-checked trace alone remains diagnostic. Invalid evidence raises an explicit exception. The fresh-run validator, exact comparator, campaign freeze logic and admission checks remain with their original producers.

The default profile's raw SHA-256 remains `8e5a6dfc329b0c71f75ac4aca41000efea6699acc5726ac7cfc61863139fba55`. Its effective SHA-256 is `985986f5da5a3e43ae6c94027b9f815fdbe8b4e19ed2c9f227517bbdc3a51f36`. Canonicalization and the accepted evidence boundary are documented in the operational definitions. Results use separate status, criterion outcome and interpretation fields, with finite JSON serialization through the shared artifact writer.

| Verification on PE01 working tree | Result |
|---|---|
| `.venv/bin/pytest -q tests/test_saved_evidence.py tests/test_viewer.py tests/test_run_trace.py tests/test_core.py` | Exit 0, 74 passed in 9.90s. `runs/pe01/focused_final.log`. The initial malformed-JSON fixture also omitted its planner field and hit that error before the intended nonfinite check. The initial failure is in `focused_initial.log`. |
| `GEOTRANSFER_ARTIFACTS="$PWD/runs/pe005/artifacts" GEOTRANSFER_RUNS="$PWD/runs/pe01/pytest" .venv/bin/pytest -q` | Exit 0, 353 passed, 1 upstream PyG deprecation warning in 34.52s. `runs/pe01/pytest.log`. |
| `.venv/bin/pytest -q --basetemp runs/pe01/synthetic tests/test_saved_evidence.py::test_archived_bundle_binds_bytes_and_joins_identity tests/test_saved_evidence.py::test_offline_without_site_packages_or_assets` | Exit 0, 2 passed. The fixture bytes were unchanged. The dependency check ran Python with `-I -S`, unavailable project asset roots, and assertions against importing NumPy, Torch, PufferDrive or Lanelet2. |
| Read-only compatibility spot check with `load_saved_trace` | The unaffected PE00.5 r07 matrix run reads as archived-attested. An old expert and an old SMART trace read as trace-only. Paths and returned identities in `runs/pe01/compatibility.log`. |
| Protected inputs and producer diff | All 577 hashes matched the PE00.5 starting snapshot. See `runs/pe01/protected_after.json`. No change to `run_trace.py`, `session.py`, execution, pinned manifest or upstream checkout. |

**Remaining block.** The seven original admissions from PE00 remain unavailable at their pinned hashes. They still block the full native verification inventory. They were not used as attestations for PE01. The historical campaign and producer fingerprints remain intact. Native single/manifest parity passed for the two unaffected PE00.5 scenes.

**PE02 handoff.** Use `load_profile`, `load_saved_trace` and `SavedTrace.frames()` from the new boundary. Bind outputs to the checked trace and sidecar hashes, effective profile hash, and known producer revision. Compute the frozen full-window and controlled-window exposure from recorded timestamps, lifetimes, and applied transitions. Keep legacy unknown transition flags explicit. Add kinematics and only the initial episode command in PE02. Use fresh output directories beneath configured runs.

## PE02 — Exposure, kinematics and episode CLI

**Dispatch.** Base `23889876ca47b384d0b1c85540191e312e88720d` on `performance-evaluation/pe02-pe14`. PE01 preflight `.venv/bin/pytest -q tests/test_saved_evidence.py tests/test_viewer.py tests/test_run_trace.py` passed 59 tests. Seven missing pinned admissions remain an independent native inventory block. PE02 is eligible for offline implementation. Campaign verification outputs go under `runs/pe_campaign/`.

**Accepted.** Implementation `9cc69c5562c60a5ed00f057179458dbca98d1ff5`. Review checked outgoing-owner attribution, separate yaw/world-jerk supports, summed irregular interval threshold exposure, null missing evidence and the shared reader/CLI boundary. `.venv/bin/pytest -q tests/test_evaluation_episode.py tests/test_saved_evidence.py tests/test_viewer.py tests/test_run_trace.py` passed 77 tests. `.venv/bin/geotransfer evaluate episode --trace "$trace" --output runs/pe_campaign/pe02/sol_archive` on the archived US SMART/IDM source-hold trace reported archived attestation, 90 transitions/9 s and 80 controlled transitions/8 s. Logs and synthetic no-native-import evidence under `runs/pe_campaign/pe02/`. Native inventory block carries forward. Next PE03.

## PE03 — Optional native event capture

**Dispatch.** Base `9cc69c5562c60a5ed00f057179458dbca98d1ff5`. Use the existing worker pre-step hook and parent batch validation. Verify capture on/off and representative single/manifest parity independently of the blocked full inventory.

**Review pending repair.** Candidate `01210d5` and PE02 test isolation repair `6883a36`. Native capture on/off and representative single/manifest parity evidence and full pytest (381 passed, 1 warning) are under `runs/pe_campaign/pe03/agent/`. Review requires binding the capture collision flags and native settings to canonical evidence and consistent handling of unmapped native partners. Full inventory still blocked.

**Accepted.** Implementation `01210d5` with evidence binding repair `4698499`; test isolation fix `6883a36`. Reviewed the existing worker hook and optional-only parent evidence path. Collision flags and native settings must agree with canonical evidence. Unmapped partners keep only the raw index and an explicit unknown status. `.venv/bin/pytest -q tests/test_evaluation_capture.py tests/test_execution_protocol.py tests/test_matrix_batch.py tests/test_saved_evidence.py tests/test_run_trace.py tests/test_evaluation_episode.py tests/test_viewer.py` passed 215 tests at the repair revision (`runs/pe_campaign/pe03/sol_review.log`). Prior full suite 381 passed. Five exact native parity comparisons passed on the copied r07/r12 subset, and a fresh capture run passed after the repair. Evidence is under `runs/pe_campaign/pe03/agent/`. The native pilot had no vehicle collision. Terminal capture, actor mapping and transforms were verified synthetically. Full inventory remains blocked on seven pinned admissions. Next PE04.

## PE04 — Collision, clearance and TTC

**Dispatch.** Base `46984996870d3bdc0e242b9c0e3c629d17346d38`. Reuse PE02 exposure/events, the PE03 bound sidecar and existing geometry helpers. Evaluate the native, sampled geometry, and predictive channels separately.

**Review pending repair.** Candidate `5dae2c1`, 106 focused tests passed (agent and Sol). Existing geometric overlap must yield TTC zero even without velocity. Review also requested reuse of the existing corner helper and removal of redundant timebase inference. Evidence under `runs/pe_campaign/pe04/`.

**Accepted.** Implementation `5dae2c1`, binding and reuse repair `45caf1e`. Reviewed present-pair coverage, causal motion fallback, terminal native evidence, oriented rectangle SAT, threshold exposure and absence of legal responsibility inference. `.venv/bin/pytest -q tests/test_evaluation_safety.py tests/test_evaluation_episode.py tests/test_saved_evidence.py tests/test_viewer.py tests/test_run_trace.py tests/test_evaluation_capture.py` passed 108 tests on the integrated revision (`runs/pe_campaign/pe04/sol_review_final.log`). Offline CLI smoke on saved legacy and bound matrix traces under `runs/pe_campaign/pe04/agent/`. Native collision evidence remains synthetic only for this pilot. Next PE05.

## PE05 — Map context and spatial metrics

**Dispatch.** Base `45caf1e7bc767c45354f032a74ea7833c6671dd1`. Reuse the inD map owner and PE04 physical footprint support. Verify optional geometry and supported coverage separately from rule applicability.

**Review pending repair.** Candidate `fe7f6b5`. Reviewed actual Lanelet surfaces and supported-footprint coverage. Sol's map/episode/run-trace set passed 52 tests with isolated Shapely. Mixed missing and known generations for one actor expose a sort failure in map output actor references. Repair requested. Evidence under `runs/pe_campaign/pe05/`.

**Accepted.** Implementation `fe7f6b5`, mixed-lifetime repair `f0e187a`. Reviewed source identity, provider variant selection, exact mapped road union/difference, boundary sampling and uncertainty, separate native off-road and local lane diagnostics. `PYTHONPATH="$PWD/runs/pe_campaign/pe05/agent/deps_no_numpy" .venv/bin/pytest -q tests/test_evaluation_map_metrics.py tests/test_evaluation_episode.py tests/test_run_trace.py` passed 53 tests (`runs/pe_campaign/pe05/sol_review_final.log`). All 16 map contexts loaded and an offline saved episode emitted spatial results. Agent evidence under `runs/pe_campaign/pe05/agent/`. Shapely remains an optional extra and was isolated to a run directory. Next PE06.

## PE06 — Route progress, tasks and efficiency

**Dispatch.** Base `f0e187a174ed8b941c1de9f25efbd3b5f3491185`. Use the existing source task/route owners and conservative offline outcomes. Do not infer successful completion from a native goal or failure from a horizon.

**Review pending repair.** Candidate `11fd1a0`; Sol's task/episode/safety/map check passed 75 tests (`runs/pe_campaign/pe06/sol_review.log`). Repair required for nonzero/reordered source ego identity, native goal versus bounded source goal binding, and deadline timing/censoring. Real r07 smoke remains scoped to its source certificates.

**Accepted.** Implementation `11fd1a0`, evidence-binding repair `5889267`. Review checked identity-based source ego selection, continuity-limited projection, separate native goal and source completion, time-bounded deadline censoring, and safe completion with missing criteria. `PYTHONPATH="$PWD/runs/pe_campaign/pe05/agent/deps_no_numpy" .venv/bin/pytest -q tests/test_evaluation_tasks.py tests/test_evaluation_episode.py tests/test_evaluation_safety.py tests/test_evaluation_map_metrics.py` passed 83 tests after repair (`runs/pe_campaign/pe06/sol_review_final.log`). Prior archived r07 smoke diagnosed source progress without treating early removal as task failure. Evidence under `runs/pe_campaign/pe06/agent/`. Next PE07.

## PE07 — Actual interaction realization

**Dispatch.** Base `5889267fb031a89d7f72fbea7a06e35d9faada28`. Build separate source opportunity and actual realization for following, pedestrian and cyclist crossing and existing controls. Keep unrealized encounters in the result.

**Review pending repair.** Candidate `c42ae21`, 163 focused tests reported by Luna. Real r07 archived smoke exposed a mismatch between the manifest scene ID and the converter's canonical scene name. Review also found PET entry/exit could treat unknown footprint occupancy as clear and join across a lifetime boundary. The first repair turn hit a usage limit before changing the workspace. Redispatched after usage was replenished. Evidence under `runs/pe_campaign/pe07/agent/`.

**Accepted.** Implementation `c42ae21`, evidence/occupancy repair `db9aae3`, stable following ego ID repair `e80dddd`. Reviewed fixed source opportunities, actual footprints and PET censoring, following route support and identities, and failure retention. `PYTHONPATH=src:runs/pe_campaign/pe05/agent/deps_no_numpy .venv/bin/pytest -q tests/test_evaluation_interactions.py tests/test_evaluation_tasks.py tests/test_evaluation_episode.py` passed 63 tests. Archived r07 crossing and r01 following smokes loaded valid source context, with indeterminate crossing due to missing terminal pose and encountered/unresolved following. Evidence and commands under `runs/pe_campaign/pe07/`. Next PE08.

## PE08 — Conditional semantic compliance

**Dispatch.** Base `e80dddd8cd1f6c1106c7c0347d515813bcb80b45`. Measure only supported obligations on the actual route. Retain independent source admission and explicit gaps in rule evidence.

**Review pending repair.** Candidate `b268e08`. Sol's explicit Python 3.11 venv with the isolated Shapely wheel passed 48 semantic/map/episode tests (`runs/pe_campaign/pe08/sol_review.log`), resolving the agent's Python 3.12 wheel mismatch for this configuration. Repair requested for the frozen safe completion contract and unsupported priority-actor absence.
