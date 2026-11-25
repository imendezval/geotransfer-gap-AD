# Step 2 source-only feasibility counts

## Scope and counting rules

This census uses the frozen source selectors, stride-50 catalogs and corrected map preflights listed below. Interaction keys are `(recording, ego, actor)`. Repeated source phases for the same key count once. Random-window keys are `(recording, ego_track_id)` after a source-positive, complete window joins to a map-preflight row with all 91 centers in road or bus lanelets and a directed start-to-goal route. These counts describe source candidate availability. Semantic eligibility and actual admission remain separate gates. No planner outcome enters the counts or the cohort procedure.

The third-family selector contains 4,982 event-centered phase windows. Those collapse to 394 distinct cyclist task keys. The window phases run from source offset -75 through +75 in five-frame steps. The body, footprint and fine-phase selectors expose 562, 265 and 128 distinct eligible task keys. Their source-positive pair arrays contain 977, 358 and 268 rows before task-key deduplication. Restart, restart-turn and restart-velocity source-positive arrays contain 18, 24 and 18 distinct task keys. The velocity selector's `jobs` list contains 16 keys and omits two source-positive keys.

The family counts below merge task keys across these seven source queues and preserve every `task_evidence.kind` label. Five keys carry both lead braking and stop/restart evidence. Two of those are in active locations. The unique union is 814 keys across all locations and 167 keys across locations 1, 3 and 4. Within that union, 79 recording-ego identities have candidates with multiple actors and 33 recording-actor identities appear with multiple egos. The active-location union has four recording-ego identities with multiple actors and five recording-actor identities shared by multiple egos. Apply the existing independence rules before selecting a cohort.

## Interaction task keys by source evidence kind

Location 2 remains visible in this census and stays outside a prospective cohort pending resolution of its applicable-rule semantics. The location counts sum by source kind. Multi-kind keys are counted under every recorded kind and once in the unique union.

| Interaction family | Source evidence kinds | All keys | Location 1 | Location 2 pending | Location 3 | Location 4 | Active locations 1, 3, 4 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cyclist crossing | `cyclist_crossing` | 400 | 53 | 338 | 2 | 7 | 62 |
| Pedestrian crossing | `pedestrian_crossing` | 278 | 18 | 235 | 1 | 24 | 43 |
| Longitudinal following | `lead_vehicle_braking_response`, `lead_vehicle_stop_and_restart` | 136 | 28 | 74 | 15 | 19 | 62 |

The longitudinal-following row deduplicates braking-response and stop/restart evidence on `(recording, ego, actor)`. It contains five keys tagged with both kinds across all locations and two in active locations. The three family rows partition the 814-key unique source union.

Recording counts follow. Numbers omit the `r` prefix in each cell.

| Source evidence kind | Location 1 | Location 2 pending | Location 3 | Location 4 |
| --- | --- | --- | --- | --- |
| `cyclist_crossing` | 07=2, 08=6, 09=1, 10=2, 11=3, 12=4, 13=8, 14=6, 15=7, 16=8, 17=6 | 18=23, 19=16, 20=26, 21=19, 22=39, 23=31, 24=20, 25=26, 26=29, 27=32, 28=37, 29=40 | 30=1, 32=1 | 00=2, 01=1, 02=3, 05=1 |
| `pedestrian_crossing` | 07=1, 08=5, 11=1, 12=2, 13=4, 14=1, 16=3, 17=1 | 18=14, 19=9, 20=19, 21=18, 22=30, 23=18, 24=16, 25=17, 26=17, 27=24, 28=25, 29=28 | 32=1 | 00=7, 01=3, 02=8, 03=1, 04=1, 05=1, 06=3 |
| Longitudinal following | 09=1, 12=5, 13=6, 14=5, 16=8, 17=3 | 18=9, 19=3, 20=6, 21=6, 22=6, 23=5, 24=5, 25=13, 26=7, 28=6, 29=8 | 30=4, 31=2, 32=9 | 00=4, 01=5, 02=6, 06=4 |

Selector-level task totals overlap between source screens. The unique union is 814 keys.

| Source selector | Distinct keys | Location 1 | Location 2 pending | Location 3 | Location 4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Third-family event fine selection | 394 | 51 | 336 | 2 | 5 |
| Body task queue | 562 | 59 | 454 | 12 | 37 |
| Footprint task queue | 265 | 31 | 202 | 10 | 22 |
| Fine-phase task queue | 128 | 71 | 0 | 16 | 41 |
| Source restart selection | 18 | 6 | 10 | 2 | 0 |
| Source restart turns selection | 24 | 6 | 12 | 2 | 4 |
| Source restart velocity positives | 18 | 6 | 10 | 2 | 0 |

The three family rows are deduplicated across the source selectors. Pairwise selector overlap is shown below.

| Selector pair | Shared task keys |
| --- | ---: |
| Event / body | 192 |
| Event / footprint | 67 |
| Event / fine phase | 32 |
| Body / footprint | 247 |
| Body / fine phase | 108 |
| Footprint / fine phase | 61 |
| Body / restart | 3 |
| Body / restart turns | 3 |
| Body / restart velocity | 3 |
| Footprint / restart | 3 |
| Footprint / restart turns | 4 |
| Footprint / restart velocity | 3 |
| Fine phase / restart | 2 |
| Fine phase / restart turns | 1 |
| Fine phase / restart velocity | 2 |
| Restart / restart turns | 16 |
| Restart / restart velocity | 18 |
| Restart turns / restart velocity | 14 |

## Random source-window candidates

The stride catalogs have 7,952 complete source-positive windows. Of those, 5,934 join to a corrected map preflight with all 91 sampled centers inside the lanelet map and a directed route. Deduplication by `(recording, ego_track_id)` gives 2,966 random source-window candidates. The active locations contain 1,164 keys. Location 2 contributes 1,802 keys pending semantics review.

| Location | Unique random source-window keys by recording | Total |
| --- | --- | ---: |
| 1 | 07=31, 08=59, 09=22, 10=27, 11=31, 12=71, 13=53, 14=49, 15=31, 16=50, 17=45 | 469 |
| 2 pending | 18=126, 19=102, 20=143, 21=154, 22=167, 23=143, 24=101, 25=168, 26=192, 27=158, 28=166, 29=182 | 1,802 |
| 3 | 30=39, 31=26, 32=65 | 130 |
| 4 | 00=109, 01=85, 02=112, 03=64, 04=36, 05=66, 06=93 | 565 |

These keys have random-window provenance. A random draw assigns sampling provenance. A control label requires source review that establishes no applicable interaction, followed by the current control admission gates. Adjacent stride-50 windows are 225 source frames long and overlap by 175 frames. The rec+ego dedup prevents those repeated windows from inflating the random item count.

## Conservative overlap with existing anchors

The current 16-scene manifest provides each scene's ego and listed moving-track identities. Applying a conservative same-recording exclusion to the active interaction union removes a candidate whenever its ego or actor appears in any anchor scene's `moving_track_ids`. The 167 source keys become 142 candidates. Those remaining keys contain 56 cyclist-crossing, 33 pedestrian-crossing and 53 longitudinal-following candidates. An exact anchor-ego plus primary-interaction-actor exclusion would leave 152 keys.

Among the 142 conservative survivors, a maximum bipartite matching within each recording retains 136 tasks with one use of each ego and each primary actor in their respective roles. Capping the match at four per recording yields 66 candidate slots before accounting for existing scenes. Reserving slots for the 16 anchors leaves at most 53 additional interaction candidates under this identity-only calculation. Of the 1,164 active random keys, 1,059 have at least one map-passing window free of listed ego or nearest-actor overlap with an anchor's moving tracks. All map-passing windows meet that test for 1,043 keys.

These overlap counts use manifest identities and catalog-listed nearby actors. Before selecting a cohort, check inclusive source time intervals from `first_frame` through `first_frame + 225`, cross-role track reuse, and every moving context actor in each proposed window. These checks can reduce the counts further. The random catalogs cover nearby actors by source window and have incomplete context track coverage.

## Capacity and next source-only cohort

There are 21 active recordings across locations 1, 3 and 4. At four scenes per recording, those sites have an 84-scene ceiling. The 16 existing anchors leave at most 68 additional active-location slots under that cap. All 33 recordings permit at most 132 scenes. A 200-scene target exceeds both ceilings.

For the next review round, freeze a separate source-only review queue as a new version outside the existing v3 composition and ranking. Keep the existing composition, rank order and 16 anchors unchanged. Use up to two keys per interaction family and active location where availability permits, then add up to two random-window keys per active location. Location 3 has one pedestrian-crossing key, so this procedure yields at most 23 source-key slots before recording, actor and cross-family deduplication constraints.

Rank interaction keys by `SHA256("step2-source-cohort-v1|family|recording|ego|actor")` and random keys by `SHA256("step2-random-source-v1|location|recording|ego")`. Break a hash tie by the numeric task key. Retain all source-selector provenance and kind labels on one deduplicated task key. Select another ranked key when a recording cap or an existing independence rule rejects a candidate. Keep location 2 out until its applicable-rule semantics are resolved.

Freeze a primary window and ordered alternates with each task key. Build this list only from rows that pass the task's unchanged source screen. When a task appears in multiple selectors, rank its source rows by this fixed selector order: event fine selection, restart selection, restart turns, restart velocity, body task, footprint task, fine phase. For third-family event rows, sort ascending by `source_crossing_time_gap_s`, the absolute distance of the mean ego and actor crossing step from step 45, then `first_frame` and original row order. Derive the crossing-step midpoint as `(ego_path_crossing_step + actor_path_crossing_step) / 2`. Rows missing a gap or either crossing step follow rows with all three values, then sort by `first_frame` and original row order. For rows from other interaction selectors, sort by `first_frame`, then original row order within the selector. For random rec+ego keys, use the eligible window with the smallest `first_frame` and store the remaining eligible windows in that order as alternates. Advance from a primary only when a pre-execution source, map or task-integrity gate rejects it. Record the reason and preserve the selected alternate order before any controller run.

Random-window keys remain marked `unreviewed_random_source_candidate` in that manifest. Interaction keys retain their exact selector evidence. Every candidate still requires current task screening, manual and semantic review, physical and technical gates, applicable controller-input checks and the existing independence rule before admission. Freeze selected keys, primary and alternate windows, skipped-key reasons, source hashes, ranking version and reviewed exclusions together. Planner outcomes do not enter this procedure.

## Inputs and hashes

The listed SHA-256 values identify the exact JSON bytes read for this census. Selector files are schema 1, stride catalogs are schema 3 and corrected map preflights are schema 2. The third-family selector also records `selector_sha256` `36d94c3f23723df46e0c91856d7852520c04bc97d888fedeb739d9be601feb60`, composition SHA `559ce922b517c27abf6b43149986629d29a3579bac12dff8b375f79d51817673` and baseline-manifest SHA `344aab1b409e9c0138ede0960a1249e34ac667ec2947ded015db252685339b00`. Its `source_hashes` field binds track, track-metadata and recording-metadata files for all 33 recordings. Body, footprint and fine-phase selectors bind their source screens through their recorded input hashes. Restart selectors reference the source selectors at hashes `32c9e54117e854c915d9ddfade2253c39108cbfde01f5a74378b83e6026890fe` and `dd15d9a7c880ad0901d6086b51867874090264642511a463a2c7f634f39f88cb`. The conservative anchor check reads only scene identities and track lists from the 16-row `step2_expanded_current_manifest.json` at SHA `79d9f9aefee1e61bcfb98de14041d220ded680014394c7b6224b3ab9c4a5ac12`.

| Input | Schema | SHA-256 |
| --- | ---: | --- |
| `third_family_event_fine_selection_v1.json` | 1 | `76ef4971acddbe331fc830beb0c63d1de070a44a1d83b82912ea191c913f078a` |
| `body_task_selection.json` | 1 | `69f4f869d3cf9d65355f28f40ad1621a9bb989cb9851149378b4b86a4081ea8d` |
| `footprint_task_selection.json` | 1 | `366411ac0c9a223ace5d8884ea525c722b56aa60638f108e02aa5bc4682d4c75` |
| `fine_phase_task_selection.json` | 1 | `9a44e1fe506e2cb99fa51562189b4d6476cc016615ed049dac8e08ae42f1b899` |
| `source_restart_selection.json` | 1 | `efa2a0ddf238ed5bed16e624d2f5ded3bdb48a34b6ac9ed34d0794ee1fb80f11` |
| `source_restart_turns_selection.json` | 1 | `5d15539b4dd790aea38bfd764f7432dfc016c8f070de9ef3303f5f160e2edcf5` |
| `source_restart_velocity_selection.json` | 1 | `790082051827f9e6856380e0ea92fc6eed5923b816224739f6af26958837165c` |
| `all_moving_windows_loc1_stride50.json` | 3 | `0249dda3a8cf4bc293e0cd24b2d7484c66e4f1b9b5bc36295e1594f6408ba10a` |
| `all_moving_windows_loc23_stride50.json` | 3 | `1915d3ec06d6fca3e97a01fab82e2a446d0d09b94767d195126f94e33b542b21` |
| `all_moving_windows_loc4_stride50.json` | 3 | `ca0b2ca8f3ba2a9bca922c9e0e48841e3b4db967e3f3a3e4addfe8af38a81529` |
| `source_map_preflight_loc1_oriented_v3.json` | 2 | `db19f79ac175c05f916dc8be9c697a0b1113d700e8d6e244fe9d530e5ae2c0d9` |
| `source_map_preflight_loc23_oriented_v3.json` | 2 | `7c6d9a988d729a78c929c2dc195db475a0f5efe5761c737e8966fca8a2182f23` |
| `source_map_preflight_loc4_oriented_v3.json` | 2 | `ae7ad9135379fd7bae045c8b9c88e0e21bac2f3cef0009b341ea7371de3d3d23` |
| `step2_expanded_current_manifest.json` identity fields only | 16-row JSON array | `79d9f9aefee1e61bcfb98de14041d220ded680014394c7b6224b3ab9c4a5ac12` |

The stride source screen uses 225 source frames, a 50-frame stride, at least 15 m path, 10 m displacement, a goal sample at step 85, a 2 m goal radius, earliest goal-radius entry at step 75 and 12 m timed proximity. The map preflight requires every sampled ego center to lie in a road or bus lanelet polygon and a nearest-start-to-goal directed lane route. Planner-input fidelity and research admission require their own evidence.
