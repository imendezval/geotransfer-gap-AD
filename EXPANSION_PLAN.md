# Expansion experiments: standards fixed before execution

## 1. Parked and slow vehicles

**Question:** Does the current full-window path-length and speed rule ever relabel a vehicle that moves, stops temporarily, or interacts with traffic?

**Method:** scan every inD recording's track metadata and CSV at source rate; classify complete 9 s windows and short stop episodes; report thresholds, counts, near-boundary cases, and explicit counterexamples. For selected windows, build full scenes with and without the stationary flag, inspect active/static status, replay, and partner observation/collision behavior. Keep the source boxes and tracks intact. Compare the source-valid expert trace under the patched runtime and unmodified runtime.

**Pass:** zero false-static moving vehicles in a diverse sampled set; no missing valid samples in accepted full scenes; static actors visible to nearby ego and collision checks; results stable under small threshold changes. A collision between boxes already overlapping in the source is not a runtime defect. If evidence is ambiguous, narrow the rule and exclude that scene from research scoring.

## 2. Late entry and exit

**Question:** Can a geometry-valid scene with a late VRU pass normal evaluator timing, and does the patched runtime preserve actor slots and reset behavior under actual traffic modes?

**Method:** search candidates by source metadata and map occupancy, then convert, audit, replay, and run birth/exit checks. Test expert, IDM, and evaluator traffic configuration; repeat resets and compare against a no-late regression. Probe simultaneous arrivals and capacity separately. Use no-early-reset only as a technical diagnostic, never as an accepted-scene gate.

**Pass:** normal 91-step replay without missing valid samples, exact first valid state (<0.01 m/rad and <0.01 m/s), zero pre-entry state/event and post-exit presence in one episode, stable ego index, repeatable reset, and a geometry-valid ego route. VRU expert-background support is reported separately from controllable VRU policy support.

## 3. Map semantics

**Question:** Can unchanged BehaviorBench checkpoints be evaluated on source windows where omitted rules do not govern the ego task? What can the current observation format express?

**Method:** scan candidate ego windows using independent Lanelet2 polygon, directed-route, regulatory-relation, sign, crosswalk, and road-edge checks. Build only candidates that pass the map-semantic gate, then validate replay and traffic. Audit matched US map fields where local data allow. In a separate technical probe, encode supported sign/crosswalk binary types and measure whether the existing C observation changes; do not score a planner on an invented map feature.

**Pass:** at least one hand-reviewed, connected, source-replay-valid scene with no relevant omitted rule along its ego task, or a documented proof that the candidate pool is empty under this gate. A semantic representation prototype passes only if the unchanged planner observation actually carries the feature and source geometry aligns; changing observation dimensions requires a separate trained-model protocol.

The three workstreams are sequential for conclusions: complete or document the limit of 1, then 2, then 3. Failed probes stay labeled as diagnostics. Planner outcomes remain smoke tests until all gates pass.
