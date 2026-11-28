# B1 frozen Expert-traffic diagnostics preflight

**Status:** frozen preflight only. No native simulator or model run was started. The requested 16 scene by 4 ego-controller cells are ready for diagnostic execution, pending the orchestrator’s native slot.

**Base / branch:** integration commit `d21ff13013e65c59999bf4d06221d9644bd34f66`; `overnight/planner-diagnostics`.

## Preflight result

`configs/current_manifest.json` is the expected schema-v2 manifest, with SHA-256 `316438458c537adfd6b3347a8387844c95ac806d2067365fdc0d72abe2b3992c`. All 16 rows have current binary, converted source JSON, Expert evaluation contract, validation, and source files whose bytes match the referenced hashes. Each source task contract identifies the same recording, ego source track, binary index, and 91-observation window. Source ego goal samples and coordinates resolve in the converted source tracks. The machine preflight marks **16/16 scenes and 64/64 cells ready**.

Diagnostic readiness is separate from admission. The old `admission_smart_hybrid_startup.json` hash still matches the manifest in 9 scenes; it differs in 7: `r00_e321_f21017`, `r01_e280_f18833`, `r01_e301_f20017`, `r09_e136_f11030`, `r32_e391_f21356`, `r09_e196_f16232`, and `r15_e332_f25626`. Their source/binary/Expert-contract pins still match. At execution, every requested row remains `diagnostic_only=true` with `research_admission_status=not_established`; the SMART/hybrid gate cannot admit the Expert/immediate pair.

Current CPU inputs are pinned: Python 3.11.18, NumPy 1.26.4, Torch 2.5.1+cu121, BehaviorBench commit `805fe04c6977b60c41c92c31f1a5211fbd704f44` (clean), evaluation INI SHA `afdf157a7b809e31700a49f977c46a7a4913c7e73546a5803d8635a9ae1f5e4e`, PPO checkpoint SHA `50a9a580cca905fc3dae47b5847b4edf408de3b7fe7517bd4f3a781fa140e3b3`, and SMART checkpoint SHA `b2cdeb31b0336588df1fc872e2f64dc6b24ec88472936068ec7e9501e9252616`. The SMART map/motion codebooks also match their runtime pins. `late_spawn_runtime`’s patched-source digest was recomputed without calling `load()` or compiling: `beedf8f1b0e9c490`. Its existing cache binary is `/tmp/geotransfer_late_beedf8f1b0e9c490/binding.cpython-311-x86_64-linux-gnu.so`, SHA `bdf1a2cb70f4153a0283a45fe18920b09a545ecba15fdb335a87a31762b94d58`. Execution pins CUDA off and one thread for OMP, MKL, OpenBLAS, NumExpr, and Torch; model device is CPU.

## Frozen protocol and order

Use the public matrix `run` path with `--diagnostic --capture-evaluation`, one fresh child process per scene and four serial manifest batches in this order: `expert`, `idm`, `ppo`, `smart`. Each batch processes scenes in manifest order. Every cell uses traffic `expert`, startup `immediate`, and 91 **observation frames**. No source-hold schedule is supplied. The 64-cell sequence is indexed in `runs/german_200_overnight/planner_diagnostics/preflight_64.tsv`.

Before the 64 cells, run the two current-code repeatability pairs in the one-row pinned manifest `runs/german_200_overnight/planner_diagnostics/repeatability_manifest.json`: PPO twice, then SMART twice, on `r00_e321_f21017`. Compare each pair with the existing `geotransfer_gap.runtime.run_trace` bundle comparator and require byte-identical `evaluation_capture.json` SHA-256. A mismatch stops the main matrix. These four repeat runs are a pre-run gate, not part of the 64-cell denominator.

```bash
REPO=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD
WT="$REPO/runs/german_200_overnight/worktrees/planner"
OUT="$REPO/runs/german_200_overnight/planner_diagnostics"
cd "$WT"
export GEOTRANSFER_PROJECT="$REPO"
export GEOTRANSFER_SOURCE="$REPO/../data/levelxdata/inD-dataset-v1.1"
export GEOTRANSFER_BENCH="$REPO/../behavior-bench"
export GEOTRANSFER_RUNS="$OUT"
export PYTHONPATH="$WT/src"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONHASHSEED=0 CUDA_VISIBLE_DEVICES=""
export MPLCONFIGDIR=/tmp/geotransfer-b1-mpl

# Repeatability gate: run each command twice, saving each printed RUN_DIR.
$REPO/.venv/bin/geotransfer run --manifest "$OUT/repeatability_manifest.json" --ego ppo --traffic expert --traffic-startup immediate --steps 91 --diagnostic --capture-evaluation
$REPO/.venv/bin/geotransfer run --manifest "$OUT/repeatability_manifest.json" --ego ppo --traffic expert --traffic-startup immediate --steps 91 --diagnostic --capture-evaluation
# Set PPO_RUN_1 and PPO_RUN_2 to the two printed RUN_DIR values before comparing.
$REPO/.venv/bin/python -m geotransfer_gap.runtime.run_trace "$PPO_RUN_1/r00_e321_f21017" "$PPO_RUN_2/r00_e321_f21017" --output "$OUT/repeatability/ppo.json"
sha256sum "$PPO_RUN_1/r00_e321_f21017/evaluation_capture.json" "$PPO_RUN_2/r00_e321_f21017/evaluation_capture.json"

$REPO/.venv/bin/geotransfer run --manifest "$OUT/repeatability_manifest.json" --ego smart --traffic expert --traffic-startup immediate --steps 91 --diagnostic --capture-evaluation
$REPO/.venv/bin/geotransfer run --manifest "$OUT/repeatability_manifest.json" --ego smart --traffic expert --traffic-startup immediate --steps 91 --diagnostic --capture-evaluation
# Set SMART_RUN_1 and SMART_RUN_2 to the two printed RUN_DIR values before comparing.
$REPO/.venv/bin/python -m geotransfer_gap.runtime.run_trace "$SMART_RUN_1/r00_e321_f21017" "$SMART_RUN_2/r00_e321_f21017" --output "$OUT/repeatability/smart.json"
sha256sum "$SMART_RUN_1/r00_e321_f21017/evaluation_capture.json" "$SMART_RUN_2/r00_e321_f21017/evaluation_capture.json"

# Main 64 cells: the loop order is the frozen controller-batch order.
for ego in expert idm ppo smart; do
  $REPO/.venv/bin/geotransfer run --manifest "$REPO/configs/current_manifest.json" \
    --ego "$ego" --traffic expert --traffic-startup immediate --steps 91 \
    --diagnostic --capture-evaluation
done
```

For each printed matrix `RUN_DIR`, run the existing offline evaluator into a fresh directory. It does not launch the simulator or planner. Preserve the isolated Shapely environment for map geometry:

```bash
export PYTHONPATH="$WT/src:$REPO/runs/german_200_research_verification/evaluation_geometry"
$REPO/.venv/bin/geotransfer evaluate run --run "$RUN_DIR" \
  --manifest "$REPO/configs/current_manifest.json" \
  --profile "$REPO/configs/evaluation/default.toml" \
  --output "$OUT/evaluations/$EGO"
```

## Frame ownership and interpretation

`steps=91` means observations 0 through 90, with at most 90 applied transitions. Scheduler source inspection confirms that both roles use Expert replay on transitions 0→1 through 9→10; the first learned ego action is transition 10→11. Observation 10 is the first policy-window state. Expert traffic remains `expert_replay` for every later applied transition. Prove this from the saved trace’s per-observation actor assignments: for traffic-role actors require `declared_controller=expert`, `effective_owner=traffic:expert` after warmup, and `native_mode=expert_replay`; require `warmup_replay` before step 10. Context actors use `context_replay`. Parent validation in the schema-v4 ledger remains the run acceptance check.

The scene-root contracts and source tracks support bounded task evaluation for all 16 scenes. The schema-v2 capture is required to bind the native navigation goal and cumulative `goals_reached_this_episode` counter to ego binary slot, source ID, lifetime, and trace hash. Evaluator task completion requires the captured native goal to match the source task goal within 0.1 m; the counter event is separate from geometric pose. An early `ego_removed` terminal can be a recorded completion without a terminal pose; FDE remains unavailable unless the fixed requested endpoint is reached. A missing/mismatched capture or unbound native goal leaves source-task completion unresolved/censored.

Static controller inspection confirms the information-access difference. PPO infers from the native agent-centric observation, including the simulator navigation goal. SMART builds map tokens and causal joint history from observed actor state and observed-birth velocity; it does not read the navigation-goal field. Save and report `task.planner_goal_visibility` by controller. This is a controller information-access difference, not an outcome explanation.

## Metric and context plan

Use the existing offline evaluator and retain metric status, denominators, censoring, and evidence references for every row.

- `secondary_metrics.reference_deviation`: exact-timestamp source ADE and fixed-endpoint FDE. Report warmup support separately, primary expected/matched sample counts, and source-valid lifetime support. No interpolation or time warping; ADE/FDE are descriptive reference deviation.
- `task.native_goal_event`, `task.bounded_task_completion`, and `exposure`: source-goal binding, native counter onset, observed terminal reason/pose, completion time, requested-horizon status, and censoring. Do not infer goal arrival from removal alone.
- `task.planner_goal_visibility`: controller information access as recorded by the evaluator; retain its difference between SMART and PPO.
- `trajectory.route_progress` and normalized route progress require a legal, hash-bound source route certificate. Scene-local certificates are identity candidates for `r01_e280_f18833` and `r07_e200_f25439`; 14 scene roots lack `source_route_sequence.json`. Two additional certificates for `r00_e39_f3000` and `r16_e35_f1521` exist under the previous Workstream B output and were accepted by its explicit route-context override, but are not linked by the standard CLI. A current standard offline evaluation of `r16_e35_f1521` therefore reports route context unavailable. Do not silently transfer those override results into the new matrix.
- `safety.map_footprint_outside`, lane offsets, and lane heading use the current hash-bound source Lanelet map with isolated Shapely. These measure mapped surface only; map completeness and legal access remain unassessed. `safety.native_vehicle_collision_onsets` and native off-road events come from simulator trace channels. `safety.footprint_clearance`, overlap, TTC, and near-miss exposure use sampled poses; TTC is fixed-heading, constant-velocity prediction, not observed collision or continuous-time clearance.
- `efficiency.stationary_duration` uses the frozen 0.2 m/s threshold. `trajectory.observed_distance` sums supported consecutive center displacements. Retain full and primary windows and source support.
- `interactions` uses the current manifest family/subtype/actor IDs, the source scene, and the selected source fidelity audit. There are 13 source-opportunity scenes: 6 pedestrian crossing, 3 cyclist crossing, and 4 longitudinal following; 3 are controls. All 13 family/actor-type checks and fidelity identity candidates pass the static preflight. The existing source body-path conflict certificate is present in 2 scenes; following-scope evidence is optional and evaluated by its normal validator. Keep missing optional context visible; interaction opportunity is not a yielding correctness label.
- The 16 map-semantics audits bind to current map/binary inputs, but `semantic_screen_pass` is false for all 16. The audit flags unencoded ego crosswalks in 10 scenes, unencoded priority relations in 12, and unencoded signs within 5 m in 7. The reviewed annotation directory is absent. Signal/rule compliance and safe-completion therefore cannot be assumed from map geometry or a zero native event count.

## Cluster and leakage limits

The manifest carries recording IDs and inclusive source-frame windows but no separate log/sequence ID. The 16 scenes form 10 recording clusters at 3 locations; scenes within one recording are not independent. Location-4 holdout has 4 recording clusters. The static audit finds no overlapping source-frame windows or shared moving-track IDs within a recording, and no recording ID spans split labels. This is evidence against direct selected-window overlap; it does not create 16 independent recordings or prove independence across unrecorded logs/sites.

## Prior eight-cell overlap

The previous `run_001` contains all eight expert/immediate 91-observation controller rows for `r00_e39_f3000` and `r16_e35_f1521`. Current binary, protocol, schema-v2 capture hashes, checkpoint identities, evaluation code and profile match. They are **not reusable as current producer evidence**: the saved `verification.json` code map differs from current source at `evaluation/capture.py` (one file). Keep them as archived diagnostics only; do not skip new matrix cells or use the old evaluation bundle as a current batch. The older source-route override certificates are recorded separately above.

## Machine receipts

From the main workspace, regenerate only the static preflight (no native/model imports or runs):

```bash
.venv/bin/python runs/german_200_overnight/planner_diagnostics/preflight.py
```

- `runs/german_200_overnight/planner_diagnostics/preflight_64.json` records all 16 scene identities, binary/admission/source hashes, route/family context, current environment/checkpoint/runtime pins, 8 archived-run equivalence checks, and all 64 ordered cells.
- `runs/german_200_overnight/planner_diagnostics/preflight_64.tsv` is the execution-order cell index.
- `runs/german_200_overnight/planner_diagnostics/repeatability_manifest.json` is the one-row, binary-pinned repeat manifest.
- Scene-local route certificate hashes: `r01_e280_f18833` `5294efb841405adddccea739bfd39f9f8bd052f19c3feb4fcb9cfb1e7bc5357d`; `r07_e200_f25439` `b5febb93d4b611819781d2e16975c7abcdb3afd90e67d6e7f4920efad1b0b9b5`. Prior Workstream B override hashes are `r00_e39_f3000` `fd5e451f0735c18365d67f21ecef6ff2dfc52411316d9f49328dd035d44cf0c0` and `r16_e35_f1521` `53fd2ad9c4197546d0425367743d88d665888431ad377fc8da87888eabc7784d`.
- `runs/german_200_overnight/planner_diagnostics/offline_evaluation_receipt.json` records the existing evaluator path run on archived `r16_e35_f1521` expert trace SHA `e19086ac1b4014b5672b72b737ea6c286c6d4a847de672f6a3b402a9bf7dc85c`; result SHA `be99caaba3530d935d4bd074b0d6cf741502beb4aafcff8eb4d284f12cfa8e7e`. With isolated Shapely 2.1.1 it produced a valid source task/map/interaction context, source-goal binding, following encounter evidence, ADE support 71/76, FDE unavailable because the requested horizon was not reached, and route unavailable because the scene-local certificate is absent. No native simulator or model ran for this receipt.
