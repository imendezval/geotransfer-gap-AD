# Step 2 protocol scope and later US/German matching

## What the current admission means

Admission is SMART-specific and task-specific. It establishes current source,
binary, expert-state, actor-lifecycle, physical-geometry, manual rule/task and
actual-model-input evidence under one recorded runtime. Interactive traffic
also passes the prescribed ego perturbation. It does not establish that every
background driver will imitate the recording under every possible ego action.

The effective protocol is recorded by `freeze_smart_protocol.py` (current SMART
`smart_all_actors_observed_history_dense_map_v4`): checkpoint
and codebook hashes, evaluator/runtime hashes, all-actor input adapter, observed
10-step warmup, 11-sample history, 0.1s sampling, prediction every five steps,
CPU greedy inference, seed0, goal radius2m and maximum goal speed20m/s.
The recording supplies91 samples, with the source task goal at sample85 and
first goal entry no earlier than75. Selection uses source/task/fidelity evidence;
planner success cannot choose a scene or window variant.

## Differences and limits that remain explicit

- The repository adapter includes expert vehicles, VRUs and parked actors in
  stable binary order, and puts map/actor inputs in the evaluator's local frame.
  It uses observed warmup rather than unobserved future ego history.
- The isolated runtime supports source-valid births, exits and re-entry, keeps
  physical collision removal permanent, and supplies same-time expert velocity
  at reset and every replay step. The upstream BehaviorBench tree is unchanged.
- Traffic version `startup_sustained_departure_route_coverage_v2` retains the
  sustained-departure hold (startup below1m/s, at least1s/1m before release,
  five consecutive valid samples at >=2m/s). At each background route build,
  native routing remains if any of the next11 source speeds is below1m/s.
  Otherwise a logged contiguous route is used only when its length covers
  max(current speed,native desired speed) times remaining observed duration.
  IDM retains braking/control limits; the controlled ego is excluded. This
  source-intent prior is identical in both countries and is not stock traffic
  or universal human-response fidelity. Terminal tangent preview is an explicit
  controller extrapolation, not reconstructed source motion.
- Map encoding `encoded_polyline_edge_sampling_max2m_v2` samples consecutive
  edges of existing lane4/line5/edge6/crosswalk8 objects before the unchanged
  tokenizer, uniformly in both countries. It preserves supplied geometry and
  corners and never connects separate objects or adds a closing edge. This
  repairs long edges mistaken for missing-data gaps. The seven-map audit checks
  1,832 supported polylines and restores116 previously dropped representable
  objects. Ten standalone segments <=0.5m remain below the native tokenizer's
  resolution in those diagnostics; codebook approximation and short tail
  clipping also remain. Source geometry preservation is not exact latent-map
  reconstruction or upstream-training equivalence.
- Source-route legality includes102 independently native-verified conservative
  dashed-boundary lateral permissions on five maps. Ambiguous, solid/mixed and
  access-restricted transitions are not silently granted, and lateral changes
  never become IDM following successors. Scenes needing lateral reachability
  require explicit source review and a dense ordinary-road directed sequence.
  This does not give SMART dashed-versus-solid semantic features or validate
  lane-rule compliance; relevant unrepresented prohibitions remain excluded.
- Source crosswalk polygons are verified through JSON18, binary8 and actual
  SMART tokens. SMART has no corresponding Lanelet2 priority/sign or bus-access
  meaning. Applicable missing obligations stay excluded. A same-route source
  certificate can disprove a crossing heuristic; it never waives an explicit
  priority relation. Bounded stop-scope proofs need explicit source review.
- Actual model identities are checked at prediction refreshes. Birth/exit
  changes can remain between-refresh stale for up to four ticks under the
  frozen five-step prediction interval.
- Some source VRU dimensions are absent and use disclosed class defaults.
  Unobserved motion beyond source visibility is unknown; the converter does
  not reconstruct it. Minor stationary annotation-overlap exceptions require
  provider imagery and cannot hide a moving-actor collision or change a box.
- The inspected SMART path builds its model input from agent history and map
  tokens; it does not condition on a navigation goal/route. The evaluator still
  scores a source-derived goal. Goal misses at ambiguous branches therefore
  require a separate intent/route-choice interpretation. Do not call them a
  geographic planning deficit solely from the goal metric. PPO needs its own
  input/admission evidence and cannot inherit SMART observability claims.

The US diagnostic references establish interface, source-state, coordinate,
actor-switch and execution mechanics under this protocol. They are not a
matched research cohort and do not prove equivalence to upstream training.

## Source-only matching fields for the later study

Freeze matching strata and exclusions before inspecting planner outcomes.
Store unavailable values explicitly; do not silently infer equivalence.

| Group | Required fields |
| --- | --- |
| Provenance/splits | Dataset version, site/city where available, recording/sequence cluster, source scene/window, actor IDs, ego identity, source/map hashes, recording-disjoint split and location holdout |
| Ego task | Interaction family and actors, maneuver, source route/path length, initial speed, speed/acceleration profile, curvature, scored decision interval, source goal distance, first-entry time, legal branch ambiguity and goal visibility to the planner |
| Interaction | Physical box gap and timing, source body-path conflict, slow/stopped intervals, leader departure, VRU crossing phase, closest approach and whether the bounded goal can precede the interaction |
| Traffic | Density and classes in the task corridor, initial stopped/slow fraction, source-held traffic and release timing, logged-route eligibility/actual use and native desired speed, late births/exits, observed validity gaps and expert/interactive roles |
| Geometry/semantics | Intersection/corridor layout, lane count/directions, widths, supported crossing geometry, relevant priority/sign/access classes, applicable-rule exclusions and manual source decisions |
| Physical uncertainty | Measured versus imputed dimensions by class, stationary annotation exceptions, camera/source coverage and any unsupported geometry |
| Evaluator interface | Exact runtime/checkpoint/tokenizer/controller hashes, warmup/history, timing, action limits, goal/termination/collision settings and planner-specific admission |

Use a common admission and missing-rule policy in both countries. Do not retain
unsupported German obligations while treating missing US semantics as harmless.
Report distributions and unsupported strata, rather than forcing matches where
provenance, goals or dimensions are unavailable. A standardized-box or different
traffic-model sensitivity study is a separately versioned protocol requiring
new gates in both domains.

Non-overlapping windows with no shared moving source tracks remain clustered
by recording/sequence. Preserve location holdout and recording-disjoint splits;
scene count is not the number of statistically independent geographic sites.
Normalize ahead/approach pedestrian labels to one crossing family and leading
vehicle variants to one longitudinal-following family for coverage counting.

The current set has13 admitted interactions plus3 controls, including3 timed
cyclist encounters across3 recordings/two locations. These are not all source
yielding or mandatory-braking examples; preserve before/after-ego timing labels.
The original10-interaction feasibility target is retained. The later50-scene,
three-location, three-family corpus and matched-US evaluation remain separate
requirements. Prespecify source strata, interaction/control balance and the
precision/power needed for the eventual comparison before scaling or adaptation.
