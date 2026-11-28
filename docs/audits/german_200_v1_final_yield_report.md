# German-200 v1 B1-B9 primary technical funnel

## Scope and interpretation

This is a descriptive summary of the frozen B1-B9 primary cohort. The stable join key is source_window_identity_sha256; within-batch queue indexes are navigation fields only. It does not pool fallback outcomes into the primary denominator or imply a probability sample, population estimate, physical clearance, semantic finding, or research admission.

The canonical retention verifier accepted all nine records. The history SHA-256 is 27df52d6410f141c903e38a389e6dc746d13530241c7e39973ec810ec3e533d9; the final B9 record is 05d898b174bccaebab6a1a804344e69d4eadef082254ad425a713530085c9aa6. The protected 78,789-byte B8 history prefix remains SHA-256 387188faf47a4affa83bb70eb55544dfa7f5a13596836897a2a45e7d87217594. The B1-B9 primary set contains 200 unique identities, with 100 Interactive100 and 100 Random100.

The primary raw pass fraction is technical gate passes divided by all frozen primaries. The conditional technical-gate fraction uses the operational denominator recorded in each batch report; that denominator includes review-blocked rows and excludes source physical/geometry rejections. Technical passes are counted from the gate admission field and agree with every batch summary.

## Primary funnel

Across B1-B9, 39 of 200 frozen primaries passed the technical gate: 39/200 (19.5%). The batch-report eligible denominator is 115, giving 39/115 (33.9%). These are descriptive fractions for the fixed cohort.

| Primary status | Count |
| --- | --- |
| awaiting_human_review | 39 |
| review_blocked | 40 |
| source_physical_rejection | 77 |
| source_geometry_rejection | 8 |
| technical_rejection | 36 |

The status categories are mutually exclusive and sum to 200: 39 awaiting review, 40 review blocked, 77 source-physical rejections, 8 source-geometry rejections, and 36 technical rejections. The 39 technical passes overlap the awaiting-review status; they are not an additional status row.

## Batch breakdown

| Batch | Primaries | Tech pass | Gate denominator | Raw fraction | Conditional fraction | Awaiting | Blocked | Physical | Geometry | Tech reject | Fallback attempts | Fallback passes | Retained alternates | Review entries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 24 | 6 | 15 | 25.0% | 40.0% | 6 | 3 | 7 | 2 | 6 | 4 | 0 | 1 | 10 |
| B2 | 24 | 4 | 13 | 16.7% | 30.8% | 4 | 3 | 10 | 1 | 6 | 2 | 0 | 0 | 7 |
| B3 | 24 | 4 | 16 | 16.7% | 25.0% | 4 | 5 | 7 | 1 | 7 | 1 | 0 | 0 | 9 |
| B4 | 24 | 6 | 17 | 25.0% | 35.3% | 6 | 7 | 7 | 0 | 4 | 3 | 0 | 1 | 14 |
| B5 | 24 | 3 | 10 | 12.5% | 30.0% | 3 | 3 | 13 | 1 | 4 | 3 | 0 | 0 | 6 |
| B6 | 24 | 7 | 13 | 29.2% | 53.8% | 7 | 5 | 11 | 0 | 1 | 4 | 0 | 0 | 12 |
| B7 | 24 | 5 | 14 | 20.8% | 35.7% | 5 | 6 | 9 | 1 | 3 | 6 | 1 | 3 | 14 |
| B8 | 24 | 3 | 12 | 12.5% | 25.0% | 3 | 5 | 10 | 2 | 4 | 6 | 0 | 1 | 9 |
| B9 | 8 | 1 | 5 | 12.5% | 20.0% | 1 | 3 | 3 | 0 | 1 | 2 | 0 | 0 | 4 |

## Breakdowns by arm, location, source-task family, and recording

Each table uses the same funnel definitions. Family is the source queue’s source_task_families field; Random100 rows have no assigned task family and are labeled no_task_family rather than assigned an inferred task.

### Arm

| Arm | Primaries | Tech pass | Gate denominator | Raw fraction | Conditional fraction | Awaiting | Blocked | Physical | Geometry | Tech reject |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Interactive100 | 100 | 13 | 54 | 13.0% | 24.1% | 13 | 28 | 43 | 3 | 13 |
| Random100 | 100 | 26 | 61 | 26.0% | 42.6% | 26 | 12 | 34 | 5 | 23 |

### Location

| Location | Primaries | Tech pass | Gate denominator | Raw fraction | Conditional fraction | Awaiting | Blocked | Physical | Geometry | Tech reject |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 36 | 25 | 30 | 69.4% | 83.3% | 25 | 0 | 5 | 1 | 5 |
| 2 | 132 | 7 | 63 | 5.3% | 11.1% | 7 | 40 | 63 | 6 | 16 |
| 3 | 10 | 0 | 5 | 0.0% | 0.0% | 0 | 0 | 5 | 0 | 5 |
| 4 | 22 | 7 | 17 | 31.8% | 41.2% | 7 | 0 | 4 | 1 | 10 |

### Source-task family

| Family | Primaries | Tech pass | Gate denominator | Raw fraction | Conditional fraction | Awaiting | Blocked | Physical | Geometry | Tech reject |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cyclist_crossing | 33 | 5 | 20 | 15.2% | 25.0% | 5 | 10 | 10 | 3 | 5 |
| longitudinal_following | 20 | 3 | 10 | 15.0% | 30.0% | 3 | 5 | 10 | 0 | 2 |
| no_task_family | 100 | 26 | 61 | 26.0% | 42.6% | 26 | 12 | 34 | 5 | 23 |
| pedestrian_crossing | 47 | 5 | 24 | 10.6% | 20.8% | 5 | 13 | 23 | 0 | 6 |

### Recording

| Recording | Primaries | Tech pass | Gate denominator | Raw fraction | Conditional fraction | Awaiting | Blocked | Physical | Geometry | Tech reject |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 5 | 3 | 4 | 60.0% | 75.0% | 3 | 0 | 1 | 0 | 1 |
| 1 | 3 | 1 | 3 | 33.3% | 33.3% | 1 | 0 | 0 | 0 | 2 |
| 2 | 4 | 0 | 2 | 0.0% | 0.0% | 0 | 0 | 2 | 0 | 2 |
| 3 | 2 | 1 | 1 | 50.0% | 100.0% | 1 | 0 | 1 | 0 | 0 |
| 4 | 3 | 2 | 3 | 66.7% | 66.7% | 2 | 0 | 0 | 0 | 1 |
| 5 | 3 | 0 | 2 | 0.0% | 0.0% | 0 | 0 | 0 | 1 | 2 |
| 6 | 2 | 0 | 2 | 0.0% | 0.0% | 0 | 0 | 0 | 0 | 2 |
| 7 | 1 | 1 | 1 | 100.0% | 100.0% | 1 | 0 | 0 | 0 | 0 |
| 8 | 7 | 6 | 6 | 85.7% | 100.0% | 6 | 0 | 1 | 0 | 0 |
| 9 | 1 | 1 | 1 | 100.0% | 100.0% | 1 | 0 | 0 | 0 | 0 |
| 10 | 1 | 1 | 1 | 100.0% | 100.0% | 1 | 0 | 0 | 0 | 0 |
| 11 | 2 | 1 | 1 | 50.0% | 100.0% | 1 | 0 | 0 | 1 | 0 |
| 12 | 7 | 6 | 7 | 85.7% | 85.7% | 6 | 0 | 0 | 0 | 1 |
| 13 | 2 | 2 | 2 | 100.0% | 100.0% | 2 | 0 | 0 | 0 | 0 |
| 14 | 5 | 5 | 5 | 100.0% | 100.0% | 5 | 0 | 0 | 0 | 0 |
| 15 | 2 | 1 | 2 | 50.0% | 50.0% | 1 | 0 | 0 | 0 | 1 |
| 16 | 4 | 0 | 1 | 0.0% | 0.0% | 0 | 0 | 3 | 0 | 1 |
| 17 | 4 | 1 | 3 | 25.0% | 33.3% | 1 | 0 | 1 | 0 | 2 |
| 18 | 8 | 0 | 6 | 0.0% | 0.0% | 0 | 5 | 2 | 0 | 1 |
| 19 | 6 | 0 | 4 | 0.0% | 0.0% | 0 | 3 | 2 | 0 | 1 |
| 20 | 9 | 6 | 8 | 66.7% | 75.0% | 6 | 0 | 1 | 0 | 2 |
| 21 | 12 | 0 | 0 | 0.0% | — | 0 | 0 | 12 | 0 | 0 |
| 22 | 13 | 0 | 6 | 0.0% | 0.0% | 0 | 2 | 6 | 1 | 4 |
| 23 | 10 | 0 | 5 | 0.0% | 0.0% | 0 | 4 | 4 | 1 | 1 |
| 24 | 7 | 0 | 4 | 0.0% | 0.0% | 0 | 3 | 2 | 1 | 1 |
| 25 | 15 | 1 | 7 | 6.7% | 14.3% | 1 | 5 | 8 | 0 | 1 |
| 26 | 13 | 0 | 9 | 0.0% | 0.0% | 0 | 7 | 3 | 1 | 2 |
| 27 | 11 | 0 | 3 | 0.0% | 0.0% | 0 | 3 | 8 | 0 | 0 |
| 28 | 12 | 0 | 4 | 0.0% | 0.0% | 0 | 2 | 6 | 2 | 2 |
| 29 | 16 | 0 | 7 | 0.0% | 0.0% | 0 | 6 | 9 | 0 | 1 |
| 30 | 1 | 0 | 0 | 0.0% | — | 0 | 0 | 1 | 0 | 0 |
| 31 | 5 | 0 | 3 | 0.0% | 0.0% | 0 | 0 | 2 | 0 | 3 |
| 32 | 4 | 0 | 2 | 0.0% | 0.0% | 0 | 0 | 2 | 0 | 2 |

## Gate failures and review

Gate exclusion counts below are candidate-membership counts, not a partition: one gate can carry several exclusion reasons. Refresh-stage labels are reported from the saved ledger. The legacy B1/B2 technical rejections without a saved stage are kept as legacy_unstaged rather than retroactively assigned a stage.

| Gate exclusion reason | Candidate memberships |
| --- | --- |
| births_and_exits | 7 |
| exists:physical_overlap_review.json | 59 |
| exists:semantic_review_hybrid_startup.json | 76 |
| hybrid_counterfactual | 30 |
| hybrid_lifecycle | 26 |
| refresh_commands | 7 |
| source_box_overlaps_resolved | 59 |
| source_supported_irrelevance_plausible | 66 |

| Technical rejection stage | Count |
| --- | --- |
| legacy_unstaged | 29 |
| technical_gate_structured_failure | 7 |

Source-screen reason memberships also overlap: an individual physical rejection can carry more than one saved source reason.

| Source-screen layer | Reason | Candidate memberships |
| --- | --- | --- |
| Physical | source_ego_box_boundary_contact | 23 |
| Physical | unreviewable_source_box_overlap | 64 |
| Geometry | occupied_start_to_occupied_goal_unreachable | 8 |

The 115 primary gate records have 115 unique gate hashes. The nine review manifests contain 85 entries; each records manual_reviews_created=false. Across all primary ledgers, research_admitted is false and there are zero manual admissions. Per-batch gate and review-manifest SHA-256 values are in the machine receipt.

## Fallback outcomes and independence

Fallbacks are reported separately from the 200-primary funnel. Retained counts are derived through the existing retained-fallback verifier and reconciled to the canonical B1/B2 identity lists or B3-B9 structured receipts. The per-structural-primary disposition and per-attempt independence linkage table is in the [fallback disposition and independence index](../../runs/german_200_overnight/v1_final/fallback_disposition_independence.json); all links use stable primary and fallback source-window identities.

| Batch | Structural primaries | Prespecified | Attempted | Fallback statuses | Fallback tech passes | Retained |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | 9 | 11 | 4 | {"review_blocked": 1, "source_geometry_rejection": 1, "source_physical_rejection": 2} | 0 | 1 |
| B2 | 11 | 11 | 2 | {"source_physical_rejection": 2} | 0 | 0 |
| B3 | 8 | 21 | 1 | {"source_physical_rejection": 1} | 0 | 0 |
| B4 | 7 | 9 | 3 | {"review_blocked": 1, "source_physical_rejection": 2} | 0 | 1 |
| B5 | 14 | 12 | 3 | {"source_physical_rejection": 3} | 0 | 0 |
| B6 | 11 | 12 | 4 | {"source_physical_rejection": 4} | 0 | 0 |
| B7 | 10 | 17 | 6 | {"awaiting_human_review": 1, "review_blocked": 2, "source_physical_rejection": 3} | 1 | 3 |
| B8 | 12 | 11 | 6 | {"review_blocked": 1, "source_geometry_rejection": 1, "source_physical_rejection": 4} | 0 | 1 |
| B9 | 3 | 3 | 2 | {"source_physical_rejection": 2} | 0 | 0 |

Retained alternate counts by batch are [1, 0, 0, 1, 0, 0, 3, 1, 0]. There was one fallback technical pass across all batches (B7); primary technical passes remain 39 and the fallback pass is not included in the primary total.

## Structured spawn-report interpretation

The machine spawn index contains 121 saved spawn reports across 242 mode records. It records 53 mode records with post-goal untested source births, 0 mode records with explicit premature, post-exit, or pre-entry appearance fields, and 11 large aggregate birth-position discrepancies. These fields are kept distinct.

A post_goal_untested_birth_track_id is a source track whose birth step lies beyond the report’s justified goal-terminal step; when so labeled, that future birth was not tested after closure. It is not counted as an observed actor appearance. Actual appearance evidence is limited to explicit premature_appearances, postexit_appearances, or preentry_events in the saved report.

The validator checks the absent-actor position sentinel at (-10000, -10000), but its aggregate max_birth_position_error_m does not identify which sampled observation produced the maximum. Large values are therefore retained as reported discrepancies; they are not described as actor appearances unless an explicit appearance field confirms one. Sentinel confirmation count from explicit report fields is 0.

## B1/B2 legacy roots

B1 and B2 remain pinned_legacy_batch roots in the canonical history. B1 uses the frozen first_batch.json queue and stores retained alternates as retained_fallback_identity_sha256; B2 uses the frozen Workstream D queue and has an empty retained identity list. The finalizer’s pinned B1/B2 root verifier checks their queue, owner, ledger, report, review-manifest hashes, and ordered identities. Later B3-B9 records use source-only plans and receipts. Three B1 and all six B2 technical rejections lack a saved stage and remain legacy_unstaged in the failure taxonomy.

## Reproducibility and machine evidence

Machine funnel receipt SHA-256: 8d7e94b5460997c2623ef947d0420cd39229ac50985c4f18882dc0197ee72a68.

Primary candidate index SHA-256: ae68a27920d529e2b67d44e05896c0159debf961ad526e8dcc3244c5fb897bfe.

Fallback/disposition and independence index SHA-256: a420b8518ed9c588e49b4711c574403296b9e613e69f50ef74122d0c23718e21.

Spawn report index SHA-256: a05e60caffc6e789e4baae74456ca7bf067f63e24f826a149b0719de0ab25526.

The [primary candidate index](../../runs/german_200_overnight/v1_final/primary_candidate_index.json), [machine funnel receipt](../../runs/german_200_overnight/v1_final/funnel_receipt.json), [fallback/disposition index](../../runs/german_200_overnight/v1_final/fallback_disposition_independence.json), [spawn report index](../../runs/german_200_overnight/v1_final/spawn_report_index.json), and [original commands](../../runs/german_200_overnight/v1_final/commands.txt) are local machine files in the ignored runs directory. The tracked integration change is this report only; the machine files are not part of the integration diff. Their recorded hashes are unchanged.

To regenerate into a fresh directory from the effective checkout root:

    cd /home/inigo/data/git/repo/student-project/geotransfer-gap-AD
    replay_root="$(mktemp -d /tmp/german_200_v1_final_replay.XXXXXX)"
    PYTHONPATH=src .venv/bin/python runs/german_200_overnight/v1_final/build_v1_final_report.py --evidence-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD --output-dir "$replay_root/runs/german_200_overnight/v1_final" --report-path "$replay_root/docs/audits/german_200_v1_final_yield_report.md"

This reads the pinned canonical history and batch artifacts and calls the existing finalizer retained verifier and runner independence helper. It writes only under the fresh /tmp directory; it does not run native validators, edit source evidence, or change the tracked report.
