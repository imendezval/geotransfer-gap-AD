"""Audit map rules and physical boundaries omitted by the inD converter."""

from geotransfer_gap.conversion import binary as binary_io
from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from geotransfer_gap.maps.audit_scene import inside


def tags(element):
    return {t.get("k"): t.get("v") for t in element.findall("tag")}


def audit(root):
    outdir = root / "testing"
    scene = json.loads(next(outdir.glob("ind_*.json")).read_text())
    validation = json.loads((outdir / "validation.json").read_text())
    geometric = json.loads((outdir / "map_audit.json").read_text())
    recording = validation["recording"]
    with (settings().source / f"data/{recording:02d}_recordingMeta.csv").open() as f:
        meta = next(csv.DictReader(f))
    osm_path, odr_path = map_geometry.map_paths(meta, recording)
    osm, odr = (ET.parse(osm_path).getroot(), ET.parse(odr_path).getroot())
    nodes = map_geometry.project_nodes(
        osm, float(meta["xUtmOrigin"]), float(meta["yUtmOrigin"])
    )
    ways = {}
    for way in osm.findall("way"):
        ids = [int(n.get("ref")) for n in way.findall("nd")]
        ways[int(way.get("id"))] = {
            "tags": tags(way),
            "coords": [nodes[i] for i in ids],
        }
    relations = {int(r.get("id")): r for r in osm.findall("relation")}
    occupied_steps = {}
    for sample in geometric["ego_samples"]:
        for lane_id in sample["occupied_lanelets"]:
            occupied_steps.setdefault(lane_id, []).append(sample["step"])
    rules = []
    for rid, rel in relations.items():
        t = tags(rel)
        if t.get("type") != "regulatory_element":
            continue
        members = [
            {"role": m.get("role"), "type": m.get("type"), "id": int(m.get("ref"))}
            for m in rel.findall("member")
        ]
        ego_refs = [
            {"lanelet_id": m["id"], "role": m["role"], "steps": occupied_steps[m["id"]]}
            for m in members
            if m["type"] == "relation" and m["id"] in occupied_steps
        ]
        rules.append(
            {
                "id": rid,
                "subtype": t.get("subtype"),
                "members": members,
                "ego_lanelet_memberships": ego_refs,
            }
        )
    source_edges = {
        wid
        for wid, way in ways.items()
        if way["tags"].get("type") in ("road_border", "curbstone")
    }
    emitted_edges = {r["id"] for r in scene["roads"] if r["type"] == "road_edge"}
    assert emitted_edges <= source_edges
    ego_points = [(v["x"], v["y"]) for v in scene["objects"][0]["position"]]
    omitted_boundaries = []
    for wid, way in ways.items():
        if way["tags"].get("type") not in ("wall", "fence", "line_thick"):
            continue
        if len(way["coords"]) < 2:
            continue
        omitted_boundaries.append(
            {
                "id": wid,
                "type": way["tags"]["type"],
                "minimum_ego_center_distance_m": min(
                    (
                        map_geometry.point_polyline_distance(pt, way["coords"])
                        for pt in ego_points
                    )
                ),
            }
        )
    crosswalks = []
    for rid, rel in relations.items():
        if (
            tags(rel).get("type") != "lanelet"
            or tags(rel).get("subtype") != "crosswalk"
        ):
            continue
        refs = {
            m.get("role"): int(m.get("ref"))
            for m in rel.findall("member")
            if m.get("type") == "way"
        }
        if "left" not in refs or "right" not in refs:
            continue
        poly = map_geometry.lanelet_polygon(
            ways[refs["left"]]["coords"], ways[refs["right"]]["coords"]
        )
        crosswalks.append(
            {
                "id": rid,
                "ego_steps_inside": [
                    t for t, pt in enumerate(ego_points) if inside(pt, poly)
                ],
                "minimum_ego_center_distance_m": min(
                    (
                        (
                            0
                            if inside(pt, poly)
                            else map_geometry.point_polyline_distance(
                                pt, poly + [poly[0]]
                            )
                        )
                        for pt in ego_points
                    )
                ),
            }
        )
    ego_speed_limits = Counter()
    for lid, steps in occupied_steps.items():
        if lid in relations:
            limit = tags(relations[lid]).get("speed_limit")
            if limit:
                ego_speed_limits[limit] += len(steps)
    source_signs = [
        {
            "id": wid,
            "subtype": way["tags"].get("subtype"),
            "minimum_ego_center_distance_m": (
                min(
                    (
                        map_geometry.point_polyline_distance(pt, way["coords"])
                        for pt in ego_points
                    )
                )
                if len(way["coords"]) > 1
                else min((math.dist(pt, way["coords"][0]) for pt in ego_points))
            ),
        }
        for wid, way in ways.items()
        if way["tags"].get("type") == "traffic_sign" and way["coords"]
    ]
    odr_signals = [
        {
            "id": x.get("id"),
            "name": x.get("name"),
            "type": x.get("type"),
            "dynamic": x.get("dynamic"),
        }
        for x in odr.findall(".//signal")
    ]
    binary = binary_io.read_binary(outdir / "map_000000.bin")
    binary_types = Counter((int(r["type"]) for r in binary["roads"]))
    binary_edges = {
        r["id"]: list(zip(r["polyline_x"], r["polyline_y"]))
        for r in binary["roads"]
        if r["type"] == 6
    }
    edge_deviation = []
    for wid in emitted_edges:
        original, encoded = (ways[wid]["coords"], binary_edges[wid])
        edge_deviation.append(
            max(
                max(
                    (
                        map_geometry.point_polyline_distance(pt, encoded)
                        for pt in original
                    )
                ),
                max(
                    (
                        map_geometry.point_polyline_distance(pt, original)
                        for pt in encoded
                    )
                ),
            )
        )
    report = {
        "lanelet_source_sha256": hashlib.sha256(osm_path.read_bytes()).hexdigest(),
        "opendrive_source_sha256": hashlib.sha256(odr_path.read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(
            (outdir / "map_000000.bin").read_bytes()
        ).hexdigest(),
        "source_regulatory_element_count": len(rules),
        "regulatory_elements_touching_ego_lanelets": [
            r for r in rules if r["ego_lanelet_memberships"]
        ],
        "source_traffic_signs": source_signs,
        "opendrive_signals": odr_signals,
        "ego_lanelet_speed_limit_sample_counts": dict(ego_speed_limits),
        "source_road_border_and_curbstone_ways": len(source_edges),
        "emitted_road_edge_ways": len(emitted_edges),
        "missing_source_road_edges": sorted(source_edges - emitted_edges),
        "max_source_to_binary_road_edge_deviation_m": (
            max(edge_deviation) if edge_deviation else None
        ),
        "source_crosswalk_lanelets": crosswalks,
        "omitted_walls_and_fences": [
            x for x in omitted_boundaries if x["type"] in ("wall", "fence")
        ],
        "omitted_walls_and_fences_within_5m_of_ego": [
            x
            for x in omitted_boundaries
            if x["type"] in ("wall", "fence") and x["minimum_ego_center_distance_m"] < 5
        ],
        "omitted_thick_markings_within_5m_of_ego": [
            x
            for x in omitted_boundaries
            if x["type"] == "line_thick" and x["minimum_ego_center_distance_m"] < 5
        ],
        "binary_road_entity_type_counts": dict(binary_types),
        "binary_has_stop_sign": binary_types[7] > 0,
        "binary_has_crosswalk": binary_types[8] > 0,
        "json_has_dynamic_traffic_states": bool(scene.get("tl_states")),
    }
    report["ego_crosses_unencoded_crosswalk"] = any(
        (x["ego_steps_inside"] for x in crosswalks)
    )
    report["ego_has_unencoded_priority_relation"] = any(
        (r["ego_lanelet_memberships"] for r in rules)
    )
    report["ego_has_unencoded_sign_within_5m"] = any(
        (x["minimum_ego_center_distance_m"] < 5 for x in source_signs)
    )
    report["semantic_transfer_complete_for_ego"] = not (
        report["ego_crosses_unencoded_crosswalk"]
        or report["ego_has_unencoded_priority_relation"]
        or report["ego_has_unencoded_sign_within_5m"]
    )
    report["semantic_screen_pass"] = not (
        report["ego_has_unencoded_priority_relation"]
        or any((x["minimum_ego_center_distance_m"] < 20 for x in source_signs))
        or any((x["minimum_ego_center_distance_m"] < 5 for x in crosswalks))
        or report["omitted_walls_and_fences_within_5m_of_ego"]
        or report["omitted_thick_markings_within_5m_of_ego"]
    )
    (outdir / "map_semantics_audit.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k
                not in (
                    "omitted_walls_and_fences",
                    "source_traffic_signs",
                    "opendrive_signals",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    audit(ap.parse_args().root.resolve())
