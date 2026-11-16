# Old-to-new entrypoints

All old root-level commands are replaced. Append the old arguments to the new command.
`check tool` exposes retained specialist diagnostics; archived variants require explicit restoration.

| Previous script | Replacement | Responsibility |
| --- | --- | --- |
| `run_pilot_eval.py` | `geotransfer check tool run_pilot_eval` | planners |
| `probe_counterfactual.py` | `geotransfer validate counterfactual` | validation |
| `prefilter_semantic_candidates.py` | `geotransfer check tool prefilter_semantic_candidates` | corpus |
| `probe_source_route_sequence.py` | `geotransfer check route` | Independent regression |
| `background_route_intent.py` | `geotransfer check tool background_route_intent` | runtime |
| `render_overlap_reference.py` | `geotransfer check tool render_overlap_reference` | visualization |
| `freeze_smart_protocol.py` | `geotransfer corpus freeze` | corpus |
| `probe_expert_velocity_runtime.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `audit_map_semantics.py` | `geotransfer validate semantics` | maps |
| `render_rule_review.py` | `geotransfer check tool render_rule_review` | visualization |
| `expert_velocity_runtime.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `run_smart_manifest.py` | `geotransfer check tool run_smart_manifest` | planners |
| `catalog_cyclist_encounters.py` | `geotransfer corpus cyclists` | corpus |
| `register_background.py` | `geotransfer validate registration` | visualization |
| `probe_source_speed_traffic.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `source_branch_runtime.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `build_smart_pilot_manifest.py` | `geotransfer corpus build` | corpus |
| `coverage_reference_runtime.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `validate_replay.py` | `geotransfer validate replay` | validation |
| `find_turn_candidates.py` | `geotransfer check tool find_turn_candidates` | corpus |
| `probe_lanelet_orientation.py` | `geotransfer check orientation` | Independent regression |
| `probe_startup_departure.py` | `geotransfer check startup` | Independent regression |
| `scene_contract.py` | `geotransfer check tool scene_contract` | validation |
| `screen_vru_candidates.py` | `geotransfer check tool screen_vru_candidates` | corpus |
| `probe_lead_response.py` | `geotransfer check tool probe_lead_response` | validation |
| `probe_repeat_reset.py` | `geotransfer validate reset` | validation |
| `audit_task_interactions.py` | `geotransfer check tool audit_task_interactions` | validation |
| `preflight_source_map.py` | `geotransfer corpus preflight` | maps |
| `probe_queue_pair_identity.py` | `geotransfer check queue` | Independent regression |
| `late_spawn_runtime.py` | `geotransfer check tool late_spawn_runtime` | runtime |
| `report_step2_flow.py` | `geotransfer corpus report` | corpus |
| `audit_directed_rule_scope.py` | `geotransfer validate directed-rule` | maps |
| `validate_parked.py` | `geotransfer validate parked` | validation |
| `audit_crop.py` | `geotransfer check tool audit_crop` | validation |
| `source_reference_runtime.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `probe_traffic_route.py` | `geotransfer check tool probe_traffic_route` | validation |
| `select_third_family.py` | `geotransfer corpus select-cyclists` | corpus |
| `faithful_smart.py` | `geotransfer check tool faithful_smart` | planners |
| `audit_physical_source.py` | `geotransfer validate physical` | validation |
| `screen_ind_windows.py` | `geotransfer check tool screen_ind_windows` | corpus |
| `admit_scene.py` | `geotransfer validate technical` | validation |
| `probe_map_feature_visibility.py` | `geotransfer check tool probe_map_feature_visibility` | validation |
| `faithful_map.py` | `geotransfer check tool faithful_map` | planners |
| `audit_interaction_fidelity.py` | `geotransfer validate interaction` | validation |
| `full_gate_prefiltered.py` | `geotransfer check tool full_gate_prefiltered` | corpus |
| `audit_scene.py` | `geotransfer validate map` | maps |
| `admit_smart_scene.py` | `geotransfer validate smart` | validation |
| `source_guided_traffic.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `probe_hybrid_protocol_parity.py` | `geotransfer validate us-traffic` | validation |
| `audit_following_scope.py` | `geotransfer validate following` | maps |
| `run_oriented_candidate_queue.py` | `geotransfer corpus screen` | corpus |
| `probe_task_rule_scope.py` | `geotransfer check task-rule` | Independent regression |
| `validate_spawn.py` | `geotransfer validate spawn` | validation |
| `pilot_ind.py` | `geotransfer convert` | conversion |
| `probe_source_guided_idm.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `audit_rule_applicability.py` | `geotransfer validate rules` | maps |
| `find_vru_candidates.py` | `geotransfer check tool find_vru_candidates` | corpus |
| `probe_faithful_smart_closed_loop.py` | `geotransfer check tool probe_faithful_smart_closed_loop` | planners |
| `probe_source_speed_response.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `probe_source_restart_screen.py` | `geotransfer check restart` | Independent regression |
| `probe_us_reference_parity.py` | `geotransfer validate us` | validation |
| `probe_hybrid_traffic.py` | `geotransfer check tool probe_hybrid_traffic` | validation |
| `audit_task_rule_scope.py` | `geotransfer validate task-rule` | maps |
| `probe_faithful_map.py` | `geotransfer check map` | Independent regression |
| `probe_source_route_traffic.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `probe_directed_rule_scope.py` | `geotransfer check directed-rule` | Independent regression |
| `audit_final_corpus_targets.py` | `geotransfer corpus targets` | corpus |
| `catalog_ind_windows.py` | `geotransfer corpus catalog` | corpus |
| `probe_source_speed_us.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `expand_source_phase_queue.py` | `geotransfer corpus phases` | corpus |
| `probe_source_reentry.py` | `geotransfer check reentry` | Independent regression |
| `selective_reference_runtime.py` | Recoverable archive | Superseded runtime/traffic experiment; exact implementation retained in legacy-v1 archive. |
| `source_lane_changes.py` | `geotransfer check tool source_lane_changes` | maps |
| `probe_source_lane_changes.py` | `geotransfer check lane-changes` | Independent regression |
| `probe_background_route_policy.py` | `geotransfer check background` | Independent regression |
| `audit_parked_contacts.py` | `geotransfer check tool audit_parked_contacts` | validation |
| `screen_source_restarts.py` | `geotransfer corpus restarts` | corpus |
| `probe_parked_interaction.py` | `geotransfer check tool probe_parked_interaction` | validation |
| `probe_smart_admission_regressions.py` | `geotransfer check admission` | Independent regression |
| `probe_smart_map_transfer.py` | `geotransfer validate smart-input` | planners |
| `hybrid_traffic.py` | `geotransfer check tool hybrid_traffic` | runtime |
| `select_oriented_candidates.py` | `geotransfer corpus select` | corpus |
| `build_step2_corpus.py` | `geotransfer corpus build-technical` | corpus |
| `audit_goal_reporting.py` | `geotransfer check tool audit_goal_reporting` | validation |
| `screen_source_tasks.py` | `geotransfer corpus tasks` | corpus |
| `audit_source_route_sequence.py` | `geotransfer validate route` | maps |
| `audit_corpus_access.py` | `geotransfer corpus access` | corpus |
| `scan_stationary.py` | `geotransfer check tool scan_stationary` | corpus |
| `screen_source_interactions.py` | `geotransfer corpus interactions` | corpus |
| `probe_eval_replay.py` | `geotransfer check tool probe_eval_replay` | validation |
| `probe_following_scope.py` | `geotransfer check following` | Independent regression |
| `trace_eval_lifecycle.py` | `geotransfer validate lifecycle` | validation |
