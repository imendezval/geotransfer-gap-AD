"""Refresh and check a scene under the actual BehaviorBench evaluation contract.

Technical admission establishes source reconstruction. Research admission also
requires current source-linked semantic evidence and an explicit scene review.
"""

from geotransfer_gap.validation.scene_contract import contracts_equal
from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from geotransfer_gap.validation import scene_contract
from geotransfer_gap.validation.audit_interaction_fidelity import source_evidence_digest


def main():
    HERE = PROJECT_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument(
        "--no-refresh",
        action="store_true",
        help="Inspect existing reports without admission",
    )
    ap.add_argument(
        "--research",
        action="store_true",
        help="Exit successfully only for research admission",
    )
    ap.add_argument(
        "--traffic-protocol", choices=("idm", "hybrid_startup"), default="idm"
    )
    args = ap.parse_args()
    root = args.root.resolve()
    testing = root / "testing"
    commands = [
        ["audit_scene.py"],
        ["audit_map_semantics.py"],
        ["audit_rule_applicability.py"],
        ["audit_physical_source.py"],
        ["validate_replay.py", "--late-runtime"],
        ["probe_eval_replay.py"],
        ["validate_spawn.py", "--eval-config"],
        ["validate_parked.py", "--eval-config"],
        ["trace_eval_lifecycle.py", "--traffic-mode", "expert"],
        ["trace_eval_lifecycle.py", "--traffic-mode", "idm"],
        ["audit_interaction_fidelity.py"],
        ["probe_counterfactual.py", "--lateral-offset-m", "1"],
        ["scene_contract.py", "--traffic-mode", "expert"],
    ]
    if args.traffic_protocol == "hybrid_startup":
        commands[-1:-1] = [
            ["trace_eval_lifecycle.py", "--traffic-mode", "hybrid_startup"],
            ["audit_interaction_fidelity.py", "--traffic-mode", "hybrid_startup"],
            [
                "probe_counterfactual.py",
                "--lateral-offset-m",
                "1",
                "--include-hybrid",
                "--require-hybrid",
                "--report-name",
                "counterfactual_hybrid_probe.json",
            ],
        ]
    late_ids = json.loads((testing / "validation.json").read_text()).get(
        "source_late_arriving_track_ids", []
    )
    if late_ids:
        commands.insert(-1, ["probe_repeat_reset.py", "--eval-config", "--cycles", "3"])
    refresh_errors = {}
    if not args.no_refresh:
        for command in commands:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(project_path(command[0])),
                    "--root",
                    str(root),
                    *command[1:],
                ],
                capture_output=True,
                text=True,
            )
            if proc.returncode:
                refresh_errors[command[0]] = (proc.stderr or proc.stdout)[-1200:]
    checks = {}
    details = {}

    def check(name, ok, detail=None):
        checks[name] = bool(ok)
        if detail is not None:
            details[name] = detail

    def report(name):
        path = testing / name
        if not path.is_file():
            check("exists:" + name, False, "missing")
            return None
        try:
            value = json.loads(path.read_text())
        except (ValueError, OSError) as error:
            check("exists:" + name, False, str(error))
            return None
        check("exists:" + name, True)
        return value

    current = scene_contract.build(root, "expert")

    def provider_registration_valid(registration):
        meta_path = Path(current["files"]["source_recording_meta_csv"]["path"])
        with meta_path.open() as stream:
            meta = next(csv.DictReader(stream))
        return (
            registration.get("schema_version") == 2
            and registration.get("registration_is_estimate") is False
            and (registration.get("local_x_at_image_x0_m") == 0.0)
            and (registration.get("local_y_at_image_y0_m") == 0.0)
            and math.isclose(
                registration.get("pixel_scale_m", -1),
                map_geometry.background_pixel_scale(meta),
                abs_tol=1e-10,
            )
        )

    binary_hash = current["files"]["scene_binary"]["sha256"]
    ini_hash = current["files"]["evaluation_ini"]["sha256"]
    runtime_hash = current["runtime_source_sha256"]
    contract = report("evaluation_contract_expert.json")
    check("contract_current", contracts_equal(contract, current))
    check(
        "evaluator_settings",
        current["evaluator_env"]
        == {
            "dt": "0.1",
            "goal_behavior": "3",
            "termination_mode": "1",
            "collision_behavior": "2",
            "offroad_behavior": "2",
            "collision_shrink": "1.0",
            "episode_length": "91",
        },
    )
    check("behavior_bench_clean", not current["behavior_bench_dirty"])
    validation = report("validation.json")
    scene = None
    if validation:
        check(
            "binary_round_trip",
            validation.get("binary_sha256") == binary_hash
            and validation.get("max_binary_position_error_m", float("inf")) < 0.01,
        )
        check("ego_route", validation.get("ego_goal_lane_reachable_by_successors"))
        check(
            "no_actor_crop",
            not validation.get("explicit_excluded_track_ids")
            and (not validation.get("excluded_distant_static_track_ids")),
        )
        check(
            "continuation_goals", validation.get("background_goal_mode") == "continue"
        )
        scene_files = list(testing.glob("ind_*.json"))
        if len(scene_files) == 1:
            scene = json.loads(scene_files[0].read_text())
            ego_obj = scene["objects"][0]
            ego_goal = ego_obj["goalPosition"]
            first_goal_hit = next(
                (
                    t
                    for t, pos in enumerate(ego_obj["position"])
                    if ego_obj["valid"][t]
                    and math.dist((pos["x"], pos["y"]), (ego_goal["x"], ego_goal["y"]))
                    <= 2.0
                ),
                None,
            )
            check(
                "goal_placed_near_window_end",
                first_goal_hit is not None
                and first_goal_hit >= 75
                and (validation.get("ego_goal_sample") == 85),
                {
                    "first_source_goal_radius_step": first_goal_hit,
                    "required_earliest_step": 75,
                },
            )
            bad_goals = []
            for obj in scene["objects"][1:]:
                if obj["type"] != "vehicle" or obj["mark_as_expert"]:
                    continue
                goal = obj["goalPosition"]
                clearance = min(
                    (
                        math.dist((p["x"], p["y"]), (goal["x"], goal["y"]))
                        for p, valid in zip(obj["position"], obj["valid"])
                        if valid
                    )
                )
                if clearance <= 4.0:
                    bad_goals.append((obj["id"], clearance))
            check("background_goals_clear_source", not bad_goals, bad_goals[:10])
        else:
            check(
                "goal_placed_near_window_end", False, "scene JSON missing or ambiguous"
            )
            check(
                "background_goals_clear_source",
                False,
                "scene JSON missing or ambiguous",
            )
    geometry = report("map_audit.json")
    if geometry:
        check(
            "geometry_source_current",
            geometry.get("source_map_sha256")
            == current["files"]["source_lanelet2_map"]["sha256"],
        )
        from geotransfer_gap.maps import source_lane_changes

        oracle_path = project_path("pilot/audits/source_lane_change_native_oracle.json")
        oracle = json.loads(oracle_path.read_text()) if oracle_path.is_file() else {}
        lateral_current = (
            oracle.get("passed")
            and oracle.get("lane_change_tool_sha256")
            == sha(Path(source_lane_changes.__file__))
            and (oracle.get("converter_sha256") == sha(project_path("pilot_ind.py")))
            and any(
                (
                    row.get("source_sha256")
                    == current["files"]["source_lanelet2_map"]["sha256"]
                    for row in oracle.get("maps", [])
                )
            )
        )
        route_ok = geometry.get(
            "occupied_start_to_occupied_goal_reachable_following_only"
        ) or (
            lateral_current
            and geometry.get("occupied_start_to_occupied_goal_reachable")
        )
        check("ego_route", checks["geometry_source_current"] and route_ok)
        check("legal_lateral_route_permissions_current", bool(lateral_current))
        check(
            "geometry",
            not geometry.get("ego_samples_outside_lanelet_polygons")
            and (not geometry.get("successors_direction_reversed"))
            and (geometry.get("successors_with_no_boundary_ids_shared") == 0)
            and geometry.get("occupied_start_to_occupied_goal_reachable"),
        )
    semantics = report("map_semantics_audit.json")
    if semantics:
        check(
            "semantics_current",
            semantics.get("binary_sha256") == binary_hash
            and semantics.get("lanelet_source_sha256")
            == current["files"]["source_lanelet2_map"]["sha256"]
            and (
                semantics.get("opendrive_source_sha256")
                == current["files"]["source_opendrive_map"]["sha256"]
            ),
        )
        check(
            "semantic_screen",
            semantics.get("semantic_screen_pass"),
            {
                "unencoded_priority": semantics.get(
                    "ego_has_unencoded_priority_relation"
                ),
                "unencoded_sign": semantics.get("ego_has_unencoded_sign_within_5m"),
                "unencoded_crosswalk": semantics.get("ego_crosses_unencoded_crosswalk"),
            },
        )
    rule_audit = report("rule_applicability_audit.json")
    if rule_audit:
        check(
            "rule_audit_current",
            rule_audit.get("schema_version") == 10
            and rule_audit.get("binary_sha256") == binary_hash
            and (
                rule_audit.get("lanelet_source_sha256")
                == current["files"]["source_lanelet2_map"]["sha256"]
            )
            and (
                rule_audit.get("opendrive_source_sha256")
                == current["files"]["source_opendrive_map"]["sha256"]
            )
            and (
                rule_audit.get("source_tracks_sha256")
                == current["files"]["source_tracks_csv"]["sha256"]
            )
            and (rule_audit.get("ego_track_id") == current["ego_track_id"]),
        )
        unsupported = []
        if any(
            (
                sign.get("subtype") == "de206"
                for rule in rule_audit.get("governing_regulatory_elements", [])
                if any((member["role"] == "yield" for member in rule["ego_members"]))
                for sign in rule.get("signs", [])
            )
        ):
            unsupported.append(
                "ego_stop_sign_requires_stop_even_without_conflicting_traffic"
            )
        for rule in rule_audit.get("governing_regulatory_elements", []):
            if not any((member["role"] == "yield" for member in rule["ego_members"])):
                continue
            unsupported.extend(
                (
                    f"rule_{rule['id']}_priority_{actor['type']}_{actor['track_id']}_spatial_conflict"
                    for actor in rule_audit.get("priority_lane_traffic", [])
                    if actor.get("actor_source_path_m", 0) > 1
                    and actor.get("minimum_spatial_box_gap_m", float("inf")) <= 2
                    and any(
                        (
                            actor.get("priority_lanelet_steps", {}).get(str(lid))
                            for lid in rule["priority_lanelets"]
                        )
                    )
                )
            )
        unsupported.extend(
            (
                f"implicit_oncoming_turn_priority_{actor['type']}_{actor['track_id']}"
                for actor in rule_audit.get("oncoming_turn_conflicts", [])
            )
        )
        unsupported.extend(
            (
                f"slow_ego_fast_crosspath_{actor['type']}_{actor['track_id']}"
                for actor in rule_audit.get("slow_ego_fast_crosspath_conflicts", [])
            )
        )
        unsupported.extend(
            (
                f"yield_lane_fast_crosspath_{actor['type']}_{actor['track_id']}"
                for actor in rule_audit.get("yield_lane_fast_crosspath_conflicts", [])
            )
        )
        unsupported.extend(
            (
                f"crosswalk_{cw['lanelet_id']}_vru_{vru['track_id']}"
                for cw in rule_audit.get("ego_box_crosswalk_contacts", [])
                if cw.get("ego_box_contact_steps")
                for vru in cw.get("nearby_vrus", [])
                if vru.get("minimum_distance_to_crosswalk_m", float("inf")) <= 5
            )
        )
        check("source_supported_irrelevance_plausible", not unsupported, unsupported)
    review_name = (
        "semantic_review.json"
        if args.traffic_protocol == "idm"
        else "semantic_review_hybrid_startup.json"
    )
    interaction_name = (
        "interaction_fidelity_audit.json"
        if args.traffic_protocol == "idm"
        else "interaction_fidelity_audit_hybrid_startup.json"
    )
    review = report(review_name)
    interaction_audit = report(interaction_name)
    if interaction_audit:
        idm_trace_path = testing / f"lifecycle_trace_{args.traffic_protocol}.json"
        rule_audit_path = testing / "rule_applicability_audit.json"
        check(
            "interaction_audit_current",
            interaction_audit.get("schema_version") == 3
            and interaction_audit.get("traffic_mode") == args.traffic_protocol
            and (interaction_audit.get("binary_sha256") == binary_hash)
            and (interaction_audit.get("ego_track_id") == current["ego_track_id"])
            and (interaction_audit.get("evaluation_ini_sha256") == ini_hash)
            and (interaction_audit.get("runtime_source_sha256") == runtime_hash)
            and idm_trace_path.is_file()
            and (interaction_audit.get("idm_trace_sha256") == sha(idm_trace_path))
            and rule_audit_path.is_file()
            and (interaction_audit.get("rule_audit_sha256") == sha(rule_audit_path))
            and (
                interaction_audit.get("source_evidence_digest")
                == source_evidence_digest(interaction_audit)
            ),
        )
    if review:
        audit_path = testing / "rule_applicability_audit.json"
        image_path = testing / review.get("source_image", "missing_image")
        registration_path = testing / "source_image_registration.json"
        registration = (
            json.loads(registration_path.read_text())
            if registration_path.is_file()
            else {}
        )
        check(
            "semantic_review_current",
            rule_audit is not None
            and audit_path.is_file()
            and (review.get("rule_audit_sha256") == sha(audit_path))
            and (review.get("binary_sha256") == binary_hash)
            and (review.get("ego_track_id") == current["ego_track_id"])
            and image_path.is_file()
            and (review.get("source_image_sha256") == sha(image_path))
            and (
                registration.get("background_sha256")
                == current["files"]["source_background_image"]["sha256"]
            )
            and (registration.get("binary_sha256") == binary_hash)
            and (registration.get("recording") == current["recording"])
            and provider_registration_valid(registration),
        )
        expected_rules = (
            {r["id"] for r in rule_audit.get("governing_regulatory_elements", [])}
            if rule_audit
            else set()
        )
        expected_crosswalks = (
            {r["lanelet_id"] for r in rule_audit.get("ego_box_crosswalk_contacts", [])}
            if rule_audit
            else set()
        )
        expected_signs = (
            {r["id"] for r in rule_audit.get("nearby_source_signs", [])}
            if rule_audit
            else set()
        )
        expected_markings = (
            {r["id"] for r in rule_audit.get("nearby_omitted_markings", [])}
            if rule_audit
            else set()
        )
        expected_boundaries = (
            {r["way_id"] for r in rule_audit.get("ego_lanelet_boundaries", [])}
            if rule_audit
            else set()
        )
        resolutions = review.get("rule_resolutions", [])
        reviewed_rules = {
            r.get("source_id")
            for r in resolutions
            if r.get("kind") == "regulatory_element"
        }
        reviewed_crosswalks = {
            r.get("source_id") for r in resolutions if r.get("kind") == "crosswalk"
        }
        reviewed_signs = {
            r.get("source_id") for r in resolutions if r.get("kind") == "sign"
        }
        reviewed_markings = {
            r.get("source_id")
            for r in resolutions
            if r.get("kind") == "omitted_marking"
        }
        surface_steps = review.get("source_surface_steps")
        decision_steps = review.get("interaction_decision_steps")
        check(
            "semantic_review_complete",
            review.get("schema_version") == 2
            and review.get("review_status") == "complete"
            and (review.get("decision") == "admit")
            and (review.get("scope") == "recorded_window_and_tested_interaction")
            and bool(review.get("eligible_interaction_types"))
            and (reviewed_rules == expected_rules)
            and (reviewed_crosswalks == expected_crosswalks)
            and (reviewed_signs == expected_signs)
            and (reviewed_markings == expected_markings)
            and (
                set(review.get("reviewed_boundary_way_ids", [])) == expected_boundaries
            )
            and (
                len(resolutions)
                == len(expected_rules)
                + len(expected_crosswalks)
                + len(expected_signs)
                + len(expected_markings)
            )
            and all(
                (
                    r.get("resolution") == "source_supported_irrelevance"
                    and len(r.get("source_evidence", "")) >= 80
                    and isinstance(r.get("source_steps"), list)
                    and r["source_steps"]
                    for r in resolutions
                )
            )
            and (len(review.get("boundary_and_lane_change_evidence", "")) >= 80)
            and (len(review.get("source_surface_evidence", "")) >= 100)
            and isinstance(surface_steps, list)
            and (len(set(surface_steps)) >= 3)
            and all((isinstance(x, int) and 0 <= x <= 90 for x in surface_steps)),
        )
        claimed_ids = review.get("interaction_actor_ids")
        opportunities = (
            {x["track_id"]: x for x in interaction_audit.get("actor_opportunities", [])}
            if interaction_audit
            else {}
        )
        check(
            "interaction_claim_supported",
            review.get("interaction_source_digest")
            == (
                interaction_audit.get("source_evidence_digest")
                if interaction_audit
                else None
            )
            and isinstance(claimed_ids, list)
            and (
                bool(claimed_ids)
                if review.get("interaction_opportunity")
                else claimed_ids == []
            )
            and (
                all(
                    (
                        x.startswith("uncontested_")
                        for x in review.get("eligible_interaction_types", [])
                    )
                )
                if not review.get("interaction_opportunity")
                else True
            )
            and (
                len(review.get("interaction_decision_evidence", "")) >= 120
                and isinstance(decision_steps, list)
                and (len(set(decision_steps)) >= 2)
                and all(
                    (
                        isinstance(x, int)
                        and 0 <= x < interaction_audit.get("idm_observed_steps", 0)
                        for x in decision_steps
                    )
                )
                and all(
                    (
                        any(
                            (
                                abs(x - opportunities[i]["source_box_step"]) <= 10
                                for x in decision_steps
                            )
                        )
                        for i in claimed_ids
                        if i in opportunities
                    )
                )
                if review.get("interaction_opportunity")
                else True
            )
            and all(
                (
                    opportunities.get(i, {}).get("preserved_for_claimed_interaction")
                    for i in claimed_ids
                )
            ),
            (
                {i: opportunities.get(i) for i in claimed_ids}
                if isinstance(claimed_ids, list)
                else None
            ),
        )
    physical = report("physical_source_audit.json")
    if physical:
        ego = str(current["ego_track_id"])
        overlaps = physical.get("source_box_actor_overlaps", {})
        check(
            "physical_source_current",
            physical.get("schema_version") == 2
            and physical.get("binary_sha256") == binary_hash
            and (
                physical.get("lanelet_source_sha256")
                == current["files"]["source_lanelet2_map"]["sha256"]
            )
            and (physical.get("collision_scale") == 1.0)
            and math.isclose(
                physical.get("stationary_overlap_tolerance_m", -1),
                3 * physical.get("source_background_pixel_scale_m", 0),
                abs_tol=1e-06,
            ),
        )
        check(
            "ego_boundary_clear",
            ego not in physical.get("source_box_boundary_contacts", {}),
        )
        if overlaps:
            overlap_review = report("physical_overlap_review.json")
            if overlap_review:
                overlap_image = testing / overlap_review.get(
                    "source_image", "missing_image"
                )
                registration_path = testing / "source_image_registration.json"
                registration = (
                    json.loads(registration_path.read_text())
                    if registration_path.is_file()
                    else {}
                )
                check(
                    "physical_overlap_review_current",
                    overlap_review.get("schema_version") == 1
                    and overlap_review.get("physical_audit_sha256")
                    == sha(testing / "physical_source_audit.json")
                    and (overlap_review.get("binary_sha256") == binary_hash)
                    and overlap_image.is_file()
                    and (
                        overlap_review.get("source_image_sha256") == sha(overlap_image)
                    )
                    and (
                        registration.get("background_sha256")
                        == current["files"]["source_background_image"]["sha256"]
                    )
                    and (registration.get("binary_sha256") == binary_hash)
                    and (registration.get("recording") == current["recording"])
                    and provider_registration_valid(registration),
                )
                if (
                    overlap_review.get("source_image")
                    == "physical_overlap_evidence.png"
                ):
                    evidence_path = testing / "physical_overlap_evidence.json"
                    evidence = (
                        json.loads(evidence_path.read_text())
                        if evidence_path.is_file()
                        else {}
                    )
                    source_dir = Path(
                        current["files"]["source_tracks_csv"]["path"]
                    ).parent
                    reference_recording = evidence.get("reference_recording")
                    reference_root = Path(
                        evidence.get("reference_scene_root", "/missing")
                    )
                    reference_background = (
                        source_dir / f"{reference_recording:02d}_background.png"
                        if isinstance(reference_recording, int)
                        else Path("/missing")
                    )
                    reference_tracks = (
                        source_dir / f"{reference_recording:02d}_tracks.csv"
                        if isinstance(reference_recording, int)
                        else Path("/missing")
                    )
                    reference_registration = (
                        reference_root / "testing/source_image_registration.json"
                    )
                    reference_meta = (
                        source_dir / f"{reference_recording:02d}_recordingMeta.csv"
                        if isinstance(reference_recording, int)
                        else Path("/missing")
                    )
                    target_meta = (
                        source_dir / f"{current['recording']:02d}_recordingMeta.csv"
                    )
                    same_site = False
                    if reference_meta.is_file() and target_meta.is_file():
                        source_rows = [
                            next(csv.DictReader(path.open()))
                            for path in (target_meta, reference_meta)
                        ]
                        same_site = all(
                            (
                                source_rows[0][key] == source_rows[1][key]
                                for key in ("locationId", "xUtmOrigin", "yUtmOrigin")
                            )
                        )
                    evidence_pairs = evidence.get("pairs", [])
                    check(
                        "cross_record_aerial_evidence_current",
                        evidence.get("schema_version") == 1
                        and evidence.get("target_recording") == current["recording"]
                        and (evidence.get("target_binary_sha256") == binary_hash)
                        and (
                            evidence.get("target_physical_audit_sha256")
                            == sha(testing / "physical_source_audit.json")
                        )
                        and (
                            evidence.get("target_background_sha256")
                            == current["files"]["source_background_image"]["sha256"]
                        )
                        and (
                            evidence.get("target_registration_sha256")
                            == sha(registration_path)
                        )
                        and reference_background.is_file()
                        and reference_tracks.is_file()
                        and reference_registration.is_file()
                        and same_site
                        and (
                            evidence.get("reference_background_sha256")
                            == sha(reference_background)
                        )
                        and (
                            evidence.get("reference_tracks_sha256")
                            == sha(reference_tracks)
                        )
                        and (
                            evidence.get("reference_registration_sha256")
                            == sha(reference_registration)
                        )
                        and (
                            overlap_review.get("cross_record_evidence_sha256")
                            == sha(evidence_path)
                        )
                        and (evidence.get("image_sha256") == sha(overlap_image))
                        and (
                            {p.get("pair_id") for p in evidence_pairs} == set(overlaps)
                        )
                        and (len(evidence_pairs) == len(overlaps))
                        and all(
                            (
                                p.get("aerial_recording")
                                in (current["recording"], reference_recording)
                                and (
                                    p.get("aerial_recording") == current["recording"]
                                    or len(p.get("cross_record_matches", [])) == 2
                                )
                                for p in evidence_pairs
                            )
                        ),
                    )
                decisions = overlap_review.get("pair_resolutions", [])
                check(
                    "physical_overlap_review_complete",
                    overlap_review.get("decision") == "resolved"
                    and {r.get("pair_id") for r in decisions} == set(overlaps)
                    and (len(decisions) == len(overlaps))
                    and all(
                        (
                            r.get("resolution")
                            == "minor_stationary_source_box_annotation_overlap"
                            and len(r.get("source_evidence", "")) >= 80
                            and r.get("source_steps")
                            for r in decisions
                        )
                    ),
                )
            overlap_details = physical.get("source_box_actor_overlap_details", {})
            check(
                "source_box_overlaps_resolved",
                set(overlap_details) == set(overlaps)
                and all(
                    (
                        d.get("reviewable_annotation_overlap")
                        for d in overlap_details.values()
                    )
                )
                and checks.get("physical_overlap_review_current", False)
                and checks.get("physical_overlap_review_complete", False),
                {
                    k: {
                        "penetration_m": v.get("maximum_penetration_m"),
                        "ego_box_gap_m": v.get("minimum_ego_box_gap_m"),
                        "reviewable": v.get("reviewable_annotation_overlap"),
                    }
                    for k, v in overlap_details.items()
                },
            )
        else:
            check("source_box_overlaps_resolved", True)
    replay = report("replay_validation.json")
    if replay:
        check(
            "round_trip_replay",
            replay.get("binary_sha256") == binary_hash
            and replay.get("runtime", {}).get("runtime_source_sha256") == runtime_hash
            and (replay.get("test_termination_mode") == 1)
            and replay.get("replay_passed"),
        )
    eval_replay = report("evaluation_replay_probe.json")
    if eval_replay:
        check(
            "evaluation_replay",
            eval_replay.get("binary_sha256") == binary_hash
            and eval_replay.get("evaluation_ini_sha256") == ini_hash
            and (
                eval_replay.get("runtime", {}).get("runtime_source_sha256")
                == runtime_hash
            )
            and eval_replay.get("evaluation_traffic_replay_passed"),
        )
    spawn = report("spawn_evaluation_validation.json")
    if spawn:
        check(
            "births_and_exits",
            spawn.get("binary_sha256") == binary_hash
            and spawn.get("ini_sha256") == ini_hash
            and (spawn.get("runtime", {}).get("runtime_source_sha256") == runtime_hash)
            and (spawn.get("test_termination_mode") == 1)
            and (spawn.get("test_goal_behavior") == 3)
            and spawn.get("passed"),
        )
    parked = report("parked_evaluation_validation.json")
    if parked:
        check(
            "parked",
            parked.get("binary_sha256") == binary_hash
            and parked.get("ini_sha256") == ini_hash
            and (parked.get("runtime", {}).get("runtime_source_sha256") == runtime_hash)
            and (parked.get("test_termination_mode") == 1)
            and (parked.get("collision_shrink") == 1.0)
            and parked.get("passed"),
        )
    if late_ids:
        repeated = report("reset_evaluation_probe.json")
        if repeated:
            check(
                "repeated_reset",
                repeated.get("binary_sha256") == binary_hash
                and repeated.get("evaluation_config")
                and (
                    repeated.get("runtime", {}).get("runtime_source_sha256")
                    == runtime_hash
                )
                and (len(repeated.get("cycles", [])) >= 3)
                and repeated.get("passed"),
            )
    trace = report("lifecycle_trace_expert.json")
    if trace:
        timelines = trace.get("timeline", {})
        background_losses = {
            k: v
            for k, v in trace.get("first_source_valid_losses", {}).items()
            if k != str(current["ego_track_id"])
        }
        ghosts = []
        max_position = max_heading = 0.0
        for tid, rows in timelines.items():
            valid_steps = [r["step"] for r in rows if r["source_valid"]]
            if not valid_steps:
                source_obj = (
                    next(
                        (obj for obj in scene["objects"] if str(obj["id"]) == tid), None
                    )
                    if scene
                    else None
                )
                first_source_valid = (
                    next(
                        (i for i, valid in enumerate(source_obj["valid"]) if valid),
                        None,
                    )
                    if source_obj
                    else None
                )
                if first_source_valid is None or first_source_valid < trace.get(
                    "observed_steps", 91
                ):
                    ghosts.append((tid, "no valid samples"))
                continue
            for row in rows:
                if row["present"] and (
                    row["step"] < valid_steps[0] or row["step"] > valid_steps[-1]
                ):
                    ghosts.append((tid, row["step"]))
                if row["present"] and row["source_valid"]:
                    max_position = max(max_position, row["position_error_m"] or 0)
                    max_heading = max(max_heading, row["heading_error_rad"] or 0)
        ego_loss = trace.get("first_source_valid_losses", {}).get(
            str(current["ego_track_id"])
        )
        check(
            "expert_trace_current",
            trace.get("binary_sha256") == binary_hash
            and trace.get("evaluation_ini_sha256") == ini_hash
            and (trace.get("runtime_source_sha256") == runtime_hash),
        )
        check(
            "expert_lifecycle",
            not trace.get("reset_steps")
            and (not background_losses)
            and (not ghosts)
            and (max_position < 0.01)
            and (max_heading < 0.01),
            {
                "background_losses": list(background_losses),
                "ghosts": ghosts[:10],
                "max_position_m": max_position,
                "max_heading_rad": max_heading,
            },
        )
        check(
            "ego_goal_event",
            ego_loss is None or ego_loss.get("cause") == "goal",
            {
                "first_ego_loss": (
                    {k: ego_loss[k] for k in ("step", "cause")} if ego_loss else None
                )
            },
        )
        check(
            "goal_terminal_consistent",
            eval_replay is not None
            and trace.get("justified_goal_terminal_step")
            == eval_replay.get("justified_goal_terminal_step")
            and (trace.get("observed_steps") == eval_replay.get("observed_steps"))
            and (
                trace.get("justified_goal_terminal_step") is None
                or (
                    ego_loss is not None
                    and ego_loss.get("step") == trace["justified_goal_terminal_step"]
                    and (ego_loss.get("cause") == "goal")
                )
            ),
        )
    counterfactual = report("counterfactual_probe.json")
    if counterfactual:
        modes = counterfactual.get("modes", {})
        check(
            "counterfactual_lifecycle",
            counterfactual.get("schema_version") == 2
            and counterfactual.get("binary_sha256") == binary_hash
            and (counterfactual.get("evaluation_ini_sha256") == ini_hash)
            and (counterfactual.get("runtime_source_sha256") == runtime_hash)
            and (counterfactual.get("lateral_offset_m") == 1.0)
            and (set(modes) == {"expert", "idm", "zero_action_dynamics"})
            and (counterfactual.get("required_evaluator_modes") == ["expert", "idm"])
            and counterfactual.get("required_evaluator_modes_passed"),
            {mode: value.get("lifecycle_passed") for mode, value in modes.items()},
        )
    hybrid_checks = ()
    if args.traffic_protocol == "hybrid_startup":
        hybrid_trace = report("lifecycle_trace_hybrid_startup.json")
        if hybrid_trace:
            hybrid_losses = {
                k: v
                for k, v in hybrid_trace.get("first_source_valid_losses", {}).items()
                if k != str(current["ego_track_id"])
            }
            check(
                "hybrid_trace_current",
                hybrid_trace.get("binary_sha256") == binary_hash
                and hybrid_trace.get("evaluation_ini_sha256") == ini_hash
                and (hybrid_trace.get("runtime_source_sha256") == runtime_hash)
                and (hybrid_trace.get("traffic_mode") == "hybrid_startup"),
            )
            check(
                "hybrid_lifecycle",
                hybrid_trace.get("observed_steps", 0) >= 75
                and (not hybrid_trace.get("reset_steps"))
                and (not hybrid_losses)
                and (
                    hybrid_trace.get("justified_goal_terminal_step") is None
                    or hybrid_trace.get("first_source_valid_losses", {})
                    .get(str(current["ego_track_id"]), {})
                    .get("cause")
                    == "goal"
                ),
                {"background_losses": list(hybrid_losses)},
            )
        hybrid_probe = report("counterfactual_hybrid_probe.json")
        if hybrid_probe:
            check(
                "hybrid_counterfactual",
                hybrid_probe.get("schema_version") == 2
                and hybrid_probe.get("binary_sha256") == binary_hash
                and (hybrid_probe.get("evaluation_ini_sha256") == ini_hash)
                and (hybrid_probe.get("runtime_source_sha256") == runtime_hash)
                and (hybrid_probe.get("lateral_offset_m") == 1.0)
                and (
                    hybrid_probe.get("required_evaluator_modes")
                    == ["expert", "hybrid_startup"]
                )
                and hybrid_probe.get("required_evaluator_modes_passed")
                and hybrid_probe.get("modes", {})
                .get("hybrid_startup", {})
                .get("lifecycle_passed"),
            )
        parity_path = project_path("pilot/audits/hybrid_protocol_us_parity.json")
        parity = json.loads(parity_path.read_text()) if parity_path.is_file() else {}
        us_source = Path(parity.get("us_source_json", "/missing"))
        us_binary = Path(parity.get("us_binary_path", "/missing"))
        check(
            "hybrid_us_mechanical_parity",
            parity.get("mechanical_parity_pass")
            and us_source.is_file()
            and us_binary.is_file()
            and (parity.get("us_source_sha256") == sha(us_source))
            and (parity.get("us_binary_sha256") == sha(us_binary))
            and (parity.get("evaluator_ini_sha256") == ini_hash)
            and (parity.get("runtime_source_sha256") == runtime_hash)
            and (
                parity.get("hybrid_protocol_sha256")
                == sha(project_path("hybrid_traffic.py"))
            ),
        )
        hybrid_checks = (
            "hybrid_trace_current",
            "hybrid_lifecycle",
            "hybrid_counterfactual",
            "hybrid_us_mechanical_parity",
        )
    check(
        "refresh_commands", not args.no_refresh and (not refresh_errors), refresh_errors
    )
    research_only_checks = {
        "semantic_screen",
        "rule_audit_current",
        "semantic_review_current",
        "semantic_review_complete",
        "source_supported_irrelevance_plausible",
        "interaction_audit_current",
        "interaction_claim_supported",
        "exists:rule_applicability_audit.json",
        "exists:semantic_review.json",
        "exists:interaction_fidelity_audit.json",
        "exists:semantic_review_hybrid_startup.json",
        "exists:interaction_fidelity_audit_hybrid_startup.json",
        "exists:lifecycle_trace_hybrid_startup.json",
        "exists:counterfactual_hybrid_probe.json",
        "hybrid_trace_current",
        "hybrid_lifecycle",
        "hybrid_counterfactual",
        "hybrid_us_mechanical_parity",
    }
    diagnostic_only_checks = {"semantic_screen"}
    if args.traffic_protocol == "hybrid_startup":
        research_only_checks.update(
            {"counterfactual_lifecycle", "exists:counterfactual_probe.json"}
        )
        research_only_checks.difference_update(
            {
                "exists:lifecycle_trace_hybrid_startup.json",
                "exists:counterfactual_hybrid_probe.json",
                "hybrid_trace_current",
                "hybrid_lifecycle",
                "hybrid_counterfactual",
            }
        )
        diagnostic_only_checks.update(
            {"counterfactual_lifecycle", "exists:counterfactual_probe.json"}
        )
    technical_checks = [name for name in checks if name not in research_only_checks]
    technical_admitted = all((checks[name] for name in technical_checks))
    research_admitted = technical_admitted and all(
        (
            checks.get(name, False)
            for name in (
                "rule_audit_current",
                "semantic_review_current",
                "semantic_review_complete",
                "source_supported_irrelevance_plausible",
                "interaction_audit_current",
                "interaction_claim_supported",
                *hybrid_checks,
            )
        )
    )
    output = {
        "schema_version": 1,
        "contract": current,
        "checks": checks,
        "details": details,
        "traffic_protocol": args.traffic_protocol,
        "technical_admitted": technical_admitted,
        "research_admitted": research_admitted,
        "eligible_interaction_types": (
            review.get("eligible_interaction_types", []) if research_admitted else []
        ),
        "diagnostic_traffic_modes": {
            mode: value.get("lifecycle_passed")
            for mode, value in (counterfactual or {}).get("modes", {}).items()
        },
        "diagnostic_findings": [
            name
            for name in sorted(diagnostic_only_checks)
            if not checks.get(name, False)
        ],
        "exclusion_reasons": [
            name
            for name, ok in checks.items()
            if not ok and name not in diagnostic_only_checks
        ],
    }
    (
        testing
        / (
            "admission.json"
            if args.traffic_protocol == "idm"
            else "admission_hybrid_startup.json"
        )
    ).write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {
                "scene_root": str(root),
                "technical_admitted": technical_admitted,
                "research_admitted": research_admitted,
                "exclusion_reasons": output["exclusion_reasons"],
            },
            indent=2,
        )
    )
    if not (research_admitted if args.research else technical_admitted):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
