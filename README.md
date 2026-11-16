# GeoTransfer-AD-Gap: US-to-Germany driving planner transfer

## Project aim

Identify where autonomous driving planners trained on US driving data fail when evaluated on German driving scenarios. Characterize the specific failure modes and determine which may be corrected with small, targeted additions of training data or fine-tuning, and which appear to require more substantial adaptation.

## Research claim and evaluation controls

The primary question is: **after a German recording has been transferred into a validated closed-loop planning scenario, which recurring planner failure types can be repaired by a small amount of failure-targeted data?** A lower aggregate score on German scenes alone is not evidence of a geographic transfer effect. Dataset composition, map conversion, route construction, traffic simulation, and planner interface differences are competing explanations.

A *transfer failure* is a collision, road departure, wrong-route movement, prolonged lack of progress, or other prespecified unsafe or unsuccessful behavior by an unchanged planner in a validated scene, relative to the same evaluation protocol on matched US scenes. We will record success, collision type, off-road events, progress/goal completion, and failure timing per scene; inspect trajectories and interactions before assigning a cause. Failure categories should distinguish perception/representation or conversion defects from behavioral errors such as yielding, gap acceptance, negotiation, and route following. A scene with incorrect geometry, actor timing, ego identity, route, goal, or implausible traffic response is excluded from planner-gap claims and counted as a conversion failure.

Controls are: (1) source-recording versus converted-scene and expert-replay checks; (2) unchanged planner checkpoints evaluated with identical simulation settings on German and US scenes matched as far as possible by maneuver, intersection form, traffic density, actor types, and interaction difficulty; (3) expert-replay traffic followed by multiple interactive traffic models; and (4) equal-budget random-data and broad fine-tuning comparisons for each targeted adaptation. Keep adaptation and evaluation recordings, and preferably locations, disjoint. Report per-scenario outcomes and uncertainty, not only a pooled score. If matching is incomplete, describe the result as cross-dataset generalization rather than a causal US-to-Germany effect.

The first feasibility gate is one hand-checked inD intersection scene with a defensible ego task. A loadable binary is insufficient: its coordinates, 10 Hz sampling, actor tracks, map topology, route and goal, and expert replay must agree with the source recording before a planner run can support the research claim.

The first single-scene transfer and smoke tests are recorded in [EXPERIMENT.md](EXPERIMENT.md). Visual failure inspection, construction ablations, the late-spawn probe, and the additional-scene audit are in [FOLLOWUP.md](FOLLOWUP.md).
The later [late-entry, map-topology, and stationary-car audit](AUDIT_RESULTS.md) contains the stricter converter and validated scene variants. Its [validation plan](VALIDATION_PLAN.md) states the gates and exclusions.
The [uncropped stationary-actor, late-entry, and map-semantics experiments](NEXT_AUDIT_RESULTS.md) supersede the selective crops for the three tested windows. The corresponding [standards](NEXT_AUDIT_PLAN.md) and per-scene reports identify what passed and why research scoring remains blocked.
The latest [expansion experiments](EXPANSION_RESULTS.md) add source-rate stationary checks, an exact evaluator-configuration replay gate, a geometry-valid late cyclist scene, and an exhaustive semantic screen of the defined late-VRU candidate pool. Its [standards](EXPANSION_PLAN.md) were fixed before testing. The older single-scene scores are historical smoke tests; the stricter current gate rejects their research use.
The [faithful-scenes results](docs/plans/1_faithful_scenes_results.md) document the evaluator runtime correction, actor lifecycle traces, physical-box audit, counterfactual tests, and hash-bound admission command. Earlier IDM admissions are historical and require refreshed evidence after the latest projection/runtime corrections. The [Step 2 scene-set results](docs/plans/2_admissible_scene_set_results.md) track separate IDM and hybrid traffic admissions, source-based exclusions, and the substantial interaction and coverage shortfall that still prevents planner-gap claims.

## Current conversion and evaluation status

The [current third-family execution record](docs/plans/2_third_family_execution.md) documents **16 independent SMART-admitted scenes: 13 interactions and three controls**, across **three locations and ten recording clusters**. The interaction families are six pedestrian encounters, four following tasks and three cyclist crossings. All16 reproduce their single-scene timelines exactly in fresh batch subprocesses; all13 original source anchors retain their binaries.

The prospective [50-scene composition](docs/plans/2_final_corpus_selection.md) is frozen. [Protocol amendments](docs/plans/2_final_corpus_protocol_amendment_v3.md) record the generic fidelity repairs: runtime `beedf8f1b0e9c490`, progress-covered background route intent and SMART dense-map input protocolv4. Native audits verify437 road/bus lanelets plus102 conservative legal lateral transitions on five maps. Uniform US/German map sampling restores116 previously dropped supported polylines in the seven-map diagnostic audit.

This completes the requested composition and third-family establishment work. **Full Step2 remains incomplete:**34 additional admissions, final coverage/balance and sample-size justification remain. The US references establish mechanics, not a matched geographic-performance study. PPO needs its own validation. VRU reactivity, imputed dimensions, map quantization and missing goal/lane-rule conditioning remain explicit limits; these are not all mandatory-yielding examples.

Use the [reproduction commands](docs/plans/2_reproduce_admission.md), [scope/matching requirements](docs/plans/2_protocol_scope_and_matching.md), and [Step2 plan](docs/plans/2_admissible_scene_set.md). The original intersection pilot and applicable unrepresented priority cases remain excluded. [Earlier feasibility results](docs/plans/2_expansion_execution_results.md) are historical and cannot be pooled with the current protocol.

From this directory, run a selected crossing fixture using the BB environment:

```bash
MPLCONFIGDIR=/tmp/geotransfer_mpl OMP_NUM_THREADS=2 conda run --no-capture-output -n bb_pufferdrive python probe_faithful_smart_closed_loop.py --root pilot/oriented_v3/r00_e366_f23240 --require-admission
```

This uses the repository's `FaithfulSMARTPlanner` adapter and isolated evaluator runtime. Upstream BehaviorBench remains unchanged; its stock entrypoint does not automatically include these fixes.

## Initial work

1. Review [*Beyond Self-Play and Scale: A Behavior Benchmark for Generalization in Autonomous Driving*](https://arxiv.org/abs/2605.10034), especially the five planners in Table 1 and their available [open-source checkpoints](https://github.com/boschresearch/behavior-bench). Start with SMART and PPO as candidate planners.
2. Request access to the six datasets listed by [levelXdata](https://levelxdata.com/) to obtain German driving scenarios. The application note should briefly describe the US-to-Germany planner generalization study and state that the applicant is a master's student working with the supervisor, who has a connection with the dataset manager.
3. Design and run a failure-focused evaluation on the German data. Record and group concrete planner failures, compare them across planners and scenarios, and assess whether limited targeted data or training could plausibly address each group.

## Student project deliverable

A technical report combining the failure tests and a literature review. It should document the evaluation setup, observed failure modes, and evidence for which failures are promising targets for small interventions versus broader adaptation.

## Possible master's thesis extension

Develop and evaluate solutions for the failure modes identified by the student project. This is a possible follow-on direction, separate from the supervisor's concurrent investigation of an uncertainty-aware project.
