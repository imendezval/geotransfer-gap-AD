"""Source-linked applicability evidence for inD priority and crosswalk rules.

This report is conservative evidence for review, not a legal-rule oracle.
"""

from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from geotransfer_gap.maps.audit_scene import inside
from geotransfer_gap.validation.audit_physical_source import corners
from geotransfer_gap.validation.audit_parked_contacts import segment_hits_box


def tags(node):
    return {x.get("k"): x.get("v") for x in node.findall("tag")}


def polygon_of(rel, ways):
    refs = {
        x.get("role"): int(x.get("ref"))
        for x in rel.findall("member")
        if x.get("type") == "way"
    }
    if "left" not in refs or "right" not in refs:
        return None
    return map_geometry.lanelet_polygon(ways[refs["left"]], ways[refs["right"]])


def box_hits_polygon(obj, step, polygon):
    box = corners(obj, step)
    if any((inside(pt, polygon) for pt in box)) or any(
        (inside(pt, box) for pt in polygon)
    ):
        return True
    center = obj["position"][step]
    return any(
        (
            segment_hits_box(
                a,
                b,
                (center["x"], center["y"]),
                obj["heading"][step],
                obj["length"],
                obj["width"],
            )
            for a, b in zip(polygon, polygon[1:] + polygon[:1])
        )
    )


def path_clearance(a, b):
    best = (float("inf"), None, None)
    for i, pa in enumerate(a["position"]):
        if not a["valid"][i]:
            continue
        for j, pb in enumerate(b["position"]):
            if not b["valid"][j]:
                continue
            d = math.dist((pa["x"], pa["y"]), (pb["x"], pb["y"]))
            if d < best[0]:
                best = (d, i, j)
    radius_a = math.hypot(a["length"], a["width"]) / 2
    radius_b = math.hypot(b["length"], b["width"]) / 2
    return {
        "minimum_center_distance_m": best[0],
        "ego_step": best[1],
        "actor_step": best[2],
        "bounding_circle_clearance_m": best[0] - radius_a - radius_b,
    }


def timed_clearance(a, b):
    """Closest simultaneous center distance; include source birth and exit."""
    rows = [
        (math.dist((pa["x"], pa["y"]), (pb["x"], pb["y"])), t)
        for t, (pa, pb) in enumerate(zip(a["position"], b["position"]))
        if a["valid"][t] and b["valid"][t]
    ]
    distance, step = min(rows) if rows else (None, None)
    return {
        "minimum_timed_center_distance_m": distance,
        "nearest_timed_step": step,
        "actor_first_valid_step": next(
            (t for t, valid in enumerate(b["valid"]) if valid), None
        ),
        "actor_last_valid_step": next(
            (t for t in range(len(b["valid"]) - 1, -1, -1) if b["valid"][t]), None
        ),
        "actor_source_path_m": b["source_window_path_length_m"],
    }


def polygon_overlap(ac, bc):
    for poly in (ac, bc):
        for u, v in zip(poly, poly[1:] + poly[:1]):
            axis = (v[1] - u[1], u[0] - v[0])
            ap = [x * axis[0] + y * axis[1] for x, y in ac]
            bp = [x * axis[0] + y * axis[1] for x, y in bc]
            if max(ap) < min(bp) or max(bp) < min(ap):
                return False
    return True


def point_segment_distance(pt, a, b):
    vx, vy = (b[0] - a[0], b[1] - a[1])
    denom = vx * vx + vy * vy
    fraction = (
        max(0.0, min(1.0, ((pt[0] - a[0]) * vx + (pt[1] - a[1]) * vy) / denom))
        if denom
        else 0
    )
    return math.dist(pt, (a[0] + fraction * vx, a[1] + fraction * vy))


def box_distance(ac, bc):
    if polygon_overlap(ac, bc):
        return 0.0
    return min(
        (
            point_segment_distance(pt, u, v)
            for pts, poly in ((ac, bc), (bc, ac))
            for pt in pts
            for u, v in zip(poly, poly[1:] + poly[:1])
        )
    )


def box_path_clearance(a, b):
    """Minimum source-scale oriented-box gap with and without recorded timing."""
    first = (float("inf"), None, None)
    timed = (float("inf"), None)
    ar = math.hypot(a["length"], a["width"]) / 2
    br = math.hypot(b["length"], b["width"]) / 2
    abox = {i: corners(a, i) for i, valid in enumerate(a["valid"]) if valid}
    bbox = {j: corners(b, j) for j, valid in enumerate(b["valid"]) if valid}
    for i, ac in abox.items():
        pa = a["position"][i]
        for j, bc in bbox.items():
            pb = b["position"][j]
            lower = math.dist((pa["x"], pa["y"]), (pb["x"], pb["y"])) - ar - br
            if lower >= first[0] and (i != j or lower >= timed[0]):
                continue
            d = box_distance(ac, bc)
            if d < first[0]:
                first = (d, i, j)
            if i == j and d < timed[0]:
                timed = (d, i)
    return {
        "minimum_spatial_box_gap_m": first[0],
        "spatial_box_ego_step": first[1],
        "spatial_box_actor_step": first[2],
        "minimum_timed_box_gap_m": timed[0],
        "timed_box_step": timed[1],
    }


def moving_actor_proximity(ego, obj):
    shared = [
        t for t in range(len(ego["valid"])) if ego["valid"][t] and obj["valid"][t]
    ]
    if not shared or obj["source_window_path_length_m"] < 1.0:
        return None
    center = min(
        (
            (
                math.dist(
                    (ego["position"][t]["x"], ego["position"][t]["y"]),
                    (obj["position"][t]["x"], obj["position"][t]["y"]),
                ),
                t,
            )
            for t in shared
        )
    )
    if center[0] > 25.0:
        return None
    box = min(
        (
            (box_distance(corners(ego, t), corners(obj, t)), t)
            for t in shared
            if math.dist(
                (ego["position"][t]["x"], ego["position"][t]["y"]),
                (obj["position"][t]["x"], obj["position"][t]["y"]),
            )
            <= center[0] + 15
        )
    )
    return {
        "track_id": obj["id"],
        "type": obj["type"],
        "source_path_m": obj["source_window_path_length_m"],
        "minimum_timed_center_distance_m": center[0],
        "center_step": center[1],
        "minimum_timed_box_gap_m": box[0],
        "box_step": box[1],
    }


def audit(root):
    testing = root / "testing"
    scene = json.loads(next(testing.glob("ind_*.json")).read_text())
    validation = json.loads((testing / "validation.json").read_text())
    geometry = json.loads((testing / "map_audit.json").read_text())
    semantics = json.loads((testing / "map_semantics_audit.json").read_text())
    recording = int(validation["recording"])
    source = settings().source / "data"
    with (source / f"{recording:02d}_recordingMeta.csv").open() as f:
        meta = next(csv.DictReader(f))
    osm_path, xodr_path = map_geometry.map_paths(meta, recording)
    osm = ET.parse(osm_path).getroot()
    projected = map_geometry.project_nodes(
        osm, float(meta["xUtmOrigin"]), float(meta["yUtmOrigin"])
    )
    ways = {
        int(w.get("id")): [projected[int(n.get("ref"))] for n in w.findall("nd")]
        for w in osm.findall("way")
    }
    way_tags = {int(w.get("id")): tags(w) for w in osm.findall("way")}
    relations = {int(r.get("id")): r for r in osm.findall("relation")}
    ego = scene["objects"][0]
    occupied = {
        lane
        for sample in geometry["ego_samples"]
        for lane in sample["occupied_lanelets"]
    }
    rules = []
    priority_lanes = set()
    for rid, rel in relations.items():
        rt = tags(rel)
        if rt.get("type") != "regulatory_element":
            continue
        members = [
            {"role": x.get("role"), "type": x.get("type"), "id": int(x.get("ref"))}
            for x in rel.findall("member")
        ]
        ego_members = [
            m for m in members if m["type"] == "relation" and m["id"] in occupied
        ]
        if not ego_members:
            continue
        priority = [
            m["id"]
            for m in members
            if m["type"] == "relation" and m["role"] == "right_of_way"
        ]
        priority_lanes.update(priority)
        rules.append(
            {
                "id": rid,
                "subtype": rt.get("subtype"),
                "ego_members": ego_members,
                "priority_lanelets": priority,
                "signs": [
                    {
                        "id": m["id"],
                        "type": way_tags.get(m["id"], {}).get("type"),
                        "subtype": way_tags.get(m["id"], {}).get("subtype"),
                    }
                    for m in members
                    if m["type"] == "way" and m["role"] == "refers"
                ],
            }
        )
    ego_boundaries = []
    for lid in sorted(occupied):
        rel = relations.get(lid)
        if rel is None or tags(rel).get("type") != "lanelet":
            continue
        for member in rel.findall("member"):
            if member.get("type") != "way" or member.get("role") not in (
                "left",
                "right",
            ):
                continue
            wid = int(member.get("ref"))
            ego_boundaries.append(
                {
                    "lanelet_id": lid,
                    "side": member.get("role"),
                    "way_id": wid,
                    "tags": way_tags.get(wid, {}),
                }
            )
    priority_polygons = {
        i: polygon_of(relations[i], ways) for i in priority_lanes if i in relations
    }
    traffic = []
    for obj in scene["objects"][1:]:
        lane_steps = {
            str(lid): [
                t
                for t, pt in enumerate(obj["position"])
                if obj["valid"][t] and poly and inside((pt["x"], pt["y"]), poly)
            ]
            for lid, poly in priority_polygons.items()
        }
        lane_steps = {lid: steps for lid, steps in lane_steps.items() if steps}
        priority_steps = sorted({t for steps in lane_steps.values() for t in steps})
        traffic.append(
            {
                "track_id": obj["id"],
                "type": obj["type"],
                "priority_lane_steps": priority_steps,
                "priority_lanelet_steps": lane_steps,
                **timed_clearance(ego, obj),
                **path_clearance(ego, obj),
                **box_path_clearance(ego, obj),
            }
        )
    crosswalks = []
    for rid, rel in relations.items():
        if (
            tags(rel).get("type") != "lanelet"
            or tags(rel).get("subtype") != "crosswalk"
        ):
            continue
        poly = polygon_of(rel, ways)
        if not poly:
            continue
        contact = [
            t
            for t in range(len(ego["valid"]))
            if ego["valid"][t] and box_hits_polygon(ego, t, poly)
        ]
        near = []
        for t, pt in enumerate(ego["position"]):
            if not ego["valid"][t]:
                continue
            xy = (pt["x"], pt["y"])
            if (
                inside(xy, poly)
                or map_geometry.point_polyline_distance(xy, poly + [poly[0]]) <= 5.0
            ):
                near.append(t)
        if not near:
            continue
        vrus = []
        for obj in scene["objects"][1:]:
            if obj["type"] not in ("pedestrian", "cyclist"):
                continue
            near_steps = sorted(
                {
                    j
                    for t in near
                    for j in range(max(0, t - 5), min(len(obj["valid"]), t + 6))
                    if obj["valid"][j]
                }
            )
            if not near_steps:
                continue
            distances = [
                (
                    0.0
                    if inside((obj["position"][j]["x"], obj["position"][j]["y"]), poly)
                    else map_geometry.point_polyline_distance(
                        (obj["position"][j]["x"], obj["position"][j]["y"]),
                        poly + [poly[0]],
                    )
                )
                for j in near_steps
            ]
            all_steps = [j for j, valid in enumerate(obj["valid"]) if valid]
            all_distances = [
                (
                    0.0
                    if inside((obj["position"][j]["x"], obj["position"][j]["y"]), poly)
                    else map_geometry.point_polyline_distance(
                        (obj["position"][j]["x"], obj["position"][j]["y"]),
                        poly + [poly[0]],
                    )
                )
                for j in all_steps
            ]
            vrus.append(
                {
                    "track_id": obj["id"],
                    "minimum_distance_to_crosswalk_m": min(distances),
                    "closest_step": near_steps[distances.index(min(distances))],
                    "minimum_distance_any_source_step_m": min(all_distances),
                }
            )
        crosswalks.append(
            {
                "lanelet_id": rid,
                "ego_box_contact_steps": contact,
                "ego_within_5m_center_steps": near,
                "nearby_vrus": sorted(
                    vrus, key=lambda x: x["minimum_distance_to_crosswalk_m"]
                ),
            }
        )
    near_signs = [
        s
        for s in semantics["source_traffic_signs"]
        if s["minimum_ego_center_distance_m"] <= 20.0
    ]
    near_markings = (
        semantics["omitted_thick_markings_within_5m_of_ego"]
        + semantics["omitted_walls_and_fences_within_5m_of_ego"]
    )
    moving_actors = [
        result
        for obj in scene["objects"][1:]
        if (result := moving_actor_proximity(ego, obj)) is not None
    ]
    first_heading = next(
        (ego["heading"][t] for t, valid in enumerate(ego["valid"]) if valid)
    )
    last_heading = next(
        (
            ego["heading"][t]
            for t in range(len(ego["valid"]) - 1, -1, -1)
            if ego["valid"][t]
        )
    )
    ego_turn_rad = abs(
        math.atan2(
            math.sin(last_heading - first_heading),
            math.cos(last_heading - first_heading),
        )
    )
    by_id = {obj["id"]: obj for obj in scene["objects"]}
    oncoming_turn_conflicts = []
    if ego_turn_rad >= 0.5:
        for actor in traffic:
            t = actor["spatial_box_actor_step"]
            if t is None or actor["type"] not in ("vehicle", "cyclist"):
                continue
            obj = by_id[actor["track_id"]]
            angle = abs(
                math.atan2(
                    math.sin(obj["heading"][t] - first_heading),
                    math.cos(obj["heading"][t] - first_heading),
                )
            )
            if (
                actor["actor_source_path_m"] >= 5.0
                and angle >= 2.3
                and (actor["minimum_spatial_box_gap_m"] <= 2.0)
                and (actor["minimum_timed_center_distance_m"] is not None)
                and (actor["minimum_timed_center_distance_m"] <= 10.0)
            ):
                oncoming_turn_conflicts.append(
                    {
                        "track_id": actor["track_id"],
                        "type": actor["type"],
                        "actor_step": t,
                        "ego_step": actor["spatial_box_ego_step"],
                        "approach_heading_difference_rad": angle,
                        "minimum_spatial_box_gap_m": actor["minimum_spatial_box_gap_m"],
                        "minimum_timed_center_distance_m": actor[
                            "minimum_timed_center_distance_m"
                        ],
                    }
                )
    ego_has_yield_role = any(
        (m["role"] == "yield" for rule in rules for m in rule["ego_members"])
    )
    slow_ego_fast_crosspath_conflicts = []
    yield_lane_fast_crosspath_conflicts = []
    for obj in scene["objects"][1:]:
        if (
            obj["type"] not in ("vehicle", "cyclist")
            or obj["source_window_path_length_m"] < 5
        ):
            continue
        found_narrow = False
        found_yield = False
        for t in range(len(ego["valid"])):
            if not (ego["valid"][t] and obj["valid"][t]):
                continue
            ev, av = (ego["velocity"][t], obj["velocity"][t])
            ego_speed = math.hypot(ev["x"], ev["y"])
            actor_speed = math.hypot(av["x"], av["y"])
            if ego_speed > 3 or actor_speed < 5:
                continue
            ep, ap = (ego["position"][t], obj["position"][t])
            dx, dy = (ap["x"] - ep["x"], ap["y"] - ep["y"])
            heading = ego["heading"][t]
            lateral = -dx * math.sin(heading) + dy * math.cos(heading)
            angle = abs(
                math.atan2(
                    math.sin(obj["heading"][t] - heading),
                    math.cos(obj["heading"][t] - heading),
                )
            )
            center_distance = math.hypot(dx, dy)
            if abs(lateral) > 3 or angle < 0.35 or center_distance > 14:
                continue
            gap = box_distance(corners(ego, t), corners(obj, t))
            evidence = {
                "track_id": obj["id"],
                "type": obj["type"],
                "source_step": t,
                "ego_speed_mps": ego_speed,
                "actor_speed_mps": actor_speed,
                "lateral_offset_m": lateral,
                "heading_difference_rad": angle,
                "source_box_gap_m": gap,
            }
            if ego_has_yield_role and (not found_yield) and (gap <= 5):
                yield_lane_fast_crosspath_conflicts.append(evidence)
                found_yield = True
            if (
                not found_narrow
                and abs(lateral) <= 2.2
                and (center_distance <= 12)
                and (gap <= 3)
            ):
                slow_ego_fast_crosspath_conflicts.append(evidence)
                found_narrow = True
            if found_narrow and (found_yield or not ego_has_yield_role):
                break
    report = {
        "schema_version": 10,
        "binary_sha256": hashlib.sha256(
            (testing / "map_000000.bin").read_bytes()
        ).hexdigest(),
        "lanelet_source_sha256": hashlib.sha256(osm_path.read_bytes()).hexdigest(),
        "opendrive_source_sha256": hashlib.sha256(xodr_path.read_bytes()).hexdigest(),
        "source_tracks_sha256": hashlib.sha256(
            (source / f"{recording:02d}_tracks.csv").read_bytes()
        ).hexdigest(),
        "ego_track_id": ego["id"],
        "ego_occupied_lanelets": sorted(occupied),
        "governing_regulatory_elements": rules,
        "priority_lane_traffic": traffic,
        "ego_box_crosswalk_contacts": crosswalks,
        "nearby_source_signs": near_signs,
        "nearby_omitted_markings": near_markings,
        "ego_lanelet_boundaries": ego_boundaries,
        "moving_actor_proximities": sorted(
            moving_actors, key=lambda x: x["minimum_timed_box_gap_m"]
        ),
        "ego_net_turn_rad": ego_turn_rad,
        "oncoming_turn_conflicts": oncoming_turn_conflicts,
        "slow_ego_fast_crosspath_conflicts": slow_ego_fast_crosspath_conflicts,
        "yield_lane_fast_crosspath_conflicts": yield_lane_fast_crosspath_conflicts,
        "priority_traffic_count": sum(
            (bool(x["priority_lane_steps"]) for x in traffic)
        ),
        "planner_map_observation_types": [4, 5, 6],
        "rules_7_8_visible_in_current_observation": False,
        "review_status": "evidence_only",
    }
    path = testing / "rule_applicability_audit.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("priority_lane_traffic", "ego_box_crosswalk_contacts")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    audit(ap.parse_args().root.resolve())
