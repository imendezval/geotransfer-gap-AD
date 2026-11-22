# SMART protocol pilot within Step 2

The parent plan remains `2_admissible_scene_set.md`. This pilot must satisfy its fidelity, rule review, provenance, and persistence requirements; it does not replace the 10/50-scene milestones.

1. **Verify SMART scene input.** Require stable binary actor identities; current positions, headings, dimensions and classes for every present vehicle/VRU/expert; dormant/exited actors absent from model input at prediction refresh; causal history; source crosswalk geometry preserved through binary and actual SMART tokens. Exercise both planning entrypoints, source replay, perturbed ego state and policy control. Use identical adapter, checkpoint, tokenizer, history and traffic rules on a German interaction and a US scene. Record hashes and tolerances. A finite action alone is insufficient.
2. **Admit one interaction scene.** Require a current full technical gate, source-image and decision review, a resolution for every inventoried sign/priority/crosswalk/boundary/marking, and a planner-specific gate proving applicable semantics and actors reach SMART. Exclude unresolved rules. Check missing/stale evidence fails closed. A policy collision is a diagnostic outcome rather than an automatic conversion failure; source fidelity and task fairness determine admission.
3. **Apply the fixed process to a small batch.** Select before examining policy outcomes: one source pedestrian crossing, one following scene, one turn/control and one candidate from another location. Keep all exclusions and test the same input/admission protocol. Report independent counts and interaction/site coverage; do not select based on SMART success. Use failures to diagnose general limitations before expanding the corpus.

Continue after failed candidates while an independent pilot avenue remains. Stop for user intervention only for a genuine blocker preventing all three avenues.

## Frozen protocol and acceptance standards

- Input identity/presence/class must match source-valid actors, including expert vehicles, pedestrians and cyclists. Inverse source position, evaluator-local position, heading and dimension errors must be below 0.01 m/rad; map inverse position must be below 0.01 m. Check both lifecycle transitions and actual prediction refreshes, not just finite actions.
- Use one shared evaluator-centered frame for SMART map and actors on German and US inputs. A negative-world US regression must retain surrounding actors. Source-valid re-entry must work; physics-removed collision actors must remain removed even across a later source mask gap.
- Use 10 genuinely observed expert warmup steps, 11 history samples, dt=0.1 s, a prediction every 5 steps, greedy CPU inference and seed 0. Future source mutations must not affect reset input. Freeze goal radius at 2 m and goal speed threshold at 20 m/s. This is the pilot protocol, not a claim of full upstream training equivalence.
- Provider aerial projection is fixed from the official inD visualization convention: scale `12*orthoPxToMeter`, zero translation. Fitted overlays are historical evidence requiring re-review.
- An interaction claim must survive the bounded evaluator task: the goal must not permit bypassing the claimed response. Source motion/proximity alone cannot establish required braking, restart or yielding. Retain downgraded scenes as controls and preserve original selection intent.
- All admitted scenes need current full technical, manual semantic and SMART-specific gates. Missing/stale/incorrect evidence must fail closed, including in the policy runner. Retain the fixed four-candidate ledger and exclusions; do not add candidates based on policy success. Avoid shared moving tracks and overlapping windows; cluster inference by recording.

## Pilot outcome

The three pilot stages are satisfied for their bounded purpose; see [results](2_smart_protocol_pilot_results.md). Three scenes are admitted (one pedestrian interaction and two controls), one priority-dependent scene is excluded. The parent Step 2 remains incomplete: these stages do not satisfy its 10-scene feasibility or 50-scene completion requirements. Its persistence and generalization requirements remain unchanged.
