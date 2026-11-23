"""Offline realization and geometric diagnostics for admitted interactions.

This module consumes one saved trace plus the already selected, hash-bound
source scene and its existing certificates.  It does not run a controller or
infer yielding, fault, cooperation, or intent.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from geotransfer_gap.artifacts import reference, sha256
from geotransfer_gap.evaluation.contracts import (
    AssessmentStatus,
    CriterionOutcome,
    MetricResult,
)


_FAMILIES = {"longitudinal_following", "pedestrian_crossing", "cyclist_crossing"}
_CONTROL = "control"
_MIN_AREA = 1e-8
_FOLLOWING_MIN_SPEED_MPS = 0.2
_FOLLOWING_HEADING_TOLERANCE_RAD = 0.35


@dataclass(frozen=True)
class InteractionContext:
    status: str
    reason: str
    scene_id: str | None = None
    specs: tuple[dict, ...] = ()
    source_scene: dict | None = None
    source_root: Path | None = None
    evidence_refs: tuple[dict, ...] = ()
    certificates: dict | None = None


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _ref(path, kind):
    try:
        owner = {"reference": reference(path)}
    except ValueError:
        owner = {"path": str(path.resolve())}
    return {"kind": kind, **owner, "sha256": sha256(path)}


def _scene_row(scene_root, binary_sha256):
    from geotransfer_gap.evaluation.context import _manifest_scene

    return _manifest_scene(scene_root, binary_sha256)


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _source_family_spec(row, source_scene):
    opportunity = row.get("interaction_opportunity")
    families = row.get("interaction_type_families")
    subtypes = row.get("interaction_types")
    actor_ids = row.get("interaction_actor_ids")
    if (type(opportunity) is not bool or type(families) is not list
            or type(subtypes) is not list or type(actor_ids) is not list
            or any(type(actor_id) is not int for actor_id in actor_ids)
            or len(set(actor_ids)) != len(actor_ids)):
        raise ValueError("Selected manifest interaction fields are malformed")
    if not opportunity:
        if actor_ids or families:
            raise ValueError("Control manifest row contradicts its opportunity fields")
        return ({"family": _CONTROL,
                 "subtype": subtypes[0] if len(subtypes) == 1 else "control",
                 "source_opportunity": False, "actor_ids": []},)
    if not families or len(families) != len(subtypes) or not actor_ids:
        raise ValueError("Source opportunity lacks a stable family, subtype, or actor identity")
    objects = {item.get("id"): item for item in source_scene.get("objects", ())
               if type(item.get("id")) is int}
    specs = []
    for family, subtype in zip(families, subtypes):
        if family not in _FAMILIES:
            specs.append({"family": family, "subtype": subtype,
                          "source_opportunity": True, "actor_ids": list(actor_ids),
                          "supported": False,
                          "reason": "Interaction family is outside PE07's admitted scope"})
            continue
        expected_type = {"pedestrian_crossing": 2, "cyclist_crossing": 3,
                         "longitudinal_following": 1}[family]
        if any(actor_id not in objects or objects[actor_id].get("type") != expected_type
               for actor_id in actor_ids):
            raise ValueError("Manifest interaction actor identity/type differs from converted source")
        specs.append({"family": family, "subtype": subtype,
                      "source_opportunity": True, "actor_ids": list(actor_ids),
                      "supported": True,
                      "source_map_sha256": row.get("source_map_sha256"),
                      "source_tracks_sha256": row.get("source_tracks_sha256")})
    return tuple(specs)


def _validate_fidelity(testing, row, task, ego_source_id):
    mode = "hybrid_startup" if row.get("traffic_protocol") == "hybrid_startup" else "idm"
    path = testing / f"interaction_fidelity_audit_{mode}.json"
    if mode == "idm" and not path.is_file():
        path = testing / "interaction_fidelity_audit.json"
    if not path.is_file():
        return {"status": "unavailable", "reason": "Source interaction-fidelity certificate is absent"}, None
    try:
        report = _json(path)
        if (report.get("schema_version") != 3 or report.get("traffic_mode") != mode
                or report.get("binary_sha256") != task.identity["binary_sha256"]
                or report.get("ego_track_id") != ego_source_id):
            raise ValueError("Source interaction-fidelity identity contradicts the selected scene")
        rule_path = testing / "rule_applicability_audit.json"
        lifecycle_path = testing / f"lifecycle_trace_{mode}.json"
        if not rule_path.is_file() or not lifecycle_path.is_file():
            return {"status": "unavailable", "reason": "Fidelity dependencies are absent"}, path
        lifecycle = _json(lifecycle_path)
        if (report.get("rule_audit_sha256") != sha256(rule_path)
                or report.get("idm_trace_sha256") != sha256(lifecycle_path)
                or lifecycle.get("binary_sha256") != task.identity["binary_sha256"]
                or lifecycle.get("traffic_mode") != mode
                or lifecycle.get("evaluation_ini_sha256") != report.get("evaluation_ini_sha256")
                or lifecycle.get("runtime_source_sha256") != report.get("runtime_source_sha256")
                or lifecycle.get("observed_steps") != report.get("idm_observed_steps")):
            raise ValueError("Source interaction-fidelity dependencies do not match the certificate")
        from geotransfer_gap.validation.audit_interaction_fidelity import source_evidence_digest

        if report.get("source_evidence_digest") != source_evidence_digest(report):
            raise ValueError("Source interaction-fidelity digest is inconsistent")
        actor_opportunities = report.get("actor_opportunities")
        if (not isinstance(actor_opportunities, list)
                or any(type(item) is not dict for item in actor_opportunities)):
            raise ValueError("Source interaction-fidelity actor opportunities are malformed")
        by_id = {item.get("track_id"): item for item in actor_opportunities}
        if (any(type(actor_id) is not int for actor_id in by_id)
                or len(by_id) != len(actor_opportunities)):
            raise ValueError("Source interaction-fidelity actor identities are malformed or duplicated")
        return {"status": "valid", "reason": "Bound source interaction-fidelity certificate",
                "traffic_mode": mode,
                "preserved_actor_ids": sorted(
                    actor_id for actor_id, item in by_id.items()
                    if item.get("preserved_for_claimed_interaction") is True),
                "actor_opportunities": by_id}, path
    except (OSError, KeyError, TypeError, ValueError, AttributeError,
            json.JSONDecodeError) as exc:
        return {"status": "invalid", "reason": f"Invalid source interaction-fidelity certificate: {exc}"}, path


def build_interaction_context(scene_root, task_context, report):
    """Load fixed source opportunities without consulting admission decisions."""
    if task_context is None or task_context.status != "valid":
        status = "invalid" if task_context and task_context.status == "invalid" else "unavailable"
        return InteractionContext(status, "Hash-bound task/source identity is unavailable")
    if scene_root is None:
        return InteractionContext("unavailable", "No selected source scene was supplied")
    root = Path(scene_root).expanduser().resolve()
    testing = root / "testing"
    binary = testing / "map_000000.bin"
    scene_files = sorted(testing.glob("ind_*.json"))
    if not binary.is_file() or len(scene_files) != 1:
        return InteractionContext("unavailable", "Source interaction inputs are absent or ambiguous",
                                  scene_id=task_context.scene_id, source_root=root)
    if sha256(binary) != task_context.identity.get("binary_sha256"):
        return InteractionContext("invalid", "Source binary differs from the saved episode",
                                  scene_id=task_context.scene_id, source_root=root)
    scene_path = scene_files[0]
    if sha256(scene_path) != task_context.identity.get("source_scene_sha256"):
        return InteractionContext("invalid", "Converted source scene differs from task context",
                                  scene_id=task_context.scene_id, source_root=root)
    try:
        row, manifest_path, problem = _scene_row(root, task_context.identity["binary_sha256"])
        if row is None:
            return InteractionContext("invalid" if problem in {
                "duplicate_scene_root", "manifest_binary_mismatch"} else "unavailable",
                f"No selected source interaction manifest row: {problem}",
                scene_id=task_context.scene_id, source_root=root)
        if (row.get("name") != task_context.scene_id
                or row.get("ego_track_id") != report.get("ego_source_id")
                or row.get("ego_binary_index") != report.get("ego_binary_index")
                or sha256(manifest_path) != task_context.identity.get("manifest_sha256")):
            return InteractionContext("invalid", "Selected interaction row differs from task manifest identity",
                                      scene_id=task_context.scene_id, source_root=root)
        source_scene = _json(scene_path)
        specs = _source_family_spec(row, source_scene)
        evidence = [_ref(manifest_path, "selected_portable_manifest"),
                    _ref(binary, "scene_binary"),
                    _ref(scene_path, "converted_source_scene")]
        certificates = {"fidelity": {"status": "not_required"},
                        "source_body_path_conflict": {"status": "not_required"},
                        "source_following_scope": {"status": "not_required"}}
        fidelity, fidelity_path = (
            _validate_fidelity(testing, row, task_context, report.get("ego_source_id"))
            if any(spec["family"] != _CONTROL for spec in specs)
            else ({"status": "not_applicable",
                   "reason": "Control row has no interaction obligation"}, None)
        )
        certificates["fidelity"] = fidelity
        if fidelity_path is not None:
            evidence.append(_ref(fidelity_path, "source_interaction_fidelity"))
        conflict_path = testing / "source_task_interaction_audit.json"
        if conflict_path.is_file():
            conflict = _json(conflict_path)
            if (conflict.get("schema_version") != 1
                    or conflict.get("source_scene_sha256") != sha256(scene_path)
                    or not isinstance(conflict.get("actors"), list)
                    or any(type(item) is not dict or type(item.get("actor_id")) is not int
                           for item in conflict["actors"])
                    or len({item["actor_id"] for item in conflict["actors"]})
                    != len(conflict["actors"])):
                return InteractionContext("invalid", "Source body-path conflict certificate contradicts scene",
                                          scene_id=row["name"], source_root=root)
            certificates["source_body_path_conflict"] = {
                "status": "valid", "reason": "Certificate binds converted source scene",
                "actors": {item.get("actor_id"): item for item in conflict["actors"]}}
            evidence.append(_ref(conflict_path, "source_body_path_conflict"))
        else:
            certificates["source_body_path_conflict"] = {
                "status": "absent",
                "reason": "No separate source conflict certificate; source geometry is used diagnostically"}
        following_path = testing / "source_following_scope.json"
        if following_path.is_file():
            following = _json(following_path)
            if (following.get("schema_version") != 1
                    or following.get("scene_sha256") != sha256(scene_path)
                    or following.get("source_tracks_sha256") != row.get("source_tracks_sha256")
                    or following.get("source_map_sha256") != row.get("source_map_sha256")
                    or not isinstance(following.get("actors"), list)
                    or any(type(item) is not dict or type(item.get("actor_id")) is not int
                           for item in following["actors"])
                    or len({item["actor_id"] for item in following["actors"]})
                    != len(following["actors"])):
                return InteractionContext("invalid", "Source following certificate contradicts selected source inputs",
                                          scene_id=row["name"], source_root=root)
            certificates["source_following_scope"] = {
                "status": "valid", "actors": {
                    item.get("actor_id"): item for item in following["actors"]}}
            evidence.append(_ref(following_path, "source_following_scope"))
        if (certificates["fidelity"].get("status") == "invalid"):
            return InteractionContext("invalid", certificates["fidelity"]["reason"],
                                      scene_id=row["name"], source_root=root,
                                      evidence_refs=tuple(evidence), certificates=certificates)
        # Keep source opportunity and source fidelity distinct: a non-preserved
        # actor is never silently relabelled as absent or as a passing encounter.
        for spec in specs:
            if spec["family"] == _CONTROL or not spec.get("supported"):
                continue
            opportunities = certificates["fidelity"].get("actor_opportunities", {})
            conflict_actors = certificates["source_body_path_conflict"].get("actors", {})
            following_actors = certificates["source_following_scope"].get("actors", {})
            spec["source_conflict_by_actor"] = {
                str(actor_id): conflict_actors.get(actor_id) for actor_id in spec["actor_ids"]
                if actor_id in conflict_actors}
            spec["source_following_by_actor"] = {
                str(actor_id): following_actors.get(actor_id) for actor_id in spec["actor_ids"]
                if actor_id in following_actors}
            for actor_id in spec["actor_ids"]:
                item = opportunities.get(actor_id)
                spec.setdefault("fidelity_by_actor", {})[str(actor_id)] = (
                    "preserved" if item and item.get("preserved_for_claimed_interaction") is True
                    else "not_preserved_or_unavailable")
        return InteractionContext("valid", "Hash-bound source opportunity and actor identities",
                                  row["name"], tuple(specs), source_scene, root,
                                  tuple(evidence), certificates)
    except (OSError, KeyError, TypeError, ValueError, AttributeError,
            json.JSONDecodeError) as exc:
        return InteractionContext("invalid", f"Source interaction context is malformed: {exc}",
                                  scene_id=task_context.scene_id, source_root=root)


def _actor_map(frame):
    return {row.get("id"): row for row in frame.get("actors", ())
            if type(row.get("id")) is int}


def _present_pose(actor):
    return bool(actor and actor.get("present") is True
                and _finite(actor.get("x")) and _finite(actor.get("y")))


def _generation(actor):
    value = actor.get("lifetime_generation") if actor else None
    return value if type(value) is int and value >= 0 else None


def _same_lifetime(left, right):
    if not left or not right or left.get("id") != right.get("id"):
        return False
    a, b = _generation(left), _generation(right)
    return a == b if a is not None or b is not None else True


def _times(frames, exposure, report):
    masks = exposure.get("observation_masks", ())
    values = [row.get("time_s") for row in masks] if len(masks) == len(frames) else [
        frame.get("time_s") for frame in frames]
    if values and all(_finite(item) for item in values):
        return [float(item) for item in values], exposure.get("time_source", "recorded_time_s")
    if (report.get("schema_version") == 2 and frames
            and all(item is None for item in values)):
        return [float(frame.get("step", index)) * 0.1
                for index, frame in enumerate(frames)], "inferred_legacy_10hz_step"
    return [float(item) if _finite(item) else None for item in values], "partial_or_unavailable"


def _task_event(events, before_step):
    return [row for row in events
            if row.get("channel") in {"native_vehicle_collision", "native_offroad"}
            and type(row.get("step")) is int and row["step"] <= before_step]


def _actor_refs(actors):
    refs = {(item.get("id"), _generation(item)) for item in actors if item}
    return tuple(sorted(refs, key=lambda row: (row[0], -1 if row[1] is None else row[1])))


def _risk_channels(metrics, ego_id, actor_id):
    """Link PE07 rows to PE04 measurements without recalculating risk metrics."""
    indexed = {(row.get("metric_id"), row.get("window")): row for row in metrics}
    clearance = indexed.get(("safety.footprint_clearance", "full"))
    clearance_samples = []
    if clearance and isinstance(clearance.get("value"), dict):
        for sample in clearance["value"].get("samples", ()):
            nearest = sample.get("closest_actor", {})
            if nearest.get("source_id") == actor_id:
                clearance_samples.append(sample)
    ttc = indexed.get(("safety.ttc", "full"))
    ttc_samples = []
    if ttc and isinstance(ttc.get("value"), dict):
        for sample in ttc["value"].get("pair_samples", ()):
            pairs = [pair for pair in sample.get("actor_pairs", ())
                     if pair.get("actor", {}).get("source_id") == actor_id]
            if pairs:
                ttc_samples.append({"step": sample.get("step"),
                                    "time_s": sample.get("time_s"),
                                    "ego_source_id": ego_id, "actor_pairs": pairs})
    return {
        "footprint_clearance": {
            "metric_id": "safety.footprint_clearance",
            "status": clearance.get("status") if clearance else "unavailable",
            "actor_specific_samples": clearance_samples,
            "coverage": ("PE04 minimum samples where this actor was the closest pair"
                         if clearance_samples else "PE04 did not report this actor as the closest pair"),
        },
        "ttc": {
            "metric_id": "safety.ttc",
            "status": ttc.get("status") if ttc else "unavailable",
            "actor_pair_samples": ttc_samples,
            "coverage": (ttc.get("value", {}).get("coverage") if ttc
                         and isinstance(ttc.get("value"), dict) else None),
        },
    }


def _metric(metric_id, context, spec, actor_rows, *, status, reason, value=None,
            eligible_samples=None, eligible_duration_s=None):
    return MetricResult(
        metric_id=metric_id, definition_version="1.0.0", status=status,
        reason=reason, value=value, units=None,
        criterion_outcome=CriterionOutcome.NOT_ASSESSED,
        eligible_samples=eligible_samples, eligible_duration_s=eligible_duration_s,
        window="full", actors=_actor_refs(actor_rows),
        evidence_refs=context.evidence_refs,
        limitations=("Geometric encounter diagnostics do not establish fault, yielding, cooperation, or causality",
                     "Source opportunity is fixed context and is not the actual rollout verdict"),
    ).to_dict()


def _actor_points(source_actor, start, end):
    positions, valid, headings = (source_actor.get("position"), source_actor.get("valid"),
                                  source_actor.get("heading"))
    if not isinstance(positions, list) or not isinstance(valid, list) or not isinstance(headings, list):
        return []
    result = []
    for index in range(max(0, start), min(end, len(positions), len(valid), len(headings))):
        p, h = positions[index], headings[index]
        if (valid[index] == 1 and isinstance(p, dict) and _finite(p.get("x"))
                and _finite(p.get("y")) and _finite(h)):
            result.append((index, float(p["x"]), float(p["y"]), float(h)))
    return result


def _cross(a, b, p):
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _line_intersection(start, end, clip_start, clip_end):
    dx1, dy1 = end[0] - start[0], end[1] - start[1]
    dx2, dy2 = clip_end[0] - clip_start[0], clip_end[1] - clip_start[1]
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) <= 1e-12:
        return end
    t = ((clip_start[0] - start[0]) * dy2 - (clip_start[1] - start[1]) * dx2) / denom
    return (start[0] + t * dx1, start[1] + t * dy1)


def _signed_area(poly):
    return (sum(a[0] * b[1] - b[0] * a[1]
                for a, b in zip(poly, poly[1:] + poly[:1])) / 2
            if len(poly) >= 3 else 0.0)


def _clip_polygon(subject, clip):
    # The existing audited rectangle-corner owner emits clockwise vertices.
    # Normalize both convex inputs because Sutherland-Hodgman uses CCW halfspaces.
    output = list(subject if _signed_area(subject) >= 0 else reversed(subject))
    clip = list(clip if _signed_area(clip) >= 0 else reversed(clip))
    for index, clip_start in enumerate(clip):
        clip_end = clip[(index + 1) % len(clip)]
        incoming, output = output, []
        if not incoming:
            break
        previous = incoming[-1]
        for current in incoming:
            current_inside = _cross(clip_start, clip_end, current) >= -1e-9
            previous_inside = _cross(clip_start, clip_end, previous) >= -1e-9
            if current_inside:
                if not previous_inside:
                    output.append(_line_intersection(previous, current, clip_start, clip_end))
                output.append(current)
            elif previous_inside:
                output.append(_line_intersection(previous, current, clip_start, clip_end))
            previous = current
    return output


def _area(poly):
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(poly, poly[1:] + poly[:1]))) / 2 if len(poly) >= 3 else 0.0


def _bbox(poly):
    return (min(p[0] for p in poly), min(p[1] for p in poly),
            max(p[0] for p in poly), max(p[1] for p in poly))


def _bbox_overlaps(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _reference_conflict_regions(context, spec, task, ego_id):
    from geotransfer_gap.validation.audit_physical_source import corners

    objects = {item["id"]: item for item in context.source_scene["objects"]}
    ego = objects.get(ego_id)
    if ego is None:
        return [], "invalid", "Recorded ego source ID is absent from the converted scene"
    start = max(10, task.start_source_step or 0)
    end = task.goal_source_step if task.goal_source_step is not None else 10**9
    certificate = (context.certificates or {}).get("source_body_path_conflict", {})
    ego_points = _actor_points(ego, start, end + 1)
    regions = []
    for actor_id in spec["actor_ids"]:
        actor = objects[actor_id]
        source_row = certificate.get("actors", {}).get(actor_id, {})
        actor_end = min(end, source_row.get("source_task_end_step", end))
        actor_points = _actor_points(actor, start, actor_end + 1)
        ego_boxes = []
        for step, *_ in ego_points:
            try:
                poly = corners(ego, step)
                ego_boxes.append((poly, _bbox(poly)))
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        actor_boxes = []
        for step, *_ in actor_points:
            try:
                poly = corners(actor, step)
                actor_boxes.append((poly, _bbox(poly)))
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        unique = set()
        for ego_poly, ego_box in ego_boxes:
            for actor_poly, actor_box in actor_boxes:
                if not _bbox_overlaps(ego_box, actor_box):
                    continue
                if (any(not all(_finite(value) for value in point) for point in (*ego_poly, *actor_poly))
                        or len(ego_poly) != 4 or len(actor_poly) != 4):
                    return [], "invalid", "Source footprint geometry is malformed or nonfinite"
                intersection = _clip_polygon(ego_poly, actor_poly)
                area = _area(intersection)
                if not _finite(area):
                    return [], "invalid", "Source footprint intersection area is nonfinite"
                if area <= _MIN_AREA:
                    continue
                key = tuple(sorted((round(point[0], 4), round(point[1], 4))
                                   for point in intersection))
                if key in unique:
                    continue
                unique.add(key)
                regions.append(intersection)
                if len(regions) >= 4096:
                    break
            if len(regions) >= 4096:
                break
    cert_status = certificate.get("status")
    if cert_status == "valid":
        for actor_id in spec["actor_ids"]:
            source_row = certificate.get("actors", {}).get(actor_id)
            if source_row is not None and source_row.get("crossing_corridors_overlap") is False and regions:
                return [], "invalid", "Source conflict certificate contradicts derived body-path overlap"
    if not regions:
        return [], "unavailable", "No positive-area source body-path conflict region was observed"
    return regions, "valid", "Reference region is the union of observed source ego/actor footprint intersections"


def _convex_overlap(first, second):
    intersection = _clip_polygon(first, second)
    return bool(intersection) and _area(intersection) > _MIN_AREA


def _state_occupancy(actor, regions, dimensions):
    from geotransfer_gap.evaluation.safety import _dimensions, _rectangle

    if not _present_pose(actor):
        return False, "actor_pose_missing"
    dims, source, imputed, invalid = _dimensions(actor, dimensions or {})
    if dims is None:
        return False, "invalid_dimensions" if invalid else "dimensions_unavailable"
    box = _rectangle(actor, dimensions or {})
    if box is None:
        return False, "footprint_unavailable"
    return any(_convex_overlap(box, region) for region in regions), None


def _occupancy_runs(occupied, actors, times):
    runs = []
    start = None
    previous_life = None
    entry_supported = False
    for index in range(len(occupied) + 1):
        active = index < len(occupied) and occupied[index]
        life = _generation(actors[index]) if index < len(actors) else None
        same = (index < len(occupied)
                and (start is None or index == start
                     or _same_lifetime(actors[index - 1], actors[index])))
        if active and start is not None and not same:
            runs.append({"start_index": start, "end_index": index - 1,
                         "entry_time_s": times[start], "last_occupied_time_s": times[index - 1],
                         "entry_censored": not entry_supported,
                         "exit_censored": True, "exit_observation_index": None,
                         "lifetime_generation": previous_life})
            start = None
        if active and start is None:
            start = index
            previous_life = life
            before = actors[index - 1] if index > 0 else None
            entry_supported = bool(before and before.get("present") is True
                                   and _present_pose(before)
                                   and _same_lifetime(before, actors[index]))
        if not active and start is not None:
            actor_at_exit = actors[index] if index < len(actors) else None
            observed_clear = bool(actor_at_exit and actor_at_exit.get("present") is True
                                  and _present_pose(actor_at_exit))
            runs.append({"start_index": start, "end_index": index - 1,
                         "entry_time_s": times[start],
                         "last_occupied_time_s": times[index - 1],
                         "entry_censored": not entry_supported,
                         "exit_censored": not observed_clear,
                         "exit_observation_time_s": times[index] if observed_clear else None,
                         "exit_observation_index": index if observed_clear else None,
                         "lifetime_generation": previous_life})
            start = None
    return runs


def _crossing_measure(frames, times, spec, context, task, report, events, dimensions, profile):
    from geotransfer_gap.evaluation.safety import _actor_map

    try:
        regions, region_status, region_reason = _reference_conflict_regions(
            context, spec, task, report.get("ego_source_id"))
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        regions, region_status, region_reason = [], "invalid", f"Source conflict geometry is malformed: {exc}"
    empty = {"outcome": "indeterminate", "reason": region_reason,
             "realization": "indeterminate",
             "reference_conflict_region": {"status": region_status,
                                            "method": "source_body_path_footprint_intersection_union",
                                            "polygon_count": len(regions) or None},
             "actors": []}
    if region_status != "valid":
        return {**empty, "measurement_status": region_status}, (), None
    maps = [_actor_map(frame) for frame in frames]
    ego_id = report.get("ego_source_id")
    ego_rows = [row.get(ego_id) for row in maps]
    actor_results = []
    actor_refs = []
    for actor_id in spec["actor_ids"]:
        actor_rows = [row.get(actor_id) for row in maps]
        if not any(_present_pose(row) for row in actor_rows):
            actor_results.append({"actor_id": actor_id, "realization": "indeterminate",
                                  "reason": "source actor is never observed present in this trace",
                                  "coverage_loss": True, "occupancy_runs": [], "pet": None})
            actor_refs.extend(row for row in actor_rows if row)
            continue
        ego_occ, actor_occ = [], []
        support_reasons = {"ego": {}, "actor": {}}
        for index, (ego, actor) in enumerate(zip(ego_rows, actor_rows)):
            e, er = _state_occupancy(ego, regions, dimensions)
            a, ar = _state_occupancy(actor, regions, dimensions)
            ego_occ.append(e)
            actor_occ.append(a)
            if er:
                support_reasons["ego"][er] = support_reasons["ego"].get(er, 0) + 1
            if ar:
                support_reasons["actor"][ar] = support_reasons["actor"].get(ar, 0) + 1
        ego_runs = _occupancy_runs(ego_occ, ego_rows, times)
        actor_runs = _occupancy_runs(actor_occ, actor_rows, times)
        warmup = profile.values["time"]["warmup_transitions"]
        for run in (*ego_runs, *actor_runs):
            run["entry_step"] = frames[run["start_index"]].get("step", run["start_index"])
            run["exit_step"] = (frames[run["end_index"]].get("step", run["end_index"])
                                if run["end_index"] < len(frames) else None)
            run["entry_attribution"] = (
                "warmup_or_initial_condition" if run["start_index"] < warmup
                else "controlled_window")
        missing_records = any(row is None for row in actor_rows)
        coverage_loss = missing_records or any(
            _present_pose(actor_rows[i - 1]) and not _present_pose(actor_rows[i])
            for i in range(1, len(actor_rows))) or any(
                _generation(actor_rows[i - 1]) is not None
                and _generation(actor_rows[i]) is not None
                and _generation(actor_rows[i - 1]) != _generation(actor_rows[i])
                for i in range(1, len(actor_rows)))
        simultaneous = any(a and b for a, b in zip(ego_occ, actor_occ))
        ordered_pets = []
        for ego_run in ego_runs:
            if ego_run.get("exit_censored") or ego_run.get("exit_observation_index") is None:
                continue
            for actor_run in actor_runs:
                if (actor_run.get("entry_censored")
                        or actor_run["start_index"] < ego_run["exit_observation_index"]):
                    continue
                pet = (float(actor_run["entry_time_s"] - ego_run["exit_observation_time_s"])
                       if _finite(actor_run.get("entry_time_s"))
                       and _finite(ego_run.get("exit_observation_time_s")) else None)
                ordered_pets.append({"first_occupant": "ego", "second_occupant": "actor",
                                     "pet_s": pet,
                                     "pet_status": "valid" if pet is not None else "unavailable",
                                     "sampling_method": "observed_clear_to_next_entry"})
        for actor_run in actor_runs:
            if actor_run.get("exit_censored") or actor_run.get("exit_observation_index") is None:
                continue
            for ego_run in ego_runs:
                if (ego_run.get("entry_censored")
                        or ego_run["start_index"] < actor_run["exit_observation_index"]):
                    continue
                pet = (float(ego_run["entry_time_s"] - actor_run["exit_observation_time_s"])
                       if _finite(ego_run.get("entry_time_s"))
                       and _finite(actor_run.get("exit_observation_time_s")) else None)
                ordered_pets.append({"first_occupant": "actor", "second_occupant": "ego",
                                     "pet_s": pet,
                                     "pet_status": "valid" if pet is not None else "unavailable",
                                     "sampling_method": "observed_clear_to_next_entry"})
        if simultaneous:
            realization, outcome, reason = "encountered", "unresolved", "both footprints occupied the reference conflict region at the same observation"
        elif ego_runs and actor_runs:
            realization = "encountered"
            censored = (any(row.get("entry_censored") or row.get("exit_censored")
                            for row in (*ego_runs, *actor_runs)))
            repeated = len(ego_runs) > 1 or len(actor_runs) > 1
            if censored:
                outcome, reason = "unresolved", "conflict-region entry or exit is censored by trace boundary"
            elif repeated:
                outcome, reason = "unresolved", "repeated conflict-region occupancy is retained as separate passages"
            elif ordered_pets:
                outcome, reason = "resolved", "both actors entered and exited in an observed nonoverlapping order"
            else:
                outcome, reason = "unresolved", "ordered entry and exit could not be established"
        else:
            before_index = min((run["start_index"] for run in (*ego_runs, *actor_runs)),
                               default=max(0, len(frames) - 1))
            before_step = (frames[before_index].get("step", before_index)
                           if frames else 0)
            prior_events = _task_event(events, before_step)
            support_incomplete = any(
                channel.get(key, 0) > 0 for channel in support_reasons.values()
                for key in ("actor_pose_missing", "dimensions_unavailable",
                            "invalid_dimensions", "footprint_unavailable")
            )
            incomplete = (coverage_loss or missing_records or support_incomplete
                          or any(not _finite(value) for value in times))
            if incomplete and not prior_events:
                realization, outcome = "indeterminate", "indeterminate"
                reason = "Actor coverage, footprint support, or timebase is incomplete before the conflict can be resolved"
            else:
                realization = "not_reached"
                if not ego_runs:
                    reason = ("ego failure occurred before the conflict region"
                              if prior_events else
                              "ego did not occupy the source conflict region during the observed horizon")
                else:
                    reason = "source actor did not occupy the conflict region during the observed horizon"
                if incomplete:
                    reason += "; actor/footprint support also contains a coverage gap"
                outcome = "not_assessed"
        row = {
            "actor_id": actor_id,
            "realization": realization,
            "outcome": outcome,
            "reason": reason,
            "reference_conflict_region": "source_body_path_footprint_intersection_union",
            "ego_occupancy_runs": ego_runs,
            "actor_occupancy_runs": actor_runs,
            "simultaneous_occupancy": simultaneous,
            "repeated_occupancy": len(ego_runs) > 1 or len(actor_runs) > 1,
            "post_encroachment_times": ordered_pets,
            "pet_status": ("valid" if any(item["pet_s"] is not None for item in ordered_pets) else
                           "undefined" if simultaneous else "unavailable"),
            "pet_reason": (
                "Observed clear-to-entry time difference; sampled at recorded observations"
                if any(item["pet_s"] is not None for item in ordered_pets) else
                "Passage order is observed but a complete timebase is unavailable"
                if ordered_pets else "Simultaneous or censored occupancy does not support ordered PET"),
            "support_gaps": support_reasons,
            "coverage_loss": coverage_loss,
            "yielding_compliance": {
                "status": "not_applicable" if spec["family"] == "cyclist_crossing"
                and spec["subtype"] == "cyclist_crossing_after_ego" else "unavailable",
                "outcome": "not_assessed",
                "reason": ("After-ego cyclist subtype creates no ego-yield obligation"
                           if spec["family"] == "cyclist_crossing"
                           and spec["subtype"] == "cyclist_crossing_after_ego"
                           else "No hash-bound explicit yielding criterion is available"),
            },
        }
        actor_results.append(row)
        actor_refs.extend([row for row in ego_rows if row])
        actor_refs.extend([row for row in actor_rows if row])
    if any(row.get("realization") == "encountered" for row in actor_results):
        top = "encountered"
        outcomes = {row.get("outcome") for row in actor_results
                    if row.get("realization") == "encountered"}
        fully_resolved = (outcomes == {"resolved"}
                          and all(row.get("realization") == "encountered"
                                  for row in actor_results))
        outcome = "resolved" if fully_resolved else "unresolved"
    elif any(row.get("realization") == "indeterminate" for row in actor_results):
        top = "indeterminate"
        outcome = "indeterminate"
    else:
        top = "not_reached"
        outcome = "not_assessed"
    result = {**empty, "outcome": outcome,
              "realization": top,
              "reason": "; ".join(dict.fromkeys(row["reason"] for row in actor_results)),
              "actors": actor_results,
              "clearance_ttc_channels": ["safety.footprint_clearance", "safety.ttc"],
              "fault_inferred": False}
    duration = None
    return result, tuple(actor_refs), duration


def _wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _lane_projection(actor, lane):
    projections = []
    arc = 0.0
    points = lane.points
    for start, end in zip(points, points[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            continue
        fraction = max(0.0, min(1.0, ((actor["x"] - start[0]) * dx
                                       + (actor["y"] - start[1]) * dy) / (length * length)))
        qx, qy = start[0] + fraction * dx, start[1] + fraction * dy
        distance = math.hypot(actor["x"] - qx, actor["y"] - qy)
        candidate = (distance, arc + fraction * length, arc + length,
                     math.atan2(dy, dx))
        projections.append(candidate)
        arc += length
    if not projections:
        return None
    nearest = min(row[0] for row in projections)
    tied = [row for row in projections if row[0] <= nearest + 0.1]
    if any(abs(row[1] - other[1]) > 0.5 for index, row in enumerate(tied)
           for other in tied[index + 1:]):
        return None
    return min(tied, key=lambda row: (row[0], row[1]))


def _assignment(actor, map_context):
    from geotransfer_gap.evaluation.map_metrics import _candidate_assignment

    if map_context is None or map_context.status != "valid" or not map_context.lanes:
        return None, "hash_bound_directed_map_unavailable"
    if not (_present_pose(actor) and _finite(actor.get("heading"))):
        return None, "actor_pose_or_heading_missing"
    cluster, reason = _candidate_assignment(actor, map_context.lanes,
                                            minimum_speed=_FOLLOWING_MIN_SPEED_MPS)
    if not cluster:
        return None, reason
    representative = min(cluster, key=lambda row: (row[1], row[0].lanelet_id))[0]
    projection = _lane_projection(actor, representative)
    if projection is None:
        return None, "directed_lane_geometry_unavailable"
    if abs(_wrap(float(actor["heading"]) - projection[3])) > _FOLLOWING_HEADING_TOLERANCE_RAD:
        return None, "actor_heading_does_not_match_assigned_lane_direction"
    return {"lane": representative, "s": projection[1], "length": projection[2],
            "distance_m": projection[0]}, None


def _directed_gap(ego, leader, map_context):
    ego_assignment, ego_reason = _assignment(ego, map_context)
    leader_assignment, leader_reason = _assignment(leader, map_context)
    if ego_assignment is None or leader_assignment is None:
        return None, "unavailable", ego_reason or leader_reason
    start = ego_assignment["lane"].lanelet_id
    goal = leader_assignment["lane"].lanelet_id
    if start == goal:
        gap = leader_assignment["s"] - ego_assignment["s"]
        return gap, "compatible", None
    lanes = {row.lanelet_id: row for row in map_context.lanes}
    # Only an unambiguous directed successor chain establishes a leader ahead.
    paths = []
    stack = [(start, (start,))]
    while stack:
        current, path = stack.pop()
        if len(path) > len(lanes):
            continue
        for successor in lanes.get(current, ()).successors if current in lanes else ():
            if successor == goal:
                paths.append((*path, successor))
            elif successor in lanes and successor not in path:
                stack.append((successor, (*path, successor)))
    if not paths:
        return None, "incompatible", "leader lane is not on ego's directed successor path"
    distances = []
    for path in paths:
        distance = ego_assignment["length"] - ego_assignment["s"]
        for lane_id in path[1:-1]:
            distance += sum(math.dist(a, b) for a, b in zip(lanes[lane_id].points,
                                                              lanes[lane_id].points[1:]))
        distance += leader_assignment["s"]
        distances.append(distance)
    if len(paths) != 1:
        return None, "ambiguous", "multiple directed successor paths connect the lane assignments"
    return distances[0], "compatible", None


def _following_measure(frames, times, spec, context, report, profile, map_context):
    from geotransfer_gap.evaluation.safety import (
        _dimension_observations, _dimensions, _rectangle, _geometry_helpers,
    )

    box_distance, _ = _geometry_helpers()
    map_identity = map_context.identity if map_context is not None else None
    if map_identity and map_identity.get("source_map_sha256") != spec.get("source_map_sha256"):
        return {"realization": "indeterminate", "outcome": "indeterminate",
                "measurement_status": "invalid",
                "reason": "Directed map context differs from the source interaction manifest map",
                "route_compatibility_status": "invalid", "actors": [],
                "following_duration_s": None, "physical_gap_status": "unavailable",
                "time_headway_status": "unavailable"}, (), None
    actor_maps = [_actor_map(frame) for frame in frames]
    ego_id = report.get("ego_source_id")
    ego_rows = [row.get(ego_id) for row in actor_maps]
    all_actor_rows = [actor_map.get(actor_id) for actor_map in actor_maps
                      for actor_id in spec["actor_ids"] if actor_map.get(actor_id)]
    dimensions = _dimension_observations(frames)
    primary_start = profile.values["time"]["primary_start_observation"]
    following_samples = []
    stop_state = {actor_id: {"was_stopped": False, "restarted": False,
                             "stop_start": None, "stops": []}
                  for actor_id in spec["actor_ids"]}
    actor_rows_out = []
    eligible_intervals = {actor_id: [] for actor_id in spec["actor_ids"]}
    if map_context is None or map_context.status != "valid" or not map_context.lanes:
        return {"realization": "indeterminate", "outcome": "indeterminate",
                "reason": "Hash-bound directed map lanes are unavailable for current route compatibility",
                "route_compatibility_status": "unavailable", "actors": [],
                "following_duration_s": None, "physical_gap_status": "unavailable",
                "time_headway_status": "unavailable"}, tuple(all_actor_rows), None
    for actor_id in spec["actor_ids"]:
        actor_rows = [row.get(actor_id) for row in actor_maps]
        actor_samples = []
        route_observations = {"compatible": 0, "incompatible": 0,
                              "ambiguous": 0, "unavailable": 0}
        for index in range(primary_start, len(frames)):
            ego, leader = ego_rows[index], actor_rows[index]
            if not (_present_pose(ego) and _present_pose(leader)):
                continue
            directed_gap, compatibility, compatibility_reason = _directed_gap(ego, leader, map_context)
            route_observations[compatibility] = route_observations.get(compatibility, 0) + 1
            if compatibility != "compatible" or directed_gap is None or directed_gap <= 0:
                continue
            ego_box = _rectangle(ego, dimensions)
            actor_box = _rectangle(leader, dimensions)
            dims_ego, *_ = _dimensions(ego, dimensions)
            dims_actor, *_ = _dimensions(leader, dimensions)
            if ego_box is None or actor_box is None or dims_ego is None or dims_actor is None:
                physical_gap = None
            else:
                physical_gap = box_distance(ego_box, actor_box)
            speed = (math.hypot(ego["vx"], ego["vy"])
                     if _finite(ego.get("vx")) and _finite(ego.get("vy")) else None)
            if physical_gap is None:
                headway, headway_status = None, "unavailable_physical_gap"
            elif speed is None:
                headway, headway_status = None, "unavailable_speed"
            elif speed <= _FOLLOWING_MIN_SPEED_MPS:
                headway, headway_status = None, "undefined_at_standstill"
            else:
                headway, headway_status = float(physical_gap / speed), "valid"
            sample = {"step": frames[index].get("step", index), "time_s": times[index],
                      "leader_route_compatible": True, "leader_ahead": True,
                      "directed_route_gap_m": float(directed_gap),
                      "physical_gap_m": float(physical_gap) if physical_gap is not None else None,
                      "moving_time_headway_s": headway,
                      "headway_status": headway_status,
                      "ego_speed_m_s": float(speed) if speed is not None else None,
                      "ego_lifetime_generation": _generation(ego),
                      "leader_lifetime_generation": _generation(leader)}
            actor_samples.append(sample)
            following_samples.append(sample)
            stopped = (_finite(leader.get("vx")) and _finite(leader.get("vy"))
                       and math.hypot(leader["vx"], leader["vy"])
                       < profile.values["efficiency"]["stationary_speed_below_m_s"])
            tracker = stop_state[actor_id]
            if not (_finite(leader.get("vx")) and _finite(leader.get("vy"))):
                if tracker["was_stopped"]:
                    tracker["stops"].append({"start_time_s": tracker["stop_start"],
                                             "restart_time_s": None,
                                             "resolution": "leader_motion_coverage_gap"})
                tracker["was_stopped"] = False
                tracker["stop_start"] = None
                tracker["coverage_gap"] = True
                continue
            if stopped and not tracker["was_stopped"]:
                tracker["stop_start"] = sample["time_s"]
            if not stopped and tracker["was_stopped"]:
                tracker["restarted"] = True
                tracker["stops"].append({"start_time_s": tracker["stop_start"],
                                         "restart_time_s": sample["time_s"],
                                         "resolution": "leader_motion_resumed_observed"})
            tracker["was_stopped"] = stopped
        actor_rows_out.append({"actor_id": actor_id, "samples": actor_samples,
                               "route_observation_counts": route_observations,
                               "following_duration_s": None,
                               "stop_restart": stop_state[actor_id]})
    for index in range(max(primary_start, 0), len(frames) - 1):
        dt = times[index + 1] - times[index] if (
            _finite(times[index]) and _finite(times[index + 1])
            and times[index + 1] > times[index]) else None
        if dt is None or frames[index].get("transition_applied") is False:
            continue
        ego, nxt = ego_rows[index], ego_rows[index + 1]
        if not (_present_pose(ego) and _present_pose(nxt) and _same_lifetime(ego, nxt)):
            continue
        for actor_id in spec["actor_ids"]:
            leader, leader_next = actor_maps[index].get(actor_id), actor_maps[index + 1].get(actor_id)
            if not (_present_pose(leader) and _present_pose(leader_next)
                    and _same_lifetime(leader, leader_next)):
                continue
            gap, relation, _ = _directed_gap(ego, leader, map_context)
            if relation == "compatible" and gap is not None and gap > 0:
                eligible_intervals[actor_id].append(float(dt))
    actor_durations = {actor_id: sum(values) if values else None
                       for actor_id, values in eligible_intervals.items()}
    duration_values = [value for value in actor_durations.values() if value is not None]
    duration = float(sum(duration_values)) if duration_values else None
    for output in actor_rows_out:
        output["following_duration_s"] = (actor_durations[output["actor_id"]]
                                           if output["samples"] else None)
        tracker = output["stop_restart"]
        if tracker["was_stopped"]:
            tracker["stops"].append({"start_time_s": tracker["stop_start"],
                                     "restart_time_s": None,
                                     "resolution": "no_restart_observed_before_trace_end"})
        tracker["status"] = "valid" if tracker["stops"] else "unavailable"
        tracker["reason"] = ("Observed stop and restart state only; no causal response inferred"
                             if tracker["stops"] else "No stopped-leader interval was observed")
    if not following_samples:
        counts = {status: sum(row["route_observation_counts"][status]
                              for row in actor_rows_out)
                  for status in ("compatible", "incompatible", "ambiguous", "unavailable")}
        if counts["ambiguous"]:
            realization, outcome = "indeterminate", "indeterminate"
            route_status = "ambiguous"
            reason = "Multiple directed successor paths make the designated leader relation ambiguous"
        elif counts["unavailable"] or not (counts["compatible"] or counts["incompatible"]):
            realization, outcome = "indeterminate", "indeterminate"
            route_status = "unavailable"
            reason = "Current directed route compatibility is unavailable for part or all of the observed interval"
        else:
            realization, outcome = "not_reached", "not_assessed"
            route_status = "valid"
            reason = "No route-compatible leader-ahead state was observed"
        return {"realization": realization, "outcome": outcome,
                "reason": reason,
                "route_compatibility_status": route_status,
                "actors": actor_rows_out, "following_duration_s": None,
                "physical_gap_status": "unavailable", "time_headway_status": "unavailable"}, tuple(all_actor_rows), None
    # Ending while the leader remains ahead is censored, not a completed handling outcome.
    terminal = report.get("terminal_reason")
    still_ahead = any(_present_pose(ego_rows[-1]) and _present_pose(actor_maps[-1].get(actor_id))
                      and (_directed_gap(ego_rows[-1], actor_maps[-1][actor_id], map_context)[0] or 0) > 0
                      for actor_id in spec["actor_ids"])
    outcome = "unresolved" if still_ahead or terminal not in {"horizon", "goal"} else "resolved"
    return {"realization": "encountered", "outcome": outcome,
            "reason": ("Route-compatible leader-ahead observations were measured; the relation remains at horizon"
                       if outcome == "unresolved" else
                       "Leader-ahead relation ended within the observed trace"),
            "route_compatibility_status": "valid", "actors": actor_rows_out,
            "following_duration_s": float(duration) if duration is not None else None,
            "following_duration_status": "valid" if duration is not None else "unavailable",
            "physical_gap_status": "valid" if any(row.get("physical_gap_m") is not None for row in following_samples) else "unavailable",
            "time_headway_status": (
                "valid" if any(row.get("moving_time_headway_s") is not None
                               for row in following_samples)
                else "undefined" if any(row.get("headway_status") == "undefined_at_standstill"
                                         for row in following_samples)
                else "unavailable"),
            "standstill_headway": {"value": None, "status": "undefined",
                                   "reason": "Speed-normalized headway is undefined at or below 0.2 m/s; physical gap remains separate"}}, tuple(all_actor_rows), duration


def measure_interactions(frames, ego_id, report, profile, exposure, task_context,
                         map_context, events, *, scene_root, risk_metrics=()):
    """Assess each fixed source opportunity against actual saved observations."""
    context = build_interaction_context(scene_root, task_context, report)
    times, timebase = _times(frames, exposure, report)
    metrics = []
    rows = []
    if context.status != "valid":
        state = {"source_opportunity": None, "actual_realization": "indeterminate",
                 "reason": context.reason, "source_context_status": context.status}
        for metric_id in ("encounter.realization", "interaction.outcome"):
            metrics.append(MetricResult(
                metric_id, "1.0.0", AssessmentStatus.INVALID if context.status == "invalid"
                else AssessmentStatus.UNAVAILABLE, context.reason, None, None,
                CriterionOutcome.NOT_ASSESSED, window="full").to_dict())
        return {"status": context.status, "reason": context.reason,
                "timebase": timebase, "interactions": [state], "metrics": metrics,
                "evidence_refs": []}
    if not context.specs:
        return {"status": "unavailable", "reason": "Selected source manifest has no interaction family",
                "timebase": timebase, "interactions": [], "metrics": [],
                "evidence_refs": list(context.evidence_refs)}
    dimensions = None
    if any(spec.get("family") in {"pedestrian_crossing", "cyclist_crossing"}
           for spec in context.specs):
        from geotransfer_gap.evaluation.safety import _dimension_observations

        dimensions = _dimension_observations(frames)
    for spec in context.specs:
        if spec["family"] == _CONTROL:
            state = {"family": _CONTROL, "subtype": spec["subtype"],
                     "source_opportunity": False, "actual_realization": "not_applicable",
                     "interaction_outcome": "not_applicable",
                     "reason": "Control scene has no designated interaction obligation"}
            rows.append(state)
            for metric_id in ("encounter.realization", "interaction.outcome"):
                metrics.append(MetricResult(metric_id, "1.0.0", AssessmentStatus.NOT_APPLICABLE,
                                            state["reason"], None, None,
                                            CriterionOutcome.NOT_ASSESSED, window="full",
                                            evidence_refs=context.evidence_refs).to_dict())
            continue
        if not spec.get("supported"):
            state = {"family": spec["family"], "subtype": spec["subtype"],
                     "source_opportunity": True, "actual_realization": "indeterminate",
                     "interaction_outcome": "indeterminate", "reason": spec["reason"]}
            rows.append(state)
            for metric_id in ("encounter.realization", "interaction.outcome"):
                metrics.append(MetricResult(metric_id, "1.0.0", AssessmentStatus.UNAVAILABLE,
                                            spec["reason"], None, None,
                                            CriterionOutcome.NOT_ASSESSED, window="full",
                                            evidence_refs=context.evidence_refs).to_dict())
            continue
        if spec["family"] == "longitudinal_following":
            measured, actors, duration = _following_measure(
                frames, times, spec, context, report, profile, map_context)
        else:
            measured, actors, duration = _crossing_measure(
                frames, times, spec, context, task_context, report, events, dimensions, profile)
        for actor_result in measured.get("actors", ()):
            actor_result["clearance_ttc_channels"] = _risk_channels(
                risk_metrics, ego_id, actor_result.get("actor_id"))
        state = {"family": spec["family"], "subtype": spec["subtype"],
                 "source_opportunity": True,
                 "source_actor_ids": list(spec["actor_ids"]),
                 "source_fidelity": spec.get("fidelity_by_actor", {}),
                 "source_body_path_conflict": spec.get("source_conflict_by_actor", {}),
                 "source_following_scope": spec.get("source_following_by_actor", {}),
                 "actual_realization": measured.get("realization", "indeterminate"),
                 "interaction_outcome": measured.get("outcome", "indeterminate"),
                 "reason": measured.get("reason"),
                 "measurement": measured,
                 "source_context_evidence": list(context.evidence_refs)}
        rows.append(state)
        measured_status = measured.get("measurement_status")
        status = (AssessmentStatus.INVALID if measured_status == "invalid" else
                  AssessmentStatus.VALID if state["actual_realization"] != "indeterminate"
                  else AssessmentStatus.UNAVAILABLE)
        if state["actual_realization"] == "indeterminate" and status is not AssessmentStatus.INVALID:
            status = AssessmentStatus.UNAVAILABLE
        for metric_id, field in (("encounter.realization", "actual_realization"),
                                 ("interaction.outcome", "interaction_outcome")):
            value = {"family": spec["family"], "subtype": spec["subtype"],
                     "source_opportunity": True,
                     field: state[field],
                     "reason": state["reason"]}
            if metric_id == "interaction.outcome":
                value["measurement"] = measured
            metrics.append(_metric(metric_id, context, spec, actors,
                                   status=status, reason=state["reason"] or "Interaction measured",
                                   value=value if status is AssessmentStatus.VALID else None,
                                   eligible_samples=len(measured.get("actors", ())) or None,
                                   eligible_duration_s=duration))
    return {"status": "valid", "reason": context.reason,
            "timebase": timebase, "interactions": rows,
            "metrics": metrics, "evidence_refs": list(context.evidence_refs),
            "source_admission_decision_used": False,
            "compliance_criterion": "not_assessed_without_hash_bound_explicit_interaction_criterion"}
