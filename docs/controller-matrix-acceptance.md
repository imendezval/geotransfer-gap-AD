# Controller matrix acceptance (M9)

The campaign uses the existing single-scene CLI, manifest CLI, episode worker
and schema 2 verification sidecar. The 504 slots comprise 448 German scenes
and protocols, 32 immediate-start US entries, and 24 US source-hold entries
that require an authoritative matching source JSON. Missing US hold inputs
are recorded as BLOCKED in both views.

## Viewer

Build an offline gallery from the saved campaign report and its independently
validated single-pass traces.

```bash
.venv/bin/geotransfer view --campaign runs/m9_acceptance --output runs/m9-gallery --open
.venv/bin/geotransfer view --campaign runs/m9_acceptance --scene r12_e151_f12041 \
  --ego ppo --traffic smart --traffic-startup source_hold \
  --output runs/r12-ppo-smart-hold.html --open
```

Omit the controller filters to include all passing configurations for the
selected scene. Without a scene filter, the output is a gallery directory
containing `index.html`. The grid retains the statuses of blocked, failed and
incomplete slots. The output goes outside the saved campaign directory.
Viewing uses the saved report and configured scene assets without inference
or a campaign freeze check.

Use repeated trace flags to compare hand-selected trajectories on the same
scene.

```bash
.venv/bin/geotransfer view --scene artifacts/oriented_v3/r12_e151_f12041 \
  --trace FIRST/trace.json --trace SECOND/trace.json --output runs/local-view.html
```

The time control uses recorded steps and timestamps. The actor table shows
declared and effective owners, mode readback and applied modes, action, release
steps and events. A source hold keeps an expert replay owner until takeover.
Native and source gaps are distinct. Missing optional historical fields are
shown as not recorded. Sibling verification and diagnostic files enrich the
display when they match the trace. Verification sidecars must match the scene,
binary, controller protocol and recorded outcome. The viewer checks the trace
and verification hashes when a campaign or validated attempt records them.
There is no network dependency. US references can show verified binary map geometry and
recorded actor states. Source trajectory and imagery controls indicate
unavailability. German source sampling and image registration continue to
use the local licensed inputs.

Render the actual browser evidence with
`tests/integration/probe_matrix_viewer.py --scene ROOT --trace PATH --output DIR`.
The optional integration probe uses Playwright and local Chromium. It checks
the DOM and captures screenshots. Rendered HTML, imagery and trace artifacts
belong in ignored run directories.

## Preflight

Finish and commit source, test and documentation changes first. Run the M8
regression gates in [the verification guide](controller-matrix-verification.md).
The verification suite and migration producers that write artifacts should
use a copy of the artifacts tree under runs. Keep original artifacts, native
runtime and external checkout unchanged.

Also run the native `probe_ppo_native.py`, `probe_ppo_traffic_physics.py`,
`probe_smart_controller.py`, `probe_smart_ego_reference.py` and
`probe_source_hold_models.py` integration probes and the existing M7 IDM
release readback. Use the documented M4–M8 fixture roots and thresholds.
Compare the fresh legacy SMART/hybrid diagnostic and trace hashes for every
German scene. Compare expert replay against matrix expert/expert states.
Retain the representative fresh single-versus-batch evidence for the final
source revision.

Prepare a local JSON gate record giving the Git `revision` and `gates` objects
for V and F. Each gate needs `status` of PASS and an `evidence` file path.
The supplied gate record is linked and fingerprinted in the freeze manifest.

## Freeze, execute and regenerate the report

Run from the project root with the configured Python, BehaviorBench and
artifact paths. The commands must use the same effective environment and
working directory as the freeze.

```bash
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLCONFIGDIR=/tmp/geotransfer_mpl
campaign="$PWD/runs/m9_acceptance"
.venv/bin/python -m geotransfer_gap.matrix_campaign freeze --output "$campaign" \
  --gates runs/controller_matrix_work/m9_preflight/gates.json
.venv/bin/python -m geotransfer_gap.matrix_campaign single --output "$campaign" --jobs 8
.venv/bin/python -m geotransfer_gap.matrix_campaign batch --output "$campaign" --jobs 8
.venv/bin/python -m geotransfer_gap.matrix_campaign report --output "$campaign"
```

The single pass invokes the public CLI separately for each executable slot.
The repeat groups executable scenes into one manifest per protocol. Each
episode uses a fresh worker. The freeze records the complete commit and tree,
actual code, inputs, native binary, checkpoints, INI, CPU environment and
native package digests. A source or environment change requires a separate
campaign generation, with the prior evidence retained.

Both phases can be restarted with the same command after interruption. Jobs
with terminal ledger rows are retained. Incomplete ledgers use the existing
M8 CLI resume path. If the episode ledger committed before the supervisor
recorded the CLI exit, the launcher is marked `reconciled`. The original
attempts remain intact and an unknown launcher exit code stays unset.
Resume can create another attempt when a batch is only
partially complete. An earlier failed attempt remains a campaign failure
even if a later attempt succeeds. Launch and worker logs and attempt records
remain separate in the single and batch directories.

The report command uses only persisted campaign records and artifacts and
revalidates evidence without running models. It writes the 504-row
`verification_matrix.json`, first mismatches, and `summary.md`. PASS means
both executions passed validation and were exactly equal. FAIL preserves
execution or parity errors. BLOCKED represents unavailable prerequisites.
NOT_RUN represents absent or incomplete evidence. Gate E covers complete
accounting and Gate D covers exact validated parity. A completed campaign may
contain failed executions or blocked inputs.

Original source admission applies to its recorded protocol. Matrix runs
remain diagnostic. Encounter preservation stays not assessed and collisions,
removal, goal misses and short runs are separately reported driving outcomes.
