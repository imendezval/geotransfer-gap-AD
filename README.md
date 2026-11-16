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

SMART uses the faithful adapter and corrected evaluator runtime. PPO, PDM and
other BB planners remain available as explicit diagnostics; SMART admission does
not validate their interfaces. Upstream BehaviorBench remains unchanged.

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

## Run a planner

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

For PPO, select `--planner.type ppo` and supply the checkpoint/device options
required by the configured BB checkout. This is not a validated planner comparison.

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

[Step 1](docs/plans/1_faithful_scenes.md), [Step 2](docs/plans/2_admissible_scene_set.md)
and the [research scope](docs/plans/2_protocol_scope_and_matching.md) retain the
research requirements. Older reports are historical records, not current commands.
