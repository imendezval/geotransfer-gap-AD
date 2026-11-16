# Standards for the next three experiments

## 1. Stationary actors

Trace each disappearance to a specific C state transition, using the uncropped source binary and simulator state before and after the first step. Compare source vehicle boxes and recorded velocity with simulator dimensions and goals. A proposed fix passes only if the uncropped scene keeps every source-valid actor for 91 steps, matches expert positions/headings within 0.01 m/rad, preserves ego replay, and does not merely suppress a real overlap. Check all three affected recordings. Stop at a documented unresolved cause if the source itself contains ambiguous overlapping boxes.

## 2. Late arrivals

Keep source validity masks unchanged. Test vehicle, pedestrian, and cyclist births where source recordings permit, plus simultaneous births, actor capacity, and exit behavior. Before birth, require invalid position, zero observation and event rewards. At birth, require <0.01 m and <0.01 rad error; after birth, require no missing valid samples in expert replay. Compare IDM and action-driven first steps; do not treat a synthetic actor as a source-validity test. Separate an engine limitation from a scene-specific failure.

## 3. Map semantics

Audit lanelet and regulatory-element tags, ego lane occupancy and heading, directed successors, road-edge coverage, and cross-check with OpenDRIVE where possible. Flag any source priority or traffic-control rule that the JSON/binary cannot carry. Inspect selected intersections, not just map-wide counts. Do not invent traffic rules from the ego trajectory. A map passes geometry only when source polygons and boundary IDs support the route; planner claims remain conditional if right-of-way or road-edge semantics are missing.
