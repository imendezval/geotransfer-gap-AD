# Late entry and map/crop audit (6 November 2026)

## Standards and reproducible artifacts

The acceptance rules are in [VALIDATION_PLAN.md](VALIDATION_PLAN.md). These are feasibility tests, not planner-transfer evidence. The final scenes below use a directed Lanelet2 graph: each successor shares at least one boundary node ID, its centerline endpoints are within 1 m, and its tangent dot product exceeds 0.5. `audit_scene.py` checks Lanelet2 polygons, source IDs, directions, and reachability independently of the converter's centerline-nearest check. The goal is still chosen from the source ego trajectory at sample 85; traffic rules and priority are not yet encoded.

| Scene | Retained objects | Expert samples | Polygon occupancy | Directed links | Replay |
|---|---:|---:|---:|---:|---|
| [04/12/605 with late arrivals](pilot/validated/late04_selective/testing/validation.json) | 9 | 577 | 91/91 | 106; zero without a shared boundary node or reversed | Pass |
| [13/108/6858 selective crop](pilot/validated/selective13/testing/validation.json) | 14 | 1153 | 91/91 | 48; zero unsupported or reversed | Pass |
| [21/320/16936 selective crop](pilot/validated/selective21/testing/validation.json) | 16 | 1382 | 91/91 | 35; zero without a shared boundary node or reversed | Pass |

The maximum ego heading error against an occupied lanelet is 0.247, 0.212, and 0.434 radians respectively. The location 2 path overlaps several lane polygons near its goal, so map matching remains ambiguous even though the directed route exists. The Lanelet2/OpenDRIVE origin checks remain in each `validation.json`. The full link and occupancy records are in each scene's `map_audit.json`.

## Late entry

`late_spawn_runtime.py` builds a source-hashed BehaviorBench C binding under `/tmp` without editing the checked-in benchmark. It reserves slots for future-valid actors during both agent counting and environment initialization. Such actors have invalid position, zero observation, and no pre-entry reward. At the first valid sample they receive recorded position, heading, velocity, and reset controller state. IDM and dynamics apply their first movement one step later; expert replay follows the source sample immediately. `pilot_ind.py --late-mode runtime_spawn` preserves the source validity mask.

The [late scene](pilot/validated/late04_selective/testing/spawn_validation.json) has track 13 entering at step 16 and track 14 at step 48. In both action-driven and IDM modes, neither appears or earns a collision/off-road/goal reward before entry; maximum birth position error is 0.0000061 m. Their first controlled movement is approximately 1.9–2.0 m over 0.1 s. Expert replay matches all 577 valid samples with no missing actor or ego collision/off-road event. The full scene loses 90 valid samples from stationary track 1; the final selective variant excludes only that car, which remains at least 33.55 m clear of the ego bounding circle. The same runtime also passes the original no-late scene and two nearby late-window replays. An early recording-00 probe remains rejected: another vehicle is removed for five valid samples after an off-road event despite successful late births. This is a scene-specific replay failure, not a reason to alter its source track.

PDM with IDM traffic on the late scene reached its goal with no reported collision or road departure in one smoke run. This does not establish robustness of the runtime across all actor types, maps, or traffic policies. In particular, actor capacity, exit/re-entry behavior, and PPO/SMART runs with the patched binding still need broader testing before research scoring.

## Stationary cars

The original 15 m radius crop removed five stationary cars from recording 13 and 17 from recording 21. All were at least 13.39 m and 12.52 m clear of the ego's bounding circle over the window, respectively, but deleting that many cars changes the traffic scene. The uncropped expert replay loses 90 valid samples from one car in recording 13 and 540 samples across six cars in recording 21. The late-arrival scene's 15 m crop removed three stationary cars, while the uncropped replay loses only track 1; the final late scene uses selective exclusion too. The removal happens in the simulator, even though the source validity masks remain set.

Changing the crop radius demonstrates this sensitivity: recording 13 passes at 10 and 15 m, then fails at 20 and 30 m; recording 21 passes at 10, 15, and 20 m, then fails at 30 m. A selective exclusion of only the cars lost by the uncropped replay gives passing scenes while retaining more parked traffic: exclude track 3 in recording 13 (14 objects retained), and tracks 8, 16, 17, 18, 19, 43 in recording 21 (16 objects retained). Every excluded source track is stationary; the minimum ego bounding-circle clearance among excluded tracks is 13.92 m and 16.14 m. No retained source position or validity flag changes. The per-track evidence is in each `crop_audit.json`.

The selective sets are diagnostic ablations, not evidence that the dropped cars are irrelevant to other actors or to a different ego path. A same-map PDM/IDM comparison on recording 21 collided in both the selective scene and the 15 m crop at step 26; the broader crop did **not** change that smoke outcome. A future benchmark must resolve why these parked cars are removed and test multiple traffic models and planner trajectories before using either crop for a geographic-transfer claim.

## Reproduce

From this directory, using the local `bb_pufferdrive` environment:

```bash
python pilot_ind.py --recording 4 --ego 12 --first-frame 605 --static-crop-radius 1000000 --exclude-track-ids 1 --late-mode runtime_spawn --output-root pilot/validated/late04_selective
python audit_scene.py --root pilot/validated/late04_selective
/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python validate_replay.py --root pilot/validated/late04_selective --late-runtime
python audit_crop.py --cropped pilot/validated/late04_selective --full pilot/probes/late04_full
/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python validate_spawn.py --root pilot/validated/late04_selective
GEOTRANSFER_SCENE_ROOT=pilot/validated/late04_selective GEOTRANSFER_LATE_RUNTIME=1 /home/inigo/miniconda3/envs/bb_pufferdrive/bin/python run_pilot_eval.py --planner.type pdm --traffic.type idm
```

For the selective crop, use `--static-crop-radius 1000000 --exclude-track-ids 3` on recording 13 or `--exclude-track-ids 8 16 17 18 19 43` on recording 21, with their ego/frame settings in the table. Run `audit_crop.py --cropped <scene> --full <uncropped-scene>` after replay. The `--exclude-track-ids` option is an explicit documented ablation; it is never applied by default.
