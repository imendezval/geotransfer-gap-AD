# Final-corpus fidelity protocol amendment v2

The composition/source-selection rules in `2_final_corpus_selection.md` remain
unchanged: target50=20 pedestrian+15 following+5 cyclist+10 controls, fixed
location/recording splits, independence and coverage requirements. V1 remains
immutable. This amendment records generic fidelity repairs discovered while
establishing the third family, before new German closed-loop corpus diagnostics
under the amended protocol. Source/model-input and US mechanical diagnostics
already exist; they are not blinded study results or policy-success selection.

Use runtime `beedf8f1b0e9c490`, traffic
`startup_sustained_departure_route_coverage_v2`, SMART
`smart_all_actors_observed_history_dense_crosswalk_v3`, and map sampling
`crosswalk_edge_sampling_max2m_v1`. Refresh every affected technical/input/
admission/rollout proof; do not pool earlier passes. All13 original source
anchors are retained by identity and unchanged binary, not by reusing old gates.

At each background route build, native routing remains when any of the next11
contiguous source speeds is below1m/s. Otherwise a contiguous logged route is
used only if its length covers max(current speed,native desired speed) times
remaining observed duration. Native IDM retains acceleration, leading-actor
braking and collision response; the controlled ego is explicitly excluded.
The source intent prior is applied identically to US/German binaries. Terminal
tangent continuation supports controller preview and is not reconstructed
source motion. The actual source-startup hold/release protocol remains in place.
Unrestricted route, speed-guided and heuristic route alternatives failed
retained fixtures and were not promoted.

Source reachability now includes a conservative native-verified subset of
same-direction dashed-boundary lane changes. Ambiguous overlapping neighbours,
solid/mixed boundaries, bus access and explicit access restrictions are not
silently granted. Lateral permissions never become IDM following successors.
When following-only reachability fails, SMART admission additionally requires a
hash-bound manual review and a dense directed ordinary-road source sequence.
This validates source legality, not a new checkpoint ability to read lane rules.
The admitted crossing tasks do not claim lane-rule compliance; in the third
example the source lane change follows the primary crossing interval. Missing
navigation-goal conditioning still limits interpretation of later lane/goal
choices. Relevant unrepresented prohibitions or priority obligations remain
excluded. No generic lane token is claimed to encode dashed-versus-solid meaning.

Sparse crosswalk edges are sampled at <=2m before the unchanged SMART tokenizer
in both domains. This preserves every original corner and consecutive polyline
segment, adds no closing edge/new feature class, and prevents long edges from
being mistaken for missing-data gaps. Actual model-input and geometric tests
are required, rather than only successful binary conversion.

The third family consists of timed cyclist crossings. These are not all source
yielding or mandatory braking examples: record whether the cyclist crosses
before/after ego passage, and retain source response/goal evidence without
unsupported causal labels. The new protocol does not make VRUs reactive, remove
imputed dimensions, establish upstream-training equivalence or create a matched
US/German performance study. Full Step2 and its50-scene/three-family requirements
remain separate from this three-example family-establishment run.
