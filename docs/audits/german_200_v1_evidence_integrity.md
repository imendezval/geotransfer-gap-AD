# German-200 v1 evidence integrity index

The machine-readable cohort and historical decision index is [`german_200_v1_evidence_index.json`](german_200_v1_evidence_index.json). It records all 200 frozen identities, the 16 anchor identities, membership in the original first batch and Workstream C batch 001, the 28 original Workstream B decisions, and the 24 Workstream C outcomes with two attempted alternates. Raw images and binaries remain in their existing artifact locations.

## Integrity results

- The frozen queue and first-batch files match the hashes in `provenance.json`. Canonical source identity and row hashes match for all selected rows.
- All 198 recording-level input files listed by the cohort source manifest match their SHA-256 pins. The original and Workstream C batches contain 24 distinct cohort rows apiece.
- All 480 output-tree files referenced by the 28 Workstream B decision records match the historical ledger. All 417 files referenced by the 26 Workstream C decision records match their ledger entries. Every saved admission report also matches its decision and output-tree hash.
- The historical pilot snapshot is a separate inventory from the protected-input snapshot. The 700-file pilot inventory matches in full. The 1,017-entry protected-input inventory also matches in full.
- The saved Workstream B runner stamp is version 1 with SHA-256 `5baa5aafe76cfd7413edb9ff8f521e939af2d1d6b8b3f6d458e7a6bbbfc2e69d`. Its exact source is absent from the 206 reachable/reflog commits checked. The only reachable history entry for the runner path is `ae62069`, whose file SHA-256 is `491eac83a7609f2cc1a13f7204806b0b29cfb6656f623d5afddc06c25b97f84b`. All 28 saved tool fingerprints match current source, including the `admit_scene.py` pin. The historical `pilot_ind.py` fingerprint resolves through the saved gate contract to `src/geotransfer_gap/conversion/pipeline.py` with the same SHA-256.
- All 16 Workstream B and 13 Workstream C saved admission reports bind to native runtime source digest `beedf8f1b0e9c490`. Recomputing the patch/build-input digest yields the same value. The cached Python 3.11 and 3.12 native binaries and both historical interpreter executable SHA-256 values are recorded in the JSON index. Each interpreter file matches its historical stamp.

The unavailable Workstream B runner source limits exact producer replay. The saved gate and scene outcomes remain hash-verifiable. This producer limitation is recorded separately from each technical rejection or source-screen outcome.

## Historical decisions and review status

Workstream B’s 24 primaries recorded 6 technical rejections, 6 technical passes awaiting human review, 7 source-physical rejections, 2 source-geometry rejections, and 3 overlap-blocked decisions. Its four attempted alternates recorded 2 source-physical rejections, 1 source-geometry rejection, and 1 review-blocked decision. The human-review manifest has `manual_reviews_created: false`.

Workstream C’s 24 primaries recorded 6 technical rejections, 4 technical passes awaiting review, 10 source-physical rejections, 1 source-geometry rejection, and 3 overlap-blocked decisions. Its two attempted alternates were source-physical rejections. The human-review manifest has `manual_reviews_created: false`. Workstream C’s own analysis and receipt remain with that workstream.

The saved rule audits remain `evidence_only`. The index creates no semantic findings, physical clearances, or research admissions.

## Source census and Workstream C proofs

The index links and hashes the source census and next-validation queue artifacts under [`artifacts/german_200_v1_workstream_d`](../../artifacts/german_200_v1_workstream_d). Its Workstream C proof hashes cover the batch ledger, run report, source-queue verification, independence audit, source-support provenance, hybrid protocol parity audit, and native source-lane-change oracle under [`artifacts/german_200_v1_runs/workstream_c_batch_001`](../../artifacts/german_200_v1_runs/workstream_c_batch_001).

## Separate legacy hold

The seven stale SMART admission hashes documented in [`current_matrix_inventory_status.json`](../../runs/pe00_baseline_20261122/current_matrix_inventory_status.json) remain part of the separate protected-input set. Their scene IDs and the status-file hash appear in the machine index. These legacy admission files were not edited as part of German-200 evidence indexing.

## Human review workflow

Workstream B's pending dossiers are indexed in [`german_200_v1_workstream_b_hardening.md`](german_200_v1_workstream_b_hardening.md). The dossiers keep physical adjudication, technical gate status, and later source/rule review distinct. A physical conflict or deferred pair stays non-admitted. The repository's hash-bound review fields are enforced by [`admit_scene.py`](../../src/geotransfer_gap/validation/admit_scene.py) and the later batch gate [`finalize_german_200_batch.py`](../../src/geotransfer_gap/corpus/finalize_german_200_batch.py).
