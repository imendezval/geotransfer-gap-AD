# German-200 v1 Workstream E: off-stride source-only availability

## Scope and distinct task counts

This analysis reads the seven frozen source-positive task selectors and current source tracks. It does not create a new queue, alter the Random100/Interactive100 selection, read planner outcomes, or grant scene admission.

A task is identified by recording, ego track, and actor track. Of the 944 distinct task keys in the selector union, 931 have at least one off-stride source-positive phase (first frame not divisible by 50). Of these, 832 are absent from the frozen 100 Interactive100 task assignments. The complete eligible stride-50 interaction universe contains 764 distinct tasks; 180 off-stride task keys are outside that full universe, so those 180 represent task units beyond the existing stride-50 selection coverage.

The 180 incremental task units have 156 cyclist-crossing, 12 pedestrian-crossing, and 12 longitudinal-following family memberships. Their location memberships are 38 at location 1, 128 at location 2, four at location 3, and 10 at location 4. They span 29 recordings. These counts describe the seven selectors only.

## Source-only independence witness

For each of the 180 task units, source phases were ranked with the frozen selector priority and deterministic source-phase ordering. Current raw tracks and metadata were passed through the existing full-context reconstruction helper; every moving actor in the converter-supported source context was retained, with no actor cap. A deterministic SHA-ranked greedy pass checked inclusive source-window overlap and shared moving tracks against all 200 frozen primaries plus all 16 anchors, with none excluded.

This produced a 39-task source-only independent witness: 34 cyclist, four pedestrian, and one longitudinal task. The witness spans 23 recordings and locations 1, 2, and 4 (12, 24, and three tasks respectively). Of the remaining incremental units, 126 conflicted with the frozen baseline and 12 more conflicted only with earlier witness rows under this greedy order; three had no usable converter-context phase after source-context checks. This is a witness, not a maximum independent set.

## Current map preflight on the witness

The existing oriented preflight files have sparse exact coverage of all 1,387 off-stride phases for the 180 incremental tasks: 11 exact phase rows across eight tasks, all with a failed stored preflight result. A current preflight was therefore run on exactly the already selected 39 witness windows, using the existing source-map preflight producer in a scratch catalog under the E artifact namespace.

The three-condition test is source ego completeness, zero ego centers outside road/bus lanelets across all 91 samples, and a directed start-to-goal lane route. Twenty-six of the 39 witness windows pass all three conditions; 13 fail at least one (11 have no directed route and four have outside samples, with two windows in both categories). All 39 ego windows are source-complete. The map-passing subset remains independent against all 200 primaries and all 16 anchors, and pairwise within the subset. It gives a 26-task map-qualified source-only witness: 21 cyclist, four pedestrian, and one longitudinal task; locations 1, 2, and 4 contribute six, 17, and three tasks.

The current source input hashes for the 23 unique recordings represented by the 39 witness windows matched the earlier full-context reconstruction inputs. The preflight producer SHA-256 is `d17e4b525dfdbef931d6852a81080557bf2756988c85283995673138839946ee`. The 26 map-passing windows cover 19 recordings, with 17 tasks at location 2, six at location 1, three at location 4, and none at location 3. The other off-stride task phases and tasks outside this 39-row witness remain map-unassessed. No conversion, technical admission, semantic review, or manual review was performed for Workstream E.

The exact current preflight command was:

    MPLCONFIGDIR=/tmp/geotransfer_mpl OMP_NUM_THREADS=1 PYTHONPATH=src .venv/bin/python -m geotransfer_gap.maps.preflight_source_map --catalog artifacts/german_200_v1_workstream_e_source_only/witness_39_source_catalog.json --output artifacts/german_200_v1_workstream_e_source_only/witness_39_map_preflight.json

## Reproducibility

The full task, phase, family/location counts, moving-track identities, source inputs, selector/producers hashes, and source-only conflicts are in [offstride_source_witness.json](../../../artifacts/german_200_v1_workstream_e_source_only/offstride_source_witness.json), SHA-256 `2755616dbbe26f18e6716ed5f42a423ed4888532d8e2ee19d7169ee2578573af`.

The exact 39-window preflight input and output are [witness_39_source_catalog.json](../../../artifacts/german_200_v1_workstream_e_source_only/witness_39_source_catalog.json) and [witness_39_map_preflight.json](../../../artifacts/german_200_v1_workstream_e_source_only/witness_39_map_preflight.json). The hash-bound input/output and 26-row independence audit are in [witness_39_map_audit.json](../../../artifacts/german_200_v1_workstream_e_source_only/witness_39_map_audit.json), SHA-256 `c85474bf26ecdc459c0a14d39f92a600df08386f93d2d66c338b88f7155e655f`.

## Recommendation and boundary

Continue the frozen v1 design and expand the source-only off-stride inventory under an outcome-blind, predeclared task, family, and location plan with the same source-context, independence, and map gates. The v1 queues remain frozen as specified. No v2 queue is frozen from this analysis.

Random100 v1's intended sampling unit is one `(recording, ego_track_id)`. The sampler hash-ranks these units, then selects an eligible stride-50 phase within each unit subject to the frozen independence gates. The pilot batches provide descriptive results for selected rows and no estimate of technical-gate outcomes in the eligible-unit population. Uniform sampling of eligible windows would give more selection weight to long tracks with more eligible phases. The off-stride witness uses `(recording, ego, actor)` task units and measures source availability.

Interactive100 has 87 of 100 assignments at location 2. The map-qualified off-stride witness also has a location imbalance: 17 of 26 tasks at location 2, six at location 1, three at location 4, and none at location 3. Preserve the location-4 holdout and seek source-only location-3 coverage. If source-blind discovery in the current German corpus cannot supply independent, source-context and map-qualified tasks at underrepresented sites, another German dataset will likely be needed to support site diversity. The 39-to-26 result supports this scoped source-supply decision. It provides no technical-admission estimate or population inference.
