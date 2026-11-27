# Workstream A — German-200 technical reject reproduction (A4)

## Result

The frozen seven-case cohort was reproduced with the current, hash-verified
lane-change support. The legacy immediate-IDM gate is technically admitted on
2/7 cases (`Interactive100-0…` and `Random100-16…`); the other five fail. The
hybrid-startup gate is technically admitted on 0/7. The separate
Expert-ego/immediate-IDM fidelity probe is `current` on 7/7, while its task view
is `not_established` on 7/7 because no current human task identity is bound.
Research admission is **0/7**, reported separately from suitability.

**Suitability count: 0 confirmed suitable; 7 not established.** A technical
gate pass does not establish a reviewed task claim. The two Interactive rows
have source-positive selector evidence; their runtime encounter evidence is
reported below, while human rule/task review remains absent. The five Random
rows have no prespecified source task actor or encounter evidence.

## Freeze, support, and execution identity

The cohort is exactly the seven B/C records selected by the tracked A
validity-matrix rule `original=technical_rejection`, `source=passed`,
`physical=passed`. The original freeze remains unchanged: [frozen protocol
plan](2_german_200_workstream_a_protocol_freeze_v1.md), SHA-256
`0ae5dabf858d1402b939aed10d4c9edc169795fd5962354056871750e4fc6ec9`, and
[freeze JSON](../../../artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/protocol_freeze_v1.json),
SHA-256 `d17c51f88194249621c7210d147ca9205e44f3dd108e93de5a222826585440de`.
It binds candidate/source identities, six raw source files per scene, old
gate and output-tree hashes, and the 147 hash-bound historical detail reports.

Before native execution, the dated [support addendum](2_german_200_workstream_a_support_addendum_20261127.md)
resolved the stale-default-oracle confound without changing the freeze. The
Batch 4 lane-change oracle SHA-256 is
`41357eaf2f5ba5b8cbbad2c91fe05eb4a62e9d38400b43f511ab7dc27a7256e7`; its
current lane tool, integration probe, converter fingerprint, and all five
configured source-map hashes match. The Batch 4 hybrid mechanics parity
artifact SHA-256 is
`99bc840376f286baeb955e63fd1f88ec6d519157fc2409aecc3744a7dffd838e`; its
runtime, protocol, evaluation INI, US source, and US binary bindings match.
Exact copies were staged only under A's `GEOTRANSFER_ARTIFACTS` root. The
default oracle (`8ac4e8f5…`) remains a stale-converter diagnostic and was not
used.

Runs used the configured inD dataset and clean BehaviorBench commit
`805fe04c6977b60c41c92c31f1a5211fbd704f44`, Python
`.venv/bin/python` 3.11.18, evaluation INI SHA-256
`afdf157a7b809e31700a49f977c46a7a4913c7e73546a5803d8635a9ae1f5e4e`, native
runtime source digest `beedf8f1b0e9c490`, and runtime binary SHA-256
`bdf1a2cb70f4153a0283a45fe18920b09a545ecba15fdb335a87a31762b94d58`. No
learned model or checkpoint was used. Current producer fingerprints and
configured paths are in the machine summary.

The new native attempt used 14 separate execution copies (406 files) under
`executions/current_support_bound_v1`; the original prepared copies and their
historical outputs remain intact. There are 21 recorded commands: seven full
`admit_scene --traffic-protocol idm` gates, seven `idm_traffic_fidelity
--traffic-protocol idm` Expert-ego/IDM matrix probes, and seven full
`admit_scene --traffic-protocol hybrid_startup` gates. Each gate refreshed an
all-Expert lifecycle replay control. Exact argv, environment overrides, exit
codes, stdout/stderr hashes, report hashes, and changed-file hashes are in the
[run manifest](../../../artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/machine_outcomes/native_current_v1/run_manifest.json),
SHA-256 `9e6f1689e95518a52856bccdbc8f078d1055ab20ce788e2b8f56850a3b3f47e8`.
Full per-case extraction is in [summary JSON](../../../artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/machine_outcomes/native_current_v1/summary_v1.json),
SHA-256 `d833c2e925be7b42c4c5fa461228a1cc22930eafe82b8872c72a5c84d84d8a56`.

The first driver launch stopped with a wrapper `NameError` before invoking any
native subcommand. It was recorded with stdout/stderr hashes, corrected, and
followed by the 21 planned probe launches: [bootstrap diagnostic](../../../artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/machine_outcomes/bootstrap_failure_20261127_0443/record.json).
No production source was edited for this workstream.

## A4 case table

`Current matrix` means protocol/runtime fidelity status, not scene admission.
`Task view NE` means task view `not_established` with reason
`current_manual_task_identity_missing`. The per-protocol event details and
full failed-check lists are hash-bound in the machine summary.
All seven frozen rows have `source=passed` and `physical=passed` in the tracked
validity matrix.

| Candidate (batch; recording / ego; location) | Expert reference | Legacy immediate IDM | Expert-ego + IDM matrix | Hybrid startup | Native births and lifecycle signal | Task suitability |
| --- | --- | --- | --- | --- | --- | --- |
| `Random100-0-ed3193d495c0` (B; 17 / 290; L1) | Pass; 84 observed steps, goal marker@83 | **Fail** — `births_and_exits`, `counterfactual_lifecycle`; refresh fails at spawn validation | Current; task view NE | **Fail** — birth, lifecycle, hybrid checks | Late births 291@3, 292@36, 293@40, 294@74; actor 291 removed offroad@3; no collision pair | Not established; no prespecified task |
| `Random100-10-b80e615825be` (B; 1 / 12; L4) | Pass; 78 observed steps, goal marker@77 | **Fail** — `births_and_exits`, `counterfactual_lifecycle`; refresh fails at spawn validation | Current; task view NE | **Fail** — birth, lifecycle, hybrid checks | Late births 13@7, 14@39, 15@56, 16@83; actor 13 removed offroad@7; no collision pair | Not established; no prespecified task |
| `Random100-9-357e0fd2356b` (B; 4 / 101; L4) | Pass; 85 observed steps, goal marker@84 | **Fail** — `births_and_exits`, `counterfactual_lifecycle`; refresh fails at spawn validation | Current; task view NE | **Fail** — birth, lifecycle, hybrid checks | Late births 109@10, 110@53; actors 108 removed offroad@1 and 109@10; no collision pair | Not established; no prespecified task |
| `Interactive100-0-a386442265d8` (C; 20 / 200; L2) | Pass; 82 observed steps, goal marker@81 | **Pass technical**; research admission fails for missing review/semantic support | Current; task view NE | **Fail** — hybrid counterfactual and research checks | Late cyclist 205@49; no non-goal loss/collision; ego goal marker@81 | Not established; lead-vehicle encounter geometry is not preserved under IDM |
| `Interactive100-2-4f0aa5c24bfd` (C; 15 / 194; L1) | Pass; 82 observed steps, goal marker@81 | **Fail** — counterfactual lifecycle; research review also absent | Current; task view NE | **Fail** — counterfactual and hybrid lifecycle checks | Late pedestrian 200@32; actor 199 removed offroad@1; no collision pair | Not established; source encounter geometry is preserved by replay-owned cyclist, but task review is absent |
| `Random100-12-447f18f939e8` (C; 2 / 76; L4) | Pass; 84 observed steps, goal marker@83 | **Fail** — counterfactual lifecycle; research review also absent | Current; task view NE | **Fail** — counterfactual checks | Late births 77@2, 78@39, 79@40; no non-goal removal/collision pair | Not established; no prespecified task |
| `Random100-16-33eecbfa0e4f` (C; 17 / 135; L1) | Pass; 83 observed steps, goal marker@82 | **Pass technical**; research admission fails for missing review/semantic support | Current; task view NE | **Fail** — hybrid lifecycle | Late births 136@36, 137@58, 138@76; one ego–background collision pair at step 36 (details below) | Not established; no prespecified task |

All seven immediate-IDM reports say `research_admitted=false`. The current
lateral-permission check is true in all 14 fresh gate reports, and hybrid US
mechanical parity is true in all seven hybrid reports. No human review,
semantic review, or admission was generated automatically. The five pending
overlap rejects stayed outside this cohort and were not executed:
`Random100-7-947545952a10`, `Random100-8-6be6bc5d7aec`,
`Interactive100-16-01096bb714f4`, `Interactive100-7-e76c43a28531`, and
`Random100-18-3e0be3c1a3fe`.

The machine summary also retains each trace's source-valid losses/goal exits,
first removal per actor, collision pairs, reset markers, and observed horizon
for Expert replay, immediate IDM, and hybrid startup. The table highlights
late births and non-goal removals/collisions.

## Interactive source events and runtime geometry

The source steps below are relative to each 91-step scene window at 0.1 s per
step. Coordinates are source-local metres. Selector evidence is source-positive
but is not a human task confirmation.

### Lead vehicle braking response — actor 198, ego 200, location 2

The source selector binds the decision to step 20 (2.0 s): ego speed drops
1.507 m/s and lead speed is 0.076 m/s. The nearest source centres are at step
29 (2.9 s), 6.993 m apart. The source oriented-box opportunity is at step 30
(3.0 s), with 1.966 m gap; source centres are ego `(37.851, -32.859)` and
lead `(44.710, -31.489)`.

The Expert replay control has both source-valid actors present in Expert Replay
mode 2 at steps 20, 29, and 30. Under the fresh immediate-IDM lifecycle
diagnostic, the lead is present but reads native mode 1 (IDM). At step 30 its
position error is 5.907 m, oriented-box gap 7.849 m, and speed 3.726 m/s,
against source gap 1.966 m and source speed 0.728 m/s. Only 3 of 63 source-close
steps match; the IDM audit says `preserved_for_claimed_interaction=false`.
Actor survival therefore does not preserve the braking encounter. The matrix
task view remains not established because current human task identity is
missing.

### Cyclist crossing — actor 187, ego 194, location 1

The source-positive selector records cyclist path crossing at step 43
(4.3 s), ego path crossing at step 62 (6.2 s), and a 1.9 s crossing-time gap.
The closest source centres are at step 61 (6.1 s), 6.693 m apart. The source
oriented-box opportunity is step 58 (5.8 s), with 3.424 m gap. At step 58 the
source centres are cyclist `(55.878, -34.874)` and ego `(52.781, -28.873)`;
at step 62 they are `(56.063, -35.722)` and `(54.074, -29.306)`.

In the **legacy lifecycle trace named `idm`**, both actors are present and
source-valid at steps 43, 58, 61, and 62. The ego reads mode 2; the cyclist's
raw native movement-mode enum reads `0` (the `DYNAMICS` bit). Across those
samples, both ego and cyclist positions match source within 0.0000036 m, with
speed and heading matching to stored precision. At step 58 the cyclist speed is
2.191 m/s and the measured oriented-box gap is 3.424 m; the audit matches all
25/25 source-close steps. This is a measured replay-geometry diagnostic, not
reactive cyclist resolution. The raw mode names and enum values are in
[`native_modes.py`](../../../src/geotransfer_gap/runtime/native_modes.py#L6),
and the all-background mode assignment for this lifecycle trace is in
[`trace_eval_lifecycle.py`](../../../src/geotransfer_gap/validation/trace_eval_lifecycle.py#L65).

The separate **Expert-ego/IDM matrix probe** is not the same actor-mode record:
its per-role scheduler expects an IDM-owned traffic actor to use mode 1 and a
reviewed context actor to use Expert Replay mode 2. The role rule is in
[`idm_traffic_fidelity.py`](../../../src/geotransfer_gap/validation/idm_traffic_fidelity.py#L95)
and context replay assignment is in
[`scheduler.py`](../../../src/geotransfer_gap/runtime/scheduler.py#L390).
The probe is current overall, but no reviewed task identity assigns cyclist
187 to a task role, so its task view has no actor-specific result and remains
not established. Source/runtime geometry agreement does not substitute for
that review.

## Random16 collision scope and gate result

`Random100-16-33eecbfa0e4f` has **one ego–background collision pair** in the
separate 91-step immediate-IDM lifecycle trace, at step 36 (3.6 s):

- Ego vehicle source ID 135, binary index 0: native mode 2 (Expert Replay),
  collision state code 1, removed, `collided_with_index=11`.
- Background vehicle source ID 133, binary index 11: native mode 1 (IDM),
  collision state code 1, removed, `collided_with_index=0`.

These are two actor records for one pair event. `admission.json` nevertheless
reports `technical_admitted=true`: `births_and_exits=true` and the checked
`counterfactual_lifecycle=true` (Expert and IDM modes pass; zero-action
dynamics is a false diagnostic). The legacy gate does not consume this separate
`lifecycle_trace_idm.json` collision record and has no check requiring this
trace to be collision-free. Its research admission remains false because
semantic review and source-supported-irrelevance evidence are absent. The
technical calculation includes all checks outside the research-only set, as
shown in [`admit_scene.py`](../../../src/geotransfer_gap/validation/admit_scene.py#L1033).
The technical pass is not a collision-free or task-suitability claim.

## Machine evidence

The report values above are extracted from the hash-bound [machine summary](../../../artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/machine_outcomes/native_current_v1/summary_v1.json)
and [21-command manifest](../../../artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/machine_outcomes/native_current_v1/run_manifest.json).
The manifest preserves exact commands, environment overrides, outputs, and
per-command hashes. The raw command logs and every fresh scene report remain
under `artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/`.
