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
