"""Certify the recorded source path through directed roads and legal lane changes.

Checks converted centre interpolation at0.01s; it does not invent new measured
motion or certify continuous physical-box clearance. Source/access/manual and
evaluator physical checks remain separate mandatory evidence.
"""

from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import argparse
import csv
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from matplotlib.path import Path as PolygonPath
from geotransfer_gap.maps import source_lane_changes


def audit(root, allow_lane_changes=True):
    t = root / "testing"
    scene_path = next(t.glob("ind_*.json"))
    ego = json.loads(scene_path.read_text())["objects"][0]
    validation = json.loads((t / "validation.json").read_text())
    recording = int(validation["recording"])
    meta_path = settings().source / f"data/{recording:02d}_recordingMeta.csv"
    meta = next(csv.DictReader(meta_path.open()))
    source_map, _ = map_geometry.map_paths(meta, recording)
    tree = ET.parse(source_map).getroot()
    nodes = map_geometry.project_nodes(
        tree, float(meta["xUtmOrigin"]), float(meta["yUtmOrigin"])
    )
    tags = {
        int(r.get("id")): {x.get("k"): x.get("v") for x in r.findall("tag")}
        for r in tree.findall("relation")
    }
    roads, lanes = map_geometry.make_roads(meta, recording)
    allowed = {
        lid
        for lid in lanes
        if tags[lid].get("subtype") == "road"
        and (
            not any(
                (
                    k.startswith("participant:")
                    or k in ("access", "vehicle", "motor_vehicle")
                    for k in tags[lid]
                )
            )
        )
    }
    graph = {
        r["id"]: set(r["exit_lanes"]) & allowed
        for r in roads
        if r["type"] == "lane" and r["id"] in allowed
    }
    changes = source_lane_changes.edges(lanes, source_map) if allow_lane_changes else []
    for row in changes:
        graph[row["source"]].add(row["target"])
    steps = np.linspace(0, len(ego["valid"]) - 1, (len(ego["valid"]) - 1) * 10 + 1)
    xy = np.column_stack(
        [
            np.interp(
                steps, np.arange(len(ego["valid"])), [v[k] for v in ego["position"]]
            )
            for k in ("x", "y")
        ]
    )
    heading = np.interp(steps, np.arange(len(ego["valid"])), np.unwrap(ego["heading"]))
    choices = [set() for _ in steps]
    for lid in allowed:
        lane = lanes[lid]
        polygon = [nodes[i] for i in lane["left_nodes"]] + [
            nodes[i] for i in reversed(lane["right_nodes"])
        ]
        contained = PolygonPath(polygon).contains_points(xy, radius=1e-08)
        coords = np.asarray(lane["coords"])
        vectors = np.diff(coords, axis=0)
        fractions = np.clip(
            ((xy[:, None, :] - coords[None, :-1, :]) * vectors[None, :, :]).sum(2)
            / np.maximum((vectors * vectors).sum(1), 1e-12),
            0,
            1,
        )
        distance = np.linalg.norm(
            coords[None, :-1, :]
            + fractions[:, :, None] * vectors[None, :, :]
            - xy[:, None, :],
            axis=2,
        )
        nearest = distance.argmin(1)
        direction = np.arctan2(vectors[nearest, 1], vectors[nearest, 0])
        error = abs((direction - heading + np.pi) % (2 * np.pi) - np.pi)
        for step in np.flatnonzero(contained & (error <= 0.35)):
            choices[step].add(lid)
    paths = {lid: ([lid], []) for lid in sorted(choices[0])}
    failure = None
    for step, candidates in enumerate(choices[1:], 1):
        updated = {}
        for lane in sorted(candidates):
            for prior, (route, transitions) in sorted(paths.items()):
                if lane == prior or lane in graph.get(prior, set()):
                    updated[lane] = (
                        (route, transitions)
                        if lane == prior
                        else (
                            route + [lane],
                            transitions
                            + [
                                {
                                    "source": prior,
                                    "target": lane,
                                    "source_step": float(steps[step]),
                                }
                            ],
                        )
                    )
                    break
        paths = updated
        if not paths:
            failure = {
                "source_step": float(steps[step]),
                "compatible_lanelets": sorted(candidates),
            }
            break
    route, transitions = next(iter(paths.values()), ([], []))
    indexed = {(r["source"], r["target"]): r for r in changes}
    used = [
        dict(indexed[r["source"], r["target"]], source_step=r["source_step"])
        for r in transitions
        if (r["source"], r["target"]) in indexed
    ]
    return {
        "schema_version": 1,
        "audit_sha256": sha(Path(__file__)),
        "lane_change_tool_sha256": sha(Path(source_lane_changes.__file__)),
        "scene_sha256": sha(scene_path),
        "binary_sha256": sha(t / "map_000000.bin"),
        "source_map_sha256": sha(source_map),
        "source_recording_meta_sha256": sha(meta_path),
        "sample_dt_s": 0.01,
        "direction_tolerance_rad": 0.35,
        "permission_set": "legal_changes" if allow_lane_changes else "following_only",
        "samples": len(steps),
        "ordinary_road_only": True,
        "source_path_legal": failure is None and bool(route),
        "route": route,
        "transitions": transitions,
        "used_lane_changes": used,
        "first_failure": failure,
        "scope": "Dense converted source centre/direction sequence; native-verified conservative lateral permissions. Not continuous box clearance or ground-truth motion between source samples.",
    }


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()
    result = audit(args.root.resolve())
    (args.root / "testing/source_route_sequence.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "legal": result["source_path_legal"],
                "lane_changes": result["used_lane_changes"],
                "failure": result["first_failure"],
            }
        )
    )
    if not result["source_path_legal"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
