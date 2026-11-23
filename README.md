# GeoTransfer Gap AD

Convert German inD recordings into BehaviorBench / PufferDrive scenes, audit their
faithfulness, and execute planners under an explicit evaluation protocol.

The research question is which recurring geographic planner failure types small,
targeted adaptations can repair. A German performance gap alone does not establish
a geographic effect: conversion, traffic, representation and task intent are controls.

## Current state

There are **16 independent SMART-admitted scenes**: six pedestrian encounters,
four following tasks, three cyclist crossings and three controls, spanning three
locations and ten recording clusters. Their original JSON and binaries are
preserved. The prospective corpus target is 50; the remaining 34 admissions and
coverage/sample-size requirements are separate work.

The maintained pipeline is:

```text
Source CSV + Lanelet2/OpenDRIVE
  → source selection → converted JSON → upstream BB binary writer
  → source/map/physical/replay/counterfactual validation
  → explicit semantic review → SMART input proof and admission
  → independent corpus manifest → isolated execution → offline playback
```

The controller matrix runs expert, IDM, PPO and SMART as ego or vehicle traffic.
It supports 16 immediate-start protocols and 12 source-hold protocols. At the
frozen M9 revision, all 448 German slots and all 32 immediate US slots passed
independent single/batch validation and exact trace comparison. The 24 US
source-hold slots lack authoritative source JSON. Matrix runs are diagnostic.
Original SMART admission applies to its recorded protocol, and encounter
preservation remains unassessed. See the [acceptance guide](docs/controller-matrix-acceptance.md).

## Setup

Use the existing `bb_pufferdrive` environment and make a local editable installation:

```bash
/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python -m venv --system-site-packages .venv
.venv/bin/python -m pip install --no-build-isolation -e '.[test,native-map]'
export MPLCONFIGDIR=/tmp/geotransfer_mpl
export OMP_NUM_THREADS=2
.venv/bin/geotransfer doctor
```

The BB checkout, licensed datasets, SMART weights and codebooks are external
inputs. They are not downloaded or included in this repository. Copy
`configs/example.toml` to `configs/local.toml` to override their locations, or use
`geotransfer --config /path/to/config.toml ...`. Relative configured paths use the
project root. Commands work outside this directory after the editable installation.

## Browse and visualize the 16 scenes

```bash
.venv/bin/geotransfer scenes list
.venv/bin/geotransfer scenes show r07_e200_f25439

# Offline gallery of the source and converted scenes; no inference required.
.venv/bin/geotransfer view --manifest artifacts/corpus/current.json --output runs/gallery

# Source + converted + fresh expert and admission-enforced SMART playback.
.venv/bin/geotransfer view --scene r07_e200_f25439 --run both --output runs/cyclist.html --open
```

Open `runs/gallery/index.html` in a browser. The pages are self-contained and need
no server. The time slider, actor labels, aerial background and comparison selector
show the original source, converted tracks and any captured evaluator rollouts.
An HTML page contains licensed source imagery; handle it as a dataset-derived artifact.

## Browse a saved controller campaign

```bash
# All scenes and accepted configurations from the saved M9 campaign.
.venv/bin/geotransfer view --campaign runs/m9_acceptance \
  --output runs/m9-gallery --open

# One scene with one saved configuration. Omit the controller flags for all its runs.
.venv/bin/geotransfer view --campaign runs/m9_acceptance --scene r12_e151_f12041 \
  --ego ppo --traffic smart --traffic-startup source_hold \
  --output runs/r12-ppo-smart-hold.html --open
```

The campaign index opens any passing cell in the offline viewer. Use the two
viewer menus to compare configurations on one scene. It reads the local
campaign report and traces and generates HTML without running models. A fresh
clone needs the saved campaign artifacts and the configured scene assets.

## Run a planner

```bash
# Run a fresh matrix episode and open the saved trace.
scene=r12_e151_f12041
episode=$(.venv/bin/geotransfer run --scene "$scene" \
  --ego ppo --traffic smart --traffic-startup source_hold)
.venv/bin/geotransfer view --scene "$scene" --trace "$episode/trace.json" \
  --output runs/ppo-smart-hold.html --open
```

Matrix startup defaults to `immediate`. Source hold is available for IDM,
PPO and SMART traffic. The original replay and faithful SMART commands remain
available for baseline reproduction.

```bash
.venv/bin/geotransfer run --scene r07_e200_f25439 --planner smart
.venv/bin/geotransfer run --manifest artifacts/corpus/current.json --planner smart
.venv/bin/geotransfer run --scene r07_e200_f25439 --planner expert
```

Every run gets its own directory under `runs/`. SMART and expert runs include
provenance, logs and a state trace; the BB bridge retains upstream outputs and logs.
SMART requires current admission by default. `--diagnostic` explicitly
allows an unadmitted experiment and cannot grant admission. To view a saved trace:

```bash
.venv/bin/geotransfer view --scene r07_e200_f25439 \
  --trace runs/RUN_ID/r07_e200_f25439/trace.json --output runs/saved.html
```

The BB diagnostic bridge retains its planner/config options:

```bash
.venv/bin/geotransfer run --scene r07_e200_f25439 --planner bb --diagnostic \
  --bb-args --planner.type pdm --traffic.type expert
```

The BB bridge can also run upstream PPO with the checkpoint and device options
required by the BB checkout. The verified matrix uses `--ego ppo` or
`--traffic ppo` and the pinned policy adapter.

## Evaluate saved runs offline

The evaluation commands read existing run ledgers, campaign traces and their
recorded evidence. They do not launch a simulator or planner. Choose a fresh
output directory beneath `runs/`; an existing campaign remains an input and is
never rewritten by evaluation.

```bash
evaluation=runs/evaluation/m9-diagnostic
.venv/bin/geotransfer evaluate run --campaign runs/m9_acceptance \
  --output "$evaluation" --profile configs/evaluation/default.toml
.venv/bin/geotransfer evaluate aggregate --evaluation "$evaluation" \
  --output runs/evaluation/m9-aggregate
.venv/bin/geotransfer evaluate sensitivity --evaluation "$evaluation" \
  --output runs/evaluation/m9-sensitivity
```

`evaluate run --run DIR --manifest PATH` accounts for a saved run instead of a
campaign. `evaluate report --evaluation DIR` rebuilds its CSV and Markdown from
the already stored results. A campaign's `PASS` means its existing single and
manifest executions were validated and canonically equal; it is not a driving
success. Execution validity, metric assessment, encounter realization, task
result and driving outcome remain separate. Missing evidence stays unavailable
or blocked, never zero or pass. Read [the metric definitions](docs/performance_evaluation.md)
before interpreting thresholds, exposures or geographic comparisons.

## Convert and admit a new scene

```bash
.venv/bin/geotransfer convert --recording 7 --ego 200 --first-frame 25439 \
  --output-root artifacts/candidates/my_scene
.venv/bin/geotransfer validate technical --root artifacts/candidates/my_scene \
  --traffic-protocol hybrid_startup
.venv/bin/geotransfer validate registration --root artifacts/candidates/my_scene
.venv/bin/geotransfer check tool render_rule_review \
  --root artifacts/candidates/my_scene --steps 10 30 50 75
```

Inspect the source/audit evidence and supply the explicit semantic review. Missing
or stale review never becomes an automatic pass. Then generate the actual SMART
input proof and request planner admission:

```bash
.venv/bin/geotransfer validate smart-input --root artifacts/candidates/my_scene \
  --us-binary artifacts/probes/us_hybrid_1002fdc9826fc6d1/testing/map_000000.bin \
  --all-actors --inference --steps 81
.venv/bin/geotransfer validate smart --root artifacts/candidates/my_scene \
  --us-root artifacts/probes/us_hybrid_1002fdc9826fc6d1
```

[The workflow guide](docs/workflows.md) covers corpus selection, queue resume,
full evidence refresh and freezing. [Architecture](docs/architecture.md) explains
module responsibilities. [The migration record](docs/migration.md) records
baseline equivalence, recovery and the old-to-new command inventory.

## Checks and interpretation limits

```bash
.venv/bin/pytest -q
.venv/bin/geotransfer check all
.venv/bin/geotransfer check migration conversion
.venv/bin/geotransfer check migration execution
```

Integration checks require the local scene/reference artifacts and external BB/data
assets. Model runs use CPU greedy SMART, seed 0 and the recorded warmup/protocol.

Faithfulness remains scoped: VRUs are replayed, some dimensions are estimated,
map tokenization has quantization limits, background traffic uses a logged route
prior, and SMART lacks navigation-goal and full lane-rule conditioning. The US
fixtures establish mechanics, not a matched geographic study. The cyclist crossing
after ego passage is not a mandatory-yielding example.

[Step 1](docs/plans/step_1/1_faithful_scenes.md),
[Step 2](docs/plans/step_2/2_admissible_scene_set.md) and the
[research scope](docs/plans/step_2/2_protocol_scope_and_matching.md) retain the
research requirements. The
[controller matrix plan](docs/plans/controller_matrix/GEOTRANSFER_CONTROLLER_MATRIX_PLAN.md)
and [stage prompts](docs/plans/controller_matrix/CODEX_STAGE_PROMPTS.md) record
the M0–M9 specification.
