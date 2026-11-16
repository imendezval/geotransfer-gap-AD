"""Check whether source-timed close interactions survive IDM evaluator traffic.

This is evidence for manual review.  It deliberately does not infer that a
nearby actor creates a planning decision; that judgment remains per scene.
"""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import argparse
import hashlib
import json
import math
from pathlib import Path
from geotransfer_gap.validation.audit_physical_source import corners
from geotransfer_gap.maps.audit_rule_applicability import box_distance


def source_evidence_digest(report):
    """Bind a review to source events without hashing float-noisy IDM states."""
    source = {
        "binary_sha256": report["binary_sha256"],
        "rule_audit_sha256": report["rule_audit_sha256"],
        "ego_track_id": report["ego_track_id"],
        "actor_opportunities": [
            {
                "track_id": x["track_id"],
                "type": x["type"],
                "source_box_step": x["source_box_step"],
                "source_timed_box_gap_m": round(x["source_timed_box_gap_m"], 6),
                "source_speed_mps": round(x["source_speed_mps"], 6),
                "source_close_steps_after_warmup": x["source_close_steps_after_warmup"],
                "longest_source_close_run_steps": x["longest_source_close_run_steps"],
            }
            for x in report["actor_opportunities"]
        ],
    }
    return hashlib.sha256(
        json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sim_corners(row):
    x, y = row["source_local_position"]
    h = row["sim_heading_rad"]
    c, s = (math.cos(h), math.sin(h))
    return [
        (
            x + a * row["sim_length_m"] / 2 * c - b * row["sim_width_m"] / 2 * s,
            y + a * row["sim_length_m"] / 2 * s + b * row["sim_width_m"] / 2 * c,
        )
        for a, b in ((-1, -1), (-1, 1), (1, 1), (1, -1))
    ]


def observed_speed(rows, step, actor_type):
    row = rows[step]
    if actor_type == "vehicle" or step == 0:
        return row["sim_speed_mps"]
    prior = rows[step - 1]
    if not (
        prior
        and prior["present"]
        and row["present"]
        and prior["source_local_position"]
        and row["source_local_position"]
    ):
        return None
    return math.dist(prior["source_local_position"], row["source_local_position"]) / 0.1


def audit(root, traffic_mode="idm"):
    testing = root / "testing"
    scene = json.loads(next(testing.glob("ind_*.json")).read_text())
    rules_path = testing / "rule_applicability_audit.json"
    if traffic_mode not in ("idm", "hybrid_startup"):
        raise ValueError(f"Unsupported interaction traffic mode: {traffic_mode}")
    idm_path = testing / f"lifecycle_trace_{traffic_mode}.json"
    rules = json.loads(rules_path.read_text())
    idm = json.loads(idm_path.read_text())
    ego = scene["objects"][0]
    objects = {obj["id"]: obj for obj in scene["objects"]}
    opportunities = []
    for near in rules["moving_actor_proximities"]:
        actor = objects[near["track_id"]]
        t = near["box_step"]
        rows = idm["timeline"][str(actor["id"])]
        row = rows[t] if t < idm["observed_steps"] else None
        present = bool(row and row["present"] and row["source_valid"])
        sim_gap = box_distance(corners(ego, t), sim_corners(row)) if present else None
        source_speed = math.hypot(actor["velocity"][t]["x"], actor["velocity"][t]["y"])
        sim_speed = row["sim_speed_mps"] if present else None
        effective_speed = observed_speed(rows, t, actor["type"]) if present else None
        stopped_limit = 2.0 if actor["type"] == "vehicle" else 1.0
        moving_tolerance = 5.0 if actor["type"] == "vehicle" else 1.0
        speed_phase_preserved = bool(
            present
            and effective_speed is not None
            and (
                effective_speed <= stopped_limit
                if source_speed < 1.0
                else abs(effective_speed - source_speed) <= moving_tolerance
            )
        )
        close_steps = []
        matched_steps = []
        for step in range(10, min(len(ego["valid"]), idm["observed_steps"])):
            if not (ego["valid"][step] and actor["valid"][step]):
                continue
            source_gap = box_distance(corners(ego, step), corners(actor, step))
            if source_gap > 5.0:
                continue
            close_steps.append(step)
            sim = rows[step]
            if not (
                sim
                and sim["present"]
                and sim["source_valid"]
                and (sim["position_error_m"] is not None)
            ):
                continue
            simulated_gap = box_distance(corners(ego, step), sim_corners(sim))
            source_speed_at_step = math.hypot(
                actor["velocity"][step]["x"], actor["velocity"][step]["y"]
            )
            effective_speed_at_step = observed_speed(rows, step, actor["type"])
            speed_matches = bool(
                effective_speed_at_step is not None
                and (
                    effective_speed_at_step <= stopped_limit
                    if source_speed_at_step < 1.0
                    else abs(effective_speed_at_step - source_speed_at_step)
                    <= moving_tolerance
                )
            )
            if (
                sim["position_error_m"] <= 3.0
                and simulated_gap <= source_gap + 3.0
                and speed_matches
            ):
                matched_steps.append(step)

        def longest_run(steps):
            longest = current = 0
            previous = None
            for step in steps:
                current = (
                    current + 1 if previous is not None and step == previous + 1 else 1
                )
                longest = max(longest, current)
                previous = step
            return longest

        match_fraction = len(matched_steps) / len(close_steps) if close_steps else 0.0
        preserved = (
            len(close_steps) >= 5
            and longest_run(close_steps) >= 5
            and (longest_run(matched_steps) >= 5)
            and (match_fraction >= 0.8)
        )
        opportunities.append(
            {
                "track_id": actor["id"],
                "type": actor["type"],
                "source_box_step": t,
                "source_timed_box_gap_m": near["minimum_timed_box_gap_m"],
                "source_speed_mps": source_speed,
                "idm_present_at_source_step": present,
                "idm_position_error_at_source_step_m": (
                    row["position_error_m"] if present else None
                ),
                "idm_box_gap_at_source_step_m": sim_gap,
                "idm_speed_at_source_step_mps": sim_speed,
                "idm_observed_motion_speed_at_source_step_mps": effective_speed,
                "speed_phase_preserved": speed_phase_preserved,
                "source_close_steps_after_warmup": len(close_steps),
                "matched_close_steps_after_warmup": len(matched_steps),
                "close_step_match_fraction": match_fraction,
                "longest_source_close_run_steps": longest_run(close_steps),
                "longest_matched_close_run_steps": longest_run(matched_steps),
                "preserved_for_claimed_interaction": preserved,
            }
        )
    report = {
        "schema_version": 3,
        "traffic_mode": traffic_mode,
        "binary_sha256": sha(testing / "map_000000.bin"),
        "rule_audit_sha256": sha(rules_path),
        "idm_trace_sha256": sha(idm_path),
        "evaluation_ini_sha256": idm["evaluation_ini_sha256"],
        "runtime_source_sha256": idm["runtime_source_sha256"],
        "ego_track_id": ego["id"],
        "idm_observed_steps": idm["observed_steps"],
        "thresholds": {
            "minimum_source_step": 10,
            "minimum_source_close_steps": 5,
            "minimum_contiguous_close_steps": 5,
            "minimum_matched_close_fraction": 0.8,
            "maximum_source_gap_m": 5.0,
            "maximum_idm_position_error_at_source_step_m": 3.0,
            "maximum_idm_gap_increase_m": 3.0,
            "stopped_source_speed_mps": 1.0,
            "maximum_idm_speed_if_source_stopped_mps": 2.0,
            "maximum_moving_speed_error_mps": 5.0,
            "maximum_vru_motion_speed_if_source_stopped_mps": 1.0,
            "maximum_vru_moving_speed_error_mps": 1.0,
            "vru_speed_source": "observed_position_displacement_per_0.1s",
        },
        "actor_opportunities": opportunities,
    }
    report["source_evidence_digest"] = source_evidence_digest(report)
    path = testing / (
        "interaction_fidelity_audit.json"
        if traffic_mode == "idm"
        else f"interaction_fidelity_audit_{traffic_mode}.json"
    )
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "path": str(path),
                "preserved_actor_ids": [
                    x["track_id"]
                    for x in opportunities
                    if x["preserved_for_claimed_interaction"]
                ],
                "close_actor_count": sum(
                    (x["source_timed_box_gap_m"] <= 5.0 for x in opportunities)
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--traffic-mode", choices=("idm", "hybrid_startup"), default="idm")
    args = ap.parse_args()
    audit(args.root.resolve(), args.traffic_mode)
