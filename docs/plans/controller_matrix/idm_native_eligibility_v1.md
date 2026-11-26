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

## IDM/IDM immediate pair

`idm_traffic_fidelity` writes a separate versioned traffic-protocol record for
the IDM traffic side. It checks native IDM intent and mode readback, route
validity, startup semantics, identity, and lifecycle. Its task-preservation
view uses Expert reference ego replay with IDM traffic, and records pre-step
source ownership/presence at the manually reviewed decision and actor-context
steps. Missing manual review stays `not_established` independently of live
traffic mechanics. The producer does not use rollout outcomes.

`idm_pair_admission` derives the IDM ego + IDM traffic immediate pair gate from
current shared, role, and traffic-fidelity records. It rechecks their hashes,
scene/runtime binding, concrete startup and native-protocol payload, and exact
task actor/context coverage. A current role or fidelity status string by itself
does not pass the gate. The derived record does not use collision, goal, or
other performance outcomes for admission.

The historical `hybrid_startup` input runs matrix source-hold mechanics for
diagnostics, but its `protocol_compatibility` remains `not_established`: the
legacy hybrid startup gate is not proof of matrix source-hold equivalence.
Source-prior fields describe the trajectory coverage/applicability guard and
its route-source classification. They do not independently establish that
native Drive used that source trajectory as route ancestry.

Run the three producers with a current shared record and fresh output paths:

```bash
GEOTRANSFER_ARTIFACTS="$PWD/artifacts/german_200_v1_workstream_b" \
  .venv/bin/python -m geotransfer_gap.validation.idm_eligibility \
  --root artifacts/german_200_v1_workstream_b/candidate_runs/002_b2d71b77534e9748 \
  --traffic-protocol idm --shared-record /path/to/scene_admission_shared_v1.json \
  --output-dir /tmp/idm-role-evidence

GEOTRANSFER_ARTIFACTS="$PWD/artifacts/german_200_v1_workstream_b" \
  .venv/bin/python -m geotransfer_gap.validation.idm_traffic_fidelity \
  --root artifacts/german_200_v1_workstream_b/candidate_runs/002_b2d71b77534e9748 \
  --traffic-protocol idm --shared-record /path/to/scene_admission_shared_v1.json \
  --output /tmp/idm-role-evidence/traffic_protocol_idm_immediate_v1.json

GEOTRANSFER_ARTIFACTS="$PWD/artifacts/german_200_v1_workstream_b" \
  .venv/bin/python -m geotransfer_gap.validation.idm_pair_admission \
  --root artifacts/german_200_v1_workstream_b/candidate_runs/002_b2d71b77534e9748 \
  --shared-record /path/to/scene_admission_shared_v1.json \
  --ego-record /tmp/idm-role-evidence/controller_input_idm_ego_v1.json \
  --traffic-record /tmp/idm-role-evidence/controller_input_idm_traffic_v1.json \
  --traffic-fidelity-record /tmp/idm-role-evidence/traffic_protocol_idm_immediate_v1.json \
  --output /tmp/idm-role-evidence/pair_admission.json
```

## Protocol identity

The command accepts `idm` and `hybrid_startup` as the shared technical-gate
protocol. It records the actual matrix pair and startup version separately.
For `idm`, the matrix probe uses immediate IDM startup. For `hybrid_startup`,
the matrix probe uses the scheduler's source-hold release protocol. The legacy
`hybrid_startup` gate uses `hybrid_traffic` and is not treated as equivalent to
matrix `source_hold`; compatibility stays `not_established`. The native route
producer is fingerprinted independently. Ego IDM always uses native lane
routing. Background IDM may use the progress-covered source route prior, with
the lane route as fallback. That source-prior label reports the trajectory
coverage/applicability guard, not independently observed native route ancestry.
The source prior is never assigned to ego.

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
  --traffic-protocol idm \
  --shared-record /path/to/scene_admission_shared_v1.json \
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

## Exercised fixture

The native pipeline was run on an isolated copy of recording 2, ego track 347,
with the verified five-map lane-change oracle. `admit_scene --traffic-protocol
idm` established the technical gate; both IDM role controller-input records
and reference-ego traffic mechanics were current. Pair admission remained
`not_established` because current manual task evidence and linked task-view
evidence were absent. Research admission also remained unestablished because
the semantic review was missing and a source-supported irrelevance conflict
remained. The copied records, exact hashes, and executed commands are in the
[oracle-enabled verification report](../../../runs/german_200_hardening_v1_verification/idm_pair/oracle_enabled/README.md).

Focused unit coverage is in `tests/test_idm_eligibility.py` and
`tests/test_idm_pair_admission.py`. The pair tests cover missing/stale
evidence, startup and role mismatches, concrete fidelity payload validation,
task actor/context coverage, and outcome independence.
