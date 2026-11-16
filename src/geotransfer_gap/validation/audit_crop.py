"""Compare a cropped scene with its full stationary-actor counterpart."""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import json
import math
from pathlib import Path


def read(root):
    return json.loads(next((root / "testing").glob("ind_*.json")).read_text())


def audit(cropped, full):
    a, b = (read(cropped), read(full))
    aa, bb = ({x["id"]: x for x in a["objects"]}, {x["id"]: x for x in b["objects"]})
    assert aa.keys() <= bb.keys()
    ego = a["objects"][0]
    excluded = []
    for tid in sorted(bb.keys() - aa.keys()):
        obj = bb[tid]
        valid = [t for t, v in enumerate(obj["valid"]) if v]
        first, last = (obj["position"][valid[0]], obj["position"][valid[-1]])
        center = min(
            (
                math.dist(
                    (obj["position"][t]["x"], obj["position"][t]["y"]),
                    (ego["position"][t]["x"], ego["position"][t]["y"]),
                )
                for t in valid
            )
        )
        ego_radius = math.hypot(ego["width"] / 2, ego["length"] / 2)
        actor_radius = math.hypot(obj["width"] / 2, obj["length"] / 2)
        excluded.append(
            {
                "track_id": tid,
                "type": obj["type"],
                "valid_steps": len(valid),
                "displacement_m": math.dist(
                    (first["x"], first["y"]), (last["x"], last["y"])
                ),
                "minimum_ego_center_distance_m": center,
                "minimum_ego_bounding_circle_clearance_m": center
                - ego_radius
                - actor_radius,
            }
        )
    retained_changed = [
        tid
        for tid in aa
        if aa[tid]["position"] != bb[tid]["position"]
        or aa[tid]["valid"] != bb[tid]["valid"]
    ]
    crop_replay = json.loads((cropped / "testing/replay_validation.json").read_text())
    full_replay = json.loads((full / "testing/replay_validation.json").read_text())
    report = {
        "cropped_root": str(cropped),
        "full_root": str(full),
        "crop_radius_m": json.loads((cropped / "testing/validation.json").read_text())[
            "static_crop_radius_m"
        ],
        "excluded": excluded,
        "retained_source_tracks_changed": retained_changed,
        "full_missing_valid_samples_count": full_replay["missing_valid_samples_count"],
        "full_missing_valid_samples_by_track": full_replay[
            "missing_valid_samples_by_track"
        ],
        "cropped_missing_valid_samples_count": crop_replay[
            "missing_valid_samples_count"
        ],
        "full_ego_raw_collision_count": full_replay["expert_ego_raw_collision_count"],
        "cropped_ego_raw_collision_count": crop_replay[
            "expert_ego_raw_collision_count"
        ],
        "all_excluded_vehicles_stationary": all(
            (o["type"] == "vehicle" and o["displacement_m"] < 0.5 for o in excluded)
        ),
        "all_excluded_bounding_circles_clear": all(
            (o["minimum_ego_bounding_circle_clearance_m"] > 0 for o in excluded)
        ),
    }
    (cropped / "testing/crop_audit.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cropped", type=Path, required=True)
    parser.add_argument("--full", type=Path, required=True)
    args = parser.parse_args()
    audit(args.cropped.resolve(), args.full.resolve())
