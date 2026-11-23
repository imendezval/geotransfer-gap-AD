# GeoTransfer — Performance Evaluation Specification

**Status:** Reviewed scope specification. A separate implementation plan will define the engineering details.

**Objective:** Establish a planner-agnostic evaluation framework that measures driving performance, identifies recurring failure modes, and supports defensible comparisons between US and German scenarios. The resulting evidence should help identify which failures warrant adaptation and which may be candidates for minimal targeted training or data.

This specification defines **what the framework must support, what it must report, and what evidence is required to interpret its results**. It does not prescribe module structure, APIs, storage schemas, algorithms, exact formulas, numerical thresholds, or a detailed execution schedule.

The framework has five parts:

1. Core driving-performance metrics.
2. Semantic and interaction evaluation.
3. Benchmark compatibility and secondary diagnostics.
4. Performance evaluation validity.
5. Geographic-transfer and failure-mode analysis.

## Scope and priorities

| Priority | Required scope |
|---|---|
| **P0 — Essential foundation** | Core metrics, metric applicability, evaluation validity, per-episode evidence, aggregate reporting, and failure-mode analysis. Geographic claims additionally require an appropriate US comparison set. |
| **P1 — Conditional semantic coverage** | Rule compliance and interaction-specific evaluation for scenario families with sufficient validated annotations. Unsupported cases must remain explicitly unassessable. |
| **P2 — Secondary extensions** | Benchmark composites, reference-trajectory diagnostics, and broader traffic-realism diagnostics. These supplement the primary metrics. |

The framework must initially support SMART and PPO evaluation while allowing additional planners without changing the meaning of the metrics. It must distinguish ego policy, traffic configuration, and startup protocol, including the effective actor control during the evaluated rollout.

A German-only diagnostic evaluation is a useful deliverable before a matched US baseline exists. It must be described as failure characterization on the tested German corpus; geographic degradation remains an unestablished claim until a suitable comparison is available.

## 1. Core driving-performance metrics

**Priority: P0**

| Category | Required measurements |
|---|---|
| **Collision safety** | Any-collision indicator and rate; collision count; collision partner/type; responsibility classification when supported by defensible evidence |
| **Collision severity** | Relative impact speed and collision geometry/type where observable; clearly identified as severity proxies |
| **Off-road compliance** | Violation indicator, maximum excursion, and duration outside a supported drivable-area definition |
| **Near-collision risk** | Minimum TTC and time below configured thresholds where TTC is meaningful; minimum footprint-to-footprint clearance |
| **Route progress** | Absolute route progress and normalized progress when a valid reference route exists |
| **Task completion** | Completed / failed / unresolved, with a separate unassessable state when the task is not sufficiently defined; safe task-completion rate |
| **Efficiency** | Completion time, timeout, stationary duration, and stalling/deadlock indicators where supported |
| **Comfort** | Longitudinal acceleration and braking, lateral acceleration, yaw rate and yaw acceleration, longitudinal and total jerk, and configured threshold violations |

### Required interpretation

- **Safety, progress, and comfort must remain separately visible.** Stopping permanently must not appear to be successful driving simply because no collision occurs.
- **Safe task completion** must combine a validated task outcome with explicitly designated critical safety criteria. Missing required evidence must not silently produce a safe-completion pass.
- **Any collision** must be reported independently of responsibility. Unsupported fault attribution must remain unknown.
- **Severity proxies** must supplement collision occurrence. Relative impact speed must not be presented as a validated injury estimate.
- **TTC and clearance** must retain their limitations. No predicted collision under a chosen TTC model, an undefined TTC, and unavailable actor data must be distinguishable. TTC alone must not determine interaction safety.
- **Progress** must distinguish route advancement from distance traveled. Normalized progress requires a meaningful reference; partial observations must not silently define the full task.
- **Timeout, truncation, and failure** must be distinguishable. A recording or evaluation horizon ending before task resolution must not automatically imply planner failure.
- **Stationary duration** must be reported separately from unjustified stalling. Legitimate yielding or waiting must not automatically be classified as deadlock.
- **Comfort** must include continuous measurements and violation summaries, with the evaluated time window and relevant data limitations identified.

Exact definitions and thresholds will be fixed in the implementation plan and versioned with the results.

## 2. Semantic and interaction evaluation

**Priority: P1, conditional on validated semantic support**

| Category | Required assessment |
|---|---|
| **Driving direction** | Wrong-way occurrence, distance, and duration where permitted direction is known |
| **Speed limits** | Violation occurrence, maximum overspeed, and duration where applicable limits are available |
| **Traffic controls** | Red-light and stop-sign compliance where controls and any required time-varying state are known |
| **Priority and yielding** | Compliance with supported right-of-way relations and yielding obligations |
| **Lane behavior** | Lane-center deviation and heading alignment where a valid reference and relevant lane assignment exist |
| **Encounter realization** | Whether the intended encounter was presented, reached, and resolved; reasons for non-realization or indeterminate status |
| **Interaction outcome** | Success, failure, unresolved outcome, or unassessable outcome for the scenario's intended maneuver |
| **Interaction quality** | Applicable safety margins, timing, and negotiation diagnostics for the supported interaction family |

Missing or unreliable semantics must be reported as missing or unreliable evidence, rather than as compliance. Lane-center deviation is a diagnostic unless the maneuver and road semantics justify treating it as a violation.

### Interaction-level requirements

Interaction evaluation is a required capability, but this specification does **not** finalize a metric catalog for every maneuver.

For each interaction family admitted to evaluation, the framework must support:

- A validated description of the intended maneuver, relevant actors, and applicable task/rule context.
- Evidence that the encounter occurred, or a reason why it did not.
- Explicit success/failure criteria and applicable safety or timing measurements.
- An unresolved or unassessable outcome when the available evidence cannot establish the result.
- Separation of observed behavior from inferred explanations, such as aggressiveness, cooperation, or unfamiliarity with a local convention.

Established measurements such as TTC, post-encroachment time (PET), time headway, and clearance should be reused where their assumptions fit. Scenario-specific benchmark criteria may be adapted where appropriate. New GeoTransfer-specific criteria are only required where existing measures do not express the intended behavior. Reuse of an established metric does not by itself establish that it is appropriate for every interaction.

**An ego that never approaches an interaction has not demonstrated successful interaction handling.** If this results from a genuine progress failure, that failure must remain in the results rather than being excluded as an invalid scene.

The initial interaction families, their exact operational definitions, and their thresholds will be selected in the implementation plan according to the admitted corpus and available annotations.

## 3. Benchmark compatibility and secondary diagnostics

**Priority: P2**

| Capability | Intended use and required boundary |
|---|---|
| **nuPlan closed-loop score compatibility** | Comparison with established evaluation conventions; distinguish faithful reproduction from an adapted score |
| **BehaviorBench score compatibility** | Comparison with the existing PufferDrive evaluation context under documented metric and protocol compatibility |
| **All-Core Pass Rate** | Share of episodes satisfying an explicitly designated core criterion set; report eligibility, missing evidence, and denominator |
| **ADE / FDE / reference deviation** | Descriptive comparison with recorded trajectories; deviation alone is not evidence of unsafe or incorrect behavior |
| **Lane-center and heading scores** | Supplemental behavioral diagnostics with maneuver-aware applicability |
| **Traffic realism diagnostics** | Independent description of simulated traffic quality and its limitations |

A composite score may only be described as equivalent to an official score when the required definitions, thresholds, scenario semantics, and aggregation are faithfully reproduced. Otherwise it must be labeled as an adapted or inspired variant, with differences stated.

Primary findings must remain interpretable through individual metrics. A new arbitrary weighted score is outside the initial scope.

Focused traffic-quality diagnostics are sufficient initially; a full WOSAC implementation is deferred. Any P0/P1 checks needed to establish that traffic produced a meaningful encounter remain required regardless of this deferral.

## 4. Performance evaluation validity

**Priority: P0 — Reuse existing validation and add metric-specific evidence**

GeoTransfer already has substantial validation infrastructure. This work must reuse existing source/conversion, scene-admission, execution, and provenance evidence rather than introduce a duplicate validation framework.

Existing validation addresses scenario fidelity and reproducibility. The additional requirements here concern whether the new metrics correctly describe the rollout and whether that rollout provides an interpretable test of the intended behavior.

### Existing coverage versus additional work

The statuses below retain the prior assessment of repository coverage. They are planning assumptions to be confirmed against existing evidence during implementation, not a fresh repository audit or a guarantee for every future configuration.

| Requirement | Existing coverage recorded in the plan | Required action |
|---|---|---|
| **Source, map, and conversion fidelity** | Covered | Reuse existing conversion/source evidence and identify any configuration-specific gaps |
| **Technical and semantic scene admission** | Covered | Reuse admission decisions and the semantic coverage actually established |
| **Deterministic execution and trace integrity** | Covered | Reuse existing verification for the configurations it covers |
| **Controller and startup provenance** | Covered | Reuse actual actor ownership, movement mode, and startup/release evidence |
| **Metric applicability and validity** | New | Make metric eligibility and assessment status explicit |
| **Performance-metric correctness** | New | Establish that the new measurements produce defensible results on known cases |
| **Intended encounter preservation** | Missing / unassessed | Determine whether each rollout presents the intended interaction |
| **Human/reference metric sanity** | Partial | Extend suitable replay checks to the new metrics and investigate implausible outcomes |
| **Threshold sensitivity** | New | Establish whether substantive findings depend on reasonable threshold choices |
| **Termination and failure attribution** | Partial | Separate planner outcomes, incomplete observation, protocol effects, and execution failures |

### Required additional evidence

1. **Metric correctness and applicability.** Each metric must have a documented meaning, required inputs, eligibility conditions, evaluation window, and assessment status. Valid measurements, unavailable data, inapplicable criteria, and undefined quantities must be distinguishable. Missing evidence must not silently become a pass, zero, or safe value.
2. **Encounter realization.** Results must identify whether the intended encounter occurred under the actual ego, traffic, and startup configuration. Non-realization must retain its reason where known, including planner behavior, traffic behavior, horizon limits, or invalid setup.
3. **Reference sanity.** Suitable human/expert replay must be evaluated with the new metrics. Implausible violations must be investigated without assuming that recorded behavior passes every criterion. Replay is a reference execution; it does not establish reactive traffic validity after ego behavior diverges.
4. **Threshold sensitivity.** Major safety, comfort, and semantic conclusions must be assessed under reasonable alternative thresholds. Threshold choice must not be tuned solely to make one geography or planner appear better.
5. **Outcome attribution.** Planner failures must be distinguishable from runtime crashes, simulator errors, annotation limitations, initialization artifacts, and incomplete observation. Uncertain attribution must remain possible. Exclusions and execution failures must be counted and explained.
6. **Evaluation exposure and provenance.** Results must identify evaluated duration and distance, task/horizon termination, relevant observation limits, metric/protocol versions, and the effective controller/startup configuration. Labels alone must not be treated as evidence of traffic reactivity.

Startup periods, held actors, actor activation/removal, and missing observations must have explicit treatment in metric eligibility and evaluation windows. Early termination must not produce an apparent safety or comfort advantage without the shortened exposure being visible.

**Encounter non-realization is not automatically scene invalidity.** Report both encounter status and driving outcome. Do not discard episodes merely because a planner's behavior prevented it from reaching the intended challenge.

## 5. Geographic-transfer and failure-mode analysis

**Priority: P0 research deliverable; geographic conclusions depend on baseline readiness**

### A. Per-episode evidence

Each episode must provide:

- Metric values, assessment status, and applicable pass/fail outcomes.
- Task, encounter, and terminal outcomes, with reasons where supported.
- Failure events with timing, relevant actors, available severity evidence, and the first observed violation.
- Scenario, recording/location, planner/checkpoint, traffic, startup, and evaluation-protocol provenance.
- Evaluated exposure, missing evidence, exclusions, and links to available trace/viewer evidence sufficient to inspect the finding.

Multiple failure labels must be allowed. A collision, off-road event, and task failure can coexist. The first observed violation must not automatically be treated as the root cause.

### B. Aggregate reporting

For each planner and evaluation condition, the framework must report:

- Collision, off-road, task-success, and safe-completion rates.
- Distributions of progress, TTC, clearance, comfort, and other applicable continuous measurements.
- Counts and recurrence of failure types.
- Submitted, executed, valid, excluded, assessable, and applicable episode counts as relevant.
- Duration and distance exposure, plus independent recording/location counts.
- Uncertainty estimates that respect dependence between overlapping scenes, repeated runs, and episodes from the same recording.

The unit and denominator of every rate must be visible. Repeated seeds or overlapping windows must not be presented as additional independent geographic evidence. Unsupported precision must not be inferred from a small corpus.

### C. Geographic comparison

| Comparison | Required interpretation |
|---|---|
| **US vs Germany overall** | Observed performance difference on the evaluated scenario sets |
| **Within interaction categories** | Whether degradation is concentrated in particular maneuver or interaction families |
| **Across cities / locations** | Whether failures recur across independent locations or are localized |
| **Matched or adjusted scenarios** | Whether differences remain after accounting for relevant scenario composition and difficulty |
| **Across traffic configurations** | Whether findings depend on the simulated traffic behavior |
| **Across startup protocols** | Whether findings depend on initialization |
| **Against reference execution** | Context for interpretation and possible reconstruction/protocol artifacts |

Geographic comparisons must use compatible metric definitions, applicability rules, and evaluation protocols, with material differences disclosed. An appropriate US baseline must cover the relevant scenario families and support comparison of important confounders such as geometry, traffic composition, task difficulty, and observation horizon.

The existing US diagnostic fixtures must not automatically be treated as a matched geographic benchmark. Differences between arbitrary US and German scene collections are descriptive evidence and do not isolate geography as the cause.

Where comparability or sample size is insufficient, the framework must report that limitation and retain the result as a diagnostic finding or hypothesis.

### D. Failure-mode taxonomy

| Failure family | Required coverage |
|---|---|
| **Collision / unsafe interaction** | Contact and supported near-miss or safety-margin violations |
| **Road-boundary / rule violation** | Off-road, wrong-way, and assessable traffic-rule failures |
| **Task / maneuver failure** | Failure to complete a validated objective |
| **Deadlock / excessive conservatism** | Unjustified inability to make appropriate progress |
| **Aggressive / uncomfortable behavior** | Supported dynamic or comfort violations |
| **Interaction-specific failure** | Failure to resolve the intended encounter according to validated criteria |
| **Evaluation artifact / invalid test** | Conversion, annotation, simulation, or protocol problems that invalidate or limit interpretation |

Evaluation artifacts must be reported separately from planner-performance failures. The taxonomy must support both quantitative events and inspected case evidence, without claiming automatic root-cause identification.

For example, excessive braking is observable; attributing it to unfamiliar German yielding conventions requires additional evidence.

### E. Evidence for adaptation priorities

For each recurring failure mode, the resulting analysis must be able to summarize:

- The affected scenario/interaction families and the observed failure behavior.
- Frequency, severity, safety–progress–comfort trade-offs, and independent supporting recordings.
- Robustness to traffic, startup, and reasonable metric-threshold choices.
- Whether the failure also occurs in comparable US scenarios.
- Supported explanations, competing explanations, and remaining uncertainty.
- Whether the evidence motivates investigating a targeted data/training intervention or a broader adaptation method.

This framework identifies and prioritizes adaptation candidates. It does not establish how much training/data is sufficient, or whether an intervention works, without subsequent controlled adaptation experiments.

## 6. Required deliverables and acceptance criteria

| Deliverable | Acceptance requirement |
|---|---|
| **Core metric evaluation** | P0 measurements are available for supported rollouts, with explicit applicability, continuous evidence, and appropriate outcomes |
| **Semantic and interaction evaluation** | Supported scenario families have validated encounter/task criteria; unsupported cases remain explicitly unassessable |
| **Validity evidence** | New metric correctness and reference sanity are demonstrated; existing validation evidence is reused; unresolved limitations are visible |
| **Episode evidence** | A result can be traced to its scenario, effective controllers, startup, protocol, outcomes, and available rollout evidence |
| **Aggregate reporting** | Rates, distributions, exclusions, exposure, and uncertainty have transparent denominators and dependence handling |
| **Geographic analysis** | Matched/adjusted comparison is supported when suitable baselines exist; otherwise claims remain limited to the tested corpus |
| **Failure analysis** | Recurring failure families are supported by quantitative results and inspectable cases, with measured events separated from inferred causes |
| **Secondary compatibility outputs** | Any benchmark-style score is labeled according to demonstrated compatibility; individual metrics remain available |
| **Research report inputs** | Outputs support a technical report describing evaluation scope, failures, validity limits, literature context, and adaptation candidates |

P0 readiness must not depend on completing every P2 extension. P1 readiness must be stated per supported semantic/interaction family, rather than implying complete coverage of all driving situations.

## 7. Deferred work and implementation-plan decisions

### Deliberately outside the initial scope

- A new arbitrary weighted leaderboard score.
- A complete WOSAC realism implementation.
- Sophisticated automatic responsibility or root-cause attribution.
- A large maneuver-specific metric catalog before the relevant scenarios are semantically validated.
- A new actuation-noise robustness benchmark.
- Training or evaluating an adaptation method as part of this evaluation-framework specification.

### To resolve in the subsequent implementation plan

- Exact metric definitions, geometric assumptions, thresholds, and sensitivity ranges.
- Initial interaction families, annotation needs, and operational success criteria.
- Task boundaries, reference routes, time windows, and treatment of truncated observations.
- Concrete module/API design, result schemas, storage, and viewer/report integration.
- Verification cases, regression scope, and execution details.
- US comparison-set selection and matching/adjustment methodology.
- Statistical procedures, sample-size requirements, and implementation milestones.

These decisions must satisfy the requirements above; they are not prerequisites for treating this document as the agreed scope.

## Reference starting points

The following references are retained as starting points for metric reuse and evaluation design. Inclusion does not imply that their complete metric sets are required, already implemented, or directly applicable to GeoTransfer.

- [nuPlan devkit — Metrics description](https://github.com/motional/nuplan-devkit/blob/master/docs/metrics_description.md)
- [Beyond Self-Play and Scale: A Behavior Benchmark for Generalization in Autonomous Driving (BehaviorBench)](https://arxiv.org/abs/2605.10034)
- [Shift & Drift](https://arxiv.org/abs/2607.07844)
- [interPlan](https://arxiv.org/abs/2404.07569)
- [NAVSIM](https://arxiv.org/abs/2406.15349)
- [Bench2Drive](https://arxiv.org/abs/2406.03877)
- [nuPlan-R](https://arxiv.org/abs/2511.10403)
