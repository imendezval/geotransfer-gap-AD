# Faithful-scenes execution criteria

These criteria were fixed before modifying the converter or runtime for this run.

1. **Contract:** Every scene report identifies the source recording and map by SHA-256, exact JSON/binary, BehaviorBench Git commit and runtime source, evaluator INI, ego index, goal settings, traffic mode, and duration. Research mode refuses absent or stale geometry and semantic audits.
2. **Trace:** For each source-valid actor at each evaluator step, record presence, position and heading error, collision/offroad/goal state, and first removal cause. Distinguish a legitimate ego goal or source exit from premature removal and an episode reset. Diagnose r02/107 and full04, full13, full21 using the same script.
3. **Lifecycle:** On expert traffic, non-ego actors follow the source until their last valid sample while the episode exists, without collision/goal removal. On IDM/action traffic, births and exits have exact timing and goals must not cause early removal or indefinite freezing. Apply one generic rule across recordings; verify the four failure fixtures and r00 without scene-specific IDs.
4. **Physical map:** Classify source boundary tags and actor-box contacts at 1.0 evaluator collision scaling. Preserve physical curbs; do not remove an edge solely to make a scene pass. Verify parked/stopped actors remain visible and collidable and that source replay has no unexplained ego collision/offroad event.
5. **Counterfactual:** Perturb ego in expert, IDM, and another available traffic mode on at least two scenes, one with late arrivals. Require no prebirth visibility, ghost actor, premature source-valid disappearance, or preterminal reset. Record plausible response separately from source-replay error.
6. **Admission:** A single command produces a pass/fail JSON tied to all hashes and the current mandatory audits. A source-invalid scene fails with a specific reason; any diagnostic configuration cannot satisfy research mode.

If a criterion cannot be met under the current simulator architecture, record the exact failure and retain a failing gate instead of widening tolerances or dropping source actors.

## Continuation criteria for remaining work

7. **Source image and collision geometry:** Establish a reproducible image-to-local-coordinate transform from dataset metadata or source landmarks. Render source boxes and classified curbs on the original background. For each reported overlap, preserve exact actor IDs, frame, box size, and map tag; accept a boundary edit only if the image and source map support it across the location.
8. **Interactive lifecycle:** Trace every first loss under IDM and zero-action dynamics with the preceding two steps, collision partner or edge, pose, speed, and source comparison. Apply only location-independent rules, then rerun the five fixtures and at least one unseen turn. Treat unperturbed and perturbed losses separately.
9. **Goal event:** Reproduce the PDM final-distance/goal discrepancy under `evaluation.ini`, inspect the metric and horizon code, and establish whether a final-step event is missing, delayed, or correctly absent. Do not tune the scene goal to PDM.
10. **Intersection admission:** Select candidates by source geometry and maneuver before reading planner outcomes. Require a source-checked turn through an intersection, exact expert replay, correct actor births/exits, no unexplained physical conflict, passing defined interactive probes, current contracts, and a repeatable canonical-environment evaluator run.

After each failed experiment, pursue the next independent diagnostic or candidate. A failed gate is a result to investigate, not a stopping condition.
