"""Exercise SMART admission failures and restore every mutated fixture."""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import json
import os
import subprocess
import hashlib
from pathlib import Path


def main():
    repo = PROJECT_ROOT
    os.chdir(repo)
    py = __import__("sys").executable
    env = dict(os.environ, MPLCONFIGDIR="/tmp/geotransfer_mpl", OMP_NUM_THREADS="2")
    root = project_path("pilot/oriented_v3/r00_e365_f22735")
    us = "pilot/probes/us_hybrid_1002fdc9826fc6d1"
    results = []

    def gate(r):
        p = subprocess.run(
            [
                py,
                str(tool_path("admit_smart_scene.py")),
                "--root",
                str(r),
                "--us-root",
                us,
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        if p.returncode not in (0, 1):
            raise RuntimeError(p.stderr[-1500:])
        report = json.loads(
            (r / "testing/admission_smart_hybrid_startup.json").read_text()
        )
        return (p.returncode, report)

    def case(name, path, mutate, expected, r=root):
        old = path.read_bytes()
        try:
            data = json.loads(old)
            mutate(data)
            path.write_text(json.dumps(data, indent=2) + "\n")
            code, report = gate(r)
            passed = code == 1 and expected in report["exclusion_reasons"]
            results.append(
                {"case": name, "passed": passed, "reasons": report["exclusion_reasons"]}
            )
            assert passed, results[-1]
        finally:
            path.write_bytes(old)

    t = root / "testing"
    case(
        "incomplete_review",
        t / "semantic_review_smart_hybrid_startup.json",
        lambda x: x.update(review_status="incomplete"),
        "manual_review_complete",
    )
    case(
        "stale_adapter_proof",
        t / "smart_map_transfer_all_actors_probe.json",
        lambda x: x["protocol_file_sha256"].update(adapter="0" * 64),
        "german_input_probe_current",
    )
    case(
        "stale_expert_velocity_state",
        t / "smart_map_transfer_all_actors_probe.json",
        lambda x: x["source_feature_audit"].update(max_evaluator_velocity_error_mps=10),
        "german_source_features_faithful",
    )
    case(
        "stale_us_traffic_mechanics",
        project_path("pilot/audits/hybrid_protocol_us_parity.json"),
        lambda x: x.update(runtime_source_sha256="0" * 16),
        "traffic_us_mechanics_current",
    )

    def omit(x):
        for row in x["rollout"]:
            row["model_track_ids"] = [
                i for i in row.get("model_track_ids", []) if i != 351
            ]

    case(
        "missing_claimed_pedestrian",
        t / "smart_map_transfer_all_actors_probe.json",
        omit,
        "claimed_actors_reach_model_at_encounter",
    )
    case(
        "wrong_provider_image_scale",
        t / "source_image_registration.json",
        lambda x: x.update(pixel_scale_m=x["pixel_scale_m"] * 10 / 12),
        "manual_review_current",
    )
    f = project_path("pilot/oriented_v3/r15_e332_f25626")

    def claim(x):
        x.update(
            interaction_opportunity=True,
            interaction_actor_ids=[324],
            eligible_interaction_types=["lead_vehicle_braking_response"],
        )

    case(
        "false_following_claim_goal_before_queue",
        f / "testing/semantic_review_smart_hybrid_startup.json",
        claim,
        "longitudinal_goal_requires_claimed_response",
        r=f,
    )

    def restart_claim(x):
        x.update(
            interaction_opportunity=True,
            interaction_actor_ids=[324],
            eligible_interaction_types=["lead_vehicle_stop_and_restart"],
        )

    case(
        "restart_goal_must_clear_stopped_leader",
        f / "testing/semantic_review_smart_hybrid_startup.json",
        restart_claim,
        "restart_goal_region_bound",
        r=f,
    )

    def creeping_claim(x):
        x.update(
            interaction_opportunity=True,
            interaction_actor_ids=[324],
            eligible_interaction_types=["lead_vehicle_constrained_following"],
        )

    case(
        "creeping_goal_must_clear_leader",
        f / "testing/semantic_review_smart_hybrid_startup.json",
        creeping_claim,
        "constrained_following_task_bound",
        r=f,
    )
    c = project_path("pilot/oriented_v3/r09_e196_f16232")

    def crossing_claim(x):
        x.update(
            interaction_opportunity=True,
            interaction_actor_ids=[197],
            eligible_interaction_types=["cyclist_crossing_ahead_turn"],
        )

    case(
        "false_crossing_from_turning_coordinate_frame",
        c / "testing/semantic_review_smart_hybrid_startup.json",
        crossing_claim,
        "crossing_claim_has_source_path_conflict",
        r=c,
    )
    s = project_path("pilot/oriented_v3/r32_e391_f21356")

    def lose_leading_context(x):
        for actor in x["actor_opportunities"]:
            if actor["track_id"] == 390:
                actor["preserved_for_claimed_interaction"] = False
                actor["matched_close_steps_after_warmup"] = 0

    case(
        "unclaimed_but_essential_leading_context",
        s / "testing/interaction_fidelity_audit_hybrid_startup.json",
        lose_leading_context,
        "essential_leading_context_preserved",
        r=s,
    )
    case(
        "stop_scope_requires_explicit_review",
        s / "testing/semantic_review_smart_hybrid_startup.json",
        lambda x: x.pop("stop_rules_outside_task", None),
        "no_unrepresented_applicable_rules",
        r=s,
    )
    case(
        "stop_scope_review_must_bind_current_proof",
        s / "testing/semantic_review_smart_hybrid_startup.json",
        lambda x: x.update(task_rule_scope_sha256="0" * 64),
        "stop_scope_review_bound",
        r=s,
    )
    leader = project_path("pilot/oriented_v3/r01_e301_f20017")
    case(
        "following_scope_requires_explicit_review",
        leader / "testing/semantic_review_smart_hybrid_startup.json",
        lambda x: x.pop("same_route_following_actor_ids", None),
        "no_unrepresented_applicable_rules",
        r=leader,
    )
    case(
        "following_scope_review_must_bind_current_proof",
        leader / "testing/semantic_review_smart_hybrid_startup.json",
        lambda x: x.update(following_scope_sha256="0" * 64),
        "following_scope_review_bound",
        r=leader,
    )

    def explicit_priority(x):
        x["details"]["source_supported_irrelevance_plausible"].append(
            "rule_1170_priority_vehicle_300_spatial_conflict"
        )

    case(
        "following_certificate_never_clears_explicit_priority",
        leader / "testing/admission_hybrid_startup.json",
        explicit_priority,
        "no_unrepresented_applicable_rules",
        r=leader,
    )
    moving = project_path("pilot/oriented_v3/r00_e321_f21017")
    lateral_scene = project_path("pilot/oriented_v3/r01_e280_f18833")
    case(
        "legal_lateral_route_requires_explicit_source_review",
        lateral_scene / "testing/semantic_review_smart_hybrid_startup.json",
        lambda x: x.pop("reviewed_source_lane_changes", None),
        "source_lateral_route_review_bound",
        r=lateral_scene,
    )
    case(
        "legal_lateral_route_requires_current_sequence",
        lateral_scene / "testing/semantic_review_smart_hybrid_startup.json",
        lambda x: x.update(source_route_sequence_sha256="0" * 64),
        "source_lateral_route_review_bound",
        r=lateral_scene,
    )
    case(
        "legal_lateral_route_requires_native_permission_proof",
        project_path("pilot/audits/source_lane_change_native_oracle.json"),
        lambda x: x.update(lane_change_tool_sha256="0" * 64),
        "legal_lane_change_oracle_current",
        r=lateral_scene,
    )
    case(
        "crosswalk_preprocessing_must_match_across_domains",
        lateral_scene / "testing/smart_map_transfer_all_actors_probe.json",
        lambda x: x.update(map_encoding_protocol="upstream_sparse"),
        "shared_map_encoding_protocol",
        r=lateral_scene,
    )
    case(
        "actual_model_must_receive_crosswalk_tokens",
        lateral_scene / "testing/smart_map_transfer_all_actors_probe.json",
        lambda x: x.update(actual_planner_crosswalk_tokens=0),
        "actual_planner_map_tokens",
        r=lateral_scene,
    )
    directed = project_path("pilot/oriented_v3/r09_e136_f11030")
    case(
        "directed_scope_requires_explicit_review",
        directed / "testing/semantic_review_smart_hybrid_startup.json",
        lambda x: x.pop("non_ego_yield_rule_ids", None),
        "no_unrepresented_applicable_rules",
        r=directed,
    )
    case(
        "directed_scope_requires_current_proof",
        directed / "testing/semantic_review_smart_hybrid_startup.json",
        lambda x: x.update(directed_rule_scope_sha256="0" * 64),
        "directed_rule_scope_review_bound",
        r=directed,
    )
    case(
        "directed_scope_cannot_clear_uncertified_rule",
        directed / "testing/semantic_review_smart_hybrid_startup.json",
        lambda x: x.update(non_ego_yield_rule_ids=[2169, 2177, 2175]),
        "directed_rule_scope_review_bound",
        r=directed,
    )

    def false_full_stop(x):
        x.update(eligible_interaction_types=["lead_vehicle_stop_and_restart"])

    case(
        "moving_follower_is_not_a_full_stop_restart",
        moving / "testing/semantic_review_smart_hybrid_startup.json",
        false_full_stop,
        "restart_goal_region_bound",
        r=moving,
    )
    for r in (root, f, c, s, leader, moving, directed, lateral_scene):
        code, report = gate(r)
        assert code == 0, report["exclusion_reasons"]
        results.append({"case": "restored_" + r.name, "passed": True})
    review = t / "semantic_review_smart_hybrid_startup.json"
    old = review.read_bytes()
    try:
        x = json.loads(old)
        x["source_surface_evidence"] += " Stale evidence regression."
        review.write_text(json.dumps(x))
        p = subprocess.run(
            [
                py,
                str(tool_path("probe_faithful_smart_closed_loop.py")),
                "--root",
                str(root),
                "--require-admission",
                "--steps",
                "1",
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        passed = p.returncode != 0 and "Missing or stale SMART admission" in p.stderr
        results.append({"case": "runner_rejects_changed_evidence", "passed": passed})
        assert passed, p.stderr[-1000:]
    finally:
        review.write_bytes(old)
    out = {
        "gate_sha256": hashlib.sha256(
            tool_path("admit_smart_scene.py").read_bytes()
        ).hexdigest(),
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases": results,
        "passed": all((r["passed"] for r in results)),
    }
    project_path("pilot/audits/step2_smart_gate_regressions.json").write_text(
        json.dumps(out, indent=2) + "\n"
    )
    print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
