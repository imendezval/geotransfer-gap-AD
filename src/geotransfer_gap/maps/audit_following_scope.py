"""Source certificate distinguishing a preceding vehicle from crossing traffic.

This can resolve relative-heading heuristics, never an explicit priority rule.
Requires shared directed source-lane ancestry, a matched forward route through
the turn, and the actor ahead throughout the task. Historical tracks are used
only for this offline review, never supplied to the planner or controller.
"""

from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from geotransfer_gap.maps.audit_scene import inside, alignment
from geotransfer_gap.maps.audit_rule_applicability import polygon_of


def heuristic_flags(rule_audit):
    result = {}
    for key, prefix in [
        ("oncoming_turn_conflicts", "implicit_oncoming_turn_priority"),
        ("slow_ego_fast_crosspath_conflicts", "slow_ego_fast_crosspath"),
        ("yield_lane_fast_crosspath_conflicts", "yield_lane_fast_crosspath"),
    ]:
        for actor in rule_audit.get(key, []):
            result[f"{prefix}_{actor['type']}_{actor['track_id']}"] = actor["track_id"]
    return result


def audit(root, actor_ids):
    t = root / "testing"
    scene_path = next(t.glob("ind_*.json"))
    scene = json.loads(scene_path.read_text())
    v = json.loads((t / "validation.json").read_text())
    recording = v["recording"]
    source_path = settings().source / f"data/{recording:02d}_tracks.csv"
    meta = next(
        csv.DictReader(
            (settings().source / f"data/{recording:02d}_recordingMeta.csv").open()
        )
    )
    map_path, _ = map_geometry.map_paths(meta, recording)
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = {
        "schema_version": 1,
        "scene_sha256": sha(scene_path),
        "source_tracks_sha256": sha(source_path),
        "source_map_sha256": sha(map_path),
        "audit_sha256": sha(Path(__file__)),
        "scope": "Same-route following can disprove a crossing heuristic; explicit priority/sign obligations are untouched.",
        "actors": [],
    }
    if not actor_ids:
        return report
    ego = scene["objects"][0]
    objects = {o["id"]: o for o in scene["objects"]}
    if not all(ego["valid"]):
        raise ValueError("Complete ego source coverage is required")
    osm = ET.parse(map_path).getroot()
    nodes = map_geometry.project_nodes(
        osm, float(meta["xUtmOrigin"]), float(meta["yUtmOrigin"])
    )
    ways = {
        int(w.get("id")): [nodes[int(n.get("ref"))] for n in w.findall("nd")]
        for w in osm.findall("way")
    }
    _, lanes = map_geometry.make_roads(meta, recording)
    initial = (ego["position"][0]["x"], ego["position"][0]["y"])
    initial_lanes = {}
    for rel in osm.findall("relation"):
        lid = int(rel.get("id"))
        if lid not in lanes:
            continue
        polygon = polygon_of(rel, ways)
        if (
            inside(initial, polygon)
            and alignment(initial, ego["heading"][0], lanes[lid]["coords"])[1] < 0.35
        ):
            initial_lanes[lid] = polygon
    raw = pd.read_csv(
        source_path,
        usecols=[
            "frame",
            "trackId",
            "xCenter",
            "yCenter",
            "heading",
            "xVelocity",
            "yVelocity",
        ],
    )
    xy = np.asarray([[q["x"], q["y"]] for q in ego["position"]])
    length = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    arc = np.r_[0, np.cumsum(length)]
    segments = np.flatnonzero(length > 0.05)

    def project(point):
        choices = []
        for i in segments:
            d = xy[i + 1] - xy[i]
            u = float(np.clip((point - xy[i]) @ d / length[i] ** 2, 0, 1))
            angle = (ego["heading"][i + 1] - ego["heading"][i] + math.pi) % (
                2 * math.pi
            ) - math.pi
            choices.append(
                (
                    float(np.linalg.norm(point - xy[i] - u * d)),
                    float(arc[i] + u * length[i]),
                    ego["heading"][i] + u * angle,
                )
            )
        direction = np.array(
            [math.cos(ego["heading"][-1]), math.sin(ego["heading"][-1])]
        )
        beyond = max(0.0, float((point - xy[-1]) @ direction))
        choices.append(
            (
                float(np.linalg.norm(point - xy[-1] - beyond * direction)),
                float(arc[-1] + beyond),
                ego["heading"][-1],
            )
        )
        return min(choices, key=lambda r: r[0])

    for tid in sorted(set(actor_ids)):
        actor = objects.get(tid)
        result = {"actor_id": tid, "same_route_following": False}
        report["actors"].append(result)
        if actor is None or actor["type"] != "vehicle":
            result["reason"] = "Source actor is not a represented vehicle"
            continue
        track = raw[raw.trackId == tid].sort_values("frame")
        anchors = []
        for row in track[track.frame <= v["first_frame"]].itertuples():
            point = (row.xCenter, row.yCenter)
            heading = math.radians(row.heading)
            for lid, polygon in initial_lanes.items():
                if (
                    inside(point, polygon)
                    and alignment(point, heading, lanes[lid]["coords"])[1] < 0.35
                ):
                    anchors.append((int(row.frame), lid))
        if not anchors:
            result["reason"] = (
                "No observed prior ancestry in the ego initial directed lane"
            )
            continue
        anchor_frame, lane = max(anchors)
        observed = track[
            (track.frame >= anchor_frame) & (track.frame <= v["first_frame"] + 225)
        ]
        errors = []
        reverse = False
        for row in observed.itertuples():
            dist, s, heading = project(np.array([row.xCenter, row.yCenter]))
            delta = abs(
                (math.radians(row.heading) - heading + math.pi) % (2 * math.pi)
                - math.pi
            )
            errors.append((dist, delta))
            speed = math.hypot(row.xVelocity, row.yVelocity)
            if (
                speed > 0.5
                and row.xVelocity * math.cos(heading)
                + row.yVelocity * math.sin(heading)
                <= 0
            ):
                reverse = True
        gaps = [
            project(np.array([point["x"], point["y"]]))[1] - arc[step]
            for step, point in enumerate(actor["position"])
            if actor["valid"][step]
        ]
        tolerance = min(ego["width"], actor["width"]) / 2
        maximum_distance = max((r[0] for r in errors), default=math.inf)
        maximum_heading = max((r[1] for r in errors), default=math.inf)
        minimum_gap = min(gaps, default=-math.inf)
        result.update(
            shared_initial_lanelet=lane,
            source_ancestry_frame=anchor_frame,
            source_ancestry_age_s=(v["first_frame"] - anchor_frame) / 25,
            historical_and_current_samples=len(errors),
            maximum_route_offset_m=maximum_distance,
            route_offset_bound_m=tolerance,
            maximum_route_heading_error_rad=maximum_heading,
            minimum_simultaneous_arc_gap_m=minimum_gap,
            reverse_motion=reverse,
            same_route_following=bool(
                len(segments)
                and errors
                and (maximum_distance <= tolerance)
                and (maximum_heading < 0.35)
                and (minimum_gap > 0)
                and (not reverse)
            ),
        )
        result["reason"] = (
            "Certified shared directed approach and forward preceding route"
            if result["same_route_following"]
            else "Shared ancestry alone does not establish a forward preceding route"
        )
    return report


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--root", type=Path)
    ap.add_argument("--actors", type=int, nargs="+")
    ap.add_argument("--ledgers", type=Path, nargs="+")
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--exclude-selection", type=Path, nargs="*", default=[])
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if args.root:
        if not args.actors:
            ap.error("--root requires --actors")
        result = audit(args.root.resolve(), args.actors)
        (args.root / "testing/source_following_scope.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        print(json.dumps(result))
        return
    if not (args.ledgers and args.manifest and args.output):
        ap.error("Use --root/--actors or --ledgers/--manifest/--output")
    manifest = json.loads(args.manifest.read_text())
    occupied = {
        (r["recording"], tid) for r in manifest for tid in r["moving_track_ids"]
    }
    excluded = {
        r["root"]
        for path in args.exclude_selection
        for r in json.loads(path.read_text())["jobs"]
        if "root" in r
    }
    excluded_windows = {
        tuple((r[k] for k in ("recording", "ego", "first_frame")))
        for path in args.exclude_selection
        for r in json.loads(path.read_text())["jobs"]
        if all((k in r for k in ("recording", "ego", "first_frame")))
    }
    candidates = {}
    inputs = []
    for path in args.ledgers:
        inputs.append(
            {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
        for row in json.loads(path.read_text()).get("results", []):
            if not all(
                (
                    k in row
                    for k in ("root", "recording", "ego", "actor", "task_evidence")
                )
            ):
                continue
            if "/oriented_v3/" not in row["root"] or row["root"] in excluded:
                continue
            if (
                tuple((row[k] for k in ("recording", "ego", "first_frame")))
                in excluded_windows
            ):
                continue
            if any(((row["recording"], row[k]) in occupied for k in ("ego", "actor"))):
                continue
            flags = row.get("source_unsupported_rule_flags", [])
            root = Path(row["root"])
            rules = json.loads(
                (root / "testing/rule_applicability_audit.json").read_text()
            )
            heuristics = heuristic_flags(rules)
            if flags and set(flags) <= set(heuristics):
                candidates[row["root"]] = row
    ledger = []
    jobs = []
    for root_name, row in sorted(candidates.items()):
        root = Path(root_name)
        rules = json.loads((root / "testing/rule_applicability_audit.json").read_text())
        flags = heuristic_flags(rules)
        ids = sorted({flags[x] for x in row["source_unsupported_rule_flags"]})
        proof = audit(root, ids)
        path = root / "testing/source_following_scope.json"
        path.write_text(json.dumps(proof, indent=2) + "\n")
        passed = bool(proof["actors"]) and all(
            (x["same_route_following"] for x in proof["actors"])
        )
        ledger.append(
            {
                "root": root_name,
                "source_heuristics": row["source_unsupported_rule_flags"],
                "all_heuristics_are_same_route_following": passed,
                "proof_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
        if passed:
            keep = {
                k: row[k]
                for k in (
                    "recording",
                    "location",
                    "ego",
                    "first_frame",
                    "actor",
                    "actor_class",
                    "role",
                    "task_evidence",
                )
            }
            jobs.append(keep)
        print(root.name, "source same-route certificate", passed, flush=True)
    result = {
        "schema_version": 1,
        "selection": "All previously rejected task windows with heuristic-only crossing flags and certified same-route source ancestry/order. Explicit priority flags excluded; skip source egos/claimed actors already in independent manifest. No planner outcomes. Full technical/manual/model gates remain mandatory.",
        "audit_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "inputs": inputs,
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "source_certificate_ledger": ledger,
        "jobs": jobs,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        "source-certified queue",
        len(jobs),
        "from",
        len(ledger),
        "screened windows",
        flush=True,
    )


if __name__ == "__main__":
    main()
