# Location-2 spawn reporting projection v2

This experimental change adds a versioned physical readout to the existing spawn validator. It classifies each observed source-valid late birth as `valid_native_position` or `missing_invalid_native_state`. A native `valid=0`, the `-10000` position sentinel, an unavailable position, or a nonfinite position makes the state missing/invalid. Such rows carry the reason and false metric-support flags, without position, heading, velocity, or collision-channel values or deltas. Valid states retain position, wrapped-heading, and velocity error support counts; their position metric uses the existing actor-zero-step offset for direct comparability.

The historical raw numeric fields and the `birth_passed`/overall return-code predicate remain unchanged. The legacy maxima can still contain sentinel-derived numbers by design in this comparison version. The new projection is the physical readout and excludes those numbers when native state is invalid. It changes neither the native simulation nor any thresholds or gates. Use `--report-output` to save this report under a new filename; without that option the validator keeps its existing default output path.

## E3a replay note

Replays should start from fresh copies of each candidate testing tree and write to a new report path. The independent E3a replay matched native presence/validity, trajectory XY, offsets, coverage, and the large position-error fields. Raw fields from invalid/dormant states were not stable: heading and collision coordinates varied while `collision_state=0`. An E3a B5 replay also changed the unsupported invalid-state heading delta from `2.968468907` to `2.968479769` rad, with the same missing actor and nonpass. Do not interpret those heading or collision-channel values. The v2 projection drops them from invalid rows and keeps the legacy fields only for reproducibility.

## Focused reproduction

Both commands ran the current validator from this branch against fresh copies under `runs/german_200_overnight/location2_spawn_reporting_v2`. Each returned exit code 1 because Dynamics remained nonpassing; the report still records the passing IDM mode. The original saved spawn reports and validation reports remained byte-identical in the copies, and the original candidate trees were unchanged.

```bash
GEOTRANSFER_PROJECT=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD \
PYTHONPATH=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2-spawn-reporting-v2/src \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLCONFIGDIR=/tmp/mpl_location2_spawn_reporting_v2 \
/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/.venv/bin/python \
/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2-spawn-reporting-v2/src/geotransfer_gap/validation/validate_spawn.py \
--root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_spawn_reporting_v2/cases/B5_actor111 \
--eval-config \
--report-output /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_spawn_reporting_v2/cases/B5_actor111/testing/spawn_evaluation_validation_v2.json
```

The B8 command was:

```bash
GEOTRANSFER_PROJECT=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD \
PYTHONPATH=/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2-spawn-reporting-v2/src \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLCONFIGDIR=/tmp/mpl_location2_spawn_reporting_v2 \
/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/.venv/bin/python \
/home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2-spawn-reporting-v2/src/geotransfer_gap/validation/validate_spawn.py \
--root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_spawn_reporting_v2/cases/B8_actors321_323 \
--eval-config \
--report-output /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_spawn_reporting_v2/cases/B8_actors321_323/testing/spawn_evaluation_validation_v2.json
```

Full command strings and exact input fingerprints are also in `runs/german_200_overnight/location2_spawn_reporting_v2/inputs.json`.

| Case / mode | Input / observed / unobserved births | Valid native position / missing-invalid | Position / heading / velocity metric support | `birth_passed` |
|---|---:|---:|---:|---|
| B5 Dynamics | 1 / 1 / 0 | 0 / 1 | 0 / 0 / 0 | false |
| B5 IDM | 1 / 1 / 0 | 1 / 0 | 1 / 1 / 1 | true |
| B8 Dynamics | 3 / 3 / 0 | 1 / 2 | 1 / 1 / 1 | false |
| B8 IDM | 3 / 2 / 1 | 2 / 0 | 2 / 2 / 2 | true |

The three dynamics births B5 actor 111 and B8 actors 322–323 are explicitly missing/invalid. B8 actor 321 has a valid native position and supported metrics in Dynamics. IDM confirms a valid state for B5 actor 111 and B8 actors 321–322. B8 actor 323 is listed as unobserved in IDM because goal termination occurs at step 81, before its source birth at step 89. The mode outcomes match the existing saved reports: both Dynamics checks fail and both IDM checks pass.

Legacy position maxima are unchanged: B5 Dynamics `14173.574821940067` m; B8 Dynamics `14144.36843396168` m. The new readout does not expose either number as a physical delta for its invalid actor rows. Existing heading/velocity maxima remain for comparability and are not interpreted for invalid rows.

## Tests and fingerprints

Focused regression command:

```bash
PYTHONPATH=src /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/.venv/bin/python -m pytest -q tests/test_spawn_reporting.py
```

Result: `4 passed`. Tests cover valid metric calculation, native validity false, sentinel positions despite a true validity flag, omission of collision/pose values for invalid rows, and birth denominator consistency. `py_compile` and `git diff --check` also passed.

Machine receipt `reporting_v2_evidence.json` SHA-256: `3da6b96ba4ac663da6f1d0d5778a7b8379f8074307f9738ad41bd5651c98034e`. Input and exact-command receipt `inputs.json` SHA-256: `ef311db390f98b3bfc141163888b966375dff5d77f844598120d628403a3f127`.

| File | SHA-256 |
|---|---|
| `src/geotransfer_gap/validation/validate_spawn.py` | `14636993a50de0f22f3e32806dd1cb2be5a0e977b2379840a7d2516253d9fd87` |
| `src/geotransfer_gap/validation/spawn_reporting.py` | `2815c908c207d7f2ed586922b5c673fe5dd63401ebd21e216add49659437aa6f` |
| `tests/test_spawn_reporting.py` | `2d0e24a7e9ca47355aed61fe130bc1e1b8c6f0f82c9819be7b26b70d57532a29` |
| B5 v2 report | `963caf193fdfcb5ce0877633e00fef71648a54d5f598cf0fb99eebf19ae23ea0` |
| B8 v2 report | `a10cad12f78a094f609265bf776d5f12d5e51e718fb4cbfad4e27a6299418f9b` |

The run used evaluation INI SHA-256 `afdf157a7b809e31700a49f977c46a7a4913c7e73546a5803d8635a9ae1f5e4e` and runtime source id `beedf8f1b0e9c490`. This is an experimental reporting change for independent review; no lifecycle repair is proposed.
