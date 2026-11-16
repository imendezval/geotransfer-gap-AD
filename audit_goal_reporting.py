"""Reconcile an evaluator goal trace with its CSV goal result and observation scale."""

import argparse
import csv
import json
import math
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--trace", type=Path, required=True)
ap.add_argument("--per-map", type=Path, required=True)
ap.add_argument("--goal-radius-m", type=float, default=2.0)
args = ap.parse_args()
steps = json.loads(args.trace.read_text())
row = next(csv.DictReader(args.per_map.open()))
last = steps[-1]
physical = last["after"]["distance_m"]
normalized = last["observation_goal_distance_m"] * 0.005
report = {
    "steps": len(steps), "final_physical_goal_distance_m": physical,
    "goal_radius_m": args.goal_radius_m,
    "final_goal_event": last["after"]["reached_goal"],
    "final_truncation": last["ego_truncated"],
    "csv_goal_reached": row["goal_reached"],
    "csv_goal_distance_displayed_as_m": float(row["final_goal_distance"]),
    "observed_goal_distance_normalization": 0.005,
    "observation_and_physical_distance_agree": math.isclose(
        physical, last["observation_goal_distance_m"], abs_tol=1e-4),
    "displayed_distance_is_normalized": abs(float(row["final_goal_distance"]) - normalized) < 0.005,
    "goal_event_consistent_with_radius": (physical >= args.goal_radius_m and
        not last["after"]["reached_goal"] and row["goal_reached"] == "False"),
}
path = args.trace.with_name("goal_reporting_audit.json")
path.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
if not all(report[k] for k in ("observation_and_physical_distance_agree",
                               "displayed_distance_is_normalized",
                               "goal_event_consistent_with_radius")):
    raise SystemExit(1)
