# Reproducing a SMART scene admission

Run from `geotransfer-AD-gap`. The checked environment is `bb_pufferdrive`;
stock BehaviorBench execution does not include this repository's runtime and
SMART adapter. The upstream repository must remain clean. Source data and the
checkpoint/codebooks must exist at the paths recorded in each scene contract.

```bash
export MPLCONFIGDIR=/tmp/geotransfer_mpl
export OMP_NUM_THREADS=2
PY=/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python
ROOT=pilot/oriented_v3/r00_e366_f23240
US=pilot/probes/us_hybrid_1002fdc9826fc6d1
```

For a new source-selected scene, convert into a new root (this example's source
coordinates are those of the named fixture). Never overwrite reviewed inputs
as a side effect of an evaluation run.

```bash
$PY pilot_ind.py --recording 0 --ego 366 --first-frame 23240 \
  --goal-sample 85 --late-mode runtime_spawn --static-crop-radius 1000000 \
  --parked-as-static-expert --emit-crosswalks --output-root "$ROOT"
$PY admit_scene.py --root "$ROOT" --traffic-protocol hybrid_startup
$PY register_background.py --root "$ROOT"
$PY render_rule_review.py --root "$ROOT" --steps 10 30 50 75
```

Inspect the source overlay and applicable rule/physical/interaction reports.
Create `testing/semantic_review_smart_hybrid_startup.json` as a distinct manual
input, binding the source image, binary, rule audit and interaction-source
digest. Existing admitted reviews show the schema. Stop-scope and same-route
following interpretations require the corresponding source certificates and
explicit review fields; certificates cannot clear explicit applicable priority.
No command automatically creates a passing review. Missing or stale evidence
must fail. The original pilot is a current technical exclusion.

For actual SMART input proof, use the available US reference binary and an
81-action diagnostic (the proof also includes the observed startup history).
US reference input proofs and `hybrid_protocol_us_parity.json` must already be
current. The two US fixtures establish mechanics, not matched study admission.

```bash
$PY probe_hybrid_protocol_parity.py \
  --us-json ../data/WOMD/gpudrive/validation/WOMD_v1.3_1002fdc9826fc6d1.json \
  --output-root pilot/probes/us_hybrid_parity --steps 50
$PY probe_smart_map_transfer.py --root "$ROOT" \
  --us-binary "$US/testing/map_000000.bin" --all-actors --inference --steps 81
$PY admit_smart_scene.py --root "$ROOT" --us-root "$US"
$PY probe_faithful_smart_closed_loop.py --root "$ROOT" --require-admission
```

For the fixed selected cohort, refresh every affected admission first. The
manifest excludes shared moving tracks and overlapping windows, orders by
source recording/frame rather than planner success, and keeps controls apart
from the ten-interaction requirement. Each batch scene uses a fresh canonical
subprocess. Generate a fresh single-scene rollout for every selected root before
batch execution so the batch report can prove exact timeline reproduction.

```bash
$PY probe_smart_admission_regressions.py
$PY build_smart_pilot_manifest.py \
  --selection pilot/audits/step2_expanded_current_selection.json \
  --output-prefix pilot/audits/step2_expanded_current \
  --retain-independence-exclusions --source-order
$PY audit_corpus_access.py \
  --manifest pilot/audits/step2_expanded_current_manifest.json \
  --output pilot/audits/step2_corpus_access.json
$PY run_smart_manifest.py \
  --manifest pilot/audits/step2_expanded_current_manifest.json \
  --output pilot/audits/step2_expanded_batch_parity.json
$PY freeze_smart_protocol.py \
  --manifest pilot/audits/step2_expanded_current_manifest.json \
  --batch-report pilot/audits/step2_expanded_batch_parity.json
$PY report_step2_flow.py
```

The freeze also requires the current native map-orientation, source re-entry,
stop-scope, restart-screen and following-scope regression reports and both US
closed-loop references. It rejects mixed protocols and stale hashes. Any source,
map, binary, runtime, controller or core technical-tool change invalidates the
scene contract. Adapter/model/tokenizer or SMART-gate changes invalidate their
proofs/admissions. Rebuild affected evidence; never pool historical passes.

See [scope and matching](2_protocol_scope_and_matching.md) for the source-held
traffic prior, nonreactive VRUs, imputed dimensions, refresh latency and SMART's
lack of navigation-goal conditioning. Passing these commands is not evidence
of a geographic performance gap.

## Current protocol and additional proofs

The current runtime is `beedf8f1b0e9c490`, traffic version
`startup_sustained_departure_route_coverage_v2`, SMART protocol
`smart_all_actors_observed_history_dense_map_v4`, map encoding
`encoded_polyline_edge_sampling_max2m_v2`. The adapter applies normalization to
all supported explicit polylines in both domains. No session monkeypatch is
needed for production commands; earlier experimental runtimes are diagnostic.

Native audits have an optional `lanelet2==1.2.3` dependency, outside the BB tree.
If needed, install its wheel into a temporary target and run both map oracles:

```bash
$PY -m pip install --target /tmp/geotransfer_lanelet2_oracle/pkg lanelet2==1.2.3
PYTHONPATH=/tmp/geotransfer_lanelet2_oracle/pkg $PY probe_lanelet_orientation.py
PYTHONPATH=/tmp/geotransfer_lanelet2_oracle/pkg $PY probe_source_lane_changes.py
```

The existing local US reference binaries are required inputs. Refresh their
actual input/rollout proofs and aggregate using the persisted producer:

```bash
$PY probe_us_reference_parity.py
$PY probe_source_reentry.py --root "$US"
$PY probe_background_route_policy.py
$PY probe_faithful_map.py
$PY probe_source_route_sequence.py
$PY probe_directed_rule_scope.py
$PY probe_source_restart_screen.py
$PY probe_following_scope.py
$PY probe_task_rule_scope.py
$PY probe_queue_pair_identity.py
```

`probe_us_reference_parity.py --reuse-current` may aggregate already current
proofs only after validating their runtime/model/producer hashes. It cannot
replace missing evidence with a pass. The two US references are mechanical
fixtures, not research admissions.

For a candidate needing lateral source reachability, also run
`audit_source_route_sequence.py --root "$ROOT"` before manual review. The review
must bind the proof and explicitly identify the actual legal lane changes.
`audit_directed_rule_scope.py --root "$ROOT"` supplies a separate optional
certificate for false yield associations through overlapping lane polygons;
its reviewed rule IDs and proof hash are mandatory when used. Neither source
legality proof adds rule semantics to SMART. A genuine applicable unsupported
priority/stop obligation remains rejected.

After the manifest/batch commands above, publish the prospective target audit:

```bash
$PY audit_final_corpus_targets.py
$PY report_step2_flow.py
```

The active selection pointer is
`pilot/audits/final_corpus_selection_current.json`. Preserve its immutable
composition and protocol-amendment documents. Historical candidate ledgers
consolidated some same-window actor assessments: their row counts are retained
history, not an exact total of all actor-pair attempts. The current queue keeps
actor-pair/producer-version records and uses scene locks across threads/processes.
Use fresh versioned source queues when continuing expansion.
