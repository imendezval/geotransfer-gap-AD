# Architecture

The package is `src/geotransfer_gap`; `geotransfer` and
`python -m geotransfer_gap` expose the same CLI. Root-level research scripts are
replaced at cutover, with no permanent compatibility wrappers.

| Subsystem | Responsibility |
| --- | --- |
| `sources` | inD CSV loading and conversion-time trajectory interpolation |
| `maps` | coordinate projection, Lanelet2 topology, rule applicability and independent source-route certificates |
| `conversion` | immutable `ConversionConfig`, `Converter`, JSON construction, BB writer/reader integration |
| `runtime` | isolated corrected native binding, short loader aliases, startup/release/background intent, canonical environment setup |
| `planners` | faithful SMART state/map inputs, one input/execution producer registry, canonical diagnostic execution, BB diagnostic bridge |
| `validation` | reconstruction, lifecycle, physical/counterfactual checks, scoped admission and isolated check suites |
| `corpus` | source-only discovery strategies, versioned queues, independence, manifests, targets and freezing |
| `visualization` | provider registration, evidence montages and self-contained playback |
| `config`, `artifacts` | configured roots, content hashing, artifact references, atomic JSON I/O and corpus lookup |
| `execution` | supported single/batch runs into separate output directories |
| `migration` | archived-baseline recovery, conversion/execution comparison and explicitly justified review carry-forward |
| `runtime.trace_io` | shared loading and integrity checks for saved trace, sidecar and stable actor/lifecycle identities |
| `evaluation` | offline metric composition, task/encounter assessment, accounting, aggregation, sensitivity, compatibility and geographic comparison |

Some private modules retain descriptive historical names to keep producer labels
recognizable. Public entrypoints are CLI actions and documented Python objects;
callers do not need to know those module filenames.

## Dependency boundaries

Conversion does not launch simulation or planners. Source discovery does not use
planner outcomes. Map/source validators retain independent calculations where
sharing an algorithm with conversion would create circular validation. SMART
future-source access remains forbidden. Runtime changes are confined to the
isolated native build; the BB checkout is an external dependency and is not edited.

`ConversionConfig` is immutable; each `Converter(config, output_root)` owns its
samples/output state. Source-map choice takes the recording explicitly. Multiple
conversions cannot silently change each other's recording settings.

Common hashing and binary I/O live in one place. Native map proofs fingerprint
the converter together with its extracted source/map/I/O/configuration helpers;
a helper change cannot leave an old native proof current. `planners.protocol` declares the
input producer files and execution fingerprints once for both US and German
fixtures. `tool_registry.json` maps historical producer labels to their current
implementations; `configs/tool_inventory.json` accounts for all original scripts.

## Artifacts and validity

`artifacts/corpus/current.json` is the portable schema-2 discovery/execution
manifest. A scene root still contains `testing/`, required by the BB loader.
Scene data and reviewed evidence are inputs; ordinary execution and viewing write
only under `runs/`. Validation is an explicit evidence-producing operation.

Schema-2 contracts include logical root/path references and content hashes.
Absolute paths remain diagnostic metadata. Admission guards resolve all evidence
references and verify their hashes, producer code, effective settings and runtime.
Moving a configured root does not substitute a different input or waive checks.
Legacy producer reports remain available for specialized corpus workflows; their
historical absolute paths are not rewritten into fabricated passing admissions.

The existing semantic review is distinct from automated evidence. Migration may
carry it forward only after its source, binary, images, substantive audits and any
reviewed certificates are verified equivalent; the original review remains in the
archive and the carry-forward proof records exactly what was checked.

A research-scoped SMART run checks the current SMART admission. BB/PPO/PDM
execution is explicitly diagnostic and cannot inherit that admission. Every
corpus scene is evaluated in a fresh process, preserving state isolation.

The external PufferLib import may create its standard ignored `resources` symlink.
It is a runtime asset alias, rather than an additional code entrypoint.

The configured `cache` root stores verified archived reference-code checkouts.
Native compilation and short scene-loader aliases retain their content-keyed
`/tmp` locations used by the validated runtime.

The execution manifest selects scenes. The schema-4 ledger freezes the expected
selection before dispatch and records attempts. Schema-2 ledgers can be
partial, so legacy evaluation also uses the original scene manifest. Each
trace retains its own observation and evidence bindings. Optional
`evaluation.capture` fields are written by the existing episode-worker hook
and bound to the canonical trace.

The offline evaluation layer passes each selected trace through the shared
saved-evidence reader and metric engine. Standalone trace, run and campaign
selections use one indexed result writer. The index binds the input snapshot
and per-episode results and events. Standalone selection scope is independent
of execution attestation and original experiment accounting. Run and campaign
selections retain unsuccessful and unavailable entries.

The viewer reads indexed results and verifies their playback bindings against
the recorded scene, binary, trace and sidecars. Its existing playback engine
serves both explicit and evaluation-only views. Reports and summaries consume
stored metrics. Geographic comparison additionally uses frozen source cohort
manifests. See the [metric definitions](performance_evaluation.md).
