The promising paper is not “US planners perform worse in Germany.” It is: **which failures persist after the scenario is faithfully transferred, and which can be repaired with small, targeted data additiofns?** A performance gap alone is too easy to explain through differences in intersections, traffic mix, maps, or simulator behavior rather than geography.

The first inD scenario is the right feasibility test. The main question is whether the converted scene gives the planner the same meaningful task as the recording: a plausible ego route and goal, correct lane connections, consistent actor timing, and traffic behavior that remains sensible when the ego deviates. 

[inD provides trajectories and Lanelet2/OpenDRIVE maps](<https://levelxdata.com/ind-dataset/>), but those inputs still need a defensible closed-loop task definition.

For an A\* claim, I would want three layers of evidence:

1. **Validity:** hand-check the source recording against the converted scene, binary, and expert replay before scoring planners.
2. **Attribution:** compare German scenes with suitably matched US scenes, and separate planner failures from map, route, traffic-model, and conversion failures.
3. **Repair:** show that failure-specific data beats an equal-sized random data addition and a broad fine-tuning baseline, on held-out locations or recordings. Otherwise “targeted” may just mean “more training.”

Combination of a concrete transfer setting, observable failure cases, and interventions that could reveal _why_ a planner fails. 
The strongest argument against it is that dataset and simulator differences could account for the entire apparent transfer gap. **The riskiest assumption is that a faithful closed-loop German evaluation can be built from recorded trajectories.** Test that assumption with the one hand-checked inD intersection before scaling conversion or adaptation work.



1 dataset, 1 location - many windows

per window conserve

| Field | Required decision |
|---|---|
| Time | Fixed 10 Hz grid for BehaviorBench; record source frame rate and interpolation method. |
| Coordinates | One local metric frame shared by tracks and map; document origin, axis direction, heading convention. |
| Actors | Stable IDs, class, dimensions, valid mask, position, velocity, heading. Preserve source values and any derived values separately. |
| Map | Centerlines, road edges, lane IDs, successor connectivity, and evidence for each geometric mapping. |
| Ego | An eligible recorded vehicle with enough history and future, a nontrivial maneuver, and no ambiguous entry/exit. |
| Route and goal | A route consistent with the ego’s observed maneuver, plus a goal that is reachable within the simulation window. |
| Provenance | Dataset, recording, location, source track ID, window frames, parser version, and exclusion reasons. |

Verify:

- centerlines lie inside their lane polygons;
- successor IDs exist and directions align;
- the ego start and goal project onto a connected route;
- lane merges, turns, and roundabouts preserve intended connectivity;
- crossings and sidewalks are not silently treated as drivable lanes.


2 Traffics: Expert replay + controllers. controller can be source of gap so achtung there.


Validate in layers before reporting planner scores:

1. **Parser checks:** time monotonicity, finite values, stable IDs, dimensions, velocity versus position derivative, heading versus motion.
2. **Map checks:** geometry overlay on the aerial image; lane connectivity and ego route rendered.
3. **JSON round trip:** source → canonical → JSON; compare sampled actor states and map features.
4. **Binary round trip:** read the `.bin` back with BehaviorBench’s binary reader and compare to JSON.
5. **Replay check:** observed actors in the simulator should match their source trajectories within a stated position and heading tolerance.
6. **Human ego sanity check:** replay or track the recorded ego and confirm it does not trigger systematic off-road or collision flags. If it does, investigate geometry, dimensions, or metric semantics before testing models.
7. **Planner smoke test:** one scene each for a rule-based planner, PPO, and SMART, with video and per-step traces.