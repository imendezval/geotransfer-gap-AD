"""Independent source-map and crop audit for a generated inD scene.

Uses Lanelet2 boundary node IDs, polygon occupancy, and directed centerlines.
Run with --root pointing at a converter output root.
"""

import argparse
import csv
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pilot_ind as p
from source_lane_changes import edges as legal_lane_changes


def inside(point, polygon):
    x, y = point
    hit = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) != (b[1] > y):
            at_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x < at_x:
                hit = not hit
    return hit


def alignment(point, heading, coords):
    best = (float("inf"), None)
    for a, b in zip(coords, coords[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        size2 = vx * vx + vy * vy
        if size2 == 0:
            continue
        t = max(0, min(1, ((point[0] - a[0]) * vx + (point[1] - a[1]) * vy) / size2))
        d = math.dist(point, (a[0] + t * vx, a[1] + t * vy))
        if d < best[0]:
            diff = abs((heading - math.atan2(vy, vx) + math.pi) % (2 * math.pi) - math.pi)
            best = (d, diff)
    return best


def audit(root):
    scene = json.loads(next((root / "testing").glob("ind_*.json")).read_text())
    validation = json.loads((root / "testing/validation.json").read_text())
    p.RECORDING = validation["recording"]
    with (p.SOURCE / f"data/{p.RECORDING:02d}_recordingMeta.csv").open() as f:
        meta = next(csv.DictReader(f))
    osm_path, _ = p.map_paths(meta)
    osm = ET.parse(osm_path).getroot()
    projected = p.project_nodes(osm, float(meta["xUtmOrigin"]), float(meta["yUtmOrigin"]))
    ways = {int(w.get("id")): ([int(n.get("ref")) for n in w.findall("nd")]) for w in osm.findall("way")}
    bounds = {}
    for rel in osm.findall("relation"):
        tags = {t.get("k"): t.get("v") for t in rel.findall("tag")}
        if tags.get("type") != "lanelet" or tags.get("subtype") not in ("road", "bus_lane"):
            continue
        refs = {m.get("role"): int(m.get("ref")) for m in rel.findall("member") if m.get("type") == "way"}
        if "left" in refs and "right" in refs:
            left, right = p.orient_road_boundaries(ways[refs["left"]], ways[refs["right"]], projected)
            bounds[int(rel.get("id"))] = {"left": left, "right": right}
    roads = {r["id"]: [(v["x"], v["y"]) for v in r["geometry"]]
             for r in scene["roads"] if r["type"] == "lane"}
    links = []
    for road in scene["roads"]:
        if road["type"] != "lane":
            continue
        source = road["id"]
        for dest in road["exit_lanes"]:
            a, b = bounds[source], bounds[dest]
            left_id = a["left"][-1] == b["left"][0]
            right_id = a["right"][-1] == b["right"][0]
            left_gap = math.dist(projected[a["left"][-1]], projected[b["left"][0]])
            right_gap = math.dist(projected[a["right"][-1]], projected[b["right"][0]])
            gap = math.dist(roads[source][-1], roads[dest][0])
            av = (roads[source][-1][0] - roads[source][-2][0], roads[source][-1][1] - roads[source][-2][1])
            bv = (roads[dest][1][0] - roads[dest][0][0], roads[dest][1][1] - roads[dest][0][1])
            turn = abs((math.atan2(av[1], av[0]) - math.atan2(bv[1], bv[0]) + math.pi) % (2 * math.pi) - math.pi)
            links.append({"from": source, "to": dest, "both_boundary_nodes_shared": left_id and right_id,
                          "one_boundary_node_shared": left_id or right_id, "center_gap_m": gap,
                          "left_boundary_gap_m": left_gap, "right_boundary_gap_m": right_gap,
                          "direction_change_rad": turn})
    ego = scene["objects"][0]
    graph = {r["id"]: r["exit_lanes"] for r in scene["roads"] if r["type"] == "lane"}
    samples = []
    for t, (pos, heading) in enumerate(zip(ego["position"], ego["heading"])):
        pt = (pos["x"], pos["y"])
        occupied = []
        for lid, boundary in bounds.items():
            polygon = [projected[n] for n in boundary["left"]] + [projected[n] for n in reversed(boundary["right"])]
            if inside(pt, polygon):
                occupied.append(lid)
        nearest = min(roads, key=lambda lid: alignment(pt, heading, roads[lid])[0])
        aligned = [(lid, alignment(pt, heading, roads[lid])) for lid in occupied]
        samples.append({"step": t, "occupied_lanelets": occupied,
                        "nearest_centerline": nearest,
                        "nearest_centerline_distance_m": alignment(pt, heading, roads[nearest])[0],
                        "best_occupied_heading_error_rad": min((x[1][1] for x in aligned), default=None)})
    out = {
        "source_map": str(osm_path), "source_map_sha256": __import__("hashlib").sha256(osm_path.read_bytes()).hexdigest(),
        "lanelets": len(bounds), "emitted_successors": len(links),
        "successors_with_both_boundary_ids_shared": sum(x["both_boundary_nodes_shared"] for x in links),
        "successors_with_no_boundary_ids_shared": sum(not x["one_boundary_node_shared"] for x in links),
        "successors_direction_reversed": [x for x in links if x["direction_change_rad"] > math.pi / 2],
        "successors_gap_over_1m": [x for x in links if x["center_gap_m"] > 1],
        "successors_boundary_gap_over_1m": [x for x in links if x["left_boundary_gap_m"] > 1 or x["right_boundary_gap_m"] > 1],
        "unsupported_heuristic_successors": [x for x in links if not x["both_boundary_nodes_shared"]],
        "ego_samples_outside_lanelet_polygons": [x["step"] for x in samples if not x["occupied_lanelets"]],
        "ego_start_occupancy": samples[0], "ego_goal_occupancy": samples[validation["ego_goal_sample"]],
        "ego_max_occupied_heading_error_rad": max((x["best_occupied_heading_error_rad"] or 0 for x in samples)),
        "ego_samples": samples,
    }
    reachable = set(samples[0]["occupied_lanelets"])
    frontier = list(reachable)
    while frontier:
        for next_id in graph[frontier.pop()]:
            if next_id not in reachable:
                reachable.add(next_id)
                frontier.append(next_id)
    out["occupied_start_to_occupied_goal_reachable"] = bool(reachable.intersection(samples[validation["ego_goal_sample"]]["occupied_lanelets"]))
    out['occupied_start_to_occupied_goal_reachable_following_only'] = out['occupied_start_to_occupied_goal_reachable']
    _, native_lanes = p.make_roads(meta)
    changes = legal_lane_changes(native_lanes, osm_path)
    route_graph = {lane: set(targets) for lane, targets in graph.items()}
    for change in changes:
        route_graph[change['source']].add(change['target'])
    reachable = set(samples[0]['occupied_lanelets']);frontier = list(reachable)
    while frontier:
        for target in route_graph[frontier.pop()]:
            if target not in reachable:reachable.add(target);frontier.append(target)
    out['source_legal_lane_change_edges'] = changes
    out['occupied_start_to_occupied_goal_reachable'] = bool(reachable.intersection(samples[validation['ego_goal_sample']]['occupied_lanelets']))
    out["geometry_supported_successors"] = sum(x["left_boundary_gap_m"] <= 1 and x["right_boundary_gap_m"] <= 1 and x["direction_change_rad"] <= math.pi / 2 for x in links)
    path = root / "testing/map_audit.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "ego_samples" and k != "unsupported_heuristic_successors"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    audit(parser.parse_args().root.resolve())
