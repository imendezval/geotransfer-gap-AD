# US source matching pilot preflight

**Decision:** the bounded screen produced five US source task candidates but no defensible US/German pair under the rules frozen before the scan. The existing matrix worker cannot resolve any of the five new US scenario IDs. Stop before any model or native experiment; do not force a pair.

This is a source-only preflight. It ran no training, model inference, simulator, native validator, or download. The reproducible raw scan uses the installed Waymo protobuf with `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` and the repository’s offline binary reader.

## Frozen screen

The scan covered raw record indices 0–127 of the first WOMD validation shard. Indices 0–2 were already inspected by the accepted inventory audit, so they remain in the denominator as parser controls and are excluded from candidate selection. Each later record was joined by `scenario_id` to its validation JSON and then to a binary only through `validation_json_order.csv`; no other shard or replacement record was searched.

Before the scan, the screen froze a 10-sample warmup, steps 10–85 as the scored interval, 0.1 s sampling, the source ego position at step 85 as the goal, a 2 m goal radius, and first goal entry at or after step 75. It limited tasks to source-defined uncontested controls and longitudinal following. Following required a same-path lead, 3–50 m initial physical gap, valid overlap, and a source braking response or stop-and-restart subtype. Control candidates required no same-corridor lead within 30 m, no VRU within 20 m of the path, and no applicable unsupported route control.

The accepted [US availability inventory](../../runs/german_200_overnight/us_inventory/report.md) records 150 local raw shards and 41,828 validation JSON/binary pairs. The raw Scenario supplies source timestamps, `current_time_index`, dynamic map states, and map-feature IDs/types/geometry needed beyond the binary; the binary does not retain source timestamps or dynamic traffic-light states, and the sampled conversion omits some raw map features. The inventory lists the complete raw proto field set and conversion limits.

Pairing required the same task and following subtype; exact geometry class, speed, route-length, curvature, traffic-density bins from the geographic comparison config; exact traffic-composition buckets; and the frozen calipers for speed (2 m/s), route length (25 m), curvature (0.01/m), goal distance (15 m), density (5 actors/km), and following lead/gap features. Relevant ego, lead, and context dimensions had to be causal and bounded within 0.25 m of warmup dimensions. Route-relevant unsupported or omitted map features were exclusions. The complete rules and their pre-scan hash are in the [predeclared protocol](../../runs/german_200_overnight/us_pilot/predeclared_protocol.json), SHA-256 `bc59758645bc9e902d6fc2818ccca3481cda35cb933bf4e28fb75ce0d17f3eba`.

## Scan funnel

| Stage | Count |
| --- | ---: |
| Raw records read from the fixed prefix | 128 |
| Unique scenario IDs | 128 |
| Previously inspected audit records excluded from pilot eligibility | 3 |
| Candidate-range records (indices 3–127) | 125 |
| Records without a local CSV-linked JSON/binary | 9 |
| CSV-linked source records | 116 |
| Linked records without either predeclared task class | 111 |
| US source task candidates | 5 |
| Candidate classes | 3 controls, 2 following |

The five candidate IDs are unique and have five distinct exact route-map signatures. This does not establish distinct WOMD recordings or logs; the local `Scenario` proto has no recording/log ID. None of the five appears in the local `interactive1k` or `random1k` benchmark manifests.

| US source ID (record index) | Task | Speed | Path length | Curvature | Goal distance | Traffic composition / density | Following lead at step 10 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `889ee82248a1d999` (68) | Control | 16.96 m/s | 93.33 m | 0.00052/m | 93.33 m | 0 / 0 / 0; 0 actors/km | — |
| `63f927c014c7b3a6` (102) | Control | 17.46 m/s | 89.27 m | 0.00020/m | 89.27 m | 1 / 0 / 0; 11.20 actors/km | — |
| `8ffa5b454ab8218a` (120) | Control | 0.00 m/s | 24.62 m | 0.05164/m | 22.45 m | 1 / 0 / 0; 40.62 actors/km | — |
| `bc742007c1d78acb` (83) | Following, braking response | 16.12 m/s | 80.96 m | 0.00013/m | 80.96 m | 3 / 0 / 0; 37.05 actors/km | Gap 21.03 m; lead 14.29 m/s; minimum gap 9.13 m |
| `e03a38608d9e19a5` (92) | Following, braking response | 12.44 m/s | 54.00 m | 0.00185/m | 53.99 m | 4 / 0 / 0; 74.07 actors/km | Gap 26.17 m; lead 10.33 m/s; minimum gap 11.94 m |

Traffic vectors list vehicles / pedestrians / cyclists. All five meet the declared goal-entry and time rules. The full 128-row source status and per-actor dimension evidence are in [us_scan.json](../../runs/german_200_overnight/us_pilot/us_scan.json).

## German support and pair result

The frozen 16-scene `current_manifest.json` supplies three uncontested-control labels and four longitudinal-following labels. Existing task-review decisions and each candidate’s converted JSON/binary/source-track hashes were retained. Their source recording IDs are known; the WOMD log IDs are not.

Under the frozen task/support checks, **zero of the three German controls** is a strict control candidate: `r00_e39_f3000` has two governing regulatory elements, two in-horizon crosswalk contacts, and two nearby VRUs; `r09_e196_f16232` has five governing elements, six nearby VRUs, and imputed context dimensions; `r15_e332_f25626` has a same-corridor vehicle within 30 m, nearby VRUs, and imputed context dimensions.

**Zero of the four German following rows** has both an allowed source subtype and the declared initial physical gap. `r00_e321_f21017` is labeled constrained following, not either frozen subtype. The three stop-and-restart rows have initial physical gaps of 1.59, 1.69, and 1.78 m, below the 3 m floor. The five US source task candidates have bounded causal dimensions; five of seven German candidates contain at least one relevant context actor with imputed dimensions under the same corridor rule.

The pairwise machine record enumerates the **17 same-class comparisons** (3×3 controls and 2×4 following). **Zero pairs pass all feature calipers; zero are eligible; no pair was selected.** The closest control feature profile is US `63f927c014c7b3a6` versus German `r00_e39_f3000`: speed and route length are close, and traffic composition/density bins agree, but the German path turns 53.83° while the US path is straight under the frozen 15° class rule; their curvature differs by 0.01057/m, just beyond the 0.01/m caliper. The German row also fails the frozen control support screen. Every US following candidate is a braking-response case; the German labels are one constrained-following and three stop-and-restart cases, and their source speeds and lead gaps do not overlap the US candidates. See [matching_evidence.json](../../runs/german_200_overnight/us_pilot/matching_evidence.json) for all 17 comparisons, exact failure fields, and retained source identities.

## Source, map, physical, and runtime checks

For all five US candidates, raw actor IDs equal JSON and binary actor IDs; all raw/JSON/binary validity masks agree; JSON/binary road ID sets agree. Maximum source-to-binary position residual is 0.000524 m, velocity residual is 0, and heading residual is 1.12×10⁻⁷ rad. None has a route-buffer raw-map feature omitted from its JSON, a route-relevant driveway, or a route-associated traffic signal. The full maps still omit 1–47 raw feature IDs per candidate, but none of those omissions is within the declared 20 m route buffer. Candidate JSON/binary/task dimensions and route-map signatures are recorded in [candidate_triplet_verification.json](../../runs/german_200_overnight/us_pilot/candidate_triplet_verification.json).

The US candidates are source-linked and conversion-consistent, but are **not compatible with an existing worker input route as currently laid out**. `matrix_inputs.py` has an external-WOMD path for only two pinned fixture names and source/binary hashes; none of these candidates matches them. Its generic source-hold path expects a scene root with one `ind_*.json` and `testing/map_000000.bin`; these candidates remain as external WOMD validation JSON/binary files and have no such scene roots. This is a current external source linkage/layout gap. No worker changes or native execution were attempted.

The source inventory records validation-only local WOMD data and no checkpoint source-scenario exposure manifest. Absence from the two benchmark test manifests does not establish that a checkpoint did not train on these scenarios. No geographic, recording-independent, or unseen-US claim is supported.

## Reproduction and machine evidence

The machine outputs and three short source readers are local ignored artifacts under `runs/german_200_overnight/us_pilot/`; only this report is intended for tracking. Run from the repository root using the exact commands in [commands.txt](../../runs/german_200_overnight/us_pilot/commands.txt). The accepted inventory report/parser remain unchanged. The original [machine receipt](../../runs/german_200_overnight/us_pilot/receipt.json) is preserved byte-for-byte. A separately named [documentation-correction receipt](../../runs/german_200_overnight/us_pilot/receipt_doc_correction.json) links this revised report hash to that original receipt.

This screen yielded no pair eligible for a native or model experiment. A future pilot needs a new bounded source screen and an independently reviewed worker source route before any experiment.
