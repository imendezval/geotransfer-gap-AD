# Supported workflows

Use `.venv/bin/geotransfer ACTION --help` for each action's options. Pass a config
before the command: `geotransfer --config configs/local.toml ...`.

## Scene construction and review

Follow the README conversion → technical validation → provider registration →
manual review → actual SMART-input proof → SMART admission sequence. The default
conversion retains stationary actors, uses source-valid spawning and emits supported
crosswalks. Historical ablations remain explicit conversion options. No binary
writer is reimplemented.

Technical admission, planner admission and corpus independence are separate gates.
An admitted SMART scene can still be excluded from a corpus because its source
window overlaps another selected scene or shares moving actor tracks.

## Source discovery and resumable screening

`corpus catalog`, `corpus cyclists`, `corpus tasks`, `corpus restarts` and
`corpus interactions` expose distinct source-search strategies. They are not
interchangeable acceptance tests. `corpus select`, `corpus select-cyclists` and
`corpus phases` create ordered source-only queues.

```bash
.venv/bin/geotransfer corpus screen --selection artifacts/audits/MY_SELECTION.json \
  --ledger artifacts/audits/MY_LEDGER.json --workers 2 --limit 12
```

The ledger keys recording/ego/frame/interaction-actor and producer versions.
Resume skips only matching producer/selection identities. Shared-scene mutations
are serialized across threads and processes. Scene screening does not create a
passing semantic review and never selects on planner success.

## Refresh interfaces and corpus evidence

```bash
.venv/bin/geotransfer validate us
.venv/bin/geotransfer corpus build \
  --selection artifacts/audits/step2_expanded_current_selection.json \
  --output-prefix artifacts/audits/step2_expanded_current \
  --retain-independence-exclusions --source-order --publish-current
.venv/bin/geotransfer corpus access \
  --manifest artifacts/audits/step2_expanded_current_manifest.json \
  --output artifacts/audits/step2_corpus_access.json
```

The internal manifest remains available to the corpus producers. The portable
`artifacts/corpus/current.json` is the normal discovery/run/view entrypoint.

The frozen baseline requires fresh admission-enforcing single-scene and isolated
batch evidence, plus the independent global checks. Specialized producers remain
available through `check tool NAME`; the complete mapping is in
`configs/tool_inventory.json`. For example:

```bash
.venv/bin/geotransfer check tool probe_faithful_smart_closed_loop \
  --root artifacts/oriented_v3/r07_e200_f25439 --require-admission
.venv/bin/geotransfer check tool run_smart_manifest \
  --manifest artifacts/audits/step2_expanded_current_manifest.json \
  --output artifacts/audits/step2_expanded_batch_parity.json
.venv/bin/geotransfer corpus freeze \
  --manifest artifacts/audits/step2_expanded_current_manifest.json \
  --batch-report artifacts/audits/step2_expanded_batch_parity.json
.venv/bin/geotransfer corpus targets
.venv/bin/geotransfer corpus report
```

A source/runtime/producer change requires affected evidence to be regenerated.
Archive previous results; do not pool protocol versions. `validate us --reuse-current`
checks existing proofs; it never creates evidence that has not been produced.

## Diagnostics and less-common checks

`validate lifecycle`, `counterfactual`, `spawn`, `parked`, `reset`, `map`, `rules`,
`physical`, `route`, `following`, `task-rule` and `directed-rule` expose their
specific audits. `check all` runs the current regression producers in fresh
processes and records logs and a summary under `runs/checks`.

The inventory maps remaining useful tools such as stationary scans, crop/contact
checks, goal reporting, turn/VRU searches, lead-response diagnostics and overlap
rendering to `check tool OLD_STEM ...`. Rejected source-speed/route experiments
are historical archive material rather than production switches.

`configs/scenes.json` versions the 16 source-window conversion recipes and expected
binary identities. `configs/reviews/` preserves their existing review records.
`configs/current_manifest.json` is the versioned portable index for this frozen
baseline; regenerated admissions require a freshly built manifest. Converted data,
plots and execution traces remain local ignored artifacts.

## Offline performance evaluation

A scene manifest selects scene inputs for execution. A run ledger records the
submitted episodes and their execution and retry status. A trace records the
observations of one episode. An evaluation index binds the selected saved
evidence to metrics, events and reports. Use a new output directory beneath the
configured `runs` root for each evaluation or summary.

### Single-scene run

```bash
.venv/bin/geotransfer run --scene r12_e151_f12041 \
  --ego ppo --traffic smart --traffic-startup source_hold
# Set RUN_DIR to the saved directory printed by the run command.
.venv/bin/geotransfer evaluate run --run "$RUN_DIR" --output runs/evaluation/single
.venv/bin/geotransfer view --evaluation runs/evaluation/single --open
```

Schema-4 evaluation takes every expected episode from the ledger, including
failed, blocked and incomplete entries. Supply `--manifest PATH` if you also
want to validate it against the original manifest. The current corpus is never
used to reconstruct the historical run selection. Source-context metrics still
require their existing validated source inputs.

### Individual trace

```bash
.venv/bin/geotransfer evaluate episode --trace "$TRACE_PATH" --output runs/evaluation/standalone
.venv/bin/geotransfer view --evaluation runs/evaluation/standalone --open
```

`evaluate episode` accepts `--scene ID_OR_ROOT` for explicit scene identity
checking and `--profile PATH` for a different valid metric profile. Both
evaluation commands write `index.json`, `input_snapshot.json`, `episodes.csv`,
`report.md`, and `episodes/<id>/{result,events}.json`. Standalone evaluations
describe a single selected trace and preserve its recorded evidence level.
Original experiment completeness and execution rates are unavailable. To use
an older evaluation containing `episode.json`, run `evaluate episode` on its
original trace and choose a new output directory.

### Corpus run

```bash
.venv/bin/geotransfer run --manifest artifacts/corpus/current.json --ego ppo --traffic smart
# Set RUN_DIR to the saved directory printed by the run command.
.venv/bin/geotransfer evaluate run --run "$RUN_DIR" --output runs/evaluation/corpus
.venv/bin/geotransfer evaluate aggregate --evaluation runs/evaluation/corpus \
  --output runs/evaluation/corpus-aggregate
.venv/bin/geotransfer view --evaluation runs/evaluation/corpus --open
```

The evaluation-only viewer uses the exact recorded trace. A single playable
entry opens a playback page. Multiple entries open a gallery with all episode
statuses and same-scene comparison for viewable episodes. A missing trace or
scene binary can leave an entry without playback. Use `--output DIRECTORY`
for a multi-episode gallery or `--output FILE.html` for a single entry. Omit
`--output` to use a directory under `runs/views/evaluations`. Outputs must stay
outside saved evidence and protected source roots.

The explicit modes are also available. For example, use
`view --scene SCENE --trace TRACE --evaluation EVALUATION --output FILE.html`.
Repeat `--trace` to compare saved traces and repeat `--evaluation` to attach
multiple saved evaluations in explicit mode. Evaluation-only selection accepts
one evaluation directory.

### Frozen campaign

```bash
evaluation=runs/evaluation/m9
.venv/bin/geotransfer evaluate run --campaign runs/m9_acceptance --output "$evaluation"
.venv/bin/geotransfer evaluate report --evaluation "$evaluation"
.venv/bin/geotransfer evaluate aggregate --evaluation "$evaluation" \
  --output runs/evaluation/m9-aggregate
.venv/bin/geotransfer evaluate sensitivity --evaluation "$evaluation" \
  --output runs/evaluation/m9-sensitivity
.venv/bin/geotransfer view --campaign runs/m9_acceptance --evaluation "$evaluation" \
  --output runs/views/m9-gallery
```

The campaign's single trace is the primary episode. Its batch trace is retained
as parity evidence. Campaign integration, execution validity, driving outcomes,
task completion, encounter realization, and metric validity are separate.
`evaluate report` regenerates the CSV and Markdown from indexed results and
events. Aggregate and sensitivity summaries of a standalone input describe the
selected trace and report supported quantities only.

### Legacy run

```bash
.venv/bin/geotransfer evaluate run --run "$LEGACY_RUN_DIR" \
  --manifest "$ORIGINAL_MANIFEST" --output runs/evaluation/legacy
```

The original manifest is mandatory for schema-2 ledgers because they may record
only the episodes that ran. Geographic comparison separately requires the
frozen source-only cohort manifests and all existing eligibility checks. The
configured US fixtures remain diagnostic. See the
[metric definitions and limits](performance_evaluation.md).
