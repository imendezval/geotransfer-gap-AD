# German-200 v1 B/C admission yield diagnostic

This offline audit joins the 24 Workstream B primaries and the 24 Workstream C
primaries. It preserves the saved ledger verdicts, excludes alternates, and does
not use planner outcomes to select or admit scenes.

## Recorded outcomes

| Original primary verdict | Count |
| --- | ---: |
| Technical pass, awaiting human review | 10 |
| Technical rejection | 12 |
| Review blocked | 6 |
| Source physical rejection | 17 |
| Source geometry rejection | 3 |
| **Total** | **48** |

Twenty-eight cases reached the full gate: 10 have `technical_admitted: true`,
12 retain the original `technical_rejection` verdict, and six are
`review_blocked` on physical review. Thus the descriptive technical pass count
is 10/28 (35.7%) among gate-evaluated primaries and 10/48 (20.8%) over all
frozen primaries. These are fixed-batch counts, not a population estimate or
final research admission rate. All 10 technical passes and six review-blocked
cases remain pending human review; the saved B and C run reports say no manual
reviews were created.

All 48 source identity, source hash, context identity, conversion log, binary
round-trip, and converted-binary hash checks pass. The three geometry
rejections fail the saved occupied start-to-goal route check. All 12 technical
rejections pass source and map-route checks; separately, seven have a clear
physical source screen and five have reviewable overlaps awaiting physical
review. This separates common source/map validity from traffic-mode failures
without declaring the five unresolved physical cases clear.

The technical rejections have overlapping traffic failure markers: three fail
the saved birth/exit check, nine fail the counterfactual lifecycle check, eight
fail hybrid lifecycle, and ten fail hybrid counterfactual. Every one of the 12
has at least one explicit failed traffic marker in its saved gate report. A
marker count can exceed the case count because one case can fail several
checks. Structured birth reports exist for three B cases; absence of such a
report elsewhere is not treated as a failure.

## By site and family

| Location | Awaiting review | Review blocked | Technical rejection | Physical rejection | Geometry rejection | Total |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 8 | 0 | 3 | 2 | 0 | 13 |
| 2 | 0 | 6 | 4 | 13 | 2 | 25 |
| 3 | 0 | 0 | 2 | 2 | 0 | 4 |
| 4 | 2 | 0 | 3 | 0 | 1 | 6 |
| **Total** | **10** | **6** | **12** | **17** | **3** | **48** |

| Family / arm | Awaiting review | Review blocked | Technical rejection | Physical rejection | Geometry rejection | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cyclist crossing | 1 | 1 | 1 | 1 | 1 | 5 |
| Pedestrian crossing | 2 | 2 | 2 | 5 | 0 | 11 |
| Longitudinal following | 3 | 1 | 1 | 3 | 0 | 8 |
| Random100 source candidates | 4 | 2 | 8 | 8 | 2 | 24 |
| **Total** | **10** | **6** | **12** | **17** | **3** | **48** |

## Attribution of the 12 technical rejections

The table lists the gate's false traffic checks, a concrete actor/step event
where the saved trace has one, and the exact gate report SHA-256. Counterfactual
events use the saved tuple `[track_id, step, collision_state, removed]`. Full
per-mode events, all false gate checks, structured excerpts, and hashes for the
supporting reports are in the machine matrix. Some rows also have separate
semantic-review or unresolved-overlap gate markers; those are retained there
and are not recast as traffic failures.

| Candidate | Site / family | Failed traffic checks | Saved event detail | Gate SHA-256 |
| --- | --- | --- | --- | --- |
| `Random100-0-ed3193d495c0` | 1 / Random100 | `births_and_exits`, `counterfactual_lifecycle`, `hybrid_lifecycle`, `hybrid_counterfactual` | Dynamics and IDM birth reports fail; track 291 birth step 3. Hybrid trace records track 291 off-road at step 3, collision state 2. | `f2dc5926034d1d1decf075517684a520a914c7b74c5fa9cdbd0c04c8b0f80eeb` |
| `Random100-7-947545952a10` | 3 / Random100 | `counterfactual_lifecycle`, `hybrid_lifecycle`, `hybrid_counterfactual` | Track 236 is missing in IDM at step 6 (state 2); hybrid trace records it off-road at step 54 (state 2). | `193a2583cf66881058391db06a5ddc960fd755bcfcf979d93f89b49310381cff` |
| `Random100-8-6be6bc5d7aec` | 3 / Random100 | `counterfactual_lifecycle`, `hybrid_counterfactual` | Expert, IDM, zero-action, and hybrid counterfactual egos terminate at step 1, collision state 2, removed. No source-valid-missing actor event is recorded. | `7ee83a45944d561d5d68117a262474a64f7c40ce4198546b81348f318657d1b1` |
| `Random100-9-357e0fd2356b` | 4 / Random100 | `births_and_exits`, `counterfactual_lifecycle`, `hybrid_lifecycle`, `hybrid_counterfactual` | Dynamics and IDM birth reports fail; track 109 birth step 10. Hybrid trace records tracks 108 and 109 off-road at steps 1 and 10 (state 2). | `bead7b343873555407c44be847a1652e530c8f2ebac19e74874baa7f919e561e` |
| `Random100-10-b80e615825be` | 4 / Random100 | `births_and_exits`, `counterfactual_lifecycle`, `hybrid_lifecycle`, `hybrid_counterfactual` | Dynamics and IDM birth reports fail; track 13 birth step 7; track 16 birth step 83 is untested after terminal step 77. Hybrid trace records track 13 off-road at step 7 (state 2). | `fd5ada11eeda0b728d11fbe3a880307adac6db7c85070642924e812e8f903ef8` |
| `Interactive100-16-01096bb714f4` | 2 / Pedestrian crossing | `hybrid_lifecycle` | Hybrid trace records tracks 191 and 193 colliding at step 49, collision state 1, with entity indices 26 and 24. The physical source overlap remains pending review. | `4ca353a2114c31250f3d8f2a5daa23cb7a02d610a37c04b24a6838b44c6a0627` |
| `Interactive100-0-a386442265d8` | 2 / Longitudinal following | `hybrid_counterfactual` | Zero-action counterfactual has tracks 198 and 199 missing at step 31 (state 1); hybrid counterfactual has track 199 missing at step 37 (state 1). | `c06554138f207a91caa164e27d987bdf0276c55df5451881320483e1fef1f23f` |
| `Interactive100-2-4f0aa5c24bfd` | 1 / Cyclist crossing | `counterfactual_lifecycle`, `hybrid_lifecycle`, `hybrid_counterfactual` | Track 199 is missing at step 1 (state 2); hybrid trace records it off-road at step 1 (state 2). | `3dfe752b2944cfdfeef749c9e5edc3290bbd9166c984bd3cbd4e2874fe62566d` |
| `Interactive100-7-e76c43a28531` | 2 / Pedestrian crossing | `counterfactual_lifecycle`, `hybrid_lifecycle`, `hybrid_counterfactual` | IDM counterfactual has track 543 missing at step 1 (state 2); hybrid trace records track 545 colliding at step 28 (state 1, entity index 18). | `a80fc11abdb578e05ceb1421a217bf1a0351e5855f1b56992b5fe9b97704e0b6` |
| `Random100-12-447f18f939e8` | 4 / Random100 | `counterfactual_lifecycle`, `hybrid_counterfactual` | Expert, IDM, zero-action, and hybrid counterfactual egos terminate at step 1, collision state 2, removed. | `b821965d002ca5e701117b7d1786ac87eacce003c701c92fc770b28af84d8df5` |
| `Random100-16-33eecbfa0e4f` | 1 / Random100 | `hybrid_lifecycle` | Hybrid trace records track 133 colliding at step 36 (state 1, entity index 0); zero-action counterfactual records tracks 132 and 133 missing at step 28 (state 1). | `387a4234cfde42bb6c11b9c2502dd44ad9e764381985abcefd2a1626d9a5402d` |
| `Random100-18-3e0be3c1a3fe` | 2 / Random100 | `counterfactual_lifecycle`, `hybrid_counterfactual` | IDM and hybrid counterfactuals record track 353 missing at step 85 (state 1), followed by source-valid-missing steps 86–89 with state 0. Physical overlap review is also pending. | `ba02df27fb8eee066974567928c887c837840b359eb618878f5c3857ff4719d1` |

## Evidence status and limits

The producer keeps expert replay, dynamics and IDM birth/exit, IDM/native,
hybrid-startup lifecycle, and counterfactual modes separate. Among the 28
gate-evaluated cases, expert replay passes 28; dynamics and IDM birth/exit pass
25 and fail 3; the saved IDM counterfactual mode passes 17 and fails 11;
hybrid-startup lifecycle passes 20 and fails 8; hybrid-startup counterfactual
passes 18 and fails 10. The other 20 primaries have `not_established` where
these tests were not hash-bound or did not produce evidence. Missing reports do
not count as failures.

Rule applicability remains pending human review for all 48 cases; the audits
are labelled `evidence_only`. Planner-specific eligibility is
`not_established`. Separately, the legacy map audit reports map observation
types `[4, 5, 6]` and `rules_7_8_visible_in_current_observation: false` in all
48 cases. That field is not treated as a planner result or eligibility check.

The matrix producer validates each available case report against the saved
output-tree or gate SHA before interpreting it. A mismatch aborts the run;
missing or unbound evidence stays `not_established`. The focused regression
tests cover missing, ambiguous, conflicting, and mismatched evidence, mode
classification (including unresolved physical overlaps), and refusal to
overwrite existing outputs.

The detailed ignored-workspace matrix is
[matrix.json](../../../artifacts/german_200_v1_runs/workstream_a_yield_diagnostics/matrix.json).
The tracked 48-row status index is
[2_german_200_admission_yield_cases_v1.json](2_german_200_admission_yield_cases_v1.json).
The producer is
[german_200_yield.py](../../../src/geotransfer_gap/corpus/german_200_yield.py).

To reproduce in a fresh workspace, choose output paths that do not already
exist; the CLI refuses to overwrite either output:

```bash
PYTHONPATH=src python -m geotransfer_gap.corpus.german_200_yield \
  --output artifacts/german_200_v1_runs/workstream_a_yield_diagnostics/matrix.rerun_001.json \
  --compact-output /tmp/german_200_admission_yield_cases_v1.rerun_001.json
```

Use fresh names on subsequent runs. The tracked compact index can be compared
with a compact output generated from a fresh matrix by passing
`--compact-output /tmp/german_200_admission_yield_cases_v1.rerun_001.json`.
