# Shared admission and PPO scene role proof

`validation/shared_admission.py` reads the current technical admission without
refreshing it. `build_shared_admission(root, traffic_protocol)` recomputes the
current scene contract and independently checks source-bound manual rule and
task evidence. `write_shared_admission(...)` requires an explicit new output
path and refuses to overwrite a file. `read_shared_admission(root,
traffic_protocol, record_path=None)` returns the same structured statuses; if a
stored versioned record is supplied, it also checks the record type, producer
hash, source identity, technical/manual evidence hashes, and task status.

The shared result separates `shared_validity`, `manual_evidence`, and
`task_eligibility`. A SMART review can contribute source-bound human evidence
only after its scene, rule audit, registration image, task actor, and interaction
digest are checked again. A SMART planner pass is never copied. A rule resolved
as represented in a particular planner blocks shared PPO eligibility; missing,
malformed, or stale evidence stays `not_established`.

Manual prose alone cannot clear the legacy rule audit's applicable stop, yield,
or crosswalk flags. Task eligibility is blocked when the current protocol gate's
`source_supported_irrelevance_plausible` result is false or unknown, with the
gate's named reasons retained. The interaction audit must also match the current
rule audit and selected lifecycle trace hashes before its actor evidence is used.

Use explicit new output paths under an isolated scene copy:

```bash
python -m geotransfer_gap.validation.shared_admission \
  --root /tmp/scene-copy \
  --traffic-protocol hybrid_startup \
  --output /tmp/scene-copy/testing/scene_admission_shared_v1.json

python -m geotransfer_gap.validation.ppo_scene_proof \
  --root /tmp/scene-copy \
  --traffic-protocol hybrid_startup \
  --shared-record /tmp/scene-copy/testing/scene_admission_shared_v1.json \
  --output /tmp/scene-copy/testing/controller_input_ppo_roles_v1.json
```

The PPO proof captures real native `float32[1151]` rows on the expert replay
source timeline and runs the pinned deterministic PPO checkpoint over them.
PPO actions are not applied during this eligibility proof, so planner outcomes
cannot censor reviewed task frames. It records ego and traffic rows separately,
their current native slots and source lifetime masks, partner feature identities,
normalized goal and actor features, road rows matched back to current native map
geometry with the pinned Drive normalization, recurrent state hashes, action
decoding, deterministic replay, and pinned upstream `PPOPlanner` parity.

Each role records its tested pairing explicitly. This probe uses the immediate
startup replay timeline: the tested ego role is PPO observation with both
transition roles owned by expert replay; the tested traffic role has the same
replay owners while PPO observes eligible traffic rows. The controller warmup
and takeover transition remain separately covered by the focused PPO scheduler
tests. `controller_protocol` describes the learned model protocol;
`protocol.status` remains `not_established` until a matching traffic fidelity
record exists. Pair research admission therefore remains unestablished here,
even when observation mechanics and the controller role task gate pass.

Controller role research eligibility also requires every manually reviewed
post-warmup decision step for each claimed task actor to appear in that role's
observed partner rows. A short run can verify mechanics while leaving role
eligibility `not_established`. Collision, goal completion, progress, reward,
and aggregate score are not admission inputs.
