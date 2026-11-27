# Workstream A: German-200 technical reject reproduction freeze

## Freeze status

This protocol was frozen before native execution on 2026-11-27. The selected
cohort is fixed from the tracked A validity matrix, and every historical source
and technical report binding was checked against its archived bytes. Native
runs have not started.

The full source, report, copied-input, and producer bindings are in
[`protocol_freeze_v1.json`](../../../artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/protocol_freeze_v1.json),
SHA-256 `d17c51f88194249621c7210d147ca9205e44f3dd108e93de5a222826585440de`.
The pre-execution attestation records 42/42 current raw source files and 147
hash-bound detailed report files verified, with 14 untouched isolated scene
copies prepared.

## Fixed cohort

The rule is: batch B or C; original verdict `technical_rejection`; source
`passed`; physical `passed`. These seven cases are the entire cohort.

| Candidate | Batch | Recording / ego / first frame | Location / family | Historical hybrid gate SHA-256 |
| --- | --- | --- | --- | --- |
| `Random100-0-ed3193d495c0` | B | 17 / 290 / 19941 | 1 / Random100 | `f2dc5926034d1d1decf075517684a520a914c7b74c5fa9cdbd0c04c8b0f80eeb` |
| `Random100-9-357e0fd2356b` | B | 4 / 101 / 8897 | 4 / Random100 | `bead7b343873555407c44be847a1652e530c8f2ebac19e74874baa7f919e561e` |
| `Random100-10-b80e615825be` | B | 1 / 12 / 590 | 4 / Random100 | `fd5ada11eeda0b728d11fbe3a880307adac6db7c85070642924e812e8f903ef8` |
| `Interactive100-0-a386442265d8` | C | 20 / 200 / 11105 | 2 / longitudinal following | `c06554138f207a91caa164e27d987bdf0276c55df5451881320483e1fef1f23f` |
| `Interactive100-2-4f0aa5c24bfd` | C | 15 / 194 / 14659 | 1 / cyclist crossing | `3dfe752b2944cfdfeef749c9e5edc3290bbd9166c984bd3cbd4e2874fe62566d` |
| `Random100-12-447f18f939e8` | C | 2 / 76 / 3353 | 4 / Random100 | `b821965d002ca5e701117b7d1786ac87eacce003c701c92fc770b28af84d8df5` |
| `Random100-16-33eecbfa0e4f` | C | 17 / 135 / 8619 | 1 / Random100 | `387a4234cfde42bb6c11b9c2502dd44ad9e764381985abcefd2a1626d9a5402d` |

The five `physical=pending_human_review` technical rejects are a separate,
unexecuted overlap cohort: `Random100-7-947545952a10`,
`Random100-8-6be6bc5d7aec`, `Interactive100-16-01096bb714f4`,
`Interactive100-7-e76c43a28531`, and `Random100-18-3e0be3c1a3fe`.

The matrix SHA-256 is
`7288d0b8b59e4d515dcab7624db67890796b225eff80ec96751726437653fcf5`; the
hash-bound detailed matrix SHA-256 is
`87753050eecd7369e6c6e072482f7f21e60901f704c737aae2cedbfe74082099`. Each
row's frozen candidate digest, source-window identity digest, six raw source
hashes, preflight digest, scene-binary digest, old output-tree digest, old gate
digest, and detailed report digests are carried in the JSON freeze.

## Source-defined task evidence fixed before execution

Only two Interactive rows have source-positive task selector evidence. Their
selector events and previously recorded source-box opportunities will be
reported separately from human confirmation and from native actor survival.

| Candidate | Source task / actor | Source event timing | Source encounter evidence |
| --- | --- | --- | --- |
| `Interactive100-0-a386442265d8` | `lead_vehicle_braking_response`, vehicle 198 | selector decision step 20; nearest center sample step 29 | ego speed drop 1.507 m/s; lead speed 0.076 m/s; source oriented-box opportunity at step 30 with 1.966 m gap; goal-radius entry step 81 |
| `Interactive100-2-4f0aa5c24bfd` | `cyclist_crossing`, bicycle 187 | cyclist path crossing step 43; ego path crossing step 62; 1.9 s source crossing-time gap | nearest center sample step 61; source oriented-box opportunity at step 58 with 3.424 m gap; goal-radius entry step 81 |

These are source-selected candidates, not human-confirmed task claims. Both
remain pending human rule/task review. The five Random100 cases declare no task
actor or task evidence. Their suitability remains unestablished even if some
actor is visible or survives a native run.

Task evidence criteria are frozen as follows:

1. Bind the task actor, ego, source event steps, location, and source geometry
   to the frozen queue row and verified source files.
2. Use all-Expert replay as a nonreactive timing and identity control. At a
   task anchor, verify ego and actor source validity, native presence, identity,
   and native movement-mode readback.
3. Keep the legacy matrix probe separate: it uses Expert ego plus immediate IDM
   traffic. Verify task-actor role and owner, mode readback, route when the
   actor is IDM-owned, and presence at the source-defined decision/encounter
   samples.
4. Actor visibility, survival, or traffic fidelity alone cannot pass task
   suitability. The source-defined task event and encounter geometry must be
   present for both ego and actor at the corresponding event interval.
5. Missing human review leaves task semantics and suitability
   `not_established`. No review or admission is generated automatically.

## Runtime and protocol identity

Runs use the configured inD dataset root
`/home/inigo/data/git/repo/student-project/data/levelxdata/inD-dataset-v1.1`,
the clean BehaviorBench checkout at commit
`805fe04c6977b60c41c92c31f1a5211fbd704f44`, and its evaluation INI SHA-256
`afdf157a7b809e31700a49f977c46a7a4913c7e73546a5803d8635a9ae1f5e4e`. The
current isolated native runtime source digest is `beedf8f1b0e9c490`, and its
binary SHA-256 is
`bdf1a2cb70f4153a0283a45fe18920b09a545ecba15fdb335a87a31762b94d58`. No
learned checkpoint or model is involved; the experiment uses Expert replay
and native IDM.

The current hybrid protocol's US mechanics parity report is current for the
source, binary, evaluator INI, native runtime, and `hybrid_traffic.py` producer.
The lane-change oracle covers all three source map hashes and its lane-change
tool hash matches, but its converter fingerprint is stale against the pinned
current converter. The full legacy gate will still be run on copies and its
`legal_lateral_route_permissions_current` and route checks will be reported
explicitly; a technical result cannot be described as supported by a current
lane-change certificate when that check is false.

## Frozen executions

The seven historical candidate roots were copied into separate immediate-IDM
and hybrid-startup namespaces. The source roots remain untouched. Commands run
sequentially with the environment below:

```sh
PYTHONPATH=src OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/geotransfer_mpl \
  .venv/bin/python -m geotransfer_gap.validation.admit_scene \
  --root <immediate-copy> --traffic-protocol idm

PYTHONPATH=src OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/geotransfer_mpl \
  .venv/bin/python -m geotransfer_gap.validation.admit_scene \
  --root <hybrid-copy> --traffic-protocol hybrid_startup

PYTHONPATH=src OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/geotransfer_mpl \
  .venv/bin/python -m geotransfer_gap.validation.idm_traffic_fidelity \
  --root <immediate-copy> --traffic-protocol idm --output <runs-output>
```

Both admission commands refresh an `lifecycle_trace_expert.json` replay
control. The immediate `admit_scene` run is the legacy IDM technical gate. The
separate `idm_traffic_fidelity` record is the exact Expert-ego / IDM-traffic
matrix reference; it does not itself establish task eligibility or admission.
The hybrid command preserves the existing hybrid-startup release protocol and
reports its gate status separately. All evidence and logs will be versioned
under the ignored Workstream A output namespace.
