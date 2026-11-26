# German-200 v1 Workstream C: next 24 validation results

## Frozen input and reproducibility

Workstream C consumed the existing flattened next queue unchanged: 12 Interactive100 rows followed by 12 Random100 rows. The queue file SHA-256 is `a7d39afc578cbb2e7c95e54b79ba1463e23ce0b74fc78022facc015fcb2fb11f`. Its source queue SHA-256 is `33069002fe04000c0b6e35213f90a219554a1accba6c9bce8230bb990d779cba`; the immutable first batch SHA-256 is `5af1c9ef57cb57adffbbf54a59cf74ab5181b2347c68ca4282121b9ed5a2c6a0`. The actual source provenance sidecar SHA-256 is `496922f50e6aa36f3d37342a7092a60c8b872a4d016d6588cb0cd5e5ea5f558c`.

The next queue was reconstructed with the frozen census helper from the immutable source queue and first batch. The reconstructed JSON exactly matches the saved queue. Current source hashes pass for all 200 frozen primaries; the complete 200-row primary set has exact moving-context identities and no window or moving-track conflicts with the 16 anchors or with one another. The next 24 also have no conflicts against all 200 primaries plus the anchors. Ordered identities, producer/catalog/preflight/selector hashes, and this audit are retained in [the queue verification receipt](../../../artifacts/german_200_v1_runs/workstream_c_batch_001/source_queue_verification.json), SHA-256 `1c113c899c7d3925d74fe5551ce791fe7519022af0524737ffe28df22f50e667`. The preserved envelope-form queue archive SHA-256 is `b99184aa4498021afdceec6eee3d142be217b521e3f1ed3005c450825f2afe9d`.

The current native lane-change oracle passed the runner's producer, converter, probe, and source-map coverage checks for the map assets used by all 33 recordings (SHA-256 `41357eaf2f5ba5b8cbbad2c91fe05eb4a62e9d38400b43f511ab7dc27a7256e7`). Current US hybrid-mechanics parity also passed with source, binary, evaluator, runtime, and hybrid-protocol fingerprints verified (report SHA-256 `99bc840376f286baeb955e63fd1f88ec6d519157fc2409aecc3744a7dffd838e`). The accepted finalizer SHA-256 used for the run is `0fb055e09040ef8d721b309526cc8b0543f9da5de18b7232a7dd3a0e9a167b4d`.

For an independent replay, use a fresh named namespace and the preserved Workstream B support-copy oracle:

    PYTHONPATH=src OMP_NUM_THREADS=2 MPLCONFIGDIR=/tmp/geotransfer_mpl .venv/bin/python -m geotransfer_gap.corpus.run_german_200_batch --queue artifacts/german_200_v1_workstream_d/next_validation_queue.json --lane-oracle artifacts/german_200_v1_workstream_b/audits/source_lane_change_native_oracle.json --output-root artifacts/german_200_v1_runs/workstream_c_replay_001 --workers 2

    PYTHONPATH=src OMP_NUM_THREADS=2 MPLCONFIGDIR=/tmp/geotransfer_mpl .venv/bin/python -m geotransfer_gap.corpus.finalize_german_200_batch --queue artifacts/german_200_v1_workstream_d/next_validation_queue.json --output-root artifacts/german_200_v1_runs/workstream_c_replay_001

The completed run itself is preserved at artifacts/german_200_v1_runs/workstream_c_batch_001. Its exact command lines and producer fingerprint are in the machine-readable report below.

The source identity/hash checks, conversion, map/physical/rule audits, native support verification, and full technical gate ran under the current producers in this namespace. No historical queue or ledger was changed.

## Primary results

All rows belong to this fixed batch only. No prior batch outcomes were pooled.

| Arm | Frozen rows | Awaiting human review | Review-blocked | Technical rejection | Source-physical rejection | Source-geometry rejection |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Interactive100 | 12 | 2 | 2 | 3 | 5 | 0 |
| Random100 | 12 | 2 | 1 | 3 | 5 | 1 |
| Total | 24 | 4 | 3 | 6 | 10 | 1 |

The technical-eligible denominator is 13 after the 11 primary source-geometry/physical rejections. Four rows passed the technical gate and await human review: 4/13 (30.8%) of the technical-eligible denominator and 4/24 (16.7%) of the frozen rows. These are technical gate results, not final manual admissions.

| Location | Rows | Awaiting human review | Review-blocked | Technical rejection | Source-physical rejection | Source-geometry rejection |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 6 | 3 | 0 | 2 | 1 | 0 |
| 2 | 16 | 0 | 3 | 3 | 9 | 1 |
| 4 | 2 | 1 | 0 | 1 | 0 | 0 |

| Frozen family / arm | Rows | Awaiting human review | Review-blocked | Technical rejection | Source-physical rejection | Source-geometry rejection |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cyclist crossing | 2 | 0 | 0 | 1 | 1 | 0 |
| Pedestrian crossing | 7 | 1 | 2 | 1 | 3 | 0 |
| Longitudinal following | 3 | 1 | 0 | 1 | 1 | 0 |
| Random100 source candidates | 12 | 2 | 1 | 3 | 5 | 1 |

Among the 10 source-physical rejections, there were 10 unreviewable source-box-overlap reason occurrences and one ego-box boundary-contact occurrence; reasons can co-occur in a row. The geometry-rejected primary also had an unreviewable overlap, so the all-primary audit total is 11 overlap occurrences and one boundary-contact occurrence. One primary was rejected because its occupied start-to-goal route was unreachable. Six technical rejections had five hybrid-counterfactual and three hybrid-lifecycle gate-marker occurrences; marker occurrences overlap across cases. Three other rows remain review-blocked on unresolved physical-overlap review (two, one, and three overlapping pairs respectively). Rule-applicability flags remain annotations and did not exclude rows from the full technical gate.

## Prespecified alternates

The frozen queue contains 11 alternate windows. Two passed the current source-hash and independence checks and were attempted; both ended in source-physical rejection due to unreviewable source-box overlaps, with no alternate reaching the technical gate.

| Primary | Alternate | Result |
| --- | --- | --- |
| Random100-17, recording 21, ego 164 | frame 7804, identity SHA-256 `25dc8583db9203f37dca636032bf11a94399b380007ed38076ba42337281571e` | Source-physical rejection; one unreviewable overlap |
| Random100-23, recording 24, ego 250 | frame 11845, identity SHA-256 `e34cd2ac6b70d78b6a9d3750a402ab2abfddc8e20faf2ea9c991ae5eb3b9a08e` | Source-physical rejection; two unreviewable overlaps |

Of the 11 frozen alternate windows, eight belong to non-structural primary rows and were not triggered. Two first-ranked alternates were attempted (shown above). One second-ranked option for Random100-23 was not reached after the first option under the one-attempt-per-primary policy. Nine structural primary rejections had no prescribed alternate. The ledger records zero skipped alternates. No fallback-adjusted technical passes were added.

## Human-review assets and runtime

The review manifest contains seven reviewer-facing cases: four technical passes awaiting human review and three review-blocked cases. All seven have both a source-image registration and rule-review montage on disk. No manual review was created, and no final manual admission is recorded. The manifest is [human_review_manifest.json](../../../artifacts/german_200_v1_runs/workstream_c_batch_001/human_review_manifest.json), SHA-256 `66a4841a3b511ec784ccb76f4ea465118927eb779792f6337dc63e315678c304`.

Primary per-candidate runtime averaged 14.202 seconds across 24 rows (median 17.718; range 3.132–25.267). There were no outliers under the 1.5-IQR rule. The two attempted alternates averaged 5.415 seconds (range 4.973–5.856), also with no outliers. Runtime is the structured per-candidate start-to-completion wall time, with primary and alternate work summarized separately.

The machine-readable batch report is [batch_descriptive_report.json](../../../artifacts/german_200_v1_runs/workstream_c_batch_001/batch_descriptive_report.json), SHA-256 `c0bb11bbd9a7fa492ba5b55783a18cb5a2a341ed886085d37ae6e0d788ca681e`. It retains every primary case, per-arm/location/family status counts, alternate outcomes, pending asset checks, runtime values, exact commands, and the runner's producer fingerprint. The finalizer-generated summary has a null frozen-provenance field because it looks for that sidecar beside the next queue; the source provenance hash above is the actual file in the frozen source-queue directory and is recorded in the descriptive report.

## Combined B/C descriptive view

Across the two separate frozen batches (24 B rows and 24 C rows), 6/24 Interactive100 and 4/24 Random100 rows passed the technical gate and await human review. Combined status totals are 10 awaiting review, six review-blocked, 12 technical rejections, 17 source-physical rejections, and three source-geometry rejections. Per-batch outcomes remain separate in the combined report; no rows were pooled for an admission estimate.

The combined location counts are: location 1 (13 rows: 8 awaiting, 3 technical rejects, 2 physical rejects); location 2 (25: 6 blocked, 2 geometry rejects, 4 technical rejects, 13 physical rejects); location 3 (4: 2 technical and 2 physical rejects); location 4 (6: 2 awaiting, 3 technical rejects, 1 geometry reject). By family: cyclist (5: 1 awaiting, 1 blocked, 1 geometry reject, 1 technical reject, 1 physical reject); pedestrian (11: 2 awaiting, 2 blocked, 2 technical rejects, 5 physical rejects); longitudinal following (8: 3 awaiting, 1 blocked, 1 technical reject, 3 physical rejects); Random100 source candidates (24: 4 awaiting, 2 blocked, 8 technical rejects, 8 physical rejects, 2 geometry rejects).

There are 17 reviewer-facing cases across B and C, including the one retained fallback review case from B; all referenced review assets are recorded in the combined report. Runtime remains summarized per batch: B averaged 15.785 seconds per primary (n=24; median 20.009; range 2.14–30.44), and C averaged 14.202 seconds (n=24; median 17.718; range 3.132–25.267). Neither batch had a 1.5-IQR runtime outlier. See [the combined B/C descriptive report](../../../artifacts/german_200_v1_runs/workstream_c_batch_001/batch_b_c_descriptive_report.json), SHA-256 `735939205c6e31629bd2750b6d032c621b07090976b2721b6f8996e05de0d013`, for per-arm, location, family, status, review-case, and runtime detail.

This batch is descriptive evidence for the selected 24 rows. It does not estimate population admission or research performance. For the separate off-stride source-only analysis, see [Workstream E](2_german_200_v1_workstream_e.md).
