"""Convert and validate an inD recording window for BehaviorBench.

Run from anywhere with: python pilot_ind.py [--recording N --ego N --first-frame N]
The script uses the unmodified save_map_binary function from BehaviorBench's drive.py.
"""

from __future__ import annotations

import ast
import argparse
import csv
import hashlib
import json
import math
import subprocess
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "data/levelxdata/inD-dataset-v1.1"
BENCH = ROOT / "behavior-bench"
OUT = HERE / "pilot/testing"  # Drive currently accepts a fixed set of split names.
RECORDING = 0
EGO_ID = 7
FIRST_FRAME = 260
GOAL_SAMPLE = 85
EDGE_MODE = "all"
LATE_MODE = "reject"
STATIC_CROP_RADIUS = 30.0
EXCLUDE_TRACK_IDS = set()
PARKED_AS_STATIC_EXPERT = False
BACKGROUND_GOAL_MODE = "continue"
BACKGROUND_GOAL_MIN_DISTANCE = 5.0
EMIT_CROSSWALKS = False
SCENE_NAME = f"ind_{RECORDING:02d}_track_{EGO_ID}_frame_{FIRST_FRAME}"
FRAMES = np.arange(91, dtype=float) * 2.5 + FIRST_FRAME  # 25 Hz -> 10 Hz

MAPS = {
    1: ("01_bendplatz/location1.osm", "01_bendplatz/bendplatz.xodr"),
    2: ("02_frankenburg/location2.osm", "02_frankenburg/frankenburg.xodr"),
    3: ("03_heckstrasse/location3.osm", "03_heckstrasse/heckstrasse.xodr"),
    4: ("04_aseag/location4.osm", "04_aseag/aseag.xodr"),
}


def map_paths(recording_meta):
    location = int(recording_meta["locationId"])
    if location == 1 and 11 <= RECORDING <= 17:
        return (SOURCE / "maps/lanelets/01_bendplatz_constuction/location1_construction.osm",
                SOURCE / "maps/opendrive/01_bendplatz_constuction/bendplatz_construction.xodr")
    lanelet, opendrive = MAPS[location]
    return SOURCE / "maps/lanelets" / lanelet, SOURCE / "maps/opendrive" / opendrive


def background_pixel_scale(recording_meta):
    """Provider inD visualizer downsamples orthophotos by twelve."""
    return float(recording_meta["orthoPxToMeter"]) * 12.0


def polyline_length(coords):
    return float(sum(math.dist(a, b) for a, b in zip(coords, coords[1:])))


def lanelet_polygon(left, right):
    """Join boundaries even when the source ways have opposite directions."""
    same = math.dist(left[0], right[0]) + math.dist(left[-1], right[-1])
    opposite = math.dist(left[0], right[-1]) + math.dist(left[-1], right[0])
    aligned_right = list(reversed(right)) if opposite < same else list(right)
    return list(left) + list(reversed(aligned_right))


def orient_road_boundaries(left_ids, right_ids, nodes):
    """Orient OSM ways using Lanelet2 geometry::align's left/right rule.

    OSM way storage direction is independent of lane travel direction. Keep
    original node identities for directed connectivity; never infer direction
    from recorded vehicle motion. Native-loader parity is audited separately.
    """
    left, right = list(left_ids), list(right_ids)
    if min(len(left), len(right)) < 2:
        raise ValueError("Road lanelet needs two nondegenerate boundaries")

    def middle(ids):
        if len(ids) > 2:
            return nodes[ids[len(ids) // 2]]
        a, b = nodes[ids[0]], nodes[ids[-1]]
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    def signed_distance(ids, point):
        coords = [nodes[i] for i in ids]
        best = None
        for index, (a, b) in enumerate(zip(coords, coords[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            size2 = dx * dx + dy * dy
            if size2 == 0:
                continue
            t = max(0.0, min(1.0, ((point[0]-a[0])*dx + (point[1]-a[1])*dy) / size2))
            projected = (a[0]+t*dx, a[1]+t*dy)
            distance = math.dist(point, projected)
            if best is None or distance < best[0]:
                best = (distance, index, t)
        if best is None:
            raise ValueError("Road boundary has zero length")
        distance, index, t = best
        a, b = coords[index:index+2]
        def is_left(u, v, q):
            return (v[0]-u[0])*(q[1]-u[1]) - (v[1]-u[1])*(q[0]-u[0]) > 0
        side = is_left(a, b, point)
        if t == 1.0 and index + 2 < len(coords):
            following = coords[index+2]
            if side != is_left(b, following, point) and side == is_left(a, b, following):
                side = not side
        return distance if side else -distance

    if signed_distance(left, middle(right)) >= 0:
        left.reverse()
    if signed_distance(right, middle(left)) <= 0:
        right.reverse()
    return left, right


def interpolate_polyline(coords, fraction):
    target = fraction * polyline_length(coords)
    for a, b in zip(coords, coords[1:]):
        length = math.dist(a, b)
        if target <= length or b == coords[-1]:
            t = min(1.0, max(0.0, target / length)) if length else 0.0
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        target -= length
    return coords[-1]


def point_polyline_distance(point, coords):
    px, py = point
    best = float("inf")
    for (ax, ay), (bx, by) in zip(coords, coords[1:]):
        dx, dy = bx - ax, by - ay
        denom = dx * dx + dy * dy
        t = min(1.0, max(0.0, ((px - ax) * dx + (py - ay) * dy) / denom)) if denom else 0.0
        best = min(best, math.hypot(px - ax - t * dx, py - ay - t * dy))
    return best


def load_source_writer():
    """Load BehaviorBench's writer without importing its Python 3.11 C extension."""
    source = BENCH / "pufferlib/ocean/drive/drive.py"
    tree = ast.parse(source.read_text())
    names = {"calculate_area", "dist", "simplify_polyline", "save_map_binary"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == names
    ns = {"struct": struct}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    return ns["save_map_binary"]


def source_tracks():
    tracks = {}
    with (SOURCE / f"data/{RECORDING:02d}_tracks.csv").open() as f:
        for row in csv.DictReader(f):
            frame = int(row["frame"])
            if FIRST_FRAME <= frame <= math.ceil(FRAMES[-1]):
                tracks.setdefault(int(row["trackId"]), []).append(row)
    with (SOURCE / f"data/{RECORDING:02d}_tracksMeta.csv").open() as f:
        meta = {int(r["trackId"]): r for r in csv.DictReader(f)}
    with (SOURCE / f"data/{RECORDING:02d}_recordingMeta.csv").open() as f:
        recording_meta = next(csv.DictReader(f))
    return tracks, meta, recording_meta


def enforce_actor_capacity(count):
    if count > 128:
        raise ValueError(f"Scene has {count} actors; BehaviorBench supports at most 128")


def make_object(track_id, rows, meta):
    src_frames = np.array([int(r["frame"]) for r in rows])
    if len(src_frames) < 2:
        return None
    valid = (FRAMES >= src_frames[0]) & (FRAMES <= src_frames[-1])
    if valid.sum() < 2:
        return None

    def series(key):
        return np.interp(FRAMES, src_frames, [float(r[key]) for r in rows])

    x, y, vx, vy = (series(k) for k in ("xCenter", "yCenter", "xVelocity", "yVelocity"))
    angles = np.unwrap(np.deg2rad([float(r["heading"]) for r in rows]))
    heading = np.interp(FRAMES, src_frames, angles)
    cls = meta["class"]
    kind = {"car": "vehicle", "truck_bus": "vehicle", "pedestrian": "pedestrian", "bicycle": "cyclist"}.get(cls)
    if kind is None:
        return None
    source_length, source_width = float(meta["length"]), float(meta["width"])
    source_xy = [(float(r["xCenter"]), float(r["yCenter"])) for r in rows]
    source_path_length = sum(math.dist(a, b) for a, b in zip(source_xy, source_xy[1:]))
    source_max_speed = max(math.hypot(float(r["xVelocity"]), float(r["yVelocity"])) for r in rows)
    defaults = {"pedestrian": (0.6, 0.6), "cyclist": (1.8, 0.6), "vehicle": (4.5, 1.8)}
    length = source_length if source_length > 0 else defaults[kind][0]
    width = source_width if source_width > 0 else defaults[kind][1]
    positions = [{"x": float(a), "y": float(b), "z": 0.0} for a, b in zip(x, y)]
    velocities = [{"x": float(a), "y": float(b), "z": 0.0} for a, b in zip(vx, vy)]
    last = int(np.flatnonzero(valid)[-1])
    return {
        "id": track_id, "type": kind, "length": length,
        "width": width, "height": 1.6 if kind == "vehicle" else 1.7,
        "dimension_imputed": source_length <= 0 or source_width <= 0,
        "source_window_path_length_m": source_path_length,
        "source_window_max_speed_mps": source_max_speed,
        "position": positions, "velocity": velocities, "heading": heading.tolist(),
        "valid": valid.astype(int).tolist(), "goalPosition": positions[last],
        "mark_as_expert": 0,
    }


def continued_background_goal(obj):
    """Put a non-ego continuation goal beyond the recorded track end.

    The source validity mask still controls actor retirement. This goal only
    prevents GOAL_REMOVE from erasing a traffic actor before its source exit.
    """
    valid = [i for i, value in enumerate(obj["valid"]) if value]
    last = valid[-1]
    first_recent = valid[max(0, len(valid) - 6)]
    end = obj["position"][last]
    recent = obj["position"][first_recent]
    dx, dy = end["x"] - recent["x"], end["y"] - recent["y"]
    norm = math.hypot(dx, dy)
    if norm < 0.5:
        dx, dy = math.cos(obj["heading"][last]), math.sin(obj["heading"][last])
        norm = 1.0
    ux, uy = dx / norm, dy / norm
    for multiplier in (1.0, 1.6, 2.4, 4.0, 6.0):
        distance = multiplier * BACKGROUND_GOAL_MIN_DISTANCE
        goal = {"x": end["x"] + ux * distance, "y": end["y"] + uy * distance, "z": 0.0}
        if all(math.dist((obj["position"][i]["x"], obj["position"][i]["y"]),
                         (goal["x"], goal["y"])) > 4.0 for i in valid):
            return goal
    raise ValueError(f"No continuation goal clear of track {obj['id']}")


def project_nodes(osm, origin_x, origin_y):
    nodes = osm.findall("node")
    payload = "".join(f"{n.get('lon')} {n.get('lat')}\n" for n in nodes)
    proc = subprocess.run(
        ["cs2cs", "-f", "%.7f", "+proj=longlat", "+datum=WGS84", "+to",
         "+proj=utm", "+zone=32", "+datum=WGS84"],
        input=payload, text=True, capture_output=True, check=True,
    )
    projected = [line.split() for line in proc.stdout.splitlines()]
    assert len(projected) == len(nodes)
    return {int(n.get("id")): (float(p[0]) - origin_x, float(p[1]) - origin_y)
            for n, p in zip(nodes, projected)}


def make_roads(recording_meta):
    # All inD maps here use UTM zone 32 with recording-specific local origins.
    lanelet_path, _ = map_paths(recording_meta)
    osm = ET.parse(lanelet_path).getroot()
    nodes = project_nodes(osm, float(recording_meta["xUtmOrigin"]), float(recording_meta["yUtmOrigin"]))
    ways = {}
    way_nodes = {}
    way_types = {}
    for way in osm.findall("way"):
        wid = int(way.get("id"))
        way_nodes[wid] = [int(nd.get("ref")) for nd in way.findall("nd")]
        ways[wid] = [nodes[nid] for nid in way_nodes[wid]]
        way_types[wid] = {t.get("k"): t.get("v") for t in way.findall("tag")}

    lanes = {}
    for rel in osm.findall("relation"):
        tags = {t.get("k"): t.get("v") for t in rel.findall("tag")}
        if tags.get("type") != "lanelet" or tags.get("subtype") not in ("road", "bus_lane"):
            continue
        refs = {m.get("role"): int(m.get("ref")) for m in rel.findall("member") if m.get("type") == "way"}
        if "left" not in refs or "right" not in refs:
            continue
        left_ids, right_ids = orient_road_boundaries(
            way_nodes[refs["left"]], way_nodes[refs["right"]], nodes)
        left, right = [nodes[i] for i in left_ids], [nodes[i] for i in right_ids]
        n = max(2, math.ceil(max(polyline_length(left), polyline_length(right)) / 2) + 1)
        coords = []
        for t in np.linspace(0, 1, n):
            a, b = interpolate_polyline(left, float(t)), interpolate_polyline(right, float(t))
            coords.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        lanes[int(rel.get("id"))] = {"coords": coords, "refs": refs,
                                      "left_nodes": left_ids, "right_nodes": right_ids,
                                      "width": math.dist(interpolate_polyline(left, 0.5), interpolate_polyline(right, 0.5))}

    roads = []
    for lid, lane in lanes.items():
        end = lane["coords"][-1]
        a = np.array(lane["coords"][-1]) - np.array(lane["coords"][-2])
        exits = []
        for next_id, other in lanes.items():
            if lid == next_id:
                continue
            start = other["coords"][0]
            b = np.array(other["coords"][1]) - np.array(start)
            left_shared = lane["left_nodes"][-1] == other["left_nodes"][0]
            right_shared = lane["right_nodes"][-1] == other["right_nodes"][0]
            # A following lane shares both directed boundary endpoints.
            # One shared endpoint can instead be an adjacent/lateral lane;
            # it must not become an IDM successor just because it is close.
            shared = left_shared and right_shared
            near = math.dist(end, start) <= 1.0
            aligned = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)) > 0.5
            # Shared endpoints alone do not establish travel direction: a
            # lanelet can meet the same node while pointing back upstream.
            if aligned and shared and near:
                exits.append(next_id)
        roads.append({"id": lid, "type": "lane", "map_element_id": 2,
                      "geometry": [{"x": x, "y": y, "z": 0.0} for x, y in lane["coords"]],
                      "width": lane["width"], "exit_lanes": sorted(exits)})
    edge_types = {"all": ("road_border", "curbstone"),
                  "road_border_only": ("road_border",),
                  "none": ()}[EDGE_MODE]
    for wid, coords in ways.items():
        if way_types[wid].get("type") in edge_types:
            roads.append({"id": wid, "type": "road_edge", "map_element_id": 15,
                          "geometry": [{"x": x, "y": y, "z": 0.0} for x, y in coords]})
    if EMIT_CROSSWALKS:
        for rel in osm.findall("relation"):
            rel_tags = {tag.get("k"): tag.get("v") for tag in rel.findall("tag")}
            if rel_tags.get("type") != "lanelet" or rel_tags.get("subtype") != "crosswalk":
                continue
            refs = {member.get("role"): int(member.get("ref"))
                    for member in rel.findall("member") if member.get("type") == "way"}
            if "left" not in refs or "right" not in refs:
                raise ValueError(f"Crosswalk {rel.get('id')} lacks left/right boundaries")
            polygon = lanelet_polygon(ways[refs["left"]], ways[refs["right"]])
            if len(polygon) < 4:
                raise ValueError(f"Crosswalk {rel.get('id')} has fewer than four vertices")
            roads.append({"id": int(rel.get("id")), "type": "crosswalk",
                          "map_element_id": 18,
                          "geometry": [{"x": x, "y": y, "z": 0.0} for x, y in polygon]})
    return roads, lanes


def read_binary(path):
    import importlib.util
    source = BENCH / "pufferlib/prediction/binary_reader.py"
    spec = importlib.util.spec_from_file_location("behaviorbench_binary_reader", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_binary_scenario(str(path))


def validate(data, binary, lanes, recording_meta):
    assert binary["sdc_track_index"] == 0
    assert len(binary["objects"]) == len(data["objects"])
    assert len(binary["roads"]) == len(data["roads"])
    source_crosswalks = {road["id"]: road for road in data["roads"] if road["type"] == "crosswalk"}
    binary_crosswalks = {road["id"]: road for road in binary["roads"] if road["type"] == 8}
    assert source_crosswalks.keys() == binary_crosswalks.keys()
    for crosswalk_id, source_crosswalk in source_crosswalks.items():
        encoded = binary_crosswalks[crosswalk_id]
        assert len(encoded["polyline_x"]) == len(source_crosswalk["geometry"])
        for source_point, x, y in zip(source_crosswalk["geometry"],
                                      encoded["polyline_x"], encoded["polyline_y"]):
            assert math.dist((source_point["x"], source_point["y"]), (x, y)) < 0.01
    assert len(FRAMES) == 91 and float(recording_meta["frameRate"]) == 25.0
    _, opendrive_path = map_paths(recording_meta)
    odr_header = ET.parse(opendrive_path).getroot().find("header")
    odr_offset = odr_header.find("offset")
    origin_delta = math.dist(
        (float(odr_offset.get("x")), float(odr_offset.get("y"))),
        (float(recording_meta["xUtmOrigin"]), float(recording_meta["yUtmOrigin"])),
    )
    # Some OpenDRIVE headers round their UTM offset to 0.1 m (location 2).
    assert origin_delta < 0.1
    errors = []
    for src, obj in zip(data["objects"], binary["objects"]):
        assert obj["id"] == src["id"]
        for axis in ("x", "y"):
            expected = np.array([p[axis] for p in src["position"]])
            actual = obj[f"traj_{axis}"]
            errors.append(float(np.max(abs(expected - actual))))
        assert np.array_equal(obj["traj_valid"], src["valid"])
        assert np.max(abs(np.array(src["heading"]) - obj["traj_heading"])) < 1e-5
        assert np.max(abs(np.array([v["x"] for v in src["velocity"]]) - obj["traj_vx"])) < 1e-5
    ego = data["objects"][0]
    ego_pts = [(p["x"], p["y"]) for p in ego["position"]]
    lane_lines = [lane["coords"] for lane in lanes.values()]
    lane_distances = [min(point_polyline_distance(pt, line) for line in lane_lines) for pt in ego_pts]
    lane_by_id = {r["id"]: r for r in binary["roads"] if r["type"] == 4}
    assert all(e in lane_by_id for r in lane_by_id.values() for e in r["exit_lanes"])
    goal_pt = (ego["goalPosition"]["x"], ego["goalPosition"]["y"])
    nearest_lanes = [min(lanes, key=lambda lid: point_polyline_distance(pt, lanes[lid]["coords"]))
                     for pt in (ego_pts[0], goal_pt)]
    reachable = {nearest_lanes[0]}
    frontier = [nearest_lanes[0]]
    while frontier:
        for next_id in lane_by_id[frontier.pop()]["exit_lanes"]:
            if next_id not in reachable:
                reachable.add(next_id)
                frontier.append(next_id)
    return {
        "recording": RECORDING, "location": int(recording_meta["locationId"]),
        "ego_track": EGO_ID, "first_frame": FIRST_FRAME,
        "late_arriving_objects": sum(not obj["valid"][0] for obj in data["objects"]),
        "edge_mode": EDGE_MODE,
        "source_hz": 25,
        "scenario_hz": 10, "duration_seconds": 9.0,
        "opendrive_csv_origin_delta_m": origin_delta,
        "objects": len(data["objects"]), "roads": len(data["roads"]),
        "emitted_crosswalk_ids": sorted(source_crosswalks),
        "imputed_dimension_track_ids": [obj["id"] for obj in data["objects"] if obj["dimension_imputed"]],
        "lanes": len(lanes), "lane_connections": sum(len(r["exit_lanes"]) for r in lane_by_id.values()),
        "max_binary_position_error_m": max(errors),
        "ego_start": ego["position"][0], "ego_goal": ego["goalPosition"],
        "ego_start_goal_distance_m": math.dist(
            tuple(ego["position"][0][k] for k in ("x", "y")),
            tuple(ego["goalPosition"][k] for k in ("x", "y"))),
        "ego_lane_distance_median_m": float(np.median(lane_distances)),
        "ego_lane_distance_max_m": max(lane_distances),
        "ego_start_lane": nearest_lanes[0], "ego_goal_lane": nearest_lanes[1],
        "ego_goal_lane_reachable_by_successors": nearest_lanes[1] in reachable,
        "binary_round_trip": "passed",
    }


def plot_scene(data, lanes):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 8))
    for lane in lanes.values():
        x, y = zip(*lane["coords"])
        ax.plot(x, y, color="#888888", linewidth=0.7)
    for obj in data["objects"]:
        points = [p for p, valid in zip(obj["position"], obj["valid"]) if valid]
        if not points:
            continue
        color = "#d62728" if obj["id"] == EGO_ID else "#1f77b4"
        ax.plot([p["x"] for p in points], [p["y"] for p in points], color=color,
                linewidth=2.5 if obj["id"] == EGO_ID else 0.9, alpha=0.9)
    ego = data["objects"][0]
    ax.scatter([ego["position"][0]["x"], ego["goalPosition"]["x"]],
               [ego["position"][0]["y"], ego["goalPosition"]["y"]], c=["green", "red"])
    ax.set(xlabel="inD local x (m)", ylabel="inD local y (m)",
           title=f"inD recording {RECORDING:02d}, ego track {EGO_ID}, frames {FIRST_FRAME}–{int(FRAMES[-1])}")
    ax.set_aspect("equal")
    ego_x = [p["x"] for p in ego["position"]]
    ego_y = [p["y"] for p in ego["position"]]
    ax.set_xlim(min(ego_x) - 50, max(ego_x) + 50)
    ax.set_ylim(min(ego_y) - 50, max(ego_y) + 50)
    fig.tight_layout()
    fig.savefig(OUT / "overlay.png", dpi=150)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tracks, meta, recording_meta = source_tracks()
    candidate_objects = []
    for track_id in sorted(tracks, key=lambda x: (x != EGO_ID, x)):
        obj = make_object(track_id, tracks[track_id], meta[track_id])
        if obj is not None:
            candidate_objects.append(obj)
    ego_positions = candidate_objects[0]["position"]
    objects = []
    excluded = []
    for obj in candidate_objects:
        valid_positions = [p for p, valid in zip(obj["position"], obj["valid"]) if valid]
        path_length = sum(math.dist((a["x"], a["y"]), (b["x"], b["y"]))
                          for a, b in zip(valid_positions, valid_positions[1:]))
        max_speed = max(math.hypot(v["x"], v["y"]) for v, valid in zip(obj["velocity"], obj["valid"]) if valid)
        stationary = (path_length < 0.5 and max_speed < 0.1
                      and obj["source_window_path_length_m"] < 0.5
                      and obj["source_window_max_speed_mps"] < 0.1)
        closest_to_ego = min(
            math.dist((p["x"], p["y"]), (ep["x"], ep["y"]))
            for p, ep, valid in zip(obj["position"], ego_positions, obj["valid"]) if valid
        )
        if PARKED_AS_STATIC_EXPERT and obj["type"] == "vehicle" and stationary:
            obj["mark_as_expert"] = 1
        if obj["id"] in EXCLUDE_TRACK_IDS or (obj["id"] != EGO_ID and stationary and closest_to_ego > STATIC_CROP_RADIUS):
            excluded.append(obj["id"])
        else:
            objects.append(obj)
    assert objects and objects[0]["id"] == EGO_ID and all(objects[0]["valid"])
    if BACKGROUND_GOAL_MODE == "continue":
        for obj in objects[1:]:
            if obj["type"] == "vehicle" and not obj["mark_as_expert"]:
                obj["goalPosition"] = continued_background_goal(obj)
    # The C engine stores at most 128 actor slots, including future births and
    # expert background actors. Reject rather than silently dropping extras.
    enforce_actor_capacity(len(objects))
    source_late_ids = [obj["id"] for obj in objects if not obj["valid"][0]]
    if source_late_ids and LATE_MODE == "reject":
        raise ValueError(f"Late arrivals need simulator spawn support: {source_late_ids}")
    if source_late_ids and LATE_MODE == "bootstrap_probe":
        # Technical probe only: the actor flashes at its future entry point at t=0.
        # This changes the source scene and must never be used for planner scores.
        for obj in objects:
            if obj["id"] in source_late_ids:
                obj["valid"][0] = 1
    assert LATE_MODE == "runtime_spawn" or all(obj["valid"][0] for obj in objects)
    # Leave half a second after the recorded goal for the evaluator to register it.
    objects[0]["goalPosition"] = objects[0]["position"][GOAL_SAMPLE]
    roads, lanes = make_roads(recording_meta)
    data = {"name": SCENE_NAME, "scenario_id": SCENE_NAME,
            "metadata": {"sdc_track_index": 0, "tracks_to_predict": []},
            "objects": objects, "roads": roads, "tl_states": {}}
    json_path = OUT / f"{SCENE_NAME}.json"
    json_path.write_text(json.dumps(data, separators=(",", ":")))
    bin_path = OUT / "map_000000.bin"
    load_source_writer()(data, str(bin_path), 0, trajectory_length=91)
    binary = read_binary(bin_path)
    report = validate(data, binary, lanes, recording_meta)
    report["binary_sha256"] = hashlib.sha256(bin_path.read_bytes()).hexdigest()
    report["excluded_distant_static_track_ids"] = excluded
    report["static_crop_radius_m"] = STATIC_CROP_RADIUS
    report["explicit_excluded_track_ids"] = sorted(EXCLUDE_TRACK_IDS)
    report["parked_as_static_expert_track_ids"] = [obj["id"] for obj in objects if obj["mark_as_expert"]]
    report["stationary_rule"] = {"sampled_path_length_max_m": 0.5,
                                 "sampled_speed_max_mps": 0.1,
                                 "source_rate_path_length_max_m": 0.5,
                                 "source_rate_speed_max_mps": 0.1}
    report["background_goal_mode"] = BACKGROUND_GOAL_MODE
    report["background_goal_min_distance_m"] = BACKGROUND_GOAL_MIN_DISTANCE
    report["source_late_arriving_track_ids"] = source_late_ids
    report["late_mode"] = LATE_MODE
    report["ego_goal_sample"] = GOAL_SAMPLE
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    with (OUT / "manifest.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["new_filename", "original_filename", "ego_agent_idx", "map_id"])
        w.writeheader()
        w.writerow({"new_filename": bin_path.name, "original_filename": bin_path.name,
                    "ego_agent_idx": 0, "map_id": 0})
    plot_scene(data, lanes)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=int, default=RECORDING)
    parser.add_argument("--ego", type=int, default=EGO_ID)
    parser.add_argument("--first-frame", type=int, default=FIRST_FRAME)
    parser.add_argument("--goal-sample", type=int, default=GOAL_SAMPLE)
    parser.add_argument("--edge-mode", choices=["all", "road_border_only", "none"], default=EDGE_MODE)
    parser.add_argument("--late-mode", choices=["reject", "bootstrap_probe", "runtime_spawn"], default=LATE_MODE)
    parser.add_argument("--static-crop-radius", type=float, default=STATIC_CROP_RADIUS)
    parser.add_argument("--exclude-track-ids", type=int, nargs="*", default=[])
    parser.add_argument("--parked-as-static-expert", action="store_true")
    parser.add_argument("--background-goal-mode", choices=["source_end", "continue"], default=BACKGROUND_GOAL_MODE)
    parser.add_argument("--background-goal-min-distance", type=float, default=BACKGROUND_GOAL_MIN_DISTANCE)
    parser.add_argument("--emit-crosswalks", action="store_true",
                        help="Encode Lanelet2 crosswalk polygons as BehaviorBench map type 8")
    parser.add_argument("--output-root", type=Path, default=HERE / "pilot")
    args = parser.parse_args()
    assert 10 <= args.goal_sample <= 85, "Leave at least 0.5 s for goal registration"
    RECORDING = args.recording
    EGO_ID = args.ego
    FIRST_FRAME = args.first_frame
    GOAL_SAMPLE = args.goal_sample
    EDGE_MODE = args.edge_mode
    LATE_MODE = args.late_mode
    STATIC_CROP_RADIUS = args.static_crop_radius
    EXCLUDE_TRACK_IDS = set(args.exclude_track_ids)
    PARKED_AS_STATIC_EXPERT = args.parked_as_static_expert
    BACKGROUND_GOAL_MODE = args.background_goal_mode
    BACKGROUND_GOAL_MIN_DISTANCE = args.background_goal_min_distance
    EMIT_CROSSWALKS = args.emit_crosswalks
    if EGO_ID in EXCLUDE_TRACK_IDS:
        parser.error("Cannot exclude ego track")
    FRAMES = np.arange(91, dtype=float) * 2.5 + FIRST_FRAME
    SCENE_NAME = f"ind_{RECORDING:02d}_track_{EGO_ID}_frame_{FIRST_FRAME}"
    OUT = args.output_root.resolve() / "testing"
    main()
