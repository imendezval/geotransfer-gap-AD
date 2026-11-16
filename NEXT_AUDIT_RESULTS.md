# Stationary actors, late entry, and map semantics (7 November 2026)

The acceptance standards were fixed before these experiments in [NEXT_AUDIT_PLAN.md](NEXT_AUDIT_PLAN.md). All results here are feasibility checks. The three full scenes are under `pilot/validated/full04`, `full13`, and `full21`; none excludes a source actor.

## 1. Stationary actors: uncropped replay now passes

**Cause.** BehaviorBench reads `offroad_behavior = 2` (remove) from `drive.ini`; the Python `offroad_behavior=0` argument does not override that INI setting. The lost cars already have `collision_state = OFFROAD` and `removed = 1` at reset, before the first step. The C metric checks whether a car box crosses a `ROAD_EDGE`. A source-coordinate box test using the configured 0.7 collision scaling found curb/road-border intersections for every car lost in the original full replays: track 1 in recording 04, track 3 in recording 13, and tracks 8, 16, 17, 18, 19, 43 in recording 21. The per-track edge IDs are in the original full probes' `parked_contact_audit.json` files.

**Change.** `pilot_ind.py --parked-as-static-expert` marks a car only when its full-window path length is below 0.5 m and maximum recorded speed below 0.1 m/s. The isolated C runtime honors that mark in evaluation: it creates an expert background obstacle, applies the same 0.7 collision-box scaling, replays its source track, and prevents IDM from moving it. It receives no driving reward or controlled-agent slot. The source trajectory and validity mask remain unchanged. This is a simulator representation change, not a source crop.

| Full scene | Retained objects | Parked expert obstacles | Matched expert samples | Largest position error | Parked IDM check |
|---|---:|---:|---:|---:|---|
| [04/12/605](pilot/validated/full04/testing/replay_validation.json) | 10 | 3 | 668 | 0.000014 m | [Pass](pilot/validated/full04/testing/parked_validation.json) |
| [13/108/6858](pilot/validated/full13/testing/replay_validation.json) | 15 | 6 | 1,244 | 0.000006 m | [Pass](pilot/validated/full13/testing/parked_validation.json) |
| [21/320/16936](pilot/validated/full21/testing/replay_validation.json) | 22 | 17 | 1,928 | 0.000007 m | [Pass](pilot/validated/full21/testing/parked_validation.json) |

All three uncropped expert replays have zero missing valid samples and zero expert ego collision/off-road events. All parked cars remain at the recorded position for 91 IDM steps; their C box dimensions match 0.7 times the source dimensions within 0.000001 m. The runtime source hash in the reports identifies the isolated build. PDM/IDM smoke runs on the full scenes reached the goal in recordings 04 and 13 and collided in recording 21; those outcomes are not research scores because map semantics remain incomplete.

**Remaining limit.** Static treatment is justified for these truly stationary cars; the same rule must be reviewed on new recordings with slow or temporarily stopped vehicles. The parked-car runtime is tested in the evaluation control mode and with PDM/IDM smoke runs, not across every BehaviorBench training mode or planner. Its collision behavior as a background obstacle still needs targeted interaction tests before claiming that these scenes reproduce every roadside interaction.

## 2. Late arrivals: births, exits, VRUs, and simultaneous entries

The runtime now reserves future-valid actors, initializes all dormant state, spawns them once at the first valid sample, and retires action-driven/IDM actors after their last valid sample. A retired actor cannot reappear during the same episode. The first controller movement occurs one step after birth; birth position, heading, and velocity are source values. VRUs remain expert background actors under IDM traffic. The converter rejects more than 128 retained actors, the C engine's actor-slot limit; a boundary check accepted 128 and rejected 129.

| Probe | Births | Birth/exit check | Expert replay | Research-scene status |
|---|---|---|---|---|
| [Full 04](pilot/validated/full04/testing/spawn_validation.json) | 2 vehicles, steps 16 and 48; first exits at step 75 | Pass in action-driven and IDM modes | 668 samples pass under normal termination | Geometry-valid candidate; map rules missing |
| [Recording 07 technical probe](pilot/probes/vru07/testing/spawn_validation.json) | vehicle, pedestrian, cyclist | Pass in both modes | Pass with early termination disabled | Ego lies outside mapped lane polygons; not a planning scene |
| [Recording 20 technical probe](pilot/probes/vru_20e3/testing/spawn_validation.json) | 10 actors including vehicles, pedestrians, cyclists, and two pedestrians at step 55 | Pass in both modes | Pass under normal termination | Ego route fails map gate; not a planning scene |

Across these probes, no late actor appears, emits a controlled observation, or earns an event reward before birth. Maximum birth position error is below 0.000007 m, heading error below 0.00000013 rad, and velocity error below 0.000001 m/s. No actor remains after its recorded exit in the full-duration technical check. Recording 07 requires `termination_mode=0` for its 91-step technical replay because its parked ego and remaining controlled agents otherwise finish early and the default engine starts a second episode. The evaluator explicitly rejects a replay report made with this altered termination mode.

**Remaining limit.** The VRU examples prove expert-background entry, not controllable pedestrian or cyclist policy behavior. The actor-capacity guard prevents silent loss but does not expand the 128-slot engine. Broad multi-map, PPO, and SMART regression is still needed before treating the patched runtime as a benchmark-wide replacement.

## 3. Map semantics: geometry passes, right-of-way transfer does not

`audit_scene.py` confirms all 91 ego samples in each full scene lie inside Lanelet2 polygons. Occupied start and goal lanelets are connected by directed successors; every emitted successor shares at least one source boundary node, no successor reverses direction, and all centerline gaps are at most 1 m. `audit_map_semantics.py` compares the Lanelet2 ways, regulatory relations, OpenDRIVE signal inventory, emitted JSON, and binary road types.

| Scene | Source curb/border ways emitted | Largest source-to-binary edge deviation | Ego-lane priority relations | Crosswalks traversed | Nearby source sign |
|---|---:|---:|---:|---:|---|
| [Full 04](pilot/validated/full04/testing/map_semantics_audit.json) | 131/131 | 0.000008 m | 1 (yield) | 2 | `de205` yield, 2.7 m |
| [Full 13](pilot/validated/full13/testing/map_semantics_audit.json) | 36/36 | 0.000005 m | 4, conflict-specific roles | 0 | `de301`, 4.4 m |
| [Full 21](pilot/validated/full21/testing/map_semantics_audit.json) | 166/166 | 0.0993 m | 6, conflict-specific roles | 1 | `de102`, 4.3 m |

The converter emits lanes and road edges only. All three binaries contain no stop-sign or crosswalk entity, and their JSON has no traffic-control state. Lanelet2 right-of-way relations and speed-limit tags are also absent from the planner input. OpenDRIVE independently contains relevant signs and markings. BehaviorBench's C road-observation grid indexes entity types 4–6 (lane, line, edge); types 7–8 (stop sign, crosswalk) are not inserted into that grid. Merely adding those types to the binary would not give this planner interface the missing rule semantics.

The omitted `line_thick` ways near the ego in recordings 13 and 21 include stop/priority markings; they should not be misclassified as physical curbs. No omitted wall or fence way comes within 5 m of the selected ego paths. `run_pilot_eval.py` labels these evaluations as **geometry-only smoke tests**. Setting `GEOTRANSFER_RESEARCH_SCORE=1` rejects them until the source priority, sign, and crosswalk information is represented and validated, or semantically simpler scenes are selected.

**Remaining blocker.** The current JSON-to-binary path and BehaviorBench observation interface have no tested way to express conflict-specific Lanelet2 right-of-way rules. Resolving this requires a map-semantic representation and planner observation change, or scene selection that avoids such rules. The three current scenes cannot support a geographic planner-failure claim on right-of-way behavior.

## Reproduce a full-scene check

```bash
python pilot_ind.py --recording 4 --ego 12 --first-frame 605 --late-mode runtime_spawn --static-crop-radius 1000000 --parked-as-static-expert --output-root pilot/validated/full04
python audit_scene.py --root pilot/validated/full04
python audit_map_semantics.py --root pilot/validated/full04
/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python validate_replay.py --root pilot/validated/full04 --late-runtime
/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python validate_parked.py --root pilot/validated/full04
/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python validate_spawn.py --root pilot/validated/full04
GEOTRANSFER_SCENE_ROOT=pilot/validated/full04 GEOTRANSFER_LATE_RUNTIME=1 /home/inigo/miniconda3/envs/bb_pufferdrive/bin/python run_pilot_eval.py --planner.type pdm --traffic.type idm
```

This replaces the earlier selective-crop variants as the best current representation of these source windows. The previous variants remain under `pilot/validated/` for comparison.
