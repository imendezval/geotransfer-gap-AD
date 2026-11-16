# Single-scene inD transfer pilot

## Result

Recording 00 at inD location 4, frames 260–485, ego track 7 was converted to a 91-step, 10 Hz BehaviorBench scene. The reproducible converter is `pilot_ind.py`; its outputs are in `pilot/testing/`. This scene passes a source-to-binary round trip and a direct C-engine expert replay check. It is a feasibility pilot, not evidence of a US-to-Germany planner gap.

## Scene construction

- Source: inD 25 Hz CSV tracks and track metadata; location 4 Lanelet2 map. The OpenDRIVE header is used as an independent UTM-origin cross-check. CSV and OpenDRIVE origins differ by 0.00065 m.
- Time sampling: frames 260 through 485 at 2.5-frame intervals, using linear position/velocity interpolation and unwrapped heading interpolation. There are no actors entering after the chosen start frame. An earlier frame-0 window was rejected because the simulator does not initialize late-arriving actors (`set_active_agents` requires `traj_valid[init_steps] == 1`).
- Map: Lanelet boundaries are projected from WGS84 to UTM zone 32 and shifted by the recording origin. The script emits 119 road/bus-lane centerlines, 131 curb/border polylines, and 106 successor links. It crops two distant stationary cars (tracks 4 and 5); one was suppressed by the simulator in the uncropped replay. The remaining eight actors are all active.
- Ego: track 7 starts at `(126.463, -54.180)` m. Its goal is its recorded position at sample 85, `(99.255, -72.514)` m, leaving 0.5 s for goal registration. The start and goal are on lanelets 1127 and 1045, connected through the generated successor graph. The goal is 32.81 m from the start.
- The JSON is written to `pilot/testing/ind_00_track_7_frame_260.json`, then passed to BehaviorBench's **unmodified** `save_map_binary()` function. The converter loads that function from the local source file because the default Python 3.12 interpreter cannot import the repository's Python 3.11 extension. The resulting `map_000000.bin` is read back with BehaviorBench's binary reader. `manifest.csv` sets ego index 0.

## Validation

`pilot/testing/validation.json` reports maximum JSON-to-binary actor-position error of 0.0000076 m, median/max ego distance to a mapped lane centerline of 0.78/1.29 m, and a reachable goal lane. The hand-viewed overlay in `pilot/testing/overlay.png` shows the ego turn and other actor tracks aligned with the map.

`validate_replay.py`, run in the `bb_pufferdrive` Python 3.11 environment, puts every actor in expert mode and compares every valid simulator position and heading to the converted source window. `pilot/testing/replay_validation.json` reports 575 position samples compared, maximum position error 0.0000078 m, maximum heading error 0.00000024 rad, zero missing valid samples, and zero ego collision/off-road events in the expert replay. The expert ego also reaches the goal in this direct replay.

## Closed-loop smoke tests

BehaviorBench's evaluator defaults to 100 maps even for a one-map split. `run_pilot_eval.py` supplies `num_maps=1` at runtime without editing BehaviorBench. The split must be named `testing` because `Drive` has a fixed allowlist of split names. The table below reflects one run per condition with the provided checkpoints, not a statistical comparison.

| Ego planner | Traffic | Goal | Collision | Off-road | Notes |
|---|---|---:|---:|---:|---|
| PDM | Expert | yes | no | no | Baseline scenario executes. |
| PDM | IDM | yes | no | no | Interactive traffic executes. |
| PPO (`simple_ppo.pt`) | Expert | no | yes | no | Rear collision at step 23, classified as not ego-at-fault. |
| PPO (`simple_ppo.pt`) | IDM | yes | no | no | Outcome changes with traffic model. |
| SMART (`SMART_epoch_030.pt`) | Expert | no | yes | no | Lateral collision at step 40, classified as not ego-at-fault. |
| SMART (`SMART_epoch_030.pt`) | IDM | no | no | yes | Off-road event at step 66. |

Per-map CSVs, configs, logs, and collision snapshots are under `pilot/runs/`. The expert-traffic collisions are especially poor evidence of a planner defect: replay actors cannot react to the ego's changed path, and the benchmark's collision classifier marks the two observed collisions as not ego-at-fault. The SMART/IDM off-road event is a candidate for manual trajectory and map-edge inspection, not a transfer conclusion.

## Remaining validity limits

The conversion uses Lanelet2 road geometry and OpenDRIVE only for origin verification. It has not yet checked every lane boundary, traffic sign, priority rule, or road-edge collision polygon against the source map. Lanelet successor links are inferred from shared endpoints or proximity; they are not a complete traffic-rule graph. The simulator also applies its standard collision-box scaling to loaded vehicles, so simulator collision outcomes do not directly reproduce source physical overlaps. This window has no late arrivals, but a general adapter must address late-spawn handling before it can represent arbitrary inD recordings. The 9-second episode and goal at sample 85 are pilot choices and need sensitivity checks before benchmark use.

## Reproduce

The original pilot predates the exact `evaluation.ini` traffic audit. It now fails that stricter gate because a background actor disappears at step 1 and the episode resets before the nominal end. Use the guarded late-VRU reproduction in [EXPANSION_RESULTS.md](EXPANSION_RESULTS.md) for current integration tests. The commands below reproduce only the historical converter and direct replay, not an accepted evaluator scene.

From this directory:

```bash
MPLCONFIGDIR=/tmp/mpl-geotransfer python pilot_ind.py
/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python validate_replay.py
```

For PPO or SMART, pass the corresponding `--planner.type`, `--planner.<type>.weights-path` pointing to a local BehaviorBench checkpoint, `--planner.<type>.device cpu`, and `--traffic.type expert` or `idm`.
