# Admission stage profiling

This one-sample profile times the four source screens used by the oriented queue, then compares an ordinary hybrid technical admission with a second run using a timer scoped to `admit_scene.subprocess`. Both runs use the same copied scene root. The scoped timer is restored before the harness exits.

The experiment used Python 3.11.18, Lanelet2 1.2.3, BehaviorBench `805fe04c6977b60c41c92c31f1a5211fbd704f44`, and repository HEAD `1f95fd30341a6073398f992c4953b6f1d87d859b`. Scratch roots and reports are under `/tmp/geotransfer-admission-profile-1o5zqize`. The durable per-stage data is in [admission_stage_profile.json](admission_stage_profile.json).

## Results

| Fixture | Queue screen slice | Ordinary gate | Profiled gate | Decision parity | Technical result |
| --- | ---: | ---: | ---: | --- | --- |
| `r15_e332_f25626` | 1.35 s | 14.35 s | 14.28 s | Exact across 9 decision fields | Pass |
| `r00_e321_f21052` | 1.20 s | 15.34 s | 16.55 s | Exact across 9 decision fields | Reject |

Lifecycle traces and the two counterfactual probes took the most wall-clock time. The full gate also reran all four queue source checks. Those repeated checks took 1.40 s on the passing fixture and 1.27 s on the rejected fixture. Rule applicability took roughly 0.91 s and 0.65 s of those totals. These are single serial samples.

`r15_e332_f25626` passed technical admission and remained research-excluded because the hybrid semantic review report is absent. `r00_e321_f21052` failed technical admission at `hybrid_lifecycle`; it also lacked the hybrid semantic review and failed `source_supported_irrelevance_plausible`. Both fixtures passed the four source-screen commands. Their raw rule flags were empty, so the queue did not need optional scope proofs.

The harness recomputed the 31 hashed tool files in the current scene contract before and after each profiled run. The combined inventory hash was unchanged for both. This workstream added the profiling harness and report. Validation source hashes remained unchanged.

## Inputs and current evidence

The passing fixture required a current `source_lane_change_native_oracle.json`. The canonical oracle still records converter fingerprint `b7921aeb4c752b0de4b552efd59ba44e78e7d264c9282a4f1469ffb3df7a1d26`, while the current converter fingerprint is `4cf8f74187dcc5e9884feff7c199fc7d7b3f58b2d98562293790ac77a2fdcb3f`. The profile read the current oracle from `/tmp/geotransfer-scale-native.hoxqKh/artifacts` and copied the two pinned audit reports into its scratch artifact root before timing. It did not regenerate evidence inside the measured gate.

The current oracle file SHA256 is `41357eaf2f5ba5b8cbbad2c91fe05eb4a62e9d38400b43f511ab7dc27a7256e7`. If a future run uses the stale canonical oracle, the route permission check can reject the passing fixture at `legal_lateral_route_permissions_current`.

The native queue probe processed two actor pairs in the same scene across two selection versions. The baseline executed the scene four times. The updated queue executed it twice and reused scene evidence for the second actor in each version. Both runs retained the same four actor/version decisions and left the ledger byte-identical on each warm resume. This fixture stops at source rule screening, so it measures queue overhead and duplicate source work.

## Reproduction

Generate the lane-change oracle in a temporary support tree and copy the existing US parity report into it. Run the profile from the repository root.

```bash
profile_support=$(mktemp -d /tmp/geotransfer-profile-support.XXXXXX)
mkdir -p "$profile_support/audits"
cp artifacts/audits/hybrid_protocol_us_parity.json "$profile_support/audits/"
GEOTRANSFER_ARTIFACTS="$profile_support" .venv/bin/geotransfer check lane-changes
OMP_NUM_THREADS=2 MPLCONFIGDIR=/tmp/geotransfer_mpl \
  .venv/bin/python -m geotransfer_gap.corpus.profile_admission \
  --support-artifacts "$profile_support"
```

The harness creates a new `/tmp` run directory on every invocation. Generated admission reports stay in that run directory.
