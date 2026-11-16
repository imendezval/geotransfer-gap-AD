# Validation plan for the next adapter iteration

## Late-arriving actors

**Target:** a source actor with first valid sample after step 0 is absent from reset state and observations, enters at its recorded sample with source position, heading, and velocity, and remains present until its recorded exit. Ego index and earlier actors must stay stable.

**Standards:** compare every valid replay sample to source with position error below 0.01 m and heading error below 0.01 rad; assert no actor appears before its first valid sample; assert no pre-entry collision, off-road, or goal event; rerun the original no-late scene as a regression. For interactive traffic, spawn at the recorded state before applying the controller, and record any discontinuity or immediate collision.

**Constraints:** preserve original inD validity masks and tracks; no first-frame ghost, invented trajectory, or silent actor omission. Keep BehaviorBench's checked-in source untouched. Any experimental engine change must be isolated under this project and identified by its source hash/build command. A loadable binary or matching expert-only replay is not enough to claim interactive support.

## Map topology and stationary actors

**Target:** establish that selected ego start and goal lie in drivable lane polygons connected in the recorded direction, and that every emitted successor is supported by map boundaries and direction. Measure how many source actors are removed or altered by cropping and why.

**Standards:** compare CSV and OpenDRIVE origins; check heading against lane direction at start and goal; check ego samples against lanelet polygons as well as centerlines; count successor gaps, direction reversals, and route ambiguities. Do not use the ego trajectory to create map links. Compare full and cropped binaries under identical replay conditions, reporting every actor lost at initialization or later. A cropped actor must have negligible direct interaction with the ego over the full window, and the threshold must be stated.

**Constraints:** preserve Lanelet2 way and relation IDs, left/right boundary orientation, and map provenance. Keep moving actors and VRUs unless a documented validity failure excludes the entire scene. Treat any heuristic map repair or parked-actor exclusion as an ablation until it passes independent geometry and replay checks. Planner scores remain exploratory until these gates pass.
