# German reviewed-scene native diagnostic comparison

This bounded diagnostic compares the two specified reviewed scenes under a
fixed expert-traffic background. It ran eight controller/scene combinations
plus one exact SMART repeat. Every execution returned success; all nine offline
evaluations completed, and a viewer HTML was generated for each trace. The
traces and evaluation outputs are diagnostic-only. They do not establish a
controller-pair admission or transfer claim.

## Inputs and fingerprints

| Scene | Source review | Opportunity | Scene binary SHA-256 | Review JSON SHA-256 | Reviewed montage SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `r00_e39_f3000` | complete, admit | No qualifying interaction; adjacent vehicle 40 is source context | `55e0e8d2cbbeb9684cb435c7dd7da116e1886737d0c4e437f03d1b7ed8521edf` | `d1a7acaec575679aec203d986e7714c1c0c3be167e9a55b4c097feb43e8639fd` | `c3ea0b4a32682fe831f2895d691a7038e7df3847adeaf331b087af80eb5acb5a` |
| `r16_e35_f1521` | complete, admit | Lead vehicle 33 stops and restarts; tested as a longitudinal-following scene | `b0e66005dd27f2c02edc741d1b20274d0f66e8e5ae64cbcc496f76035c1dea1b` | `aa4baa5a76c43d3784f99a03cf4b4a979537b248ea9bdb91f43b44d2413c9a57` | `5415218a704682065900b0eefa219dacde5bb248e2d3ffe983e50f20fa209eda` |

The saved source tracks and lanelet map fingerprints were also present and
matched: r00 tracks `d222312f2c87cc492624c09109af0c6688871fa111939c45eba3ea089ccaf32c`,
map `16dcaffd0cf6e3b50eff8c23af303f445a0b43db1474bf25f0440f54d8585973`;
r16 tracks `4a58dbb5e242166e58f7558708b19a7eb49458d8191ca1c087d9156070907534`,
map `e6cb0b8218bebbe5953cb1338afd96c63b18fa15f5010e44645623d39d5ce4fe`.

For both scenes, the saved SMART admission evidence files still match current
files (35/35), the scene binary and review montage match, and the original
SMART protocol source fingerprints match (7/7). `SMART_epoch_030.pt` is
`b2cdeb31b0336588df1fc872e2f64dc6b24ec88472936068ec7e9501e9252616`. The
loaded native runtime source digest is `beedf8f1b0e9c490`, and the runtime
binding SHA-256 is
`bdf1a2cb70f4153a0283a45fe18920b09a545ecba15fdb335a87a31762b94d58`. The
current evaluation INI matches the saved fingerprint
`afdf157a7b809e31700a49f977c46a7a4913c7e73546a5803d8635a9ae1f5e4e`.

The saved expert evaluation contract is not fully current: 40/41 inputs match
for each scene. Its `src/geotransfer_gap/artifacts.py` pin is
`e98bf52382dcd63e9288983a49b7a5efb12db9362bd9f5313361e2ed720e86ee`; current
SHA-256 is
`9d914a603264e63716f24a386f7f4993e79a917dd1406fc858e5834994e4a467`. This
preflight mismatch and the run configuration below are reasons to treat the
new runs only as diagnostics. Their verification records leave
`controller_pair_research_admission` as `not_established`.

The original SMART scene protocol used `hybrid_startup` with 10 warmup steps.
These runs instead use `--traffic expert --traffic-startup immediate` for
every ego. The traces still record 10 source replay warmup frames for ego
control, followed by controller actions. Immediate traffic startup does not
reproduce the original hybrid-startup traffic policy.

The PPO checkpoint was `weights/simple_ppo.pt`, SHA-256
`50a9a580cca905fc3dae47b5847b4edf408de3b7fe7517bd4f3a781fa140e3b3`, on
BehaviorBench commit `805fe04c6977b60c41c92c31f1a5211fbd704f44`. Its pinned
provenance reports a 1,151-wide float32 observation with current actor state,
static road geometry, and the simulator navigation goal. Its architecture is
`Drive(64,256) + LSTMWrapper(256,256)`, with CPU inference, seed 0, and argmax
over 91 joint logits. Future actor arrays and background IDM route points are
not model inputs. SMART used
`SMART_epoch_030.pt` (`b2cdeb31b0336588df1fc872e2f64dc6b24ec88472936068ec7e9501e9252616`)
on CPU with greedy decoding. Its run provenance describes static map,
observed joint histories, and observed-birth velocity as inputs; it does not
list the simulator goal field as a separate model input. IDM's ego prior is a
native lane route; source-informed route points apply only to eligible
background IDM actors, and this matrix fixed background traffic to expert
replay.

## Commands and artifacts

The first eight commands were launched sequentially by
[`run_matrix.sh`](../../../runs/german_200_yield_workstream_e/run_001/run_matrix.sh).
The corresponding evaluation and viewer loop is
[`evaluate_matrix.sh`](../../../runs/german_200_yield_workstream_e/run_001/evaluate_matrix.sh):

```sh
GEOTRANSFER_RUNS="$PWD/runs/german_200_yield_workstream_e/run_001/native" \
PYTHONPATH=src OMP_NUM_THREADS=1 \
.venv/bin/geotransfer run --scene SCENE --ego EGO \
  --traffic expert --traffic-startup immediate --diagnostic --capture-evaluation
```

`SCENE` was each of `r00_e39_f3000` and `r16_e35_f1521`; `EGO` was each of
`expert`, `idm`, `ppo`, and `smart`. Every first-matrix command returned 0.
For each run, the following were run into the same isolated `run_001` tree:

```sh
.venv/bin/geotransfer evaluate run --run RUN_DIR --output EVALUATION_DIR
.venv/bin/geotransfer view --scene SCENE --trace TRACE_JSON \
  --evaluation EVALUATION_DIR --output VIEW_HTML
```

An exact SMART repeat used:

```sh
GEOTRANSFER_RUNS="$PWD/runs/german_200_yield_workstream_e/run_001/native" \
PYTHONPATH=src OMP_NUM_THREADS=1 \
.venv/bin/geotransfer run --scene r16_e35_f1521 --ego smart \
  --traffic expert --traffic-startup immediate --diagnostic --capture-evaluation
```

Its evaluation and view commands were:

```sh
.venv/bin/geotransfer evaluate run \
  --run runs/german_200_yield_workstream_e/run_001/native/20261126T122321_smart_expert_c246e0 \
  --output runs/german_200_yield_workstream_e/run_001/evaluations/20261126T122321_smart_expert_c246e0
.venv/bin/geotransfer view --scene r16_e35_f1521 \
  --trace runs/german_200_yield_workstream_e/run_001/native/20261126T122321_smart_expert_c246e0/r16_e35_f1521/trace.json \
  --evaluation runs/german_200_yield_workstream_e/run_001/evaluations/20261126T122321_smart_expert_c246e0 \
  --output runs/german_200_yield_workstream_e/run_001/views/20261126T122321_smart_expert_c246e0.html
```

The repeat trace SHA-256 is identical to the first `r16_e35_f1521` SMART trace:
`d8190bc79fb8d93a967f97f80448ffaae7c4618a5e7d04bf1fcdd826da65c366`.
Its evaluation is complete and its viewer was generated as well.

Raw native traces, evaluation captures, run ledgers, evaluation results, and
HTML views are under ignored
[`runs/german_200_yield_workstream_e/run_001`](../../../runs/german_200_yield_workstream_e/run_001).
The matrix completion log is `matrix_status.tsv`; compact trace-derived results
are in `native_summary.json` (SHA-256
`d14435fe18897ca68b003c280e62e947611db1955814e2d20145a529b2950877`), and
fingerprint comparisons are in `preflight_fingerprints.json` (SHA-256
`10379ac7593ea2f52a0ee46d881a105b40939d89862978b7b144f325d0caefe1`).
Fingerprint and metric summaries were regenerated with `PYTHONPATH=src
.venv/bin/python runs/german_200_yield_workstream_e/run_001/fingerprint_audit.py`
and the same command with `summarize_native.py`.
Eight matrix trace SHA-256 values are:

```text
r00_e39_f3000 expert  3f0213e7491b3fe3758a664d130507eb51148c6cb18a1c679fb079028c1c72e8
r00_e39_f3000 idm     5340f786a9e7b792e289fecea08d8fd0346b221f858f0032f8d3e153c61165b0
r00_e39_f3000 ppo     7ae8a105cf8be26f5b0716eb6c4fa7419e628b032afed7a277712550facb1fa0
r00_e39_f3000 smart   3784ae6765596b90c61ff731d5118b0833548c5be652d4eb84fda39e8b391a24
r16_e35_f1521 expert  e19086ac1b4014b5672b72b737ea6c286c6d4a847de672f6a3b402a9bf7dc85c
r16_e35_f1521 idm     86a6c9cc2d19f0a449e375cabe7b64ae9e9f8f0e32a9dd563d80b97130a88b46
r16_e35_f1521 ppo     0cf1dfa6f38112d0cb82d98c98f38409cdf568f60818ccdc7f84ce2fcf9cd4a5
r16_e35_f1521 smart   d8190bc79fb8d93a967f97f80448ffaae7c4618a5e7d04bf1fcdd826da65c366
```

## Trace results

Each evaluation completed 1/1 episodes with valid archived-attested trace
evidence. All nine task outcomes remain unresolved; no run reported a native
collision or off-road onset, and each sampled footprint overlap count is zero.
The onset counters are trace observations, not exhaustive contact catalogs.
Minimum clearance is the smallest supported sampled footprint gap. Stationary
duration is a speed-threshold measure, not a stall verdict.

| Scene / ego | Observations / transitions | Terminal reason | Native collision / off-road onsets | Minimum sampled gap (m) | Distance observed (m) | Goal gap at terminal (m) | Stationary duration (s) | Task result |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| r00 / expert | 84 / 83 | ego removed | 0 / 0 | 2.095 | 101.906 | 2.802 | 0.0 | unresolved |
| r00 / IDM | 91 / 90 | horizon | 0 / 0 | 5.076 | 143.606 | 48.597 | 0.0 | unresolved |
| r00 / PPO | 60 / 59 | ego removed | 0 / 0 | 5.346 | 103.305 | 2.365 | 0.0 | unresolved |
| r00 / SMART | 91 / 90 | horizon | 0 / 0 | 4.940 | 171.482 | 74.923 | 0.0 | unresolved |
| r16 / expert | 82 / 81 | ego removed | 0 / 0 | 1.767 | 10.938 | 2.145 | 4.0 | unresolved |
| r16 / IDM | 86 / 85 | ego removed | 0 / 0 | 1.137 | 10.883 | 2.182 | 1.4 | unresolved |
| r16 / PPO | 74 / 73 | ego removed | 0 / 0 | 1.309 | 13.509 | 2.293 | 2.1 | unresolved |
| r16 / SMART | 74 / 73 | ego removed | 0 / 0 | 0.999 | 10.912 | 2.337 | 1.9 | unresolved |

The table reports the first eight traces. The ninth trace exactly repeats the
r16 SMART row. `ego removed` ends observation before the requested episode
horizon, so any later trajectory is unobserved. In the r16 run, the controller
ends around 2.1–2.3 m from the saved goal; this is not a completion signal.
Route progress and interaction-outcome metrics are unavailable in these
diagnostics because current route compatibility certificates are absent.

## Source replay, warmup, and goals

The trace frames use the converted scene's own source positions at the same
simulation step. Under expert traffic, the reviewed source actor is replayed
with near-zero position error: r16 actor 33 has mean error `0.00000216 m`
(p95 `0.00000361 m`, 82 common samples); r00 actor 40 has mean error
`0.00000308 m` (p95 `0.00000643 m`, 76–79 samples depending on ego lifetime).
This is parity against the saved converted-scene trajectory, not a new
independent raw-CSV timing audit. It confirms that fixed expert traffic
preserves the recorded actor timing within this saved episode window.

All four ego position traces match through step 10 and first differ from the
expert trace at step 11. The SMART provenance records its first prediction at
step 10 and subsequent refreshes every five steps. Exact SMART input tensors
are not included in the evaluation capture, so these runs do not establish
controller observation parity. The captured navigation goal is the same across
controllers and agrees with the saved source goal within `0.00001 m` for both
scenes.

This captured goal parity does not make planner inputs identical. The r00 goal
field is `[144.10134, -43.61995]`; r16 is `[70.149935, -52.840485]`. At the r00
horizon, SMART and IDM end respectively 74.923 m and 48.597 m from the saved
goal, while PPO and expert terminate about 2.365 m and 2.802 m away. Without a
current route/task certificate, the intended route and meaning of that
difference are indeterminate. For r16, all four end 2.145–2.337 m from the
goal, but stationary duration and sampled clearance differ while actor 33
follows the same replayed source path. These trace differences do not establish
causal adaptation or task success.

Those coordinates are the scene contract's sample-85 goal. The evaluation
capture records native goal coordinates `[144.101333618, -43.619949341]` for
r00 and `[70.149932861, -52.840484619]` for r16, within 0.00001 m of that
contract field. PPO provenance describes consuming the simulator goal and its
German goal rule as the final valid source position; SMART provenance lists
observed histories/map/birth velocity but not a separate simulator-goal input.
The captured field verifies what the environment exposes, not which fields a
model actually consumes; exact model observation tensors are not saved here.

The converted source replay is limited to the saved 91-observation window
(9.0 s at the requested horizon). Expert traffic follows recorded actor paths;
after the 10-frame ego warmup, IDM/PPO/SMART trajectories are policy outputs.
Terminal ego removal truncates several traces before the requested horizon.
The control scene has no reviewed interaction opportunity. The r16 source
review identifies a following opportunity, but the outcome metrics remain
unresolved and do not establish yielding, task completion, or safety. These
German-only diagnostics do not establish transfer.

## US matching and remaining matrix hold

No matched US control/longitudinal pair was available for this diagnostic. The
local `us_hybrid_1002fdc9826fc6d1` and
`us_smart_negative_world_739e0513c6f7cfe8` roots are SMART interface references,
not geographic-study controls. The existing
`expert_idm_source_hold.json` manifest is diagnostic-only, uses source-hold,
and contains no source-only matching annotations for family, subtype, initial
speed, route length/curvature, traffic composition/density, horizon, or
geometry. Those two binaries do not supply a matched US control and following
comparison to these German runs.

A geographic comparison first needs reviewed US control and longitudinal
scenes with the same task-goal meaning, goal visibility, interaction timing,
and source-verified legal semantics. Match scenes using the fixed source-only
strata: interaction family/subtype, initial speed, route length/curvature,
traffic composition/density, horizon, and geometry. Run the same ego
controllers with expert-immediate traffic, identical checkpoints, evaluation
INI, goal rule, warmup, and metric profile. Repeated controller runs within one
source scene remain clustered by that scene and its recording/site; they are
not independent geographic samples. A blinded pilot must estimate
recording/site variance across multiple independently identified US sites and
recordings. Use matched/paired uncertainty clustered by recording/site. The
current comparison readiness config calls for at least three independent sites
per domain and has no valid matched cohort. The full controller matrix remains
on its stale-evidence hold; this two-scene diagnostic does not clear or
revalidate that matrix.
