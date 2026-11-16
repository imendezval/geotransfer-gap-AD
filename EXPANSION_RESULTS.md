# Expansion experiments (9 November 2026)

The standards were set before work in [EXPANSION_PLAN.md](EXPANSION_PLAN.md). All planner results below are integration smoke tests. No scene has yet passed the source-map semantic gate for a geographic performance claim.

## 1. Stationary actors

**Problem.** Downsampling a temporarily stopped car can make it look permanently parked. A stationary background obstacle also has to remain present in observations and collision checks, including when the evaluator uses different collision-box settings.

**Work and evidence.** [scan_stationary.py](scan_stationary.py) checked 98,476 overlapping 9 s vehicle windows in recordings 0, 4, 8, 13, 20, 21, 24, and 28 at source 25 Hz. The existing 0.5 m path / 0.1 m/s maximum-speed rule marked 91,945 windows; 91,813 still qualify at 0.25 m / 0.05 m/s. A 10 Hz classification produced zero false-static windows relative to the 25 Hz rule in this scan. The large marked fraction reflects long parked tracks and overlapping windows, not independent vehicles. Recording 0 track 1 provides a useful temporary-stop case: its whole track travels 53 m, but a 9 s segment travels only 0.17 m. The converter now stores source-window path and speed and requires both source-rate and sampled checks before marking a vehicle static.

The three original full scenes retain every source actor. [validate_parked.py](validate_parked.py) now runs against `evaluation.ini` (collision scale 1.0); full04, full13, and full21 pass with zero missing parked samples and zero position drift. [probe_parked_interaction.py](probe_parked_interaction.py) confirms a nearby parked actor appears in the ego partner observation and causes a collision on direct overlap in each full scene. A temporary-stop technical scene, `pilot/probes/temporary_stop00`, keeps the stopped actor fixed; its full-scene expert replay fails because a *different* actor exits early under normal termination. The no-early-reset diagnostic passes the parked check and is deliberately excluded from the evaluator gate.

**Remaining problem.** The rule is only a per-window static representation. A car that starts moving after the chosen 9 s window cannot be represented by this mark in a longer episode. More seriously, the actual evaluator can remove a nonstatic background actor well before its source track ends; full04 track 13 is removed after a collision and full13 track 104 is removed early. The new evaluator-traffic gate rejects those scenes even though their earlier `drive.ini` replay passes.

## 2. Late arrivals and exits

**Problem.** A valid late-spawn binary can still be unfair if a future actor appears early, is assigned a policy slot inconsistently, disappears before its source exit, or triggers an early episode reset under the evaluator configuration.

**Work and evidence.** [find_vru_candidates.py](find_vru_candidates.py) found 3,016 moving-ego/late-VRU pairs across 33 recordings. The 500 closest ranked unique windows yielded 24 geometry-valid scenes. Three hand-selected geometry-valid windows with late cyclists/pedestrians passed normal source replay, evaluator-config birth/exit checks in dynamics and IDM modes, and evaluator-config parked checks. Birth position/heading/velocity errors remain below 0.01 in their respective units; pre-entry state/event and post-exit appearance counts are zero. [probe_repeat_reset.py](probe_repeat_reset.py) confirms deterministic actor slots and repeated outcomes over three resets under `evaluation.ini`.

The best guarded runtime scene is [r00_e299_f19630](pilot/probes/vru_search/r00_e299_f19630/testing/evaluation_replay_probe.json): recording 0, ego 299, 13 objects, five late actors including a cyclist, two parked static actors. Its original expert replay matches 812 samples within 0.000011 m. Under `evaluation.ini`, no background actor disappears more than two samples before its source exit, and preterminal position error is below 0.000011 m. Expected ego goal removal occurs near its goal. PDM with expert traffic, PPO with IDM traffic, and SMART with expert traffic all run through [run_pilot_eval.py](run_pilot_eval.py). Their single-scene outcomes must not be interpreted as planner comparisons because the map omits relevant rules.

**New failure exposed.** `evaluation.ini` uses `goal_behavior=3`, `collision_shrink=1.0`, and remove-on-collision/offroad behavior. The earlier `drive.ini` validation used `goal_behavior=4` and `collision_shrink=0.7`. [probe_eval_replay.py](probe_eval_replay.py) now distinguishes expected ego removal near goal and up-to-two-sample background truncation from early background loss or preterminal episode reset. The late pedestrian scene r02 loses track 107 at step 1 although its source track remains valid through step 90; it is now rejected. Full04, full13, full21 and recording 15 scene r15 also fail the stricter evaluator-traffic gate. A reset at step 89 can cause a large apparent position jump before the nominal terminal observation; full21 is rejected. Of the 24 geometry-valid scenes in the first 500 ranked unique windows, only r00 passes this evaluator-traffic audit under the present conversion and goal definitions.

**Remaining problem.** VRUs are expert background actors, not controllable VRU policies. The 128-actor guard prevents overflow but does not increase capacity. There is still no semantically complete, evaluator-faithful late-VRU research scene.

## 3. Map semantics and compatible scenes

**Problem.** Polygon occupancy and directed route connectivity do not tell us whether missing German priority, sign, crosswalk, and marking information changes the ego task. The initial 5 m sign heuristic let recording 15 scene r15 through even though relevant signs are 5.2–8.8 m from its path.

**Work and evidence.** [audit_map_semantics.py](audit_map_semantics.py) now records minimum ego-to-crosswalk-boundary distance and applies a conservative screen: no regulatory relation on occupied ego lanelets, no source sign within 20 m, no crosswalk within 5 m, and no omitted wall/fence or thick marking within 5 m. This screen is necessary for candidate selection, not a proof of semantic equivalence. [prefilter_semantic_candidates.py](prefilter_semantic_candidates.py) checked all 3,016 late-VRU pairs against source traffic-sign geometry; only 16 pairs (13 unique windows) remained at 20 m. Full conversion and audits of those 13 found 12 semantic-screen failures. The only semantic-screen pass, r00_e367_f23513, has no directed successor route from start lanelet 1046 to goal lanelet 1048; the source ego transitions from a bus lane across a curbstone boundary, and normal expert replay also loses its final ego sample. Thus **none of this defined late-VRU candidate pool passes both gates**. This does not prove that all inD windows are unsuitable.

The binary writer accepts sign and crosswalk types 7 and 8. [probe_map_feature_visibility.py](probe_map_feature_visibility.py) added both within a few metres of the ego using the unmodified writer: the binary hash changed and the C loader reported both types, but the 1,151-value ego observation had exactly zero change. The C grid indexes road types 4–6 only. Adding map entities without changing the observation path cannot convey these rules to unchanged checkpoints.

**Remaining problem.** No selected intersection scene supports a defensible US-to-Germany planner-failure claim. Research scoring remains blocked by `GEOTRANSFER_RESEARCH_SCORE=1`. The next viable direction is to find a compatible scene outside the constrained late-VRU pool, or design and validate an observation/rule representation with an explicit model adaptation protocol. A map screen pass still needs manual route, sign-facing, lane-change, and conflict review.

## Reproduce the strongest late-VRU technical scene

```bash
PY=/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python
ROOT=pilot/probes/vru_search/r00_e299_f19630
$PY validate_replay.py --root "$ROOT" --late-runtime
$PY validate_spawn.py --root "$ROOT" --eval-config
$PY validate_parked.py --root "$ROOT" --eval-config
$PY probe_eval_replay.py --root "$ROOT"
$PY probe_repeat_reset.py --root "$ROOT" --eval-config
GEOTRANSFER_SCENE_ROOT="$ROOT" GEOTRANSFER_LATE_RUNTIME=1 $PY run_pilot_eval.py --planner.type pdm --traffic.type expert
```

The search summaries are in `pilot/audits/`. Generated binaries for failed, redundant windows were removed after screening; retained geometry-valid and sign-clear scenes can be regenerated with the search scripts.
