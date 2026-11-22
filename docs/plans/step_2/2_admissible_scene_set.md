# Step 2: An admissible German scene set

> **Current verification:**16 independent scenes:13 interactions and3 controls; three interaction families, locations1/3/4 and10 recording clusters. All16 reproduce exact single/batch timelines under runtime `beedf8f1b0e9c490`, traffic `startup_sustained_departure_route_coverage_v2` and SMART dense-map protocolv4. All13 original source anchors remain. Composition and third-family establishment are complete; full Step2 remains incomplete at16/50. See the [current execution record](2_third_family_execution.md).

## Objective

Use the Step 1 admission gate to build an independently reviewed set of inD scenes suitable for later planner comparisons. Search beyond the current late-VRU candidate pool. A loadable or geometry-valid scene is not automatically admissible: its ego task, traffic, and applicable map rules must also be represented fairly.

## Current state and next objective

The [three-stage SMART protocol pilot](2_smart_protocol_pilot.md) and [original expansion results](2_expansion_execution_results.md) are historical. The current source-ordered set contains **six pedestrian encounters, four following tasks, three cyclist crossings and three controls**. The cyclist examples cover recordings1/7/9 and locations1/4. The original13 source anchors are retained without binary changes. One further per-scene pass shares moving tracks and is excluded from independent counts. Location2 priority and the original intersection pilot remain excluded for unsupported applicable rules and perturbed background-traffic failure respectively.

Use [reproduction commands](2_reproduce_admission.md) and [scope/matching fields](2_protocol_scope_and_matching.md). The original composition is immutable; active selectionv3 incorporates [fidelity amendments](2_final_corpus_protocol_amendment_v3.md) without changing quotas, source-selection principles or splits. No planner-success selection or old/new protocol pooling is permitted.

The **10 genuinely interactive, fully admitted scenes across at least two locations** feasibility objective has been achieved under the frozen protocol. Controls remain useful but do not count toward this feasibility milestone. The final objective remains the 50-scene corpus below. Completing a pilot or an individual stage is not a stopping condition for an authorized autonomous run of the whole Step 2 plan.

## Remaining execution plan

Execute the following stages in order, revisiting earlier stages when new evidence invalidates them. Before each stage, record its intended experiment, acceptance criteria and affected evidence. Keep the original eight work areas below as cross-cutting requirements. Use source-only screening before expensive evaluator/model runs; do not repeatedly rerun unchanged evidence.

### 2.1. Freeze and reproduce the verified baseline

**Problem.** The verified path currently uses a repository adapter and isolated runtime; the stock BehaviorBench SMART entrypoint does not automatically use them. Historical reports can look valid despite referring to an obsolete protocol.

**Actions.**

- Record one explicit protocol/version: checkpoint, tokenizer/codebooks, actor selection, coordinate transform, 10 observed warmup steps, 11-sample history, 0.1 s sampling, prediction interval5, greedy CPU seed0, goal radius2 m/speed threshold20 m/s, hybrid traffic and source physical-box policy. Record effective configuration, not merely command defaults.
- Provide a reproducible command sequence for full technical evidence, SMART input proof, source review, planner-specific admission and admission-enforcing rollout. Preserve manual review as a distinct required input; do not automate it into a blanket pass.
- Verify OSM boundary orientation and directed successor construction against the native Lanelet2 loader/routing graph on every available map variant, including invariance to independent way-storage reversal. Check centerlines remain inside native road polygons. The road+bus geometry graph is not proof of ordinary-car bus-lane access; review applicable access restrictions separately. Rebuild affected scenes and source-map preflight indexes after correction.
- Keep the three admitted pilots and two US diagnostic inputs as regression fixtures. Preserve rejection fixtures for missing/stale evidence, missing encounter actors, incorrect aerial scale, unsupported priority and the false queue-response claim. Preserve runtime re-entry and permanent collision-removal regressions.
- Make evidence invalidation explicit: source/map/conversion/runtime changes require affected technical checks again; adapter/tokenizer/model/protocol changes require affected SMART proofs and admissions again. Historical reports remain archived and visibly stale.

**Complete when.** The existing three SMART admissions reproduce under one recorded protocol; their required evidence hashes are current; known failures remain rejected; and the lifecycle, coordinate and actual-model-input regressions pass. Someone can follow the documented commands without using an unrecorded session patch. A stock multi-map factory integration is not required for this baseline, but any later batch runner must use exactly this verified path.

### 2.2. Correct the source-review backlog and prepare a candidate queue

**Problem.** Incorrect fitted aerial projection contaminated some earlier surface/parked-overlap decisions. Reusing those exclusions or admissions would bias expansion.

**Actions.**

- Identify all decisions that depended on factor10/fitted translation. Mark them superseded pending review; keep unrelated source exclusions distinct.
- Reproject promising historical candidates with provider factor12 and zero translation. Recheck road surface, parked boxes, boundaries and source-map alignment; do not assume the correction makes every earlier rejection admissible.
- Prioritize previously promising interactions and locations missing from the current set. Log the queue and source-based ordering before new planner outcomes. If this queue is exhausted, open another prespecified recording/maneuver cohort.
- Record candidate-level status and reason: source reject, task reject, semantic reject, technical reject, awaiting manual review, admitted interaction or admitted control. Keep revisited candidates linked to their original decisions.

**Complete when.** Every historical aerial-dependent decision is identified as superseded or re-reviewed, and the next candidate batch has a reproducible, source-selected queue with current overlays for candidates proceeding to review. Historical admissions cannot contribute to current totals without the complete refreshed gate.

### 2.3. Establish genuine interaction tasks before expensive runs

**Problem.** A scene can contain close actors or source braking while its bounded evaluator goal permits completing the task without the claimed response. The current queue scene is such a control.

**Actions.**

- Search source tracks for pedestrian/cyclist encounters and following/stop-and-restart opportunities, then turns/conflicting traffic where applicable rules are supported. Include density and location variation; do not require late spawning.
- Apply cheap checks first: complete source coverage, sufficient ego motion, legal directed route, actor presence, encounter after warmup and before terminal, and goal timing. Retain the existing minimum source goal-first-entry standard (step75 for a step85 goal) unless a general, documented amendment is validated.
- For every claimed interaction, record actor IDs, encounter/decision interval, source evidence of the relevant response, and why a valid goal completion cannot bypass that decision. Inspect route and goal footprint, not only center-distance or total motion. Reject or relabel tasks whose response is optional under their goal.
- If a longer window or later goal is needed, define a source-derived selection rule applied consistently to a cohort, ensure actual source/map coverage and planner/evaluator horizon support, then rerun the full fidelity gate. Do not move one scene's goal simply to obtain an interaction label.
- Inventory governing rules before model runs. Queue supported interactions for full checks; preserve unsupported-priority examples as explicit semantic exclusions. The original queue control does not need to be forced into a following benchmark.

**Complete when.** The next batch includes source-reviewed candidates for at least two interaction types across at least two locations, with source/task/rule evidence sufficient to attempt full admission. Each candidate has either a defensible interaction claim or an explicit control/exclusion label. A promising queue is progress, not the 10-scene milestone itself.

### 2.4. Build the 10-scene feasibility set through the full gate

**Problem.** The ten-interaction count is meaningful only when all current gates, essential context and independence checks reproduce. Loadable files, controls and technically faithful but semantically incomplete scenes cannot fill the gap.

**Actions.**

- Process the fixed queue progressively: source/task/semantic screening, conversion using the existing JSON-to-binary writer, complete technical gate, manual source review, actual SMART input proof, then SMART admission. Run policy diagnostics after source-based decisions; keep outcomes from determining selection.
- Verify the relevant actors and rules at the actual decision interval, lifecycle through the justified terminal, source-valid replay, physical geometry and selected interactive traffic under ego perturbation. Preserve essential preceding-vehicle context even when a different actor supplies the primary interaction label. Compare model identities at prediction refreshes and explicitly retain the frozen between-refresh latency policy.
- Classify every failure. Investigate generic converter/runtime/traffic/task defects and rerun affected scenes after repairs. If the scene remains unsuitable, retain its failure and continue with the next prespecified candidate group.
- Keep controls as a separate stratum. Deduplicate windows and moving tracks, assign whole recordings to splits, retain location holdout, and report scene counts alongside recording clusters.

**Complete when.** At least **10 admitted interaction scenes** across **two locations** and **at least two supported interaction types** pass all current technical, manual and SMART gates. Their windows/moving tracks satisfy the independence rules; recording clusters and any remaining coverage gaps are explicit. Controls and duplicate protocol variants do not count toward the ten. Publish the complete candidate-to-admission flow, not just successful roots.

### 2.5. Resolve limits exposed by expansion and verify scalable execution

**Problem.** Applicable priority/sign rules remain unsupported, US checks currently establish mechanics rather than matched research cohorts, and the verified runner is single-scene. These limits must be explicit before scaling or claiming planner generalization.

**Actions.**

- Use the exclusion ledger to identify which missing rules actually prevent the required location/interaction coverage. Continue searching supported source tasks while investigating these gaps; a rejected priority scene is not a blocker for all other work.
- For each material rule gap, either retain a clearly scoped exclusion with its coverage consequence, or develop a generic representation and verify source→JSON→binary→actual planner input. Check that the checkpoint can use its meaning: an arbitrary extra feature or token does not make an unchanged model rule-aware. Any new training/adaptation protocol must be explicitly separated and applied consistently to US and German conditions.
- Reuse the same frozen protocol on US reference cases exercising relevant actor lifecycles, crossings and coordinate ranges. Document all effective interface/configuration differences from upstream training/evaluation; do not claim equivalence from finite actions or shared code alone. Define source-based matching fields for later US/German cohorts without treating the two diagnostic references as a study set.
- Add or verify a sequential manifest-driven batch runner using the canonical admission-enforcing path. Every scene must reset state/history, retain its ego and configuration, and fail closed on stale evidence. Compare representative batch outputs with the existing single-scene path before using the batch for corpus diagnostics. Stock multi-map integration is optional; consistent execution is mandatory.
- Keep admission planner-specific. PPO and other planner interfaces need their own observability/gate evidence before sharing a research-admissible set; their absence does not invalidate an explicitly SMART-scoped corpus.

**Complete when.** The admitted scope has no unresolved applicable rule gaps; excluded rule classes and resulting claim limits are explicit; relevant US/German input and traffic mechanics pass the same protocol checks; and batch execution reproduces representative single-scene behavior without cross-scene state leakage. If the supported scope cannot meet the parent coverage requirements, Step 2 stays incomplete while semantic repair and other source searches continue.

**Verified outcome for stages2.1–2.5 (2026-11-15).** Ten independent interactions plus three controls pass the current gates; native topology, ordinary-road access, source-state/lifecycle and SMART rejection regressions pass; two US references pass the same mechanics; all13 single/batch timelines match exactly; `step2_frozen_protocol_baseline.json` records the verified protocol and evidence. Source intent, expert VRUs, unknown out-of-view motion and unrepresented applicable obligations remain explicit limits. No unresolved applicable-rule gap is admitted. This does not complete stage2.6 or prove universal traffic faithfulness.

### 2.6. Expand to the final corpus and publish the audit

**Problem.** Ten scenes demonstrate feasibility, not sufficient diversity or statistical support for the geographic planner-performance study.

**Current progress.** Composition is frozen and three independently admitted cyclist encounters establish the third family. Current16 scenes preserve all13 original binaries, with13 interactions/3 controls and exact16-scene single/batch reproduction under the active protocol. Continue with source-selected expansion and balance toward50; this milestone does not complete Step2.

**Actions.**

- The composition/source-selection rules are frozen in [final corpus selection v1](2_final_corpus_selection.md). Active `pilot/audits/final_corpus_selection_current.json` points to selectionv3 with [protocol fidelity amendments](2_final_corpus_protocol_amendment_v3.md). Target50 remains20 pedestrian+15 following+5 cyclist+10 controls. Three cyclist admissions across recordings1/7/9 now establish the third family; current16/50 is not final coverage.
- After inspecting feasibility coverage and before additional policy outcomes, freeze the next selection strata and target counts by location, recording, maneuver, interaction type and density. Prespecify the interaction/control balance; do not fill the final set with easy controls to reach50.
- Expand to at least50 admitted independent windows across at leastthree locations, preserving at least the ten genuine interactions and extending to at leastthree supported interaction types. Record recording clusters separately from scene count; apply power/precision requirements for the intended comparison if they require more data.
- Continue the progressive gates and source-based exclusion ledger. Version protocol changes and rerun affected accepted scenes rather than mixing old/new admissions. Freeze recording/location splits before adaptation or performance-based selection.
- Publish a current manifest, per-scene source/ego/map provenance, task and interaction descriptions, all gate/review hashes, source visualizations, exclusions and selection-flow counts. Quantify geometry/timing/lifecycle fidelity and disclose imputed dimensions, missing source intervals and interactive-traffic limitations.
- Recheck the original intersection pilot under the current source/semantic protocol: either restore current admission or retain an explicit current exclusion. No historical pilot exemption.

**Complete when.** All parent completion requirements below are met by current evidence, the manifest reproduces its counts, known negative cases remain rejected, and documented commands rebuild admissions and diagnostics. Report the scope actually achieved and remaining fidelity limits; completing the corpus does not by itself establish a geographic performance gap or finish the later matched-US evaluation/adaptation study.

## Work sequence

1. **Specify selection before searching.** Define minimum ego motion, route length, goal placement, actor coverage, interaction opportunity, and independence between windows. Search all suitable moving inD egos rather than requiring a late VRU. Record every candidate and its rejection reason to expose selection bias.
2. **Screen route and applicable map rules.** Check directed travel and permitted lateral lane changes. Associate signs and priority relations with the lanes and conflict movements they govern. Test crosswalks against the vehicle footprint and relevant traffic, not only ego-center distance. Review curbs and other boundaries. Treat a distance threshold as a screening aid, not proof that a rule applies or does not apply. Start with the technically admitted `faithful_intersection04` scene and identify exactly which of its priority, sign, and crosswalk findings govern the ego's tested maneuver.
3. **Review promising source recordings.** Inspect the recording or source imagery alongside the track/map overlay. Confirm coordinates, sampling, ego identity, route, goal, actor timing, actual interaction, and the rules governing it. Exclude or resolve ambiguous cases and retain a short review sheet and visualization for each accepted scene.
4. **Convert and apply the full Step 1 gate.** Validate binary round trip, source expert replay, evaluator-config actor lifecycle, physical boundaries, parked actors, and map semantics. Test selected scenes with interactive traffic and ego perturbations. Tie every report to source, binary, runtime, and configuration hashes.
5. **Build a leakage-resistant corpus.** Avoid overlapping ego windows and shared tracks across adaptation and evaluation splits. Record site, maneuver, actor classes, traffic density, interaction type, rule type, and all exclusions. Reserve recordings and preferably a location for later held-out evaluation; publish a manifest and selection-flow summary.
6. **Resolve semantic transfer for admitted interactions.** For every candidate, list source priority relations, traffic signs, crosswalks, lane-change rules, and physical boundaries that could change the correct planner action. Show either how each applicable rule reaches the planner through the evaluator's map/observation and traffic protocol, or source-based evidence that the rule does not govern the tested interaction. If encoding is needed, implement and validate it generically, then apply the same observation and training protocol to US and German scenes. Do not mark a scene research-admissible solely because a sign or crosswalk lies beyond a chosen distance threshold.
7. **Expand beyond the sparse technical pilot.** Select and review scenes with varied turns, crossing or yielding traffic, pedestrian/cyclist encounters, and traffic densities across locations. Verify that actors create genuine decision opportunities at the relevant time; actor counts or proximity alone are insufficient. Apply the same Step 1 fidelity and counterfactual checks to every scene, and retain source-based exclusions when interactive traffic or physical geometry is unsuitable.
8. **Make research admission reproducible.** Update the semantic audit and admission gate so a research pass requires a current, per-scene applicability decision and its evidence, alongside the technical contract. Re-run the gate on accepted scenes and known failures, verify that missing or stale review evidence fails closed, and keep diagnostic smoke scores separate from research results.

## Milestones and completion requirements

**Feasibility milestone:** At least 10 independently reviewed, admitted **interaction** scenes across at least two inD locations and at least two supported interaction types, with no unresolved map-rule or evaluator-fidelity issue. Controls do not count toward the ten. This is a decision gate for whether scaling is worthwhile, not a research-performance sample.

**Step 2 complete:**

- At least 50 independent admitted scenes across at least three locations and at least three supported interaction types, retaining at least the ten genuine interaction scenes and a prespecified interaction/control balance, **or more if** a prespecified precision or power calculation for the intended comparison requires it.
- Every admitted scene passes the mandatory automated Step 1 gate and manual source/map-rule review. Applicable priority, sign, crosswalk, and boundary information is either represented in the planner protocol or shown to be irrelevant to that scene's tested interaction. Ambiguous scenes are excluded.
- The technically admitted intersection pilot has an explicit rule-applicability review and either passes research admission after a source-supported semantic resolution or remains excluded with the actual current failure identified (including any governing missing rule). No blanket exemption for the pilot is permitted.
- The semantic gate checks what the planner and traffic models actually receive in the evaluator. If a rule-aware representation is introduced, its source-to-binary-to-observation path and US/German protocol parity are verified. Missing, stale, or merely proximity-based review evidence cannot produce a research pass.
- At least the feasibility set, and ultimately the full admitted corpus, contains documented interaction opportunities and variation beyond the sparse Step 1 turn. Scene selection and exclusion counts show which locations and interaction types the corpus does and does not cover.
- The corpus includes reproducible per-scene reports, an ego manifest, source and map provenance, location/recording-disjoint splits, and a complete candidate-to-admission flow with rejection counts. Overlapping windows and shared tracks cannot leak between adaptation and evaluation.
- The accepted set contains enough variation and independent observations to support the later failure categories. The study claim is limited to the locations and scenario types actually covered; inD alone does not establish performance across Germany.

If meaningful interaction scenes require rules that unchanged BehaviorBench checkpoints cannot observe, this step remains incomplete. The alternatives are to find source-supported scenes where those rules do not govern the tested interaction, or to establish a rule-aware observation and training protocol applied consistently to US and German conditions.

## Persistence requirement

Continue investigating failures and newly exposed issues until the Step 2 completion requirements are met. An unsuccessful candidate, difficult semantic mapping, a finite set of failed experiments, or an incomplete corpus is not a stopping condition. Diagnose the failure, test a general source-supported correction or search another prespecified candidate group, and rerun the affected admission checks. Keep research admission failing when the evidence does not justify a pass.

Stop for user input only if a genuine blocker requires the user's intervention **and** no independent Step 2 work remains possible. Record the exact blocker, the evidence that it cannot be resolved locally, the input needed, and the other Step 2 avenues already pursued. Continue any independent work while that input is pending.
