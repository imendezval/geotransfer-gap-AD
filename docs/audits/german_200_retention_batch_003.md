# German-200 retention Batch 3

Batch 3 is finalized and appended to the authenticated retention history. The canonical record is `b7f3256a323d4d0b9a5f256346cf55c84297e6b48ada89f5b632f8ebd02ebf6c`; the B3 queue SHA is `282409a74ea7b9a7b205370a75c5ac14462ad304537290597dc67eb4ebb47a23`.

The append preserved the exact B1/B2 history prefix (SHA-256 `bb2a2d9e614b43a176117eebd014fb7c9bb8da1c4d98d229bc9532f957b49fc1`). The final canonical history SHA is `ee5b4d3cb46c1aa45ee66ef0d80c9c9f572c2f5bb176b700d5b6789d7de61253`; the tip SHA is `50e672a900de16d8142a27ebfbc70c55cd7d5ce4238b7fe428bb47847f85cb3b` and points to B3.

## Results

B3 has 24 frozen primaries and 4 technical passes. The eligible denominator is 16 (4 awaiting review, 5 review-blocked, and 7 technical rejections), giving 4/16 = 0.25. The raw primary fraction is 4/24 = 0.1667. One row initially labelled transient had a fresh structured `validate_spawn.py` failure (`spawn_evaluation_validation.json` SHA-256 `b481f859288e3953d8210b6d21c8a8b5009231e1618ed095e6c23c23193bfdcb`, `passed:false`, `birth_passed:false`) and was deterministically reclassified as a technical rejection. No retry or alternate selection used that transient label.

The final primary statuses by arm are:

| Arm | Awaiting review | Review blocked | Physical rejection | Geometry rejection | Technical rejection | Technical passes |
|---|---:|---:|---:|---:|---:|---:|
| Interactive100 | 1 | 3 | 4 | 0 | 4 | 1 |
| Random100 | 3 | 2 | 3 | 1 | 3 | 3 |

The reported stage field is `technical_gate_structured_failure` for that one reclassified row; the other 23 results have no stage field recorded. Site is the frozen `location` value: site 1 has 2 rows, site 2 has 17, site 3 has 1, and site 4 has 4. The full site-by-arm and per-row status breakdown is in the descriptive JSON report below.

There was one attempted fallback, which ended in `source_physical_rejection`; no fallback was retained. The review manifest contains 9 candidates, with all registration and montage assets present. No human reviews were created.

The B1/B2 comparison is descriptive only; batches are not pooled and no inferential claim is made.

| Batch | Passes / eligible | Raw passes / frozen | Fallback attempts | Review manifest entries | Run report SHA-256 |
|---|---:|---:|---:|---:|---|
| B1 | 6/15 (0.4000) | 6/24 (0.2500) | 4 | 10 | `f19558c5be16e0d2f14cf2f9d7e1709db9dee409db07150badb36d6fecc701d0` |
| B2 | 4/13 (0.3077) | 4/24 (0.1667) | 2 | 7 | `66104de328e525ce8619888d6a3071805820d8ec9200a3ff20d731f4721af0dd` |
| B3 | 4/16 (0.2500) | 4/24 (0.1667) | 1 | 9 | `a893186a76cbcb548774c337a7e09d8321b320d36083a1df80504f898c162d88` |

## Recovery and replay

The B3 ledger was generated under runner SHA-256 `c74d37605720b438be65116d54e082ba1e7565a13dfac3a21cd0581074007e1f` and finalizer SHA-256 `56c882e405a85220a5279615307ad73b17e99535d004b164206fb02f3fe877f4`. That finalizer wrote the complete ledger, report, summary, review manifest, and pending marker, then failed before append because its pending verifier helper was missing. Pending recovery and append used verifier SHA-256 `cc29c21d84a1fd10d7ceb45c03332dc1447639d78d4f554733df6106e3ee0f36`; it checked all 24 primary output trees and retention-relevant fallback inputs read-only, then appended the same pending record. The rejected alternate was not retained. During acceptance, all 25 saved output trees were independently checked against the ledger, including the rejected alternate. Native outputs and core report bytes were not rewritten. Tail finalizer SHA-256 `16d80f1215013a6e976e1e5132a98df73ab73b20ca63d009a564bd3e0827d234` was used only for read-only replay; queue, plan, receipt, owner, ledger, report, summary, review manifest, pending marker, history, and tip hashes remained unchanged.

The first B3 output namespace is preserved at `artifacts/german_200_v1_runs/workstream_d_batch_003`; it was not added to retention history. The retained B3 namespace is `artifacts/german_200_v1_runs/workstream_d_batch_003_corrected`.

## B4 source-only preparation

The executable `scripts/prepare_german_200_retention_batch.py` selects the next frozen rows from the canonical chain, verifies all prior retention records and output trees, checks current source identity, writes a plan and receipt without overwriting, and binds its own SHA-256 (`6f1614c1a66aec310ad1e6cdee762da3001c7fb024a4ef3f850443b3f09bb87d`) plus the three source-selection producer hashes in the receipt.

B4 is prepared in `artifacts/german_200_v1_runs/workstream_d_batch_004_history_verified_plan`. Its queue SHA is `e7f6ab3593ce50b9d4e99074e9070f1e045ae5ec3fe0ac6129ced36a1f9fb083`; plan SHA is `d671b6ba99eaa3d032b691bf2394e5910fa6562a869b60f40778c23889ad6876`; receipt SHA is `2d10112123954c1fb5d41b9e529abaf9e87dbd682c9c1c64bbf89fefecd00ce0`. It is bound to the B3 tip and passed 24 current-source identity checks. The initial, less-verified B4 plan is preserved separately at `artifacts/german_200_v1_runs/workstream_d_batch_004_plan`; use the history-verified plan. No B4 native run was started.

The successor selector now allows equal per-arm tails of 1–12 rows, which permits the final 4+4 after eight complete 12+12 batches. It refuses exhausted or unbalanced tails. B4 remains 12+12. The frozen B1/B2 roots remain fixed at 24 rows.

## Reuse commands

Read-only B3 verification:

```bash
PYTHONPATH=src OMP_NUM_THREADS=2 MPLCONFIGDIR=/tmp/geotransfer_mpl .venv/bin/python -m geotransfer_gap.corpus.finalize_german_200_batch --queue artifacts/german_200_v1_runs/workstream_d_batch_003_corrected_plan/next_validation_queue.json --output-root artifacts/german_200_v1_runs/workstream_d_batch_003_corrected
```

The B4 plan-preparation command has already been run; strict no-overwrite means it will refuse to replace that plan. The exact B4 execution command is recorded but was not run:

```bash
PYTHONPATH=src OMP_NUM_THREADS=2 MPLCONFIGDIR=/tmp/geotransfer_mpl .venv/bin/python -m geotransfer_gap.corpus.run_german_200_batch --queue artifacts/german_200_v1_runs/workstream_d_batch_004_history_verified_plan/next_validation_queue.json --lane-oracle artifacts/german_200_v1_workstream_b/audits/source_lane_change_native_oracle.json --output-root artifacts/german_200_v1_runs/workstream_d_batch_004 --workers 2
```

Then finalize with:

```bash
PYTHONPATH=src OMP_NUM_THREADS=2 MPLCONFIGDIR=/tmp/geotransfer_mpl .venv/bin/python -m geotransfer_gap.corpus.finalize_german_200_batch --queue artifacts/german_200_v1_runs/workstream_d_batch_004_history_verified_plan/next_validation_queue.json --output-root artifacts/german_200_v1_runs/workstream_d_batch_004
```

## Artifact reports

- Corrected machine-readable comparison and artifact hashes: `artifacts/german_200_v1_runs/workstream_d_batch_003_corrected/descriptive_comparison_provenance_corrected_v2.json` (SHA-256 `bd0512c392123d74c74dba3394467f354b53efebfb214579cf66ba225812dee3`). The original ignored report remains unchanged at `artifacts/german_200_v1_runs/workstream_d_batch_003_corrected/descriptive_comparison.json` (SHA-256 `ce69cbb55e68875bcf27bb7c4b48f9a9e3625d2bfcfadc7e0895d3135241b044`).
- Corrected report receipt: `artifacts/german_200_v1_runs/workstream_d_batch_003_corrected/descriptive_comparison_provenance_corrected_v2_receipt.json` (SHA-256 `95a614912a0bcf5894476f453f5f7bbca377653c9fd8d2171dbbb8ef92195335`); it binds the corrected report hash above. The original ignored receipt remains unchanged at `artifacts/german_200_v1_runs/workstream_d_batch_003_corrected/descriptive_comparison_receipt.json` (SHA-256 `c05c33c6093793ea923b31e3278a9206b6f8afaae89800e05243fbbc0f819040`).
- B3 ledger: SHA-256 `4f6e3ba0acf1d5eb44ba7fba457414b826344a1740d5411b371beb8da6a710af`.
- Human review manifest: SHA-256 `1b5215844ec795e8c7e43515dba751e87c13ad6f9d59a176b80375b38950b6f8`.
- Canonical history: SHA-256 `ee5b4d3cb46c1aa45ee66ef0d80c9c9f572c2f5bb176b700d5b6789d7de61253`.
