# Final-corpus map fidelity amendment v3

Composition, source selection, source anchors and splits stay as frozen in v1.
The runtime/traffic repairs in amendmentv2 remain unchanged. Existing policy
smoke diagnostics are known; this is a fidelity repair, not outcome-based scene
selection. Retain all16 source-admitted scenes and refresh their input/admission/
rollout evidence, rather than selecting successes under the changed input.

A follow-up audit found the tokenizer's long-edge gap heuristic also removes
some supplied lane/curb polylines. Normalize consecutive edges of every existing
supported type (lane4,line5,edge6,crosswalk8) to <=2m before the unchanged SMART
tokenizer, uniformly in both domains. Preserve every original vertex and the
same piecewise-linear geometry, never add a closing edge or connect separate
road objects. These are the explicit consecutive segments already represented
in the simulator binary; this does not infer unobserved map connections.

Use map encoding `encoded_polyline_edge_sampling_max2m_v2` and planner protocol
`smart_all_actors_observed_history_dense_map_v4`. Runtime remains
`beedf8f1b0e9c490`; traffic remains
`startup_sustained_departure_route_coverage_v2`. Archive the fully reproduced
crosswalk-only v3 baseline. Do not mix its outcomes or stale input proofs with
this protocol. Geometry/corner preservation, visibility of all polylines longer
than0.5m, actual model-input features and isolated single/batch reproduction are
mandatory checks. The unchanged tokenizer cannot represent standalone segments
of length<=0.5m; quantify those omissions rather than enlarging or fabricating
geometry. Source physical checks remain mandatory.

This restores existing geometric feature classes, not priority/sign or dashed-
versus-solid semantics. Lane-rule compliance, navigation-goal intent, nonreactive
VRUs, imputed dimensions and source-held traffic retain the disclosed limits in
amendmentv2 and the scope document. Full geographic-study or50-scene completion
is not implied by this three-example cyclist-family milestone.
