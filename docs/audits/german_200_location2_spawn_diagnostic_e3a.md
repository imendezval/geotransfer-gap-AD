# Location-2 E3a focused spawn diagnostic

This is a two-case native diagnostic of the saved B5 and B8 dynamics birth failures. It used copies of the candidate `testing` trees and the exact current evaluation configuration. The only instrumentation was an ignored scratch copy of the existing spawn validator; no source actor, production validator, threshold, original artifact, or gate changed. Both expected validator nonpasses were recorded as exit code 1.

Machine evidence is under `runs/german_200_overnight/location2_spawn_diagnostic/run_001/` in the shared repository root. `diagnostic_summary.json` SHA-256: `9778294c72ca8fc9588b51596a76daa8406df0432aac0225f858205129d92279`; `diagnostic_inputs.json` SHA-256: `e1d13739810d8f40a0bd20bc4be0cad8defc99763772bc10ba8460cc892dd5e1`. The summary preserves each selected actor's raw JSON and native state at step 0, birth−1, birth, birth+1, and terminal step 90, plus its birth metrics and saved IDM comparison.

## Findings

| Case / actor | Source birth | Native birth state | Legacy / ego-offset position error | Birth heading / velocity error | Readout |
|---|---|---|---:|---:|---|
| B5 actor 111, cyclist | 62, `[96.12927, -18.60576]` | `[-10000, -10000]`, `valid=0`, `active_agent=0`, no active slot; still sentinel at 63 and 90 | 14,173.574822 / 14,173.574821 m | 2.968469 rad / 5.795781 m/s | Native entity absent/invalid at source-valid birth |
| B8 actor 321, vehicle | 17, `[95.130565, -19.876355]` | `[40.108582, 4.332691]`, `valid=1`, `active_agent=1`, slot 2; moves at 18 and remains valid at 90 | 0.000005789 / 0.000004788 m | 4.31e-8 rad / 3.79e-8 m/s | Successful in this dynamics run |
| B8 actor 322, cyclist | 73, `[70.1849, -36.23277]` | `[-10000, -10000]`, `valid=0`, `active_agent=0`, no active slot; still sentinel at 74 and 90 | 14,144.368434 / 14,144.368435 m | 3.023841 rad / 1.183753 m/s | Native entity absent/invalid at source-valid birth |
| B8 actor 323, cyclist | 89, `[36.85564, -12.88716]` | `[-10000, -10000]`, `valid=0`, `active_agent=0`, no active slot; still sentinel at 90 | 14,137.311241 / 14,137.311242 m | 0.921438 rad / 2.912701 m/s | Native entity absent/invalid at source-valid birth |

For all four actors, the actor-specific zero-step offset and ego zero-step offset differ only at micrometer scale. For example B5 actor 111's offsets are `[54.548844738, -21.449645422]` m and `[54.548846945, -21.449645621]` m. Replacing the actor-specific offset with the ego offset changes its reported error by 0.0000014 m, not 14 km. The equivalent differences for B8 actors 321–323 are also below 0.0000035 m per coordinate.

The large values therefore do **not** measure a physical 14 km separation and are not explained by an origin-offset mistake. At those births the native current-position fields contain the `-10000` invalid-position sentinel and `valid=0`; the Euclidean error is an artifact of applying a distance calculation to an absent/invalid entity. `removed=false` and `collision_state=0` were also observed, so these records do not establish that an instantiated actor was later removed or collided. The strongest supported description is “no valid native entity at the source-valid birth.” The heading and velocity errors for those same invalid states are not meaningful physical errors either.

The native `traj_x/traj_y` arrays contain source-aligned coordinates even for the absent actors. At birth, adding the trusted ego offset to those arrays recovers the source birth positions within 0.0000014–0.0000033 m. This records that the track trajectory is present in the scene data; it does not establish that a valid native actor was spawned. B8 actor 321 provides an in-run comparison: it changes from sentinel/invalid at step 16 to valid and active at birth step 17, with near-zero source-position, heading, and velocity errors.

Saved same-case IDM reports show a mode association: B5 actor 111 passes in IDM (zero position error, heading error `6.08e-8` rad, velocity error `1.15e-7` m/s); B8 actors 321 and 322 are covered by the passing IDM result (maximum position error `5.79e-6` m). The B8 IDM run terminates at step 81, so actor 323's birth at step 89 is untested there. These saved reports make the Dynamics/IDM difference a useful paired observation, but do not identify its mechanism. In B8 dynamics, actor 321 succeeds while both late cyclists remain invalid. Actor type, birth time, mode, and control registration are not independently varied here.

The dynamics runs observed all 91 steps and did not goal-terminate. B5 had no premature appearance, post-exit appearance, or pre-entry event. B8 had the same zero counts; actor 321 moved 0.733493 m at its first step while actors 322 and 323 moved 0 m. These checks do not turn invalid actor fields into valid presence evidence.

## Evidence and reproduction

The native runs used source HEAD `0740dd06a823baad3dc96b5d5aab556d9899d728`; the report is on branch `overnight/location2-spawn-diagnostic`. The unmodified validator source SHA-256 is `fb2a1ff7e6c240623a82ecbd996ac1b1792f7a86d02e18e893acee655ee89e7b`. Runtime source id is `beedf8f1b0e9c490`; loaded runtime binary SHA-256 is `bdf1a2cb70f4153a0283a45fe18920b09a545ecba15fdb335a87a31762b94d58`. The evaluation INI SHA-256 is `afdf157a7b809e31700a49f977c46a7a4913c7e73546a5803d8635a9ae1f5e4e`. Scratch validator SHA-256 is `35052b48e21dbb5a9bcc8c9768d0170447b69ba269e62a9eb65e5d1917f0f7b8`.

The B5 and B8 original `testing` tree hashes remained respectively `23b06dc7abec50ac777ca9a70900a5fcb491c697e77be7aebe4f7aeb75495fc1` and `d3f97ac43690704aef49b12003e5a29a7910ab1fdf45f27b7ce4b1f471146836`. Their saved spawn report hashes and saved validation report hashes were unchanged in both originals and candidate copies. Each copy received only `testing/spawn_diagnostic_instrumented.json`; those outputs hash to `5c8ef1bb5030591ee2e438f886897192a0a3e0e984d91e23a0769f10d4960039` (B5) and `c86268eafc920daf5be5be96af2dfe5d81427990cf0835873d85f0f122241b1d` (B8).

Run each command separately from the diagnostic worktree; return code 1 is the expected validator nonpass. The instrumented script writes only `spawn_diagnostic_instrumented.json` in the candidate copy.

```bash
GEOTRANSFER_PROJECT=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD \
PYTHONPATH=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2-spawn-diagnostic/src \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLCONFIGDIR=/tmp/mpl_location2_spawn \
/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/.venv/bin/python \
/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_spawn_diagnostic/run_001/validate_spawn_instrumented.py \
--root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_spawn_diagnostic/run_001/cases/B5_actor111 --eval-config
```

For B8, use the same command with `--root .../cases/B8_actors321_323`.

## Interpretation and limit

The direct measurement supports a generic **reporting** correction proposal: if native `valid=0` or the position is the sentinel at birth, classify the actor as missing/invalid and do not present sentinel-based position, heading, or velocity deltas as physical errors. Keep the technical nonpass and retain the trajectory/source values separately. This is a reason-code/measurement proposal only; no code was changed.

These two rows do not establish a generic native lifecycle defect or its cause. The paired saved IDM outcomes and B8's actor 321 control suggest mode-sensitive spawn behavior in these cases, but do not justify a simulator fix, threshold change, or gate relaxation. Any broader diagnosis needs an independently reviewed mechanism and a narrowly controlled follow-up.
