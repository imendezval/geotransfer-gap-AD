# Native IDM eligibility evidence v1

`geotransfer_gap.validation.idm_eligibility` produces two additive role records,
one for ego IDM and one for traffic IDM. It runs the real matrix scheduler for
91 observation frames with IDM in both roles, reads back the effective native
movement modes, checks finite dynamics and native routes, and verifies the
actor ID to ego binary-index association. Active VRUs, marked-expert actors,
and other context actors are checked for replay ownership. Background route
intent is recorded separately from the ego's native lane route.

The records import shared technical and task statuses through
`read_shared_admission`. Missing or stale technical evidence remains
`not_established`; unsupported task rules stay in the task gate. A passing
native route proof does not make a task eligible or establish research
admission. Manual decisions are not produced here.

## Protocol identity

The command accepts `idm` and `hybrid_startup` as the shared technical-gate
protocol. It records the actual matrix pair and startup version separately.
For `idm`, the matrix probe uses immediate IDM startup. For `hybrid_startup`,
the matrix probe uses the scheduler's source-hold release protocol. The legacy
`hybrid_startup` gate uses `hybrid_traffic` and is not treated as equivalent to
matrix `source_hold`; compatibility stays `not_established`. The native route
producer is fingerprinted independently. Ego IDM always uses native lane
routing. Background IDM may use the progress-covered source route prior, with
the lane route as fallback. The source prior is never assigned to ego.

Startup release evidence that could not be observed because an actor was
permanently removed is `not_established`, not a performance rejection. Native
collision, goal, and removal data are stored under `run_outcome`; they are not
inputs to model-route eligibility, source selection, or task admission.

## Run

Use a scratch fixture or another read-only scene root, and choose a fresh output
directory outside the scene root and configured artifacts tree:

```bash
GEOTRANSFER_ARTIFACTS="$PWD/artifacts/german_200_v1_workstream_b" \
  .venv/bin/python -m geotransfer_gap.validation.idm_eligibility \
  --root artifacts/german_200_v1_workstream_b/candidate_runs/002_b2d71b77534e9748 \
  --traffic-protocol hybrid_startup \
  --output-dir /tmp/idm-native-proof-002
```

The artifacts-root setting must match the root used when the scene's legacy
technical gate was written so that its path-bound source identity compares
exactly.

The tool refuses to write either versioned record if that filename already
exists in the output directory. Each record binds role, shared source identity,
traffic protocol, technical gate, binary, evaluator INI, native runtime binary
and source digest, controller/scheduler/route/startup producer hashes, native
mode and route checks, and lifecycle observations.

Focused unit coverage is in `tests/test_idm_eligibility.py`. It checks native
route validity, identity association, source-gap route coverage, unsupported
leader evidence, stale fingerprints, and output isolation.
