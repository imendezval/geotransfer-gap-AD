# Controller matrix verification (M8)

The inventory covers the 16 German scenes in `configs/current_manifest.json`
and the two US interface references under the configured artifacts root. Each
scene has 16 immediate-start and 12 source-hold slots. A slot ID uses the
scene name, ego controller, traffic controller and startup policy. Run
directories and attempt numbers are operational metadata.

Build the read-only input inventory from the repository root. Use the local
Python environment configured for the pinned BehaviorBench checkout.

```bash
.venv/bin/python -m geotransfer_gap.verification_matrix \
  --output runs/controller_matrix_work/m8/verification_matrix.json
```

The inventory records source, binary and admission fingerprints. Its slots
begin as `not_run` or `blocked`. Both local US references have zero
authoritative `testing/ind_*.json` files, so their 24 source-hold slots are
blocked. Immediate-start reference executions use the unmodified binaries.
An input block is distinct from a worker failure.

## Run and continue a batch

Each invocation requests one pair and startup policy. Use `--scene` for one
scene or `--manifest` for a batch. A custom batch manifest needs the scene
name, portable root and expected binary SHA-256 per row. The official
manifest remains unchanged.

```bash
.venv/bin/geotransfer run --manifest configs/current_manifest.json \
  --ego expert --traffic idm --traffic-startup source_hold --steps 24
```

An invocation creates the full expected run ledger before starting a child.
A worker executes each ready scene in a fresh process. The process sends
stdout and stderr to `execution.log`; its argument vector, working
directory, effective environment and result are stored in `attempt.json`.
A successful exit must also pass parent-side trace and provenance validation.
An attempt with missing evidence records a classification and retains
partial artifacts.

| State | Meaning |
| --- | --- |
| `not_run` | The expected slot has no worker attempt. |
| `running` | The worker launch or validation has started. |
| `passed` | The worker exited successfully and the parent validated its evidence. |
| `failed` | A launch, worker exit, signal or evidence check failed. |
| `blocked` | A required input was unavailable or invalid during preflight. |
| `interrupted` | The parent stopped before committing a validated result. |

`run.json` has schema version 4. Individual attempts have schema version 1.
The CLI returns success only when every expected slot has passed. Use the same
command and environment with `--resume <run-directory>` to continue.
Validated attempts are rechecked and retained. Failed and interrupted attempts
get new directories on retry. A hard kill may leave `running` entries in the
ledger. After the inherited worker lock closes, resuming records them as
interrupted before creating a retry. A different input set or worker
environment needs a new ledger.

The worker explicitly sets the NumPy seed, uses Drive reset seed 0 and sets the
learned model seed through the existing controllers. The orchestrator pins
CPU and the OMP, MKL, OpenBLAS and NumExpr thread counts. The sidecar records the
actual library versions and Torch thread counts. PPO uses deterministic joint
argmax. SMART uses greedy autoregressive inference.

## Compare verified evidence

The existing `trace.json` bytes are retained. `verification.json` adds native
lifecycle facts, navigation goals, runtime and input hashes and references to
existing PPO and SMART provenance. It separates the original source
admission, controller-pair research admission, task preservation and driving
outcome. The parent records integration validation in `attempt.json`. New
matrix pairs are diagnostic-only, research admission is `not_established`
and task preservation is `not_assessed`.

```bash
.venv/bin/python -m geotransfer_gap.runtime.run_trace SINGLE_EPISODE BATCH_EPISODE \
  --output runs/controller_matrix_work/m8/comparison.json
```

The comparator preserves state, actions, slots, ownership, movement modes,
lifetimes, releases and outcome fields. It aligns actor records by source
identity and lifetime. It normalizes the corrected extension and PPO
checkpoint paths and reads episode evidence independently of timestamps or
paths in the attempt ledger. A mismatch returns exit 1 and reports the first
different value with scene, pair, startup, tick, actor and field.

Recorded future motion enters the source-hold schedule. PPO instead uses the
native agent-centric view, including the simulator navigation goal. SMART
uses the map and causal joint history, including the observed birth
velocity. The background IDM route prior is recorded separately. None of
these conditions establishes the preservation of an encounter task.

## Reproduce the representative gate

```bash
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLCONFIGDIR=/tmp/geotransfer_mpl
.venv/bin/python tests/integration/probe_matrix_verification.py \
  --output runs/controller_matrix_work/m8/representative_repeat
.venv/bin/python tests/integration/probe_ppo_traffic_physics.py \
  --root artifacts/oriented_v3/r07_e200_f25439 --target-index 7
.venv/bin/python tests/integration/probe_smart_ego_reference.py \
  --root artifacts/oriented_v3/r07_e200_f25439
.venv/bin/python tests/integration/probe_smart_ego_reference.py \
  --root artifacts/oriented_v3/r32_e391_f21356 --steps 4 --require-birth
.venv/bin/python tests/integration/probe_source_hold_models.py \
  --root artifacts/oriented_v3/r12_e151_f12041 --actor 137
.venv/bin/pytest -q
```

Use a new representative output directory for each run. The script performs
fresh CLI single and manifest runs, records commands and exact comparisons,
tests preflight blocks and preserves an intentional worker failure and retry.
The 504-slot inventory remains the expected corpus for M9. Representative
execution evidence is separate from full acceptance.

The legacy baseline can be reproduced with the existing command and compared
against the M0 raw trace and diagnostic hashes.

```bash
.venv/bin/geotransfer run --manifest configs/current_manifest.json \
  --preset smart_hybrid_baseline
```

Run the checks that generate validation evidence against a copy of the
artifacts tree to preserve the original testing directories.

```bash
mkdir -p runs/controller_matrix_work/m8/recheck/artifacts
cp -a --reflink=auto artifacts/. runs/controller_matrix_work/m8/recheck/artifacts/
export GEOTRANSFER_ARTIFACTS="$PWD/runs/controller_matrix_work/m8/recheck/artifacts"
export GEOTRANSFER_RUNS="$PWD/runs/controller_matrix_work/m8/recheck/runs"
.venv/bin/geotransfer check all
.venv/bin/python -m geotransfer_gap.migration conversion
.venv/bin/python -m geotransfer_gap.migration execution
```
