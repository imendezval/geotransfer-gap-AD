# Follow-up experiments: validity stress tests and additional scenes

These experiments extend the [first pilot](EXPERIMENT.md). All planner outcomes below are single-scene smoke tests. They do not establish a US-to-Germany transfer gap.

## 1. Visual inspection of failures

- PPO with expert-replay traffic: the [collision frame](pilot/runs/20261106_153950_224846/map_000/step_023.png) shows a following replay vehicle striking the ego. BehaviorBench labels it `ACTIVE_REAR_COLLISION (NO FAULT)`. The replay actor cannot react to the ego's changed path, so this outcome cannot be assigned to PPO as a planning failure.
- SMART with expert-replay traffic: the [collision frame](pilot/runs/20261106_155329_fe8c54/map_000/step_040.png) shows lateral overlap with a replay vehicle. The classifier also marks this `NO FAULT`. Because the replay vehicle cannot react, the frame alone does not establish the cause of the conflict.
- SMART with IDM traffic: [frames 65–66](pilot/runs/20261106_153950_9292b3/map_000/step_065.png) show the ego reaching the mapped traffic-island curb. The source expert trajectory remains near the lane centerline (maximum source-to-lane-center distance 1.29 m), and direct expert replay has no off-road event. This is a plausible planner deviation in this one scene, subject to a fuller map-edge audit.

## 2. Construction sensitivity

The baseline uses ego goal sample 85 and both `road_border` and `curbstone` ways as road edges. Two variants were generated from the same source window. Each variant passed JSON/binary and expert-replay checks before evaluation.

| Scene variant | SMART + IDM outcome | Interpretation |
|---|---|---|
| Baseline, goal sample 85, all edges | Off-road at step 66; goal not reached | Reference result. |
| Goal sample 75, all edges | Off-road at step 66; goal not reached | Earlier reachable goal did not remove the event. PDM still reached the earlier goal. |
| Goal sample 85, omit curbstone edges | No off-road flag; goal not reached | The [render](pilot/variants/no_curbs/runs/20261106_155053_d37823/map_000/step_065.png) shows altered driving through the area where the island curbs were removed. Omitting a physical curb changes the task and cannot be treated as a fix. |

The first variant is under `pilot/variants/goal75/`; the second is under `pilot/variants/no_curbs/`. These are ablations and are excluded from planner-gap evidence. `pilot_ind.py` now exposes `--goal-sample` and `--edge-mode` to reproduce them.

## 3. Late-arriving actors

The BehaviorBench C engine's `set_active_agents()` creates actors only when `traj_valid[init_steps] == 1`. A faithful actor that first appears later is therefore absent throughout the episode. The default converter now rejects windows containing retained late arrivals.

The technical probe under `pilot/probes/late_spawn_bootstrap/` sets the first valid flag of four late actors, making them briefly appear at their future entry position at step 0. In expert mode they can then disappear and reappear at their recorded entry time, but the extra first-frame actor changes the scene. Some actors were also removed later by simulator collision handling (35 valid samples missing). This probe is **not a fair closed-loop scenario**. A later isolated runtime with genuine birth handling and a passing two-entry scene is documented in [AUDIT_RESULTS.md](AUDIT_RESULTS.md). The unmodified engine still lacks late spawn support.

## 4. Additional-scene audit

`pilot_ind.py` now accepts `--recording`, `--ego`, `--first-frame`, `--static-crop-radius`, and `--output-root`. It selects the appropriate Lanelet2/OpenDRIVE map, including the construction-site map for inD recordings 11–17. For VRUs with zero dimensions in the source metadata, the JSON explicitly records imputation and uses 0.6 × 0.6 m for pedestrians or 1.8 × 0.6 m for cyclists. This parameter choice needs sensitivity checks before VRU safety metrics are published.

Several stationary cars in locations 1 and 2 are removed by the simulator immediately after reset because of overlaps. A targeted scan found route-connected windows in those locations; applying a 15 m *minimum distance from the ego over the whole window* crop to stationary cars removed the overlapping cars, while retaining moving traffic and VRUs. This makes two more windows usable for conversion and replay checks. It also changes scene composition and may bias planning results, especially at location 2, so these are provisional pilot scenes.

| Recording, ego, start frame | Location | Outcome |
|---|---:|---|
| 00, 7, 260 | 4 | Original accepted scene: connected lane route; 575 expert-replay samples matched; no missing actor or expert ego violation. |
| 04, 12, 724 | 4 | Second accepted scene: connected lane route; 247 expert-replay samples matched; no missing actor or expert ego violation. PDM reached the goal with expert and IDM traffic. [Overlay](pilot/scenes/ind04_t12_f724/testing/overlay.png). |
| 13, 108, 6858 | 1 | Provisional accepted scene after removing five stationary cars more than 15 m from the ego: connected route; 789 replay samples matched; no missing actor or expert ego violation. PDM reached the goal with IDM traffic. [Overlay](pilot/scenes/ind13_t108_f6858/testing/overlay.png). |
| 21, 320, 16936 | 2 | Provisional accepted short turn after removing 17 stationary cars more than 15 m from the ego: connected route; 381 replay samples matched; no missing actor or expert ego violation. PDM collided in both expert and IDM traffic, with differing fault classification. [Overlay](pilot/scenes/ind21_t320_f16936/testing/overlay.png). |
| 13, 8, 336 | 1 | Rejected: current inferred lane graph cannot connect ego start to goal; one parked car is removed after an initialization overlap. |
| 21, 32, 535 | 2 | Rejected: current inferred lane graph cannot connect ego start to goal; six parked cars disappear during replay. OpenDRIVE rounds its UTM offset, differing from CSV by 0.072 m. |
| 02, 161, 7636 | 4 | Rejected despite a connected lane route: actor 158 disappears for 51 valid replay samples. |

Other candidate windows under `pilot/scenes/` were converted and failed either the current route-reachability or replay check; they were not scored as planner cases. A disconnected *inferred* graph is an adapter failure or unresolved map-matching problem, not proof that the source map lacks a route. The location 1 and 2 scenes show that binary round-trip accuracy alone is insufficient for cross-location evaluation.

The location 2 PDM/IDM [collision frame](pilot/scenes/ind21_t320_f16936/runs/20261106_184157_f1bed2/map_000/step_025.png) shows a crossing vehicle at the junction and is classified as ego-at-fault. PDM also collides with expert traffic, but that run is classified as not ego-at-fault. The short goal, cropped parked cars, and traffic-model dependence make this a diagnostic case, not a planner-transfer result.

## Runtime note

BehaviorBench's C loader aborted with a buffer overflow when given long nested scene paths. `run_pilot_eval.py` and `validate_replay.py` now create stable short `/tmp/geo_scene_*` links and load scenes through those links. The real generated files and run logs remain in the project tree. `run_pilot_eval.py` checks route reachability, late arrivals, expert replay, and matching binary SHA-256 hashes in both validation reports before scoring a scene; `GEOTRANSFER_ALLOW_UNVALIDATED=1` is an explicit override for diagnostic runs.

## Reproduce the accepted second scene

```bash
python pilot_ind.py --recording 4 --ego 12 --first-frame 724 --output-root pilot/scenes/ind04_t12_f724
/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python validate_replay.py --root pilot/scenes/ind04_t12_f724
GEOTRANSFER_SCENE_ROOT=pilot/scenes/ind04_t12_f724 /home/inigo/miniconda3/envs/bb_pufferdrive/bin/python run_pilot_eval.py --planner.type pdm --traffic.type idm
```

For the provisional cross-location windows, use `--recording 13 --ego 108 --first-frame 6858` or `--recording 21 --ego 320 --first-frame 16936`, with `--static-crop-radius 15` and a distinct `--output-root`. Run `validate_replay.py --root <output-root>` before evaluation.
