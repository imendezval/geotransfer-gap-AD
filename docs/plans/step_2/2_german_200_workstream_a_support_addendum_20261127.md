# Workstream A support addendum — 2026-11-27

This dated addendum resolves the lane-change support binding before any fresh
native execution. It does not change the frozen seven-case cohort, the five
separate overlap cases, task evidence criteria, or traffic protocols.

The original freeze remains byte-identical: [protocol freeze](../../../artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/protocol_freeze_v1.json), SHA-256 `d17c51f88194249621c7210d147ca9205e44f3dd108e93de5a222826585440de`, and [tracked freeze plan](2_german_200_workstream_a_protocol_freeze_v1.md), SHA-256 `0ae5dabf858d1402b939aed10d4c9edc169795fd5962354056871750e4fc6ec9`. The pre-execution attestation was SHA-256 `87553bbd8d9336f49e7f85e74cbf72cac4530e4fefa77bcda466a31cf43679b6` before this addendum. At addendum time, no Workstream A native run had started.

## Validated support

The Batch 4 lane-change oracle at `artifacts/german_200_v1_runs/workstream_d_batch_004/audits/source_lane_change_native_oracle.json` is bound at SHA-256 `41357eaf2f5ba5b8cbbad2c91fe05eb4a62e9d38400b43f511ab7dc27a7256e7`. It passed, and its lane-change tool, integration probe, and converter fingerprints match current files. Its five map hashes cover all five currently configured inD source maps.

The Batch 4 hybrid US mechanics parity artifact at `artifacts/german_200_v1_runs/workstream_d_batch_004/audits/hybrid_protocol_us_parity.json` is bound at SHA-256 `99bc840376f286baeb955e63fd1f88ec6d519157fc2409aecc3744a7dffd838e`. Its mechanical parity is true and its runtime digest (`beedf8f1b0e9c490`), hybrid protocol source, evaluation INI, US source JSON, and US binary hashes match the configured resources.

Exact copies of both reports are staged only under A's own `GEOTRANSFER_ARTIFACTS` root:

- `artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/staged_artifacts/audits/source_lane_change_native_oracle.json`
- `artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/staged_artifacts/audits/hybrid_protocol_us_parity.json`

The machine addendum binds each source and staged hash, producer fingerprints, map coverage, resource locations, and 14 fresh execution copies (406 files): [support addendum JSON](../../../artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/support_addendum_20261127_v1.json), SHA-256 `71af3b1eebffdf11c41ad554bd34ae59bd4b6ac39ceebb4612a972b0ed2171cf`.

## Preserved diagnostics and run identity

The default oracle at `artifacts/audits/source_lane_change_native_oracle.json`, SHA-256 `8ac4e8f50992955533a5652f7e8cdf8f8f788a507a4283c214721ba350e8cf3d`, remains a stale-support diagnostic because its converter fingerprint differs from the current converter. It was not staged or selected. Existing historical outputs inside the first prepared copies remain unchanged; all new execution uses the separately copied tree `artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/executions/current_support_bound_v1/scene_copies/`.

The configured source dataset, BehaviorBench checkout, native runtime, evaluation INI, and interpreter stay those recorded in the original freeze. The execution commands set `GEOTRANSFER_ARTIFACTS` to A's staged support root above. This separates the fresh, support-bound attempt from the historical diagnostics without modifying production source.
