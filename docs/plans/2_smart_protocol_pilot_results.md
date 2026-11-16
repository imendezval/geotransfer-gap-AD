> Historical snapshot: the current verified set and protocol are documented in [the third-family execution record](2_third_family_execution.md) and the canonical manifest. Do not pool these earlier counts or gates with the current16-scene protocol.

# Step 2: results of the three-stage SMART protocol pilot

## Outcome and scope

The three stages in [the pilot plan](2_smart_protocol_pilot.md) are accomplished for a bounded pilot: verified SMART input/evaluation path, one admitted pedestrian interaction, and the same fixed process tested on four varied German candidates. **Three admitted scenes, one genuine interaction, two controls, one semantic exclusion.** Accepted locations are 1 and 4, from recordings 15 and 0. These are three nonoverlapping windows without shared moving tracks, but only two recording clusters; do not treat them as three independent recordings.

**Parent Step 2 is incomplete.** Its feasibility target is at least 10 admitted interaction scenes across two locations; completion requires at least 50 independent admitted scenes across three locations and multiple interaction types, or more if the study's precision requirements demand it. This pilot establishes a working foundation for expansion rather than a geographic planner-performance study. Full global fidelity has not been established.

## 1. Verify SMART input and evaluator protocol

**Problem.** A correct binary did not ensure the planner saw its actors, map semantics or source timing. Expert actors were missing from SMART. A US reference exposed 307 missing actor/time samples after source validity gaps. Another US scene with world y near −11,536 m exposed SMART's invalid-coordinate threshold: the model retained only the ego and output zero control. Source/aerial review also used an incorrect factor10-plus-fitted-translation projection.

**Changes.** `faithful_smart.py` supplies all current actor states in stable binary order, including expert vehicles and VRUs, with inactive objects absent. Map tokens and actors share the evaluator-centered frame; inverse transforms are checked against source coordinates. `late_spawn_runtime.py` supports every source invalid-to-valid transition and rebuilds an IDM route on re-entry, while a persistent collision-removal flag prevents physically removed vehicles returning. The runtime is isolated from upstream BehaviorBench. `register_background.py` uses the official inD visualization projection, `pixel_x=x/(12*orthoPxToMeter)`, `pixel_y=-y/(12*orthoPxToMeter)`, with zero translation. The provider convention is documented in the [official visualizer configuration](https://github.com/ika-rwth-aachen/drone-dataset-tools/blob/master/data/visualizer_params/visualizer_params.json); pinned source/hash evidence is in `pilot/audits/provider_background_projection.json`.

**Frozen protocol.** SMART checkpoint `SMART_epoch_030.pt`, greedy CPU, seed0, 10 Hz state updates, 11 history samples, 10 actually observed expert warmup steps, predictions every5 steps. Goal radius2 m, speed threshold20 m/s, hybrid startup traffic. Initially stopped vehicles follow their source trajectory until source movement onset, then IDM; VRUs and marked expert actors remain expert. Current histories use observed states rather than source future. The causal extrapolation bootstrap remains a separately tested entrypoint, not the admitted warmup path. Other actors can appear/disappear between prediction updates: the cached prediction can lag by up to4 ticks, explicitly part of this 2 Hz protocol.

**Evidence.** Four German and two US inputs have zero source-presence and class mismatches over observed expert-replay intervals. German position error is at most 0.00000382 m and inverse map error at most 0.00000540 m; heading and dimension errors are zero against converted source fields. US reference source presence is exact through step88 (89 unique observed states), and the negative-world case through step85. All are below the fixed 0.01 m/rad tolerance. Future mutation does not change reset input; one-metre ego perturbations reach the model correctly. Actual prediction updates have no identity mismatch. These finite-window checks do not establish correctness on all input scenes.

The negative-world binary now supplies all seven initially present actors rather than just ego, with finite nonzero action. Collision regressions ensure both a continuously source-valid actor and an actor with a later validity gap stay absent after a physical collision removal. US hybrid parity verifies the shared traffic-switch mechanics, not matched research admission or training equivalence. Evidence:

- `pilot/audits/runtime_reentry_before_after.json`
- `pilot/audits/runtime_source_reentry_regression.json`
- `pilot/audits/smart_negative_world_before_after.json`
- `pilot/audits/hybrid_protocol_us_parity.json`
- Per-scene `testing/smart_map_transfer_all_actors_probe.json`

## 2. Admit one genuine interaction

**Problem.** Proximity or visible source yielding alone cannot establish a fair planning task. Applicable source rules must reach the planner, and the evaluator goal must actually expose the claimed decision. Crosswalk polygons previously had inconsistent boundary orientation; fitted aerial alignment could also create false surface exclusions.

**Solved.** Source crosswalk polygons are consistently oriented and carried through JSON, BehaviorBench's binary writer and actual SMART map tokens. The four candidates were reviewed again using provider aerial coordinates. `admit_smart_scene.py` adds planner-specific evidence over the full technical gate: exact rule/boundary inventory, current source-image review, source-supported irrelevance or represented crosswalk semantics, actual encounter-actor input, US reference input checks, and hashes of code/checkpoint/evidence. Unsupported applicable priority/sign rules remain exclusions. A generic stopped-leader goal check rejects claims when a collision-free source goal entry exists before the leader.

The admitted interaction is recording0/ego365, first frame22735, pedestrian351 at crosswalk1146. Its source closest box gap is about1.87 m at step66; all46 source-close hybrid frames are preserved. The actual SMART map contains21 crosswalk tokens, including the applicable crossing, and the pedestrian reaches the model near the encounter. The bounded goal ends on the approach before the main-road priority conflict; admission makes no claim about the later main-road maneuver.

**Regression standard.** Incomplete reviews, stale adapter proof, a missing claimed pedestrian, incorrect aerial scale, and a false lead-response claim all fail admission. The rollout runner rejects changed evidence. Restoring the original evidence restores admission. Results: `pilot/audits/step2_smart_gate_regressions.json`.

## 3. Apply the same process to a fixed varied batch

The selection was fixed before new policy outcomes and retained unchanged. Interpretations were corrected using source and task evidence rather than selecting on SMART success.

| Candidate | Current technical gate | SMART admission | Supported task / reason |
| --- | --- | --- | --- |
| r00 ego365, frame22735, location4 | Pass | Admit | Pedestrian crossing; genuine interaction |
| r15 ego332, frame25626, location1 | Pass | Admit as control | Goal approach ends before queue; no required braking or restart |
| r00 ego39, frame3000, location4 | Pass | Admit as control | Uncontested turn; adjacent vehicle40 is not an interaction |
| r20 ego416, frame26946, location2 | Pass | Exclude | Source priority relations1202/1205/1207/1208 involving cyclists414/415 are not represented |

The queue candidate preserves all50 source-close frames of initially stopped leader324. Nevertheless its goal lies4.42 m behind the leader center, and its2 m goal region allows completion before a required lead response. It was downgraded from restart, then braking, to a control. This is a task-scope finding, not a failed actor-transfer correction. Original selection intent and excluded claims remain recorded.

All three admitted scenes completed the admission-enforcing SMART diagnostic; both US references completed50-step diagnostics. There were zero identity mismatches at actual prediction refreshes. Pedestrian and queue-control rollouts terminated at steps70 and58 with collision_state0; the turn ran through step90. Terminal state alone is not a certified success label, and these are not research-performance scores.

The current fixed ledger and manifest are `pilot/audits/step2_smart_pilot_selection.json`, `step2_smart_pilot_summary.json`, `step2_smart_pilot_manifest.json` and `.csv`. Whole recordings are assigned to splits; location4 is held out. Stationary parked tracks may recur within the held-out recording. There is no training corpus or statistically adequate comparison set yet.

## Entrypoints and reproduction

Run from `geotransfer-AD-gap` in `bb_pufferdrive`. The `pilot/` roots are generated evidence and experiment variants; do not mix their reports across protocols or binaries.

| Entrypoint | Responsibility |
| --- | --- |
| `pilot_ind.py` | Source conversion and source geometry helpers; reuses BehaviorBench JSON-to-binary writer |
| `register_background.py` | Deterministic provider aerial registration, no fitted translation |
| `admit_scene.py` | Full technical contract: round trip, replay, lifecycle, physical/map checks, selected traffic and perturbation |
| `probe_smart_map_transfer.py` | Actual SMART actor/map/source features, history, causal perturbation and inference diagnostics |
| `admit_smart_scene.py` | Planner-specific research admission over current technical/source evidence |
| `probe_faithful_smart_closed_loop.py` | Canonical single-scene SMART rollout using the adapter; `--require-admission` enforces freshness |
| `build_smart_pilot_manifest.py` | Fixed candidate ledger, hash freshness, split/independence checks and current counts |
| `probe_source_reentry.py` | Runtime collision-removal/re-entry regression |

```bash
# Refresh actual model-input evidence for the crossing candidate.
MPLCONFIGDIR=/tmp/geotransfer_mpl OMP_NUM_THREADS=2 conda run --no-capture-output -n bb_pufferdrive python probe_smart_map_transfer.py --root pilot/probes/semantic_crosswalk_r00e365 --us-binary pilot/probes/us_hybrid_1002fdc9826fc6d1/testing/map_000000.bin --inference --all-actors --steps 81

# Refresh SMART admission after changing any hashed probe evidence.
MPLCONFIGDIR=/tmp/geotransfer_mpl OMP_NUM_THREADS=2 conda run --no-capture-output -n bb_pufferdrive python admit_smart_scene.py --root pilot/probes/semantic_crosswalk_r00e365 --us-root pilot/probes/us_hybrid_1002fdc9826fc6d1

# Run only with current admission. Output remains a diagnostic.
MPLCONFIGDIR=/tmp/geotransfer_mpl OMP_NUM_THREADS=2 conda run --no-capture-output -n bb_pufferdrive python probe_faithful_smart_closed_loop.py --root pilot/probes/semantic_crosswalk_r00e365 --require-admission

conda run --no-capture-output -n bb_pufferdrive python build_smart_pilot_manifest.py
```

The upstream stock SMART entrypoint is unchanged and does not automatically use this adapter/runtime. This verifies a single-scene execution path, not complete integration into BehaviorBench's stock multi-map planner factory. Changing runtime or source/geometry requires regenerating the full technical evidence before planner admission; refreshing only SMART evidence is insufficient.

## Remaining limits and next parent work

- Applicable priority/sign semantics still cannot reach unchanged SMART through this path. Keep such scenes excluded or establish a generic supported representation and consistently validate it on US/German inputs. Crosswalk transfer does not solve all rule semantics. This result is SMART-specific; it does not establish PPO observability.
- Re-review old aerial-based surface and overlap decisions under the correct provider projection. Earlier6IDM/4hybrid admissions and their restart claims are historical; rebuilt legacy flows currently contain zero current gates. Archived records remain under `pilot/audits/history/`.
- Expand from one interaction type, retaining fixed source selection and all failures. A genuinely required following/restart task needs a defensible route/goal after that decision, then the complete gate; extending this scene arbitrarily is not justified.
- Exact source-valid replay does not recover unobserved motion through source gaps. VRU dimensions remain source-limited/imputed, and hybrid traffic is a specified counterfactual, not exact source replay after interaction changes.
- Build the parent10/50 admitted sets, rerun source/manual gates, keep recording/location separation, and establish matched US/German study cohorts and uncertainty. Mechanical parity on two US references cannot substitute for that research design or prove upstream training equivalence.

There is no known intervention-only blocker to further source search or corpus expansion. Completion here refers to the requested three-stage pilot, not the broader Step2 objective or universal scene faithfulness.
