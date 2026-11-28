# Location-2 E2 offline follow-up

This is a saved-evidence measurement report over the authenticated B1–B9 prefix. It does not run native gates, alter screening, change thresholds, or request a review. Later history is excluded.

Machine evidence: `location2_followup_e2.json` SHA-256 `d0e6c3d48f68f02ef4ef1bf3ed317797f120b84e36cecf8fc26f20a1e5c01ff4`.
Reproduction command: `/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/.venv/bin/python /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2-followup/scripts/location2_followup_e2.py --repo-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2-followup --evidence-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD --output-dir /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_followup_final_v4`

## Denominators and screening outcomes

The nine accepted ledgers contain 200 primary rows and 132 location-2 rows. 31 fallback attempts are separate from those primary denominators (28 at L2); L2 rows by batch: B1 9, B2 16, B3 17, B4 15, B5 21, B6 14, B7 15, B8 19, B9 6.

| Location | Primary rows | Physical rejection | Geometry rejection | Review blocked | Technical rejection | Awaiting review |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 36 | 5 | 1 | 0 | 5 | 25 |
| 2 | 132 | 63 | 6 | 40 | 16 | 7 |
| 3 | 10 | 5 | 0 | 0 | 5 | 0 |
| 4 | 22 | 4 | 1 | 0 | 10 | 7 |

Location groups are descriptive for these selected batches. Differences can reflect batch composition and do not estimate site populations.

## Physical and complexity measurements

Boundary-contact and overlap results below count saved source-geometry findings. A non-reviewable pair marks the saved annotation criterion as unmet; it is not a human physical adjudication. Pair recurrence uses recording plus sorted track IDs, so repeated windows are not independent events.

| Location | N | Boundary-contact cases / N | Pair findings | Non-reviewable | Moving / stationary pair counts | Mean moving actors | Median stationary actors |
|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | 36 | 1 / 36 | 6 | 6 | `{'moving_and_moving': 1, 'moving_and_stationary': 4, 'stationary_and_stationary': 1}` | 8.72 | 5.00 |
| 2 | 132 | 16 / 132 | 336 | 110 | `{'moving_and_moving': 2, 'moving_and_stationary': 64, 'stationary_and_stationary': 270}` | 12.50 | 17.00 |
| 3 | 10 | 1 / 10 | 26 | 6 | `{'moving_and_stationary': 1, 'stationary_and_stationary': 25}` | 10.20 | 8.00 |
| 4 | 22 | 5 / 22 | 0 | 0 | `{}` | 8.23 | 3.00 |

Site distributions reflect only the B1–B9 selected windows. Counts and complexity are correlated with batch, family, and recording composition; they are not site-wide rates. Recording and family quantiles, pair role and motion classes, penetration depth, and sampled occupancy duration remain available in the machine summary.

| L2 batch | N | Boundary-contact cases / N | Overlap pairs | Non-reviewable pairs | Mean moving actors | Mean stationary actors |
|---|---:|---:|---:|---:|---:|---:|
| B1 | 9 | 1 / 9 | 21 | 3 | 14.78 | 17.44 |
| B2 | 16 | 1 / 16 | 46 | 22 | 14.06 | 16.56 |
| B3 | 17 | 2 / 17 | 37 | 8 | 11.88 | 17.00 |
| B4 | 15 | 0 / 15 | 45 | 14 | 11.67 | 18.67 |
| B5 | 21 | 2 / 21 | 43 | 14 | 11.48 | 17.57 |
| B6 | 14 | 3 / 14 | 45 | 15 | 12.21 | 18.14 |
| B7 | 15 | 2 / 15 | 31 | 13 | 11.80 | 15.67 |
| B8 | 19 | 3 / 19 | 54 | 16 | 13.00 | 18.00 |
| B9 | 6 | 2 / 6 | 14 | 5 | 13.17 | 19.50 |

L2 moving actor mean is 12.50 and stationary actor mean is 17.49 over 132 primary rows. Boundary contact appears in 16/132 L2 rows (12.1%); the corresponding saved-row counts are shown for other locations above. Location 4 has 22 rows, while location 3 has 10, so cross-site contrasts are descriptive only.

### Sampled source-versus-converted cases

The representative pair checks align raw CSV rows and tracksMeta dimensions to the hash-bound converted-scene time sample. Center, wrapped heading, dimensions, and oriented-box gap/overlap are direct measurements. They characterize these sampled cases; they do not establish a systemic converter defect.

- `Random100-4-03d7c2db37de` recording 18 pair [15, 16] (stationary_and_stationary; recurrent identity occurrences 8): max center delta 0.000000000 m; max wrapped heading delta 0.000000000 rad; track 15 source [4.765, 2.35167] m → converted [4.765, 2.35167] m; track 16 source [4.15753, 2.34284] m → converted [4.15753, 2.34284] m; source boxes {'overlaps': True, 'penetration_m': 0.00107462, 'oriented_box_gap_m': 0.0}; converted boxes {'overlaps': True, 'penetration_m': 0.00107462, 'oriented_box_gap_m': 0.0}.
- `Random100-5-adca7f68d071` recording 23 pair [28, 420] (moving_and_stationary): max center delta 0.000000000 m; max wrapped heading delta 0.000000000 rad; track 28 source [4.51425, 2.41124] m → converted [4.51425, 2.41124] m; track 420 source [0.0, 0.0] m → converted [0.6, 0.6] m; source boxes {'overlaps': False, 'penetration_m': 0.0, 'oriented_box_gap_m': 0.378959028}; converted boxes {'overlaps': True, 'penetration_m': 0.004725373, 'oriented_box_gap_m': 0.0}.

In the contrast pair, track 420 has source dimensions [0.0, 0.0] m and converts to the pedestrian default [0.6, 0.6] m; at sampled step 4 this changes the computed relation from a 0.379 m gap to a 0.0047 m overlap. This is a direct measurement of the stored zero dimensions and configured fallback behavior, not evidence that a zero-size source box is physical truth or that the fallback is generically wrong.


## Map route representation cases

- `Interactive100-21-d0d1690740f0`: occupied start [1177] to occupied goal [1088] has saved connectivity paths {'1177': None}; nearest-centerline route 1177→1101 has path `[1177, 1187, 1095, 1096, 1097, 1098, 1099, 1100, 1210, 1101]`. Pinned map SHA `4e5b8c1145572d9759aa3ef41426475554b0ca87d1fd8f6bd37237862c462a44`. The two representations answer different geometric queries; neither alone identifies which source representation is semantically preferable.
- `Random100-23-7989a39a8fac`: occupied start [1125] to occupied goal [1209] has saved connectivity paths {'1125': None}; nearest-centerline route 1125→1210 has path `[1125, 1126, 1193, 1095, 1096, 1097, 1098, 1099, 1100, 1210]`. Pinned map SHA `4e5b8c1145572d9759aa3ef41426475554b0ca87d1fd8f6bd37237862c462a44`. The two representations answer different geometric queries; neither alone identifies which source representation is semantically preferable.

## Task proximity, lifecycle, and semantic support

Ego/task distance uses minimum timed center distance from valid hash-bound converted scene positions; it is a measurement, not a gate. Saved trace counts use all primary rows at each location as the availability denominator.

L2 designated-task rows: 87/132; measurable timed-distance rows: 87/132. The per-location values and unavailable reasons are recorded in the machine report.

| Location | Expert traces / N | IDM traces / N | Hybrid traces / N | Hybrid admission reports / N |
|---:|---:|---:|---:|---:|
| 1 | 30 / 36 | 30 / 36 | 30 / 36 | 30 / 36 |
| 2 | 63 / 132 | 63 / 132 | 63 / 132 | 63 / 132 |
| 3 | 5 / 10 | 5 / 10 | 5 / 10 | 5 / 10 |
| 4 | 17 / 22 | 17 / 22 | 17 / 22 | 17 / 22 |

Hybrid failure classifications distinguish lifecycle, source-box, missing-review-artifact, refresh-command, and semantic checks; missing semantic review leaves support unknown. The machine record includes by-location counts and counterfactual lifecycle fields.

## Structured birth failures and hypotheses

Eligibility is explicit as saved-report availability divided by the full primary denominator; a missing trace is unavailable, not a pass. Structured spawn reports and saved lifecycle traces are evidence from prior runs. No native execution occurred during this follow-up.

- `Random100-19-c903e9b6ad29` (B5, status `technical_rejection`): dynamics birth pass `False`, max position error `14173.574821940067` m, late actors `['111']`; IDM birth pass `True`, max position error `0.0` m, observed steps `83`, justified goal terminal `82`, untested post-goal actors `[]`. Saved Expert late-actor samples: 111@62:valid=True,present=True,position_error=0.0 m. Hybrid counterfactual summary `{'expert': True, 'idm': True, 'zero_action_dynamics': True}`; failed checks `['births_and_exits', 'exists:physical_overlap_review.json', 'exists:semantic_review_hybrid_startup.json', 'refresh_commands', 'semantic_screen', 'source_box_overlaps_resolved', 'source_supported_irrelevance_plausible'].` The large dynamics error is consistent with the validator's use of an initial trajectory offset for actors invalid at step 0 interacting with the -10000 invalid-position sentinel, but the saved report omits those exact native operands, so this remains a hypothesis requiring a focused source and dimensions capture.
- `Interactive100-3-2f0dfb373570` (B8, status `technical_rejection`): dynamics birth pass `False`, max position error `14144.36843396168` m, late actors `['321', '322', '323']`; IDM birth pass `True`, max position error `5.788623155209704e-06` m, observed steps `82`, justified goal terminal `81`, untested post-goal actors `[323]`. Saved Expert late-actor samples: 321@17:valid=True,present=True,position_error=5.788623155209704e-06 m; 322@73:valid=True,present=True,position_error=8.409794008627977e-07 m; 323@89:no saved sample (trace ended before birth). Hybrid counterfactual summary `{'expert': True, 'idm': True, 'zero_action_dynamics': True}`; failed checks `['births_and_exits', 'exists:physical_overlap_review.json', 'exists:semantic_review_hybrid_startup.json', 'refresh_commands', 'semantic_screen', 'source_box_overlaps_resolved', 'source_supported_irrelevance_plausible'].` The large dynamics error is consistent with the validator's use of an initial trajectory offset for actors invalid at step 0 interacting with the -10000 invalid-position sentinel, but the saved report omits those exact native operands, so this remains a hypothesis requiring a focused source and dimensions capture.

Automated follow-up should record source and dimension measurements and hypotheses against frozen outputs. Human adjudication is outside this overnight scope. Any code fix remains a proposal pending independent generic-defect review and separability from frozen screening.

## Reproduction and evidence

The E2 reader SHA is `83d6a98f16fa28bc2c3282f7bcb60942487beabed46befa3f02768f4e339e97d`. It authenticates B1–B9 retention record digests, chain links, ordered identities, ledger hashes, queue/source queue/receipt/plan/manifest/owner/report/summary hashes where recorded, the B9 accepted digest `05d898b174bccaebab6a1a804344e69d4eadef082254ad425a713530085c9aa6`, and the exact existing producer SHA `e53a1733f8732043442cbfeccf1d0e14c6eaa650773c6394589029c8e6d36abb`. The actual source checkout HEAD at run time was `21453b724a697e5ca387e12b81f777f8212342eb` and is recorded as incidental provenance.

The preserved E1 artifact SHA `d969088279f96ef188a97d3d6c18d3f6540dd02d9b7e1dc9a653b7b2c69b6593` was unchanged. Re-reading the B1–B4 L2 rows reproduced all 57 identity keys, all listed stable case fields, and all 23 stable E1 summary sections with zero differences.

## Focused follow-up measurements

1. For B5 actor 111 and B8 actors 321–323, preserve the saved Expert/IDM/hybrid traces and capture each actor's source scene position at step 0, validity at step 0, native initial traj_x/traj_y, computed origin offset, native birth state, and expected source position at birth. The overnight summary supports the sentinel-offset hypothesis but does not expose these operands.
2. Compare the captured offset with the existing spawn check's transformed native position on both rows, then run a diagnostic-only reproduction on a fresh candidate copy. Keep the frozen technical screen and thresholds unchanged; any proposed correction needs independent generic-defect review before it can be separated from screening.
3. For track 420 in recording 23, measure source dimension validity, selected fallback dimensions, and source/converted box gap over the full overlap sample set. The current sample shows a zero-dimension metadata value and a one-step geometry change; this does not determine the intended physical dimension.
4. For both route representation cases, retain the exact pinned map and occupancy lanelet IDs and compare occupied polygon and nearest-centerline directed paths in a dedicated map diagnostic. The current connectivity paths are direct saved-scene measurements, not a semantic adjudication.

Command: `/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/.venv/bin/python /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2-followup/scripts/location2_followup_e2.py --repo-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2-followup --evidence-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD --output-dir /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_followup_final_v4`

Output SHA-256: `d0e6c3d48f68f02ef4ef1bf3ed317797f120b84e36cecf8fc26f20a1e5c01ff4`
