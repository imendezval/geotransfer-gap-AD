# German-200 Location 2 forensic baseline (E1)

## Scope and status

This is an offline baseline of the 57 frozen Location 2 **primary** rows in B1–B4. The 10 Location 2 fallback attempts are preserved in a separate section of the machine evidence and are excluded from every primary denominator. The analysis does not clear physical evidence, alter thresholds, change source/native configuration, create reviews, run native commands, or make an admission or acceptance decision.

The reader uses the B1–B4 ledgers and identity hashes from the retention chain, then calls the saved per-case verifier in `src/geotransfer_gap/corpus/diagnose_german_200_physical.py`. That verifier is byte-pinned to commit `2d0a498af1832a4f6b9087e556d55de9f6030c0d`, SHA-256 `e53a1733f8732043442cbfeccf1d0e14c6eaa650773c6394589029c8e6d36abb`. The reader records the actual source checkout HEAD separately. At extraction, the shared retention history also contained a B5 append. The exact first-four-record B1–B4 prefix remains SHA-256 `860c5a5b1a9e3942fa43be7f1d8c49d738d97139c4ee99ee38e437d3f88d71a2`; B5 was observed and excluded as incidental provenance.

## Reconciliation

| Batch | L2 primaries | Ledger SHA-256 | Retention record SHA-256 |
|---|---:|---|---|
| B1 | 9 | `4076644465ae3d7a9483499bad9ab28b37a2e5effadc32a43bbba98a36dcdf4a` | `ab65e52b09c597c6c663bafe046cb79434ce4f87595c1527fea09e5c80b902fc` |
| B2 | 16 | `a6d36cd0e13375d4236b0a19cf393990e9fc0da1aaa6eb9df8f67e270329ac78` | `40bafed89a5f1ca33b33856b693a1f92d5aedbd7cd91efe3f39ebecda7650432` |
| B3 | 17 | `4f6e3ba0acf1d5eb44ba7fba457414b826344a1740d5411b371beb8da6a710af` | `b7f3256a323d4d0b9a5f256346cf55c84297e6b48ada89f5b632f8ebd02ebf6c` |
| B4 | 15 | `b966b91bead60b76e0cf56edb8b21db5bb949efa9c5e584da8fdc031b76fe3f6` | `874dcdd62f06e19878a2d964866619d8fe0d8af9b7581edcfa762f0cf527014d` |
| **Total** | **57** |  |  |

All 24 ordered primary identities in each batch reconcile to the pinned retention record. The selected 57 rows have 57 unique `candidate_id` values and 57 unique `source_window_identity_sha256` values. The offline verifier checked the saved scene, validation report, map and physical audits, map binary, available review media, scene structure, source actor identity, source movement metadata, physical audit/preflight agreement, route/map audit consistency, and raw-source SHA-256 bindings for every row: 57/57. It read 50 unique source files. The retention review index batch sources, queue/manifest bytes, and indexed evidence hashes reconciled; 20 indexed Location 2 primaries and two indexed fallbacks were separately identity-checked. No indexed evidence hash mismatch was found.

Initial machine evidence: `/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_baseline/location2_baseline.json` (2,052,428 bytes), SHA-256 `9007b0c0039378fa4c7f63a5d2c021dc150437b46f9ce7cfb505efc654aabfa9`.

The corrected reader was run from the checked-in worktree at actual HEAD `420390c7054372a7ab41e2cb85c060206f684b90` into the fresh output `/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_baseline_correction_run/location2_baseline.json` (2,053,224 bytes), SHA-256 `d969088279f96ef188a97d3d6c18d3f6540dd02d9b7e1dc9a653b7b2c69b6593`. It verified the existing forensic producer SHA-256 `e53a1733f8732043442cbfeccf1d0e14c6eaa650773c6394589029c8e6d36abb`, matching the bytes at commit `2d0a498`. The actual checkout HEAD and current retention tip/history are stored under `incidental_provenance`; they are separated from the stable B1–B4 comparison sections.

Compared with the initial machine file, `summary` metrics outside reconciliation, all 57 `primary_cases`, all 10 `fallback_attempts_location_2_separate`, pair recurrence details, and the stable reconciliation fields match exactly. The status counts remain 26 physical rejections, 2 geometry rejections, 18 review-blocked, 9 technical rejections, and 2 awaiting review. The mutable old `pinned_repo_head`, full-history hash, suffix, and tip fields were moved to the incidental section.

Other bound inputs include the retention review index JSON SHA-256 `32d2a0acb1b031a69423ebc08e4466dbe00f6f402edc761edb0cc866e431b168`, the A4 reproduction summary SHA-256 `d833c2e925be7b42c4c5fa461228a1cc22930eafe82b8872c72a5c84d84d8a56`, and its run manifest SHA-256 `9e6f1689e95518a52856bccdbc8f078d1055ab20ce788e2b8f56850a3b3f47e8`. The machine file also records hashes for `german_200_bc_physical_forensics.md`, `german_200_retention_batch_004.md`, the review-index report, the A4 protocol freeze, and its support addendum.

## Saved primary outcomes

The denominator is always the 57 primary rows. These ledger statuses are mutually exclusive in the selected rows.

| Batch | Physical rejection | Geometry rejection | Review blocked | Technical rejection | Awaiting review | Total |
|---|---:|---:|---:|---:|---:|---:|
| B1 | 4 | 1 | 3 | 1 | 0 | 9 |
| B2 | 9 | 1 | 3 | 3 | 0 | 16 |
| B3 | 6 | 0 | 5 | 4 | 2 | 17 |
| B4 | 7 | 0 | 7 | 1 | 0 | 15 |
| **Total** | **26** | **2** | **18** | **9** | **2** | **57** |

| Arm / source-task family | n | Physical | Geometry | Review blocked | Technical | Awaiting |
|---|---:|---:|---:|---:|---:|---:|
| Interactive100 / cyclist crossing | 13 | 3 | 1 | 5 | 4 | 0 |
| Interactive100 / longitudinal following | 6 | 2 | 0 | 2 | 2 | 0 |
| Interactive100 / pedestrian crossing | 19 | 11 | 0 | 5 | 2 | 1 |
| Random100 / unreviewed random source candidate | 19 | 10 | 1 | 6 | 1 | 1 |
| **Interactive100 total** | **38** | **16** | **1** | **12** | **8** | **1** |
| **Random100 total** | **19** | **10** | **1** | **6** | **1** | **1** |

Recording denominators are: r18=5, r19=2, r20=4, r21=5, r22=7, r23=6, r24=3, r25=5, r26=4, r27=4, r28=7, r29=5. The machine file includes each recording's status breakdown and the per-case identity key.

## Geometry and task proximity

The occupied-lane route check is false in 2/57 rows; both are saved geometry rejections. The saved nearest-centerline route check is true for those same two rows, so the representations disagree in 2/57. The rows are `Interactive100-21-d0d1690740f0` (r28, B1) and `Random100-23-7989a39a8fac` (r24, B2). The map audits report zero ego-center samples outside lanelet polygons in all 57. These are separate route representations; this difference alone does not establish a gate defect.

For the 38 Interactive rows with a designated task actor, minimum timed ego/task center distance was measured from shared valid samples in the hash-bound converted scene: median 4.883 m, mean 4.967 m, range 2.355–9.384 m. All 19 Random rows have no designated task actor, so their ego/task distance is explicitly unavailable. These distances describe sampled centers and do not establish that the task identity or interaction claim is semantically supported.

The reader directly inspected raw tracks CSV rows for four representative cases: the saved A4 L2 technical reject, one occupied-route geometry rejection, one physical rejection, and one review blocker. Those windows have 225–226 raw rows per selected track over their frozen frame intervals. For those representatives, it also binds the source map bytes, map audit, converted scene, and output-tree hashes. The remaining cases retain full raw-source byte/hash verification and saved conversion/map evidence; they do not get a second raw-row scan.

## Physical findings and pair identities

Across the 57 primaries, the saved audits contain 149 case-pair occurrences: 47 marked `reviewable_annotation_overlap=false` and 102 marked true. These are occurrences in candidate windows, not 149 independent physical conflicts.

| Ledger status | Ego pair, moving/moving | Context moving/stationary | Context stationary/stationary | Pair occurrences |
|---|---:|---:|---:|---:|
| Source physical rejection | 1 | 28 | 65 | 94 |
| Review blocked | 0 | 0 | 35 | 35 |
| Source geometry rejection | 0 | 2 | 4 | 6 |
| Technical rejection | 0 | 0 | 14 | 14 |
| **Total** | **1** | **30** | **118** | **149** |

Of the 26 physical-rejection rows, 24 have at least one non-reviewable pair, four have ego-boundary contacts, two have both markers, and two have boundary contacts without a non-reviewable pair. The 18 review-blocked rows have 35 saved pair occurrences; all are marked reviewable and both-stationary. The six pair occurrences in geometry-rejected rows include two non-reviewable and four reviewable pairs; route rejection remains independent. The 14 occurrences in technical-rejection rows are saved reviewable stationary-pair evidence, not the recorded technical-rejection reason.

Across all 149 pair occurrences, maximum penetration has median 0.148 m, mean 0.161 m, and range 0.001–0.600 m. Minimum ego-box gap has median 14.717 m and range 0–64.699 m. Saved overlap counts range from 1 to 91 samples (median 91); the scene rate is 10 Hz. A full 91-sample overlap spans 9.0 seconds between its first and last sample. For shorter overlaps, the audit may retain only leading sample indices, so the complete contiguous span is marked unknown unless the saved step list is complete. Sample occupancy count divided by rate is retained separately from elapsed first-to-last span.

Pair identity is `(recording, sorted source track IDs)`. There are 60 unique such identities; 25 recur across candidate windows, accounting for 114 occurrences. All 25 recurrent identities are marked both-stationary in every occurrence. The identity-level recurrence list, case IDs, penetration, overlap count, motion, and reviewability are in the JSON. Repeated windows and shared recordings mean these counts cannot be treated as independent observations.

## Scene complexity and lifecycle evidence

Frozen source-context complexity is descriptive. The counts include ego; pair opportunities are combinatorial counts, not collision probabilities.

| Arm / family | n | Mean context actors | Mean moving | Mean stationary | Mean active actors / step |
|---|---:|---:|---:|---:|---:|
| Interactive100 / cyclist crossing | 13 | 29.54 | 12.46 | 17.08 | 26.32 |
| Interactive100 / longitudinal following | 6 | 30.00 | 14.33 | 15.67 | 26.21 |
| Interactive100 / pedestrian crossing | 19 | 31.47 | 13.47 | 18.00 | 28.03 |
| Random100 / unreviewed random candidate | 19 | 29.68 | 12.16 | 17.53 | 26.05 |
| **Interactive100** | **38** | **30.58** | **13.26** | **17.32** | **27.16** |
| **Random100** | **19** | **29.68** | **12.16** | **17.53** | **26.05** |

Physical-rejection rows average 31.35 context actors and 27.77 active actors per step; review-blocked rows average 29.44 and 25.97, respectively; technical-rejection rows average 30.22 and 26.84. This is a fixed-batch correlation, not evidence that complexity caused rejection. The family and recording breakdowns, including medians and ranges, are in the machine evidence.

### Evidence classes

| Class | Examples in this baseline | What the evidence supports |
|---|---|---|
| Direct measurements | Ledger/hash reconciliation; saved occupied-lane route verdicts; source-box overlap count, penetration and ego-box gap; source-context movement labels; converted-scene timed center distances; saved lifecycle loss events | What the hash-bound files record for these candidate windows |
| Descriptive associations | Status counts by batch, family, recording and arm; context complexity by saved status; recurring recording/pair identities | Comparisons within this fixed cohort; repeated rows and shared recordings limit independence |
| Untested hypotheses | Dense stationary context may be associated with more pair-triggered blockers; recurrent stationary overlaps may sometimes reflect a common annotation pattern; the two route disagreements may be explained by the difference between occupied-lane and nearest-centerline routes | Questions for E2 only. None is a physical-truth finding, causal claim, or gate defect conclusion |

For example, all recurrent pair identities being stationary is a direct property of the saved movement labels. It does not establish that any recurrence is an annotation artifact. Likewise, the two route representations disagree in the saved reports, but that alone does not show which route result should govern.

Saved hybrid admission reports and hybrid lifecycle traces are present for 29/57 rows. Absence in the other 28 is treated as not run or unknown, never as a pass. Among the 29 reports, false-check counts include: `semantic_screen` 29; missing semantic review 29; `source_supported_irrelevance_plausible` 29; unresolved source-pair review 25; `counterfactual_lifecycle` 8; `hybrid_lifecycle` 7; and `hybrid_counterfactual` 7. `births_and_exits` is false in none of the available reports. These saved classifications overlap and are not mutually exclusive.

Across available lifecycle traces, first source-valid loss causes were:

| Trace mode | Goal | Collision | Off-road |
|---|---:|---:|---:|
| Expert | 29 | 0 | 0 |
| Hybrid startup | 28 | 8 | 2 |
| Immediate IDM | 28 | 10 | 4 |

Nine primary rows have at least one non-goal first source-valid loss in an available trace. Collision actor-event counts are 10 in hybrid traces and 14 in IDM traces; they are actor records and may represent the two sides of one pair event. These saved traces classify behavior but do not change primary ledger outcomes.

The saved A4 reproduction covers one L2 technical-rejection candidate, `Interactive100-0-a386442265d8` (B2). Its current immediate-IDM gate is technically admitted, while research admission remains false; the hybrid-startup gate is not technically admitted, with failed checks including `hybrid_counterfactual` and missing semantic review. Its Expert-ego/IDM matrix is current but its task view is not established. The A4 report also records a lead-vehicle geometry mismatch under IDM: at scene step 30, source oriented-box gap 1.966 m versus IDM 7.849 m and actor position error 5.907 m; only 3/63 source-close steps match. This is direct saved reproduction evidence, not a semantic judgment. See [A4 reproduction report](../plans/step_2/2_german_200_workstream_a_a4_reproduction_report_20261127.md).

Semantic applicability remains unknown in all 57 primaries: each saved row is `annotation_only_pending_human_review` and has at least one spatial/applicability flag. The review index routes 20 primaries and two fallbacks at Location 2; it does not record an adjudication. No manual review was created. Flags are review prompts, not findings.

## E2 follow-up tests

The overnight E2 work should capture automated source and dimension measurements and label resulting interpretations as hypotheses. Human adjudication, physical clearance, and semantic findings are explicitly outside the overnight scope.

1. **Measure the 60 pair identities from source bytes.** For each recording/pair identity, extract the frozen-window track rows, row coverage, source centers/headings, source class and dimensions from track metadata, and converted dimensions plus `dimension_imputed`. Recompute source oriented-box overlap steps and penetration with a separately hash-bound offline measurement, then compare those measurements with the saved audit counts and depths. Store measurements and uncertainty; add hypotheses such as “recurrent stationary pair may reflect a repeated annotation pattern” or “dimension/heading uncertainty may affect overlap.” Keep all 25 recurrent identities grouped. Record no annotation-overlap, conflict, or clearance verdicts; human adjudication is outside the overnight scope.
2. **Reproduce the two route discrepancies.** For `Interactive100-21-d0d1690740f0` and `Random100-23-7989a39a8fac`, inspect occupied start/goal lanelets and nearest-centerline IDs against the pinned L2 OSM bytes and map audit. Report the two route definitions and step-level occupancy evidence side by side. Do not alter route or geometry thresholds as part of this measurement.
3. **Freeze a lifecycle probe cohort before any new run.** Separate rows with saved lifecycle reports from early source-gate exits. Use the current A4 case as the control, then preselect technical-rejection rows by failure class and source task family. Bind runtime, converter, map, and protocol hashes before execution; report source-valid losses, births, collision pairs, and task fidelity separately. This baseline itself ran no native command.
4. **Test a complexity association with clustered units.** Compare statuses within recording and family, then resample by recording and pair identity rather than by candidate row. Treat this fixed 57-row batch as descriptive and do not call it a location population estimate.

## Extending the evidence to accepted later batches

The current generator intentionally pins B1–B4. For a later accepted batch, add a versioned batch manifest with the batch label, ledger path and SHA-256, retention record SHA-256 and predecessor, ordered primary identity hashes, queue and review-manifest paths/hashes, output root, and expected primary count. Validate that manifest against the retention prefix before reading the new ledger. Feed each primary through the same saved `_case_record` hash/provenance checks and append one JSONL record keyed by `source_window_identity_sha256`; reject identity duplicates across batches. Write fallback attempts to a separate JSONL stream and compute denominators from primary records only. Keep each versioned batch output immutable and regenerate aggregate summaries from the accepted manifests. Compare `summary`, `primary_cases`, and `fallback_attempts_location_2_separate` as stable B1–B4 sections; inspect `incidental_provenance` separately for actual HEAD and any later retention-history suffix/tip. This will let B5 and later batches be added without rewriting or silently reclassifying B1–B4.

## Rerun and review

From the location-2 worktree:

```bash
python scripts/location2_baseline.py \
  --repo-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2 \
  --evidence-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD \
  --output-dir /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_baseline
sha256sum /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_baseline/location2_baseline.json
```

The corrected rerun command was:

```bash
python scripts/location2_baseline.py \
  --repo-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2 \
  --evidence-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD \
  --output-dir /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_baseline_correction_run
```

To reproduce again, choose another fresh output directory and verify its output with `sha256sum`.

The generator refuses to overwrite a non-empty output directory. Review the machine file's `summary`, then `primary_cases` keyed by source-window identity, then `fallback_attempts_location_2_separate`. Start with `reconciliation`, `source_geometry_route`, `physical_blockers`, `pair_identity_recurrence`, `native_hybrid_lifecycle`, and `semantic_support`; inspect `incidental_provenance` separately for the actual checkout HEAD and mutable retention tip/history observations.

## Evidence limits

- Saved overlap labels, penetration, route checks, converted coordinates, and native traces are evidence about the saved artifacts; they are not human-verified physical truth or task suitability.
- Hybrid reports cover 29/57 rows. Missing reports are unknown; early source rejects were not sent through those checks.
- Pair occurrences, candidate windows, and source recordings are dependent. Counts and complexity contrasts are descriptive only.
- Direct raw CSV row inspection was bounded to four representative windows. All 57 source inputs and saved outputs still passed hash-binding checks.
- The current retention chain has a B5 suffix, but this E1 report uses only the verified B1–B4 prefix and does not ingest B5 outcomes.
