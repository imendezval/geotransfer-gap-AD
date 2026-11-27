# German-200 retention Batch 4

B4 ran from the history-verified 12+12 source-only plan on the unchanged starting revision `cf171507cc220e3fb46f6845f7ac40896e98e827`. Preflight verified all 24 current source identities, the B1–B3 chain and pinned roots, all 24 B3 primary output trees, the native lane-change oracle, and the empty B4 output namespace. The primary runner completed 24/24 rows; finalization attempted the prespecified fallback phase and published B4 once.

## Batch outcomes

| Batch | Technical passes / gate denominator | Raw passes / 24 | Fallback attempts and outcomes | Review manifest entries | Research admitted / gates evaluated | Median primary runtime (s) | Median fallback runtime (s) |
|---|---:|---:|---|---:|---:|---:|---:|
| B1 | 6/15 (0.4000) | 6/24 (0.2500) | 4: 1 review-blocked, 1 geometry rejection, 2 physical rejections | 10 | 0/15 | 20.0 | 6.5 |
| B2 | 4/13 (0.3077) | 4/24 (0.1667) | 2: 2 physical rejections | 7 | 0/13 | 17.7 | 5.4 |
| B3 | 4/16 (0.2500) | 4/24 (0.1667) | 1: 1 physical rejection | 9 | 0/16 | 20.5 | 4.7 |
| B4 | 6/17 (0.3529) | 6/24 (0.2500) | 3: 1 review-blocked, 2 physical rejections | 14 | 0/17 | 19.7 | 6.9 |

B4's final primary status counts are 7 source physical rejections, 7 review-blocked, 6 awaiting human review, and 4 technical rejections. The 6 technical passes are the separately recorded technical-admission result and overlap the awaiting-review category. No fallback passed technical admission. No manual reviews were created. Research admission was false for every primary with a recorded research gate.

The gate denominator is the number of primaries that survived source physical and geometry screening and reached the technical gate. It includes review-blocked rows; it is not a separate eligibility or research-admission claim.

Runtime is the median per-candidate elapsed time from each ledger row's `started_utc` to `completed_utc`; primary and attempted-fallback medians are separate. Concurrent runs mean these medians do not represent total batch wall time. Research figures are admitted candidates over candidates with a recorded research gate. In the table below, `pass` means `technical_admitted=true`; `await/block` and the rejection columns are final ledger statuses. A pass may overlap with awaiting human review.

## Primary outcomes by batch, arm, and site

| Batch | Arm | Site | n | Pass | Await / block | Physical / geometry / technical rejection | Research admitted / gated | Fallback attempts (outcome) | Review entries | Median runtime, primary / fallback (s) |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| B1 | Interactive100 | 1 | 4 | 3 | 3 / 0 | 1 / 0 / 0 | 0 / 3 | 0 | 3 | 19.8 / — |
| B1 | Interactive100 | 2 | 6 | 0 | 0 / 2 | 2 / 1 / 1 | 0 / 3 | 2 (1 blocked, 1 physical) | 3 | 16.2 / 15.7 |
| B1 | Interactive100 | 3 | 1 | 0 | 0 / 0 | 1 / 0 / 0 | 0 / 0 | 0 | 0 | 3.5 / — |
| B1 | Interactive100 | 4 | 1 | 1 | 1 / 0 | 0 / 0 / 0 | 0 / 1 | 0 | 1 | 21.5 / — |
| B1 | Random100 | 1 | 3 | 2 | 2 / 0 | 0 / 0 / 1 | 0 / 3 | 0 | 2 | 20.6 / — |
| B1 | Random100 | 2 | 3 | 0 | 0 / 1 | 2 / 0 / 0 | 0 / 1 | 2 (1 geometry, 1 physical) | 1 | 6.2 / 5.5 |
| B1 | Random100 | 3 | 3 | 0 | 0 / 0 | 1 / 0 / 2 | 0 / 2 | 0 | 0 | 21.3 / — |
| B1 | Random100 | 4 | 3 | 0 | 0 / 0 | 0 / 1 / 2 | 0 / 2 | 0 | 0 | 20.1 / — |
| B2 | Interactive100 | 1 | 3 | 2 | 2 / 0 | 0 / 0 / 1 | 0 / 3 | 0 | 2 | 18.6 / — |
| B2 | Interactive100 | 2 | 9 | 0 | 0 / 2 | 5 / 0 / 2 | 0 / 4 | 0 | 2 | 7.2 / — |
| B2 | Random100 | 1 | 3 | 1 | 1 / 0 | 1 / 0 / 1 | 0 / 2 | 0 | 1 | 17.8 / — |
| B2 | Random100 | 2 | 7 | 0 | 0 / 1 | 4 / 1 / 1 | 0 / 2 | 2 (2 physical) | 1 | 7.3 / 5.4 |
| B2 | Random100 | 4 | 2 | 1 | 1 / 0 | 0 / 0 / 1 | 0 / 2 | 0 | 1 | 18.5 / — |
| B3 | Interactive100 | 2 | 12 | 1 | 1 / 3 | 4 / 0 / 4 | 0 / 8 | 0 | 4 | 23.5 / — |
| B3 | Random100 | 1 | 2 | 1 | 1 / 0 | 0 / 1 / 0 | 0 / 1 | 0 | 1 | 10.4 / — |
| B3 | Random100 | 2 | 5 | 1 | 1 / 2 | 2 / 0 / 0 | 0 / 3 | 1 (1 physical) | 3 | 24.4 / 4.7 |
| B3 | Random100 | 3 | 1 | 0 | 0 / 0 | 0 / 0 / 1 | 0 / 1 | 0 | 0 | 21.4 / — |
| B3 | Random100 | 4 | 4 | 1 | 1 / 0 | 1 / 0 / 2 | 0 / 3 | 0 | 1 | 18.8 / — |
| B4 | Interactive100 | 1 | 1 | 1 | 1 / 0 | 0 / 0 / 0 | 0 / 1 | 0 | 1 | 20.1 / — |
| B4 | Interactive100 | 2 | 11 | 0 | 0 / 5 | 5 / 0 / 1 | 0 / 6 | 2 (1 blocked, 1 physical) | 6 | 22.6 / 16.2 |
| B4 | Random100 | 1 | 5 | 4 | 4 / 0 | 0 / 0 / 1 | 0 / 5 | 0 | 4 | 19.2 / — |
| B4 | Random100 | 2 | 4 | 0 | 0 / 2 | 2 / 0 / 0 | 0 / 2 | 1 (1 physical) | 2 | 15.0 / 6.9 |
| B4 | Random100 | 4 | 3 | 1 | 1 / 0 | 0 / 0 / 2 | 0 / 3 | 0 | 1 | 20.0 / — |

Per-site review entries are grouped by the frozen primary's arm and location. Alternate outcomes are likewise grouped under the primary they replace. These are descriptive batch results; no outcomes are pooled for inference.

## Pooled descriptive view

Across B1–B4 there are 96 primaries: 20 technical passes, 20 awaiting review, 18 review-blocked, 35 source rejections (31 physical and 4 geometry), and 23 technical rejections. Technical passes overlap the awaiting-review status. All 61 rows reaching the technical gate have `research_admitted=false`. The four batches attempted 10 fallbacks: 7 physical rejections, 2 review-blocked, and 1 geometry rejection. The manifests contain 40 review entries, including 20 technical passes, 18 primary review-blockers, and 2 blocked fallbacks.

| Arm | Site | Primaries | Technical passes | Await / block | Source rejections | Technical rejections | Research admitted / gated | Fallback attempts (outcome) | Review entries | Median runtime, primary / fallback (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Interactive100 | 1 | 8 | 6 | 6 / 0 | 1 | 1 | 0 / 7 | 0 | 6 | 19.4 / — |
| Interactive100 | 2 | 38 | 1 | 1 / 12 | 17 | 8 | 0 / 21 | 4 (2 blocked, 2 physical) | 15 | 22.2 / 15.7 |
| Interactive100 | 3 | 1 | 0 | 0 / 0 | 1 | 0 | 0 / 0 | 0 | 0 | 3.5 / — |
| Interactive100 | 4 | 1 | 1 | 1 / 0 | 0 | 0 | 0 / 1 | 0 | 1 | 21.5 / — |
| Random100 | 1 | 13 | 8 | 8 / 0 | 2 | 3 | 0 / 11 | 0 | 8 | 18.8 / — |
| Random100 | 2 | 19 | 1 | 1 / 6 | 11 | 1 | 0 / 8 | 6 (1 geometry, 5 physical) | 7 | 7.3 / 5.4 |
| Random100 | 3 | 4 | 0 | 0 / 0 | 1 | 3 | 0 / 3 | 0 | 0 | 21.3 / — |
| Random100 | 4 | 12 | 3 | 3 / 0 | 2 | 7 | 0 / 10 | 0 | 3 | 19.2 / — |

Site-level manifest entries use each reviewed candidate's frozen location. Fallback counts remain attached to the primary they replace. This pooled view is descriptive only and does not replace each batch's separate denominator.

## Publication and evidence

The prior B1–B3 history prefix was preserved byte for byte: 8,827 bytes, SHA-256 `ee5b4d3cb46c1aa45ee66ef0d80c9c9f572c2f5bb176b700d5b6789d7de61253`. B4 was appended once as record `874dcdd62f06e19878a2d964866619d8fe0d8af9b7581edcfa762f0cf527014d`, directly after the B3 tip `b7f3256a323d4d0b9a5f256346cf55c84297e6b48ada89f5b632f8ebd02ebf6c`. The four-record history now has SHA-256 `860c5a5b1a9e3942fa43be7f1d8c49d738d97139c4ee99ee38e437d3f88d71a2`, and the tip points to B4. The finalizer's existing-record replay exited successfully and verified the B4 record and output trees without adding another history record; all 27 primary/attempted-alternate candidate trees stayed unchanged across the replay.

The ignored run namespace is `artifacts/german_200_v1_runs/workstream_d_batch_004`; it contains the full ledger, native candidate outputs, summary, report, support provenance, and review manifest. The tracked source-only plan and receipt remain under `artifacts/german_200_v1_runs/workstream_d_batch_004_history_verified_plan`.

| Evidence | SHA-256 |
|---|---|
| B4 queue | `e7f6ab3593ce50b9d4e99074e9070f1e045ae5ec3fe0ac6129ced36a1f9fb083` |
| B4 plan | `d671b6ba99eaa3d032b691bf2394e5910fa6562a869b60f40778c23889ad6876` |
| B4 source verification receipt | `2d10112123954c1fb5d41b9e529abaf9e87dbd682c9c1c64bbf89fefecd00ce0` |
| Native lane-change oracle | `41357eaf2f5ba5b8cbbad2c91fe05eb4a62e9d38400b43f511ab7dc27a7256e7` |
| B4 ledger | `b966b91bead60b76e0cf56edb8b21db5bb949efa9c5e584da8fdc031b76fe3f6` |
| B4 run report and summary | `a8c8c0074d53e65b4afc69f700d20ef79ac97f809bba00b251b83b863f837199` |
| B4 review manifest | `57afd2a0edfc8fc693e5b4df3a9ae64f4d002309080177b31df5c1a00a306c3a` |
| B4 source-support provenance | `019dd8f155b0602b57dc33bf209b3afe1d603b7cd87ac4d623e6a0badd07b2db` |
