"""Read-only source-map context for offline spatial evaluation.

Map interpretation stays with ``maps.lanelet``. This module binds that
interpretation to the selected scene, current portable manifest and the
already-produced map-semantic certificate; it never edits or regenerates any
scene evidence.
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from geotransfer_gap.artifacts import (
    manifest_path,
    read_manifest,
    reference,
    resolve_reference,
    sha256,
)
from geotransfer_gap.config import settings


_SURFACE_SUBTYPES = {"road", "bus_lane", "walkway", "crosswalk"}
_ROAD_SUBTYPES = {"road", "bus_lane", "crosswalk"}


class UnsupportedMapSurface(ValueError):
    """The supplied source map has no polygons in this metric's scope."""


@dataclass(frozen=True)
class LaneCenterline:
    lanelet_id: int
    points: tuple[tuple[float, float], ...]
    width_m: float | None
    successors: tuple[int, ...]


@dataclass(frozen=True)
class MapContext:
    status: str
    reason: str
    road_union: object | None = None
    coverage_union: object | None = None
    lanes: tuple[LaneCenterline, ...] = ()
    identity: dict | None = None
    coverage_scope: str = "unavailable"
    access_status: str = "not_assessed"

    def summary(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "identity": self.identity,
            "coverage_scope": self.coverage_scope,
            "legal_access_status": self.access_status,
            "physical_geometry": "source Lanelet2 road, bus-lane and crosswalk polygons",
            "coverage_geometry": "source Lanelet2 road, bus-lane, walkway and crosswalk polygons",
            "map_completeness_attested": False,
            "limitations": [
                "Outside means outside the hash-bound mapped road-surface union only.",
                "Unmapped gaps and legally restricted access are not inferred from geometry.",
            ],
        }

    @property
    def evidence_refs(self):
        if not self.identity:
            return ()
        return tuple(self.identity.get("evidence_refs", ()))


@dataclass(frozen=True)
class TaskContext:
    """Hash-checked source task bounds and optional reference geometry."""

    status: str
    reason: str
    scene_id: str | None = None
    task_id: str = "source_bounded_goal"
    start_source_step: int | None = None
    goal_source_step: int | None = None
    goal_xy: tuple[float, float] | None = None
    completion_radius_m: float | None = None
    deadline_s: float | None = None
    reference_points: tuple[tuple[float, float], ...] = ()
    route_status: str = "unavailable"
    route_reason: str = "No validated source route was resolved"
    route_span_m: float | None = None
    evidence_refs: tuple[dict, ...] = ()
    identity: dict | None = None

    def summary(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "scene_id": self.scene_id,
            "task_id": self.task_id if self.status == "valid" else None,
            "start_source_step": self.start_source_step,
            "goal_source_step": self.goal_source_step,
            "goal_position_world_xy": list(self.goal_xy) if self.goal_xy else None,
            "completion_radius_m": self.completion_radius_m,
            "deadline_s": self.deadline_s,
            "route": {
                "status": self.route_status,
                "reason": self.route_reason,
                "point_count": len(self.reference_points) if self.reference_points else None,
                "task_span_m": self.route_span_m,
            },
            "identity": self.identity,
        }


def unavailable(reason: str, *, status="unavailable", identity=None) -> MapContext:
    return MapContext(status=status, reason=reason, identity=identity)


def _manifest_file():
    path = settings().artifacts / "corpus/current.json"
    return path if path.is_file() else manifest_path()


def _tags(element):
    return {item.get("k"): item.get("v") for item in element.findall("tag")}


def _surface_unions(osm, metadata, map_geometry, polygon_type, union):
    """Build surfaces only from explicit source Lanelet relations and ways."""
    nodes = map_geometry.project_nodes(
        osm, float(metadata["xUtmOrigin"]), float(metadata["yUtmOrigin"])
    )
    ways = {
        int(way.get("id")): [int(node.get("ref")) for node in way.findall("nd")]
        for way in osm.findall("way")
    }
    surfaces, road_surfaces, lane_types = [], [], {}
    for relation in osm.findall("relation"):
        tags = _tags(relation)
        subtype = tags.get("subtype")
        if tags.get("type") != "lanelet" or subtype not in _SURFACE_SUBTYPES:
            continue
        refs = {member.get("role"): int(member.get("ref"))
                for member in relation.findall("member")
                if member.get("type") == "way"}
        if "left" not in refs or "right" not in refs:
            raise ValueError(f"Surface lanelet {relation.get('id')} lacks left/right ways")
        left_ids, right_ids = map_geometry.orient_road_boundaries(
            ways[refs["left"]], ways[refs["right"]], nodes
        )
        polygon_points = map_geometry.lanelet_polygon(
            [nodes[node_id] for node_id in left_ids],
            [nodes[node_id] for node_id in right_ids],
        )
        polygon = polygon_type(polygon_points)
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            raise ValueError(f"Surface lanelet {relation.get('id')} has invalid polygon geometry")
        surfaces.append(polygon)
        lane_id = int(relation.get("id"))
        lane_types[lane_id] = subtype
        if subtype in _ROAD_SUBTYPES:
            road_surfaces.append(polygon)
    if not road_surfaces or not surfaces:
        raise UnsupportedMapSurface("Source map has no supported road-surface lanelet polygons")
    return union(road_surfaces), union(surfaces), lane_types


def select_source_lanelet_map(metadata, recording):
    """Expose the existing provider map selector, including construction scenes."""
    from geotransfer_gap.maps import lanelet as map_geometry

    return map_geometry.map_paths(metadata, recording)[0]


def _manifest_scene(scene_root: Path, binary_hash: str):
    path = _manifest_file()
    if not path.is_file():
        return None, path, "manifest_missing"
    rows = read_manifest(path)
    same_root = [row for row in rows
                 if Path(row["root"]).resolve() == scene_root.resolve()]
    if len(same_root) > 1:
        return None, path, "duplicate_scene_root"
    if not same_root:
        return None, path, "scene_not_in_current_manifest"
    if same_root[0].get("binary_sha256") != binary_hash:
        return None, path, "manifest_binary_mismatch"
    return same_root[0], path, None


def _identity(row, recording, location, binary_path, validation_path,
              manifest_file, metadata_path, lanelet_path, semantics_path,
              contract_path, map_hash):
    evidence = []
    for kind, path in (("scene_binary", binary_path), ("scene_validation", validation_path),
                       ("manifest", manifest_file), ("source_recording_metadata", metadata_path),
                       ("source_lanelet_map", lanelet_path), ("map_semantics", semantics_path),
                       ("evaluation_contract", contract_path)):
        try:
            evidence.append({"kind": kind, "reference": reference(path), "sha256": sha256(path)})
        except ValueError:
            evidence.append({"kind": kind, "path": str(path.resolve()), "sha256": sha256(path)})
    return {
        "scene_name": row.get("name"),
        "recording": recording,
        "location": location,
        "construction_variant": "location1_construction" if location == 1 and 11 <= recording <= 17
        else "standard",
        "manifest_sha256": sha256(manifest_file),
        "source_map_sha256": map_hash,
        "map_semantics_sha256": sha256(semantics_path),
        "evaluation_contract_sha256": sha256(contract_path),
        "binary_sha256": sha256(binary_path),
        "evidence_refs": evidence,
    }


def _matching_evaluation_contract(testing, root, recording, binary_hash,
                                   map_hash, metadata_hash):
    candidates = sorted(testing.glob("evaluation_contract_*.json"))
    if not candidates:
        return None, "evaluation_contract_missing"
    valid = []
    malformed = []
    for path in candidates:
        try:
            contract = json.loads(path.read_text())
            files = contract["files"]
            contract_root = (resolve_reference(contract["scene_reference"])
                             if contract.get("scene_reference") else
                             Path(contract["scene_root"]).resolve())
            matches = (
                contract.get("schema_version") == 2
                and int(contract.get("recording")) == recording
                and contract_root.resolve() == root.resolve()
                and files["scene_binary"]["sha256"] == binary_hash
                and files["source_lanelet2_map"]["sha256"] == map_hash
                and files["source_recording_meta_csv"]["sha256"] == metadata_hash
            )
            if matches:
                valid.append(path)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            malformed.append(path)
    if valid:
        return valid[0], None
    if malformed and len(malformed) == len(candidates):
        return None, "evaluation_contract_malformed"
    return None, "evaluation_contract_input_mismatch"


def build_map_context(scene_root: Path | None, expected_binary_sha256: str) -> MapContext:
    """Load a source map only when all existing scene/map identities agree.

    Missing context is unavailable. A contradictory supplied identity is
    invalid. Optional geometry support is imported only for this map path.
    """
    if scene_root is None:
        return unavailable("The saved trace has no resolvable scene root for map context")
    root = Path(scene_root).expanduser().resolve()
    testing = root / "testing"
    validation_path = testing / "validation.json"
    binary_path = testing / "map_000000.bin"
    if not root.is_dir() or not validation_path.is_file() or not binary_path.is_file():
        return unavailable("Selected scene lacks its validation record or evaluation binary")
    actual_binary_hash = sha256(binary_path)
    if actual_binary_hash != expected_binary_sha256:
        return unavailable("Selected scene binary contradicts the saved trace", status="invalid")
    try:
        validation = json.loads(validation_path.read_text())
        recording = int(validation["recording"])
        location = int(validation["location"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return unavailable("Scene validation metadata is missing or malformed", status="invalid")

    try:
        row, manifest_file, manifest_problem = _manifest_scene(root, actual_binary_hash)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return unavailable("Current scene manifest is malformed or unreadable", status="invalid")
    if row is None:
        status = "invalid" if manifest_problem in ("duplicate_scene_root", "manifest_binary_mismatch") else "unavailable"
        return unavailable(f"No current-manifest binding: {manifest_problem}", status=status)
    if row.get("recording") != recording or row.get("location") != location:
        return unavailable("Scene recording/location contradicts its manifest row", status="invalid")

    source_data = settings().source / "data"
    metadata_path = source_data / f"{recording:02d}_recordingMeta.csv"
    if not metadata_path.is_file():
        return unavailable("The source recording metadata needed for map selection is absent")
    try:
        with metadata_path.open(newline="") as stream:
            records = list(csv.DictReader(stream))
        metadata = next((item for item in records
                         if int(item.get("recordingId", recording)) == recording), None)
        if metadata is None:
            metadata = records[0] if len(records) == 1 else None
        if metadata is None or int(metadata["locationId"]) != location:
            return unavailable("Source recording metadata does not uniquely match the scene",
                               status="invalid")
    except (OSError, ValueError, KeyError, TypeError):
        return unavailable("Source recording metadata is malformed", status="invalid")

    try:
        # This is the existing provider owner, including the recording-specific
        # location-1 construction variant.
        from geotransfer_gap.maps import lanelet as map_geometry

        lanelet_path = select_source_lanelet_map(metadata, recording)
    except (KeyError, ValueError, IndexError) as exc:
        return unavailable(f"Provider map selection failed: {exc}", status="invalid")
    if not lanelet_path.is_file():
        return unavailable("The selected source Lanelet2 map is absent")
    map_hash = sha256(lanelet_path)
    if map_hash != row.get("source_map_sha256"):
        return unavailable("Selected source-map bytes differ from the manifest", status="invalid")

    metadata_hash = sha256(metadata_path)
    contract_path, contract_problem = _matching_evaluation_contract(
        testing, root, recording, actual_binary_hash, map_hash, metadata_hash
    )
    if contract_path is None:
        status = "unavailable" if contract_problem == "evaluation_contract_missing" else "invalid"
        return unavailable(f"No existing evaluation contract binds map/source metadata: {contract_problem}",
                           status=status)

    semantics_path = testing / "map_semantics_audit.json"
    if not semantics_path.is_file():
        return unavailable("The scene has no hash-bound map semantics certificate")
    try:
        semantics = json.loads(semantics_path.read_text())
    except (OSError, json.JSONDecodeError):
        return unavailable("Map semantics certificate is malformed", status="invalid")
    if (semantics.get("binary_sha256") != actual_binary_hash
            or semantics.get("lanelet_source_sha256") != map_hash):
        return unavailable("Map semantics certificate contradicts the selected inputs",
                           status="invalid")

    identity = _identity(row, recording, location, binary_path, validation_path,
                         manifest_file, metadata_path, lanelet_path,
                         semantics_path, contract_path, map_hash)

    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
    except ImportError:
        return unavailable("Install the optional evaluation-geometry extra for spatial metrics",
                           identity=identity)

    try:
        from shapely.errors import GEOSException
        osm = ET.parse(lanelet_path).getroot()
        road_union, coverage_union, lane_types = _surface_unions(
            osm, metadata, map_geometry, Polygon, unary_union
        )

        # Existing provider geometry owner supplies directed centerlines and
        # successor topology. The source relation polygons above are the exact
        # mapped surface; no edges are closed and no centerlines are buffered.
        roads, _ = map_geometry.make_roads(metadata, recording, edge_mode="none")
        centerlines = []
        for road in roads:
            if road.get("type") != "lane" or road.get("id") not in lane_types:
                continue
            points = tuple((float(point["x"]), float(point["y"]))
                           for point in road.get("geometry", ()))
            width = road.get("width")
            centerlines.append(LaneCenterline(
                lanelet_id=int(road["id"]),
                points=points,
                width_m=float(width) if isinstance(width, (int, float)) and width > 0 else None,
                successors=tuple(int(item) for item in road.get("exit_lanes", ())),
            ))
        if road_union.is_empty or coverage_union.is_empty:
            return unavailable("Source map produced an empty road/coverage union",
                               status="invalid", identity=identity)
    except UnsupportedMapSurface as exc:
        return unavailable(str(exc), identity=identity)
    except (OSError, ET.ParseError, KeyError, ValueError, TypeError, AssertionError,
            subprocess.CalledProcessError, GEOSException) as exc:
        return unavailable(f"Source map geometry could not be interpreted: {exc}",
                           status="invalid", identity=identity)
    return MapContext(
        status="valid",
        reason="Hash-bound source map and manifest provide mapped Lanelet2 surface polygons",
        road_union=road_union,
        coverage_union=coverage_union,
        lanes=tuple(centerlines),
        identity=identity,
        coverage_scope="mapped_lanelet_surfaces_only",
    )


def _finite_pair(value):
    return (isinstance(value, dict)
            and type(value.get("x")) in (int, float)
            and type(value.get("y")) in (int, float)
            and math.isfinite(value["x"]) and math.isfinite(value["y"]))


def _task_refs(paths):
    refs = []
    for kind, path in paths:
        try:
            refs.append({"kind": kind, "reference": reference(path), "sha256": sha256(path)})
        except ValueError:
            refs.append({"kind": kind, "path": str(path.resolve()), "sha256": sha256(path)})
    return tuple(refs)


def build_task_context(scene_root: Path | None, expected_binary_sha256: str,
                       expected_ego_source_id: int | None = None,
                       map_context: MapContext | None = None) -> TaskContext:
    """Resolve source goal bounds and route evidence without reading admissions.

    The bounded task comes from the existing evaluation contract and converted
    source scene. Route progress additionally requires the existing
    source-route certificate bound to the same scene, binary and source map.
    """
    if scene_root is None:
        return TaskContext("unavailable", "The saved trace has no resolvable scene root")
    root = Path(scene_root).expanduser().resolve()
    testing = root / "testing"
    binary_path = testing / "map_000000.bin"
    validation_path = testing / "validation.json"
    if not root.is_dir() or not binary_path.is_file() or not validation_path.is_file():
        return TaskContext("unavailable", "Scene task inputs are absent")
    binary_hash = sha256(binary_path)
    if binary_hash != expected_binary_sha256:
        return TaskContext("invalid", "Scene binary differs from the saved trace identity")
    try:
        validation = json.loads(validation_path.read_text())
        row, manifest_file, manifest_problem = _manifest_scene(root, binary_hash)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return TaskContext("invalid", "Scene validation or current manifest is malformed")
    if row is None:
        status = ("invalid" if manifest_problem in
                  ("duplicate_scene_root", "manifest_binary_mismatch") else "unavailable")
        return TaskContext(status, f"No current-manifest binding for task context: {manifest_problem}")
    scene_id = row.get("name")
    if (validation.get("binary_sha256") != binary_hash
            or row.get("recording") != validation.get("recording")
            or row.get("location") != validation.get("location")):
        return TaskContext("invalid", "Scene validation identity differs from its binary or manifest",
                           scene_id=scene_id)
    scene_files = sorted(testing.glob("ind_*.json"))
    if len(scene_files) != 1:
        status = "unavailable" if not scene_files else "invalid"
        return TaskContext(status, "Scene must have exactly one converted source-trajectory JSON",
                           scene_id=scene_id)
    scene_path = scene_files[0]
    route_path = testing / "source_route_sequence.json"
    if not route_path.is_file():
        route_path = None
    try:
        scene = json.loads(scene_path.read_text())
        if not isinstance(scene.get("objects"), list) or not scene["objects"]:
            raise ValueError("converted scene has no ego object")
        ego = scene["objects"][0]
        contracts = sorted(testing.glob("evaluation_contract_*.json"))
        matching = []
        for contract_path in contracts:
            contract = json.loads(contract_path.read_text())
            contract_root = (resolve_reference(contract["scene_reference"])
                             if contract.get("scene_reference") else
                             Path(contract["scene_root"]).resolve())
            files = contract.get("files", {})
            if (contract.get("schema_version") == 2
                    and contract_root.resolve() == root
                    and contract.get("recording") == validation.get("recording")
                    and contract.get("ego_track_id") == ego.get("id")
                    and files.get("scene_json", {}).get("sha256") == sha256(scene_path)
                    and files.get("scene_binary", {}).get("sha256") == binary_hash):
                matching.append((contract_path, contract))
        if not matching:
            return TaskContext("unavailable", "No evaluation contract binds this converted source task",
                               scene_id=scene_id)
        contract_path, contract = matching[0]
        bounds = [(item[1].get("goal_sample"), item[1].get("goal_position"))
                  for item in matching]
        if any(item != bounds[0] for item in bounds[1:]):
            return TaskContext("invalid", "Bound evaluation contracts disagree on task bounds",
                               scene_id=scene_id)
        goal_sample, goal = bounds[0]
        positions, valid = ego.get("position"), ego.get("valid")
        source_id = ego.get("id")
        validation_goal = validation.get("ego_goal")
        if (type(goal_sample) is not int or not isinstance(positions, list)
                or not isinstance(valid, list) or len(positions) != len(valid)
                or not 0 <= goal_sample < len(positions) or type(source_id) is not int
                or (expected_ego_source_id is not None and source_id != expected_ego_source_id)
                or not _finite_pair(goal) or ego.get("goalPosition") != goal
                or validation.get("ego_goal_sample") != goal_sample
                or not _finite_pair(validation_goal)
                or validation_goal.get("x") != goal.get("x")
                or validation_goal.get("y") != goal.get("y")):
            return TaskContext("invalid", "Source goal/window metadata is inconsistent",
                               scene_id=scene_id)
        start_sample = next((index for index in range(goal_sample + 1)
                             if type(valid[index]) is int and valid[index] == 1
                             and _finite_pair(positions[index])), None)
        if (start_sample is None or type(valid[goal_sample]) is not int
                or valid[goal_sample] != 1 or not _finite_pair(positions[goal_sample])):
            return TaskContext("unavailable", "Source task endpoints lack valid positions",
                               scene_id=scene_id)
        points = tuple((float(positions[index]["x"]), float(positions[index]["y"]))
                       for index in range(start_sample, goal_sample + 1)
                       if type(valid[index]) is int and valid[index] == 1
                       and _finite_pair(positions[index]))
        if len(points) != goal_sample - start_sample + 1:
            route_status = "unavailable"
            route_reason = "Source reference path contains an invalid observation"
            route_span = None
            points = ()
        else:
            route_span = sum(math.dist(left, right) for left, right in zip(points, points[1:]))
            route_status, route_reason = "unavailable", "Source route certificate is absent"
            if not math.isfinite(route_span) or route_span <= 0:
                route_reason = "Source task route has no positive finite span"
                route_span = None
                points = ()
            elif route_path is not None:
                route = json.loads(route_path.read_text())
                map_identity = map_context.identity if map_context else None
                metadata_path = settings().source / "data" / (
                    f"{int(validation['recording']):02d}_recordingMeta.csv")
                route_matches = (
                    route.get("schema_version") == 1
                    and route.get("source_path_legal") is True
                    and route.get("ordinary_road_only") is True
                    and isinstance(route.get("route"), list) and bool(route["route"])
                    and all(type(lane_id) is int for lane_id in route["route"])
                    and route.get("scene_sha256") == sha256(scene_path)
                    and route.get("binary_sha256") == binary_hash
                    and metadata_path.is_file()
                    and route.get("source_recording_meta_sha256") == sha256(metadata_path)
                    and map_identity is not None
                    and route.get("source_map_sha256") == map_identity.get("source_map_sha256")
                    and route.get("source_map_sha256") == row.get("source_map_sha256")
                )
                if route_matches:
                    route_status = "valid"
                    route_reason = "Source route certificate binds the converted scene and selected map"
                else:
                    route_status = "invalid" if map_identity else "unavailable"
                    route_reason = ("Source route certificate contradicts scene/map evidence"
                                    if map_identity else
                                    "Hash-bound selected source-map evidence is unavailable")
                    route_span = None
                    points = ()
        paths = [("scene_binary", binary_path), ("scene_validation", validation_path),
                 ("manifest", manifest_file), ("converted_source_scene", scene_path),
                 ("evaluation_contract", contract_path)]
        identity = {
            "scene_id": scene_id,
            "recording": validation.get("recording"),
            "location": validation.get("location"),
            "binary_sha256": binary_hash,
            "manifest_sha256": sha256(manifest_file),
            "source_scene_sha256": sha256(scene_path),
            "evaluation_contract_sha256": sha256(contract_path),
            "source_route_sequence_sha256": sha256(route_path) if route_path else None,
        }
        if route_path is not None:
            paths.append(("source_route_sequence", route_path))
        if map_context and map_context.identity:
            paths.extend((item["kind"], resolve_reference(item["reference"]))
                         for item in map_context.evidence_refs if item.get("reference"))
        return TaskContext(
            status="valid", reason="Hash-bound evaluation contract and converted source task",
            scene_id=scene_id, start_source_step=start_sample,
            goal_source_step=goal_sample, goal_xy=(float(goal["x"]), float(goal["y"])),
            completion_radius_m=2.0, deadline_s=None,
            reference_points=points, route_status=route_status,
            route_reason=route_reason, route_span_m=route_span,
            evidence_refs=_task_refs(paths), identity=identity,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return TaskContext("invalid", f"Source task evidence is malformed: {exc}", scene_id=scene_id)
