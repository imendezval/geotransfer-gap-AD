"""Source task conflict evidence; proximity/relative-frame crossing is insufficient.

Speedup is a source-path timing diagnostic, not a physically validated policy
or proof that the source driver yielded. Source geometry is unchanged.
"""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from geotransfer_gap.validation.audit_physical_source import corners
from geotransfer_gap.maps.audit_rule_applicability import (
    box_path_clearance,
    box_distance,
)


def analyze(scene, actor_ids):
    ego = scene["objects"][0]
    goal = ego["goalPosition"]
    end = next(
        (
            i
            for i, p in enumerate(ego["position"])
            if ego["valid"][i]
            and math.hypot(p["x"] - goal["x"], p["y"] - goal["y"]) <= 2
        ),
        90,
    )
    clipped = copy.deepcopy(ego)
    clipped["valid"] = [
        int(bool(v) and 10 <= i <= end) for i, v in enumerate(ego["valid"])
    ]
    out = []
    for actor in scene["objects"]:
        if actor["id"] not in actor_ids:
            continue
        other = copy.deepcopy(actor)
        other["valid"] = [
            int(bool(v) and 10 <= i <= end) for i, v in enumerate(actor["valid"])
        ]
        if not any(other["valid"]):
            continue
        evidence = box_path_clearance(clipped, other)
        speedups = {}
        for factor in (1.25, 1.5):
            best = (math.inf, None, None)
            for t in range(10, end + 1):
                u = min(end, t * factor)
                lo = int(u)
                hi = min(end, lo + 1)
                alpha = u - lo
                if not (other["valid"][t] and ego["valid"][lo] and ego["valid"][hi]):
                    continue
                sample = copy.copy(ego)
                sample["position"] = list(ego["position"])
                sample["heading"] = list(ego["heading"])
                sample["position"][t] = {
                    axis: (1 - alpha) * ego["position"][lo][axis]
                    + alpha * ego["position"][hi][axis]
                    for axis in ("x", "y")
                }
                delta = (ego["heading"][hi] - ego["heading"][lo] + math.pi) % (
                    2 * math.pi
                ) - math.pi
                sample["heading"][t] = ego["heading"][lo] + alpha * delta
                gap = box_distance(corners(sample, t), corners(actor, t))
                if gap < best[0]:
                    best = (gap, t, u)
            speedups[str(factor)] = {
                "minimum_box_gap_m": best[0],
                "time_step": best[1],
                "ego_source_progress_step": best[2],
            }
        out.append(
            {
                "actor_id": actor["id"],
                "actor_type": actor["type"],
                "source_task_end_step": end,
                "source_path_box_evidence": evidence,
                "source_path_speedup_diagnostic": speedups,
                "crossing_corridors_overlap": evidence["minimum_spatial_box_gap_m"]
                < 0.01,
                "causal_source_driver_response_not_established_by_this_audit": True,
            }
        )
    return out


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--actors", type=int, nargs="+", required=True)
    args = ap.parse_args()
    t = args.root / "testing"
    path = next(t.glob("ind_*.json"))
    scene = json.loads(path.read_text())
    result = {
        "schema_version": 1,
        "source_scene_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "audit_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "actors": analyze(scene, set(args.actors)),
    }
    (t / "source_task_interaction_audit.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
