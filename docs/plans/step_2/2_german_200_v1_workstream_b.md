# German-200 v1 first batch: Workstream B results

This report records the first frozen 24-row batch from the mixed-arm German-200
protocol. The input queue is
[`first_batch.json`](../../../artifacts/german_200_v1/first_batch.json), SHA-256
`5af1c9ef57cb57adffbbf54a59cf74ab5181b2347c68ca4282121b9ed5a2c6a0`.
It contains 12 Random100 and 12 Interactive100 rows across all four locations,
including location 2. The interactive arm has three cyclist, four pedestrian,
and five longitudinal candidates. The queue was consumed unchanged; no rows were
selected from admission or rollout results.

## Execution

Each primary candidate was converted into an isolated root under
`artifacts/german_200_v1_workstream_b/candidate_runs/`. The runner verified the
frozen window identity, current track/map/background hashes, exact supported
actor context, and the batch independence rule. The 24 primary windows have
unique identities and no inclusive-window or moving-track conflicts.

Current geometry and physical source audits used the queue's existing criteria:
outside-lanelet ego samples or an unreachable occupied start-to-goal route are
structural geometry failures; ego boundary contact or a non-reviewable source
box overlap is a physical failure. Other suitable rows went through the
unchanged full `admit_scene.py --traffic-protocol hybrid_startup` gate. SMART
rule-applicability flags remain annotations for human review and never exclude
a candidate from that gate.

The run used the fresh native lane-change oracle at
`/tmp/geotransfer-german200-native.boKMec/artifacts/audits/source_lane_change_native_oracle.json`.
It was copied only after its converter/tool fingerprints and current map
coverage were verified. The pinned US mechanics parity report was copied into
the isolated namespace after checking its source, binary, evaluator, runtime,
and hybrid-protocol hashes. The support-copy hashes are in
`artifacts/german_200_v1_workstream_b/source_support_provenance.json`.

For a new replay, use a fresh named output namespace. The original processed
ledger under `artifacts/german_200_v1_workstream_b/` has older producer stamps;
the runner preserves it and asks for a new namespace if those stamps differ.
The following commands replay the frozen first batch into a separate run:

```bash
PYTHONPATH=src OMP_NUM_THREADS=2 python -m geotransfer_gap.corpus.run_german_200_batch \
  --queue artifacts/german_200_v1/first_batch.json \
  --lane-oracle /tmp/geotransfer-german200-native.boKMec/artifacts/audits/source_lane_change_native_oracle.json \
  --output-root artifacts/german_200_v1_runs/replay_first_batch_001 \
  --workers 2

PYTHONPATH=src OMP_NUM_THREADS=2 python -m geotransfer_gap.corpus.finalize_german_200_batch \
  --queue artifacts/german_200_v1/first_batch.json \
  --output-root artifacts/german_200_v1_runs/replay_first_batch_001
```

## Results

The primary batch produced six technical passes, six technical rejections, three
review-blocked rows, seven source-physical rejections, and two source-geometry
rejections. Fifteen candidates reached the full technical gate, so the current
technical pass rate is **6/15 (40%)**. The raw pass fraction over all 24 frozen
rows is **6/24 (25%)**. These are batch-local counts; prior ledgers were not
pooled.

Three gate command failures wrote fresh structured `validate_spawn.py` reports
with `birth_passed: false`; these remain technical rejections, not transient
errors. In the `r17/e290/f19941` report, actor 291 is absent at its source birth
step 3, with `removed: true`, `collision_state: 2`, `cause: offroad`, and no
collided actor. This is candidate evidence and does not justify changing the
shared runtime.

Three otherwise reviewable physical-overlap cases are labelled
`review_blocked`. Their unchanged gate result remains `technical_admitted: false`
because a current physical-overlap review is missing. The run generated source
registration and rule-review images for those cases and did not create a human
review.

Four pre-frozen same-arm/task alternates were tried after primary source
geometry/physical failures, with independence recomputed against retained
primaries and earlier selected alternates. Two were physically rejected, one
failed geometry, and one is review-blocked. None passed the technical gate.
Five structural failures had no eligible prespecified alternate. Including the
one alternate that reached the full gate gives a fallback-adjusted eligible
fraction of **6/16 (37.5%)**; the raw primary 6/24 figure remains separate.

Six primary technical passes await human review:

| Arm | Recording / ego / first frame | Interaction actor |
| --- | --- | --- |
| Random100 | r14 / e232 / f15437 | — |
| Random100 | r12 / e30 / f2957 | — |
| Interactive100 | r14 / e310 / f20146 | 308 |
| Interactive100 | r08 / e93 / f6029 | 95 |
| Interactive100 | r01 / e114 / f7561 | 113 |
| Interactive100 | r13 / e290 / f20235 | 289 |

Each pass has its source image registration and rule-review montage. The
reviewer-facing paths and pending evidence are indexed in
`artifacts/german_200_v1_workstream_b/human_review_manifest.json`. No semantic
or physical review was fabricated, and none of these technical passes is a
research admission.

The machine-readable counts are in
`artifacts/german_200_v1_workstream_b/batch_run_report.json`; the detailed
resumable ledger is `artifacts/german_200_v1_workstream_b/batch_ledger.json`.
`artifacts/german_200_v1/batch_ledger.json` and the prior 50/16 results were not
read as outcome pools or overwritten.
