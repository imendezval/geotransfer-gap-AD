"""Outcome-blind, hash-bound PE13 comparisons over PE09 saved results.

Scene membership remains owned by the referenced manifests. This module freezes
their identities and matching rules before it reads any metric values, then
reuses PE09 result verification and PE10 cluster bootstrap/paired summaries.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import copy
import hashlib
import json
import math
from pathlib import Path
import tomllib

from geotransfer_gap.artifacts import read_json, sha256, write_json
from geotransfer_gap.config import settings
from geotransfer_gap.evaluation.aggregate import (
    _bootstrap,
    _identity,
    _load_evaluation,
    _metric_map,
    _metric_value,
    _stratum,
    paired_cluster_bootstrap,
    paired_condition_summary,
)


COMPARISON_SCHEMA_VERSION = 1
_REQUIRED_STRATA = (
    "interaction_family", "interaction_subtype", "initial_speed_m_s",
    "route_length_m", "route_curvature_per_m", "traffic_composition",
    "traffic_density_actors_per_km", "horizon_observations", "geometry_class",
)
_DIRECTIONS = {"higher_is_better", "lower_is_better"}
_PAIRED_DIMENSIONS = ("planner", "traffic", "startup", "ego_checkpoint_sha256",
                      "traffic_checkpoint_sha256")
_PROVENANCE_FIELDS = ("source_scene_sha256", "source_tracks_sha256", "source_map_sha256",
                      "map_semantics_sha256", "dimension_provenance", "legal_semantics")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _sha256(value):
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


def _freeze_payload(config):
    payload = copy.deepcopy(config)
    payload.get("freeze", {}).pop("canonical_sha256", None)
    return payload


def _manifest_rows(path):
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != 2:
        raise ValueError(f"Comparison manifest is not an existing schema-2 manifest: {path}")
    rows = value.get("scenes")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Comparison manifest has no scene rows: {path}")
    indexed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"Comparison manifest contains a malformed scene row: {path}")
        name = row.get("name") or row.get("scene_id")
        if not isinstance(name, str) or not name or name in indexed:
            raise ValueError(f"Comparison manifest has duplicate or missing scene identity: {path}")
        indexed[name] = row
    return indexed


def load_comparison_config(path=None):
    """Load, freeze-check and hash-check PE13 selection inputs before outcomes."""
    cfg_path = Path(path or (settings().project / "configs/evaluation/geographic_comparison.toml"))
    cfg_path = cfg_path.expanduser().resolve()
    raw = cfg_path.read_bytes()
    try:
        config = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Malformed PE13 comparison config: {exc}") from exc
    if config.get("schema_version") != 1 or not isinstance(config.get("comparison_id"), str):
        raise ValueError("Unsupported PE13 comparison config")
    actual_freeze = hashlib.sha256(_canonical(_freeze_payload(config))).hexdigest()
    expected_freeze = config.get("freeze", {}).get("canonical_sha256")
    if expected_freeze != actual_freeze:
        raise ValueError("PE13 frozen selection/config identity changed; create a reviewed new freeze")
    cohorts = config.get("cohorts")
    if not isinstance(cohorts, dict) or set(cohorts) != {"left", "right"}:
        raise ValueError("PE13 config must freeze exactly left and right cohort references")
    manifests, missing_manifests = {}, []
    for side in ("left", "right"):
        declaration = cohorts[side]
        if (not isinstance(declaration, dict) or not isinstance(declaration.get("manifest"), str)
                or not _sha256(declaration.get("manifest_sha256"))
                or not isinstance(declaration.get("label"), str)
                or declaration.get("status") not in {"research_candidate", "diagnostic_only"}):
            raise ValueError(f"PE13 {side} cohort manifest identity is malformed")
        manifest = (settings().project / declaration["manifest"]).resolve()
        if not manifest.is_file():
            missing_manifests.append(side)
            manifests[side] = {"path": manifest, "sha256": None, "rows": {},
                               "status": "unavailable_missing_reference"}
            continue
        if sha256(manifest) != declaration["manifest_sha256"]:
            raise ValueError(f"PE13 {side} frozen manifest is missing or changed: {manifest}")
        manifests[side] = {"path": manifest, "sha256": sha256(manifest),
                           "rows": _manifest_rows(manifest), "status": "valid"}
    matching = config.get("matching")
    if (not isinstance(matching, dict) or matching.get("strata") != list(_REQUIRED_STRATA)):
        raise ValueError("PE13 matching strata are incomplete or unsupported")
    for name in ("initial_speed_edges_m_s", "route_length_edges_m",
                 "route_curvature_edges_per_m", "traffic_density_edges_actors_per_km"):
        edges = matching.get(name)
        if (not isinstance(edges, list) or len(edges) < 2
                or any(not _finite(item) for item in edges)
                or any(left >= right for left, right in zip(edges, edges[1:]))):
            raise ValueError(f"PE13 matching bins are malformed: {name}")
    directions = config.get("metric_directions")
    if (not isinstance(directions, dict) or not directions
            or any(not isinstance(key, str) or value not in _DIRECTIONS
                   for key, value in directions.items())):
        raise ValueError("PE13 metric directions are malformed")
    precision = config.get("precision")
    if (not isinstance(precision, dict) or not _finite(precision.get("confidence_level"))
            or not 0 < precision["confidence_level"] < 1
            or not _finite(precision.get("target_half_width_pooled_sd"))
            or precision["target_half_width_pooled_sd"] <= 0
            or type(precision.get("minimum_independent_sites_per_domain")) is not int
            or precision["minimum_independent_sites_per_domain"] < 1
            or type(precision.get("site_floor_is_power_claim")) is not bool):
        raise ValueError("PE13 precision target is malformed")
    config["_raw_sha256"] = hashlib.sha256(raw).hexdigest()
    config["_freeze_sha256"] = actual_freeze
    config["_config_path"] = str(cfg_path)
    config["_missing_manifests"] = missing_manifests
    return config, manifests


def _scene_id(result):
    value = result.get("scene_id")
    return value if isinstance(value, str) and value else None


def _task_context(result):
    metrics = result.get("episode_metrics")
    task = metrics.get("task") if isinstance(metrics, dict) else None
    context = task.get("context") if isinstance(task, dict) else None
    return context if isinstance(context, dict) else {}


def _manifest_features(result, row, stratum):
    """Return only predeclared source/context fields; never inspect metric values."""
    context = _task_context(result)
    route = context.get("route") if isinstance(context.get("route"), dict) else {}
    extra = row.get("comparison_features") if isinstance(row.get("comparison_features"), dict) else {}
    families = row.get("interaction_type_families", row.get("interaction_families"))
    family = sorted(set(item for item in families if isinstance(item, str))) if isinstance(families, list) else None
    base = {
        "interaction_family": family,
        "interaction_subtype": row.get("interaction_subtypes"),
        "initial_speed_m_s": row.get("initial_speed_m_s"),
        "route_length_m": route.get("task_span_m"),
        "route_curvature_per_m": row.get("route_curvature_per_m"),
        "traffic_composition": row.get("traffic_composition"),
        "traffic_density_actors_per_km": row.get("traffic_density_actors_per_km"),
        "horizon_observations": stratum.get("requested_horizon_observations"),
        "geometry_class": row.get("geometry_class"),
    }
    # A manifest may carry a reviewed, source-only extension. Its enclosing
    # frozen manifest hash is checked before this reader accepts any labels.
    for key in _REQUIRED_STRATA:
        if key in extra:
            base[key] = extra[key]
    if base["interaction_family"] is None:
        base["interaction_family"] = extra.get("interaction_family")
    if base["interaction_subtype"] is None:
        base["interaction_subtype"] = extra.get("interaction_subtype")
    return base


def _source_provenance(result, row):
    """Collect hash-bound source/map/semantic inputs without reading outcomes."""
    context = _task_context(result)
    task_identity = context.get("identity") if isinstance(context.get("identity"), dict) else {}
    metrics = result.get("episode_metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    map_context = metrics.get("map_context")
    map_context = map_context if isinstance(map_context, dict) else {}
    map_identity = map_context.get("identity")
    map_identity = map_identity if isinstance(map_identity, dict) else {}
    extra = row.get("comparison_features") if isinstance(row.get("comparison_features"), dict) else {}
    row_map_hash = row.get("source_map_sha256")
    context_map_hash = map_identity.get("source_map_sha256")
    for field, value in (("source_scene_sha256", task_identity.get("source_scene_sha256")),
                         ("source_tracks_sha256", row.get("source_tracks_sha256")),
                         ("source_map_sha256", row_map_hash),
                         ("map_context.source_map_sha256", context_map_hash),
                         ("map_semantics_sha256", map_identity.get("map_semantics_sha256"))):
        if value is not None and not _sha256(value):
            raise ValueError(f"Malformed hash-bound source provenance {field} for {_scene_id(result)}")
    if row_map_hash and context_map_hash and row_map_hash != context_map_hash:
        raise ValueError(f"Saved map source identity conflicts with its frozen manifest row: {_scene_id(result)}")
    return {
        "source_scene_sha256": task_identity.get("source_scene_sha256"),
        "source_tracks_sha256": row.get("source_tracks_sha256"),
        "source_map_sha256": context_map_hash or row_map_hash,
        "map_semantics_sha256": map_identity.get("map_semantics_sha256"),
        "dimension_provenance": row.get("dimension_provenance", extra.get("dimension_provenance")),
        "legal_semantics": row.get("legal_semantics", extra.get("legal_semantics")),
        "interaction_family_label": bool(row.get("interaction_type_families")
                                           or row.get("interaction_families")
                                           or extra.get("interaction_family")),
        "task_context_status": context.get("status"),
        "map_context_status": map_context.get("status"),
    }


def _provenance_audit(rows, denominator):
    summary = {}
    for field in _PROVENANCE_FIELDS:
        present = [scene for scene, values in rows.items() if values.get(field) not in (None, [], "")]
        summary[field] = {
            "available_scenes": len(present),
            "submitted_manifest_scenes": denominator,
            "missing_scene_ids": sorted(set(rows) - set(present)),
        }
    for field in ("interaction_family_label", "task_context_status", "map_context_status"):
        values = Counter(str(row.get(field)) for row in rows.values())
        summary[field] = {"counts": dict(sorted(values.items())),
                          "submitted_manifest_scenes": denominator}
    return summary


def _bin(value, edges):
    if not _finite(value):
        return None
    value = float(value)
    for low, high in zip(edges, edges[1:]):
        if low <= value < high or (value == edges[-1] and high == edges[-1]):
            return f"[{low:g},{high:g}{']' if value == edges[-1] else ')'}"
    return None


def _stratum_key(features, config):
    matching = config["matching"]
    bins = {
        "initial_speed_m_s": matching["initial_speed_edges_m_s"],
        "route_length_m": matching["route_length_edges_m"],
        "route_curvature_per_m": matching["route_curvature_edges_per_m"],
        "traffic_density_actors_per_km": matching["traffic_density_edges_actors_per_km"],
    }
    normalized, missing = {}, []
    for field in _REQUIRED_STRATA:
        value = features.get(field)
        if field in bins:
            value = _bin(value, bins[field])
        elif field == "horizon_observations":
            value = str(value) if type(value) is int and value > 0 else None
        elif field in {"interaction_family", "interaction_subtype", "traffic_composition"}:
            if isinstance(value, list):
                choices = sorted(set(item for item in value if isinstance(item, str)))
                value = json.dumps(choices, separators=(",", ":")) if choices else None
            if value is not None and not isinstance(value, str):
                value = None
        elif field == "geometry_class":
            value = value if isinstance(value, str) and value else None
        if value is None:
            missing.append(field)
        normalized[field] = value
    return (None if missing else json.dumps(normalized, sort_keys=True, separators=(",", ":"))), normalized, missing


def _goal_semantics(result):
    context = _task_context(result)
    metrics = result.get("episode_metrics") or {}
    task = metrics.get("task") if isinstance(metrics, dict) else {}
    task = task if isinstance(task, dict) else {}
    visibility = task.get("planner_goal_visibility")
    annotation = context.get("annotation") if isinstance(context.get("annotation"), dict) else {}
    return {
        "task_context_status": context.get("status"),
        "task_id": context.get("task_id"),
        "completion_radius_m": context.get("completion_radius_m"),
        "deadline_s": context.get("deadline_s"),
        "planner_goal_visibility": visibility,
        "annotation_status": annotation.get("status"),
        "annotation_claim_kinds": sorted({claim.get("claim_type") for claim in annotation.get("claims", [])
                                           if isinstance(claim, dict) and isinstance(claim.get("claim_type"), str)}),
    }


def _record_protocol(records):
    signatures = []
    for result, _ in records:
        signature = _stratum(result)
        signature["goal_semantics"] = _goal_semantics(result)
        signatures.append(signature)
    unique = {json.dumps(item, sort_keys=True, separators=(",", ":")) for item in signatures}
    return (json.loads(next(iter(unique))) if len(unique) == 1 else None), sorted(unique)


def _cluster(result):
    return _identity(result)[1]


def _metric_catalog(records):
    catalog = defaultdict(set)
    for result, _ in records:
        for (metric_id, window), record in _metric_map(result).items():
            catalog[(metric_id, window)].add((record.get("definition_version"),
                                              json.dumps(record.get("units"), sort_keys=True)))
    return catalog


def _directional_better(direction, delta):
    if direction not in _DIRECTIONS or not _finite(delta):
        return None
    return delta > 0 if direction == "higher_is_better" else delta < 0


def _cluster_summary(values, *, seed, resamples, confidence_level):
    return _bootstrap(values, seed=seed, resamples=resamples,
                      confidence_level=confidence_level)


def _metric_comparisons(left, right, left_by_scene, right_by_scene, left_keys,
                        right_keys, config, matched_keys):
    catalog_left, catalog_right = _metric_catalog(left), _metric_catalog(right)
    all_keys = sorted(set(catalog_left) | set(catalog_right))
    directions = config["metric_directions"]
    output = []
    uncertainty = config.get("_uncertainty", {
        "bootstrap_seed": 0, "bootstrap_resamples": 2000, "confidence_level": 0.95,
    })
    seed = int(uncertainty.get("bootstrap_seed", 0))
    resamples = int(uncertainty.get("bootstrap_resamples", 2000))
    alpha = 1.0 - config["precision"]["confidence_level"]
    for metric_id, window in all_keys:
        definitions = catalog_left.get((metric_id, window), set()) | catalog_right.get((metric_id, window), set())
        direction = directions.get(metric_id)
        row = {"metric_id": metric_id, "window": window, "direction": direction,
               "status": "not_assessed", "definition_units": sorted(definitions),
               "matched_strata": [], "estimate_right_minus_left": None,
               "improvement": None, "uncertainty": {"status": "unavailable", "interval": None}}
        if not catalog_left.get((metric_id, window)) or not catalog_right.get((metric_id, window)):
            row["status"] = "metric_unavailable_in_cohort"
            output.append(row)
            continue
        if len(definitions) != 1:
            row["status"] = "incompatible_definition_or_units"
            output.append(row)
            continue
        if direction is None:
            row["status"] = "direction_not_declared"
            output.append(row)
            continue

        stratum_diffs, stratum_uncertainty, uncertainty_reasons, uncertainty_audit = [], [], [], []
        incomplete = []
        paired_rows = []
        for key in matched_keys:
            left_results = [left_by_scene[scene] for scene in left_keys.get(key, [])]
            right_results = [right_by_scene[scene] for scene in right_keys.get(key, [])]
            left_samples, right_samples = [], []
            for result in left_results:
                metric = _metric_map(result).get((metric_id, window))
                value = _metric_value(metric) if metric and metric.get("status") == "valid" else None
                if _finite(value):
                    left_samples.append((result, float(value)))
            for result in right_results:
                metric = _metric_map(result).get((metric_id, window))
                value = _metric_value(metric) if metric and metric.get("status") == "valid" else None
                if _finite(value):
                    right_samples.append((result, float(value)))
            if len(left_samples) != len(left_results) or len(right_samples) != len(right_results):
                incomplete.append({"stratum": json.loads(key),
                                   "left_valid": len(left_samples), "left_expected": len(left_results),
                                   "right_valid": len(right_samples), "right_expected": len(right_results)})
                continue
            lm = sum(value for _, value in left_samples) / len(left_samples)
            rm = sum(value for _, value in right_samples) / len(right_samples)
            diff = rm - lm
            stratum_diffs.append(diff)
            row["matched_strata"].append({"stratum": json.loads(key),
                                          "left_scenes": len(left_samples),
                                          "right_scenes": len(right_samples),
                                          "left_mean": lm, "right_mean": rm,
                                          "right_minus_left": diff})
            left_cluster_values = [(_cluster(result), value) for result, value in left_samples]
            right_cluster_values = [(_cluster(result), value) for result, value in right_samples]
            # Conservative two-sided 95% difference interval: Bonferroni across
            # both independent cohorts and all matched strata. Each side uses
            # PE10's recording/sequence block bootstrap unchanged.
            marginal_level = 1.0 - alpha / (2 * len(matched_keys))
            left_ci = _cluster_summary(left_cluster_values, seed=seed, resamples=resamples,
                                       confidence_level=marginal_level)
            right_ci = _cluster_summary(right_cluster_values, seed=seed, resamples=resamples,
                                        confidence_level=marginal_level)
            uncertainty_audit.append({
                "stratum": json.loads(key),
                "left": {"status": left_ci.get("status"), "clusters": left_ci.get("clusters"),
                         "reason": left_ci.get("reason")},
                "right": {"status": right_ci.get("status"), "clusters": right_ci.get("clusters"),
                          "reason": right_ci.get("reason")},
                "marginal_confidence_level": marginal_level,
            })
            if (left_ci.get("interval") and right_ci.get("interval")
                    and left_ci.get("status") not in {"unavailable", "degenerate_resamples"}
                    and right_ci.get("status") not in {"unavailable", "degenerate_resamples"}):
                stratum_uncertainty.append((left_ci["interval"]["upper"],
                                            left_ci["interval"]["lower"],
                                            right_ci["interval"]["lower"],
                                            right_ci["interval"]["upper"]))
            else:
                stratum_uncertainty.append(None)
                uncertainty_reasons.extend(
                    f"{side}: {item.get('reason') or item.get('status')}"
                    for side, item in (("left", left_ci), ("right", right_ci))
                    if not item.get("interval")
                )
            # Shared logical source scenes are a separate paired diagnostic.
            right_by_id = {_scene_id(result): (result, value) for result, value in right_samples}
            for result, value in left_samples:
                other = right_by_id.get(_scene_id(result))
                if other and _cluster(result) == _cluster(other[0]):
                    paired_rows.append({"cluster_id": _cluster(result), "difference": other[1] - value})
        if incomplete:
            row["status"] = "incomplete_metric_coverage"
            row["metric_missingness"] = incomplete
        elif not stratum_diffs:
            row["status"] = "no_supported_matched_strata"
        else:
            estimate = sum(stratum_diffs) / len(stratum_diffs)
            row["estimate_right_minus_left"] = estimate
            row["improvement"] = _directional_better(direction, estimate)
            row["status"] = "valid_descriptive_matched_difference"
            if all(item is not None for item in stratum_uncertainty):
                lo = sum(item[2] - item[0] for item in stratum_uncertainty) / len(stratum_uncertainty)
                hi = sum(item[3] - item[1] for item in stratum_uncertainty) / len(stratum_uncertainty)
                row["uncertainty"] = {
                    "status": ("exploratory_few_clusters"
                               if any(item[side]["status"] == "exploratory_few_clusters"
                                      for item in uncertainty_audit for side in ("left", "right"))
                               else "conservative_cluster_bootstrap"),
                    "confidence_level": config["precision"]["confidence_level"],
                    "interval": {"lower": lo, "upper": hi},
                    "method": "equal-stratum difference; independent PE10 recording/sequence cluster bootstraps; Bonferroni marginal intervals",
                    "stratum_support": uncertainty_audit,
                }
            else:
                row["uncertainty"]["reason"] = "; ".join(sorted(set(uncertainty_reasons))) or "cluster uncertainty unavailable"
            if paired_rows:
                paired_delta = sum(row["difference"] for row in paired_rows) / len(paired_rows)
                row["paired_shared_scene_diagnostic"] = {
                    "estimand": "paired right minus left on same scene and recording/sequence",
                    "scene_pair_count": len(paired_rows),
                    "estimate_right_minus_left": paired_delta,
                    "direction": direction,
                    "improvement": _directional_better(direction, paired_delta),
                    "summary": paired_cluster_bootstrap(
                        paired_rows, seed=seed, resamples=resamples,
                        confidence_level=config["precision"]["confidence_level"]),
                }
        output.append(row)
    return output


def compare_records(left_records, right_records, left_manifest_rows, right_manifest_rows, config):
    """Compare verified result records after freezing source-only matched sets.

    This pure entry point is used by synthetic tests. Production callers must
    first use :func:`load_comparison_config` and PE09's hash-checking loader.
    """
    left_by_scene, right_by_scene = {}, {}
    source_rows = {"left": left_manifest_rows, "right": right_manifest_rows}
    feature_rows = {"left": {}, "right": {}}
    provenance_rows = {"left": {}, "right": {}}
    missing_counts = {side: Counter() for side in ("left", "right")}
    unmatched = {side: [] for side in ("left", "right")}
    scene_rows = {"left": [], "right": []}
    # Phase 1: only source/protocol fields. No metric map or outcome is read.
    for side, records, manifest in (("left", left_records, left_manifest_rows),
                                    ("right", right_records, right_manifest_rows)):
        destination = left_by_scene if side == "left" else right_by_scene
        for result, _events in records:
            scene = _scene_id(result)
            if not scene or scene in destination:
                raise ValueError(f"Ambiguous or missing scene identity in {side} comparison results")
            destination[scene] = result
            row = manifest.get(scene)
            if row is None:
                unmatched[side].append({"scene_id": scene, "reason": "not_in_frozen_manifest"})
                continue
            scene_rows[side].append(scene)
            identity, cluster = _identity(result)
            binary = row.get("binary_sha256", row.get("expected_binary_sha256"))
            task_identity = _task_context(result).get("identity")
            task_identity = task_identity if isinstance(task_identity, dict) else {}
            recorded_scene_id = task_identity.get("scene_id")
            if recorded_scene_id is not None and recorded_scene_id != scene:
                raise ValueError(f"{side} task scene identity conflicts with saved scene {scene}")
            recorded_manifest = task_identity.get("manifest_sha256")
            expected_manifest = config["cohorts"][side]["manifest_sha256"]
            if recorded_manifest is not None and recorded_manifest != expected_manifest:
                raise ValueError(f"{side} task manifest identity conflicts with frozen cohort manifest")
            episode_input = result.get("episode_metrics", {}).get("input")
            episode_input = episode_input if isinstance(episode_input, dict) else {}
            result_binary = task_identity.get("binary_sha256") or episode_input.get("binary_sha256")
            if binary is not None and not _sha256(binary):
                raise ValueError(f"{side} manifest has a malformed binary hash for scene {scene}")
            if result_binary is not None and not _sha256(result_binary):
                raise ValueError(f"{side} saved result has a malformed binary hash for scene {scene}")
            if not binary or not result_binary:
                unmatched[side].append({"scene_id": scene,
                                        "reason": "manifest_or_result_binary_identity_missing"})
                identity_binding_missing = True
            elif binary != result_binary:
                raise ValueError(f"{side} manifest binary identity conflicts with saved scene {scene}")
            else:
                identity_binding_missing = False
            stratum = _stratum(result)
            features = _manifest_features(result, row, stratum)
            provenance_rows[side][scene] = _source_provenance(result, row)
            key, normalized, missing = _stratum_key(features, config)
            for field in missing:
                missing_counts[side][field] += 1
            source_key = key
            if identity_binding_missing:
                key = None
            feature_rows[side][scene] = {"key": key, "features": normalized,
                                         "source_key": source_key,
                                         "missing": missing, "cluster": cluster,
                                         "identity": identity, "record": result,
                                         "identity_binding_missing": identity_binding_missing}
            if key is None:
                unmatched[side].append({"scene_id": scene, "reason": "unsupported_source_stratum",
                                        "missing_fields": missing})
    left_protocol, left_protocols = _record_protocol(left_records)
    right_protocol, right_protocols = _record_protocol(right_records)
    protocol_differences = {}
    if left_protocol is None or right_protocol is None:
        protocol_differences["within_cohort"] = "multiple protocol/task/evidence identities"
    else:
        for field in sorted(set(left_protocol) | set(right_protocol)):
            if left_protocol.get(field) != right_protocol.get(field):
                protocol_differences[field] = {"left": left_protocol.get(field),
                                               "right": right_protocol.get(field)}
    protocol_compatible = not protocol_differences
    for side, records in (("left", left_records), ("right", right_records)):
        missing_context = []
        required_identity = ("planner", "traffic", "startup", "requested_horizon_observations",
                             "trace_schema_version", "definition_version", "effective_profile_sha256",
                             "evidence_status", "evidence_level", "ego_checkpoint_status",
                             "traffic_checkpoint_status")
        for result, _ in records:
            observed = _stratum(result)
            missing_context.extend(f"{result.get('episode_id')}:{field}"
                                   for field in required_identity if observed.get(field) is None)
            if (str(observed.get("planner")).lower() in {"smart", "ppo"}
                    and observed.get("ego_checkpoint_sha256") is None):
                missing_context.append(f"{result.get('episode_id')}:ego_checkpoint_sha256")
            if (str(observed.get("traffic")).lower() in {"smart", "ppo"}
                    and observed.get("traffic_checkpoint_sha256") is None):
                missing_context.append(f"{result.get('episode_id')}:traffic_checkpoint_sha256")
            semantic = _goal_semantics(result)
            for field in ("task_context_status", "task_id", "completion_radius_m",
                          "planner_goal_visibility", "annotation_status"):
                if semantic.get(field) is None:
                    missing_context.append(f"{result.get('episode_id')}:goal_semantics.{field}")
            if semantic.get("task_context_status") != "valid":
                missing_context.append(f"{result.get('episode_id')}:task_context_not_valid")
        if missing_context:
            protocol_differences[f"{side}_required_context"] = sorted(set(missing_context))
            protocol_compatible = False
        unsupported_evidence = sorted({
            str((result.get("evidence") or {}).get("level"))
            for result, _ in records
            if (result.get("evidence") or {}).get("status") != "valid"
            or (result.get("evidence") or {}).get("level") != "archived_attested"
        })
        if unsupported_evidence:
            protocol_differences[f"{side}_evidence_attestation"] = {
                "required": "valid / archived_attested",
                "observed": unsupported_evidence,
            }
            protocol_compatible = False
        invalid_execution = []
        for result, _ in records:
            accounting = result.get("accounting")
            accounting = accounting if isinstance(accounting, dict) else {}
            campaign_status = accounting.get("campaign_status")
            if (accounting.get("execution_status") != "passed"
                    or (campaign_status is not None and campaign_status != "PASS")
                    or (accounting.get("campaign_integration_validity") not in (None, "valid"))):
                invalid_execution.append({
                    "episode_id": result.get("episode_id"),
                    "execution_status": accounting.get("execution_status"),
                    "campaign_status": campaign_status,
                    "campaign_integration_validity": accounting.get("campaign_integration_validity"),
                })
        if invalid_execution:
            protocol_differences[f"{side}_execution_validity"] = invalid_execution
            protocol_compatible = False

    def grouped(side):
        result = defaultdict(list)
        for scene, row in feature_rows[side].items():
            if row["key"] is not None:
                result[row["key"]].append(scene)
        return result

    left_groups, right_groups = grouped("left"), grouped("right")
    matched_keys = sorted(set(left_groups) & set(right_groups)) if protocol_compatible else []
    supported_left = {scene for key in matched_keys for scene in left_groups[key]}
    supported_right = {scene for key in matched_keys for scene in right_groups[key]}
    for side, supported in (("left", supported_left), ("right", supported_right)):
        for scene in scene_rows[side]:
            if scene in supported or any(item["scene_id"] == scene for item in unmatched[side]):
                continue
            unmatched[side].append({"scene_id": scene, "reason": "no_counterpart_source_stratum"})

    # Hash this selection snapshot before any metric/outcome value is accessed.
    selection = {
        "freeze_sha256": config.get("_freeze_sha256"),
        "manifests": {side: config["cohorts"][side]["manifest_sha256"] for side in ("left", "right")},
        "matched_strata": matched_keys,
        "left_scenes": sorted(supported_left), "right_scenes": sorted(supported_right),
        "unmatched": unmatched,
    }
    selection_sha256 = hashlib.sha256(_canonical(selection)).hexdigest()

    balance = []
    for key in sorted(set(left_groups) | set(right_groups)):
        left_scenes, right_scenes = left_groups.get(key, []), right_groups.get(key, [])
        balance.append({"stratum": json.loads(key), "left_scene_count": len(left_scenes),
                        "right_scene_count": len(right_scenes),
                        "left_recording_clusters": len({feature_rows["left"][s]["cluster"]
                                                         for s in left_scenes if feature_rows["left"][s]["cluster"]}),
                        "right_recording_clusters": len({feature_rows["right"][s]["cluster"]
                                                          for s in right_scenes if feature_rows["right"][s]["cluster"]}),
                        "matched": key in matched_keys})

    diagnostic_only = any(config["cohorts"][side].get("status") == "diagnostic_only"
                          for side in ("left", "right"))
    # Phase 2: outcome reads begin only after the source-only selection digest
    # above is fixed. Mismatched protocol means no values are exposed as a gap.
    metric_comparison_status = (
        "withheld_diagnostic_only_cohort" if diagnostic_only else
        "withheld_incompatible_protocol" if not protocol_compatible else
        "withheld_no_matched_strata" if not matched_keys else "computed_descriptive")
    metric_rows = (_metric_comparisons(left_records, right_records, left_by_scene, right_by_scene,
                                       left_groups, right_groups, config, matched_keys)
                   if protocol_compatible and matched_keys and not diagnostic_only else [])
    paired_diagnostics = []
    shared_scenes = sorted(set(left_by_scene) & set(right_by_scene))
    if shared_scenes and not protocol_compatible:
        combined = left_records + right_records
        uncertainty = config.get("_uncertainty", {
            "bootstrap_seed": 0, "bootstrap_resamples": 2000, "confidence_level": 0.95,
        })
        left_dimensions = _stratum(left_records[0][0]) if left_records else {}
        right_dimensions = _stratum(right_records[0][0]) if right_records else {}
        contrast = next((dimension for dimension in _PAIRED_DIMENSIONS
                         if left_dimensions.get(dimension) != right_dimensions.get(dimension)
                         and all(_stratum(result).get(key) == left_dimensions.get(key)
                                 for result, _ in left_records for key in _PAIRED_DIMENSIONS
                                 if key != dimension)
                         and all(_stratum(result).get(key) == right_dimensions.get(key)
                                 for result, _ in right_records for key in _PAIRED_DIMENSIONS
                                 if key != dimension)), None)
        if contrast is not None:
            catalog = _metric_catalog(combined)
            for (metric_id, window), definitions in sorted(catalog.items()):
                if len(definitions) != 1:
                    continue
                definition, units_json = next(iter(definitions))
                summary = paired_condition_summary(
                    combined, dimension=contrast,
                    left=left_dimensions[contrast], right=right_dimensions[contrast],
                    metric_id=metric_id, window=window,
                    definition_version=definition, units=json.loads(units_json),
                    uncertainty_profile=uncertainty,
                )
                direction = config["metric_directions"].get(metric_id)
                summary["direction"] = direction
                summary["direction_status"] = "declared" if direction else "not_declared"
                for comparison_row in summary["comparisons"]:
                    mean = comparison_row["paired_difference_summary"].get("mean")
                    comparison_row["improvement"] = _directional_better(direction, mean)
                paired_diagnostics.append(summary)
    left_clusters = {value["cluster"] for value in feature_rows["left"].values() if value["cluster"]}
    right_clusters = {value["cluster"] for value in feature_rows["right"].values() if value["cluster"]}
    left_sites = {str(value["identity"].get("location")) for value in feature_rows["left"].values()
                  if value["identity"].get("location") is not None}
    right_sites = {str(value["identity"].get("location")) for value in feature_rows["right"].values()
                   if value["identity"].get("location") is not None}
    unsupported = {side: sorted({field for row in feature_rows[side].values() for field in row["missing"]})
                   for side in ("left", "right")}
    reasons = []
    if not protocol_compatible:
        reasons.append("protocol, evidence, task-goal, or semantic-context identities differ")
    if unsupported["left"] or unsupported["right"]:
        reasons.append("one or more predeclared source-only matching strata are unavailable")
    incomplete_provenance = {
        side: sorted(field for field in _PROVENANCE_FIELDS
                     if any(values.get(field) in (None, [], "")
                            for values in provenance_rows[side].values()))
        for side in ("left", "right")
    }
    if incomplete_provenance["left"] or incomplete_provenance["right"]:
        reasons.append("source trajectory/map, dimension, or legal-semantic provenance is incomplete")
    if not matched_keys:
        reasons.append("no supported common source-only strata")
    if diagnostic_only:
        reasons.append("one or more referenced cohorts are explicitly diagnostic-only")
    if config.get("_missing_manifests"):
        reasons.append("one or more frozen source manifests are unavailable")
    min_sites = config["precision"].get("minimum_independent_sites_per_domain", 0)
    if len(left_sites) < min_sites or len(right_sites) < min_sites:
        reasons.append(f"fewer than {min_sites} independently identified sites in one or both cohorts")
    if len(left_clusters) < 2 or len(right_clusters) < 2:
        reasons.append("recording/sequence cluster identities are absent or fewer than two per cohort")
    status = "baseline_not_ready" if reasons else "descriptive_comparison_available"
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "comparison_id": config["comparison_id"],
        "status": status,
        "selection": {**selection, "sha256": selection_sha256},
        "protocol_compatibility": {"status": "compatible" if protocol_compatible else "limited",
                                   "differences": protocol_differences,
                                   "left_signature": left_protocol, "right_signature": right_protocol,
                                   "left_protocol_variants": left_protocols,
                                   "right_protocol_variants": right_protocols},
        "cohorts": {
            side: {"label": config["cohorts"][side]["label"],
                   "manifest": config["cohorts"][side]["manifest"],
                   "manifest_sha256": config["cohorts"][side]["manifest_sha256"],
                   "manifest_availability": ("unavailable_missing_reference"
                                             if side in config.get("_missing_manifests", []) else "valid"),
                   "status": config["cohorts"][side]["status"],
                   "submitted_evaluation_episodes": len(left_records if side == "left" else right_records),
                   "manifest_bound_scenes": len(scene_rows[side]),
                   "source_strata_complete_scenes": sum(row["source_key"] is not None
                                                         for row in feature_rows[side].values()),
                   "matched_scenes": len(supported_left if side == "left" else supported_right),
                   "recording_sequence_clusters": len(left_clusters if side == "left" else right_clusters),
                   "independently_identified_sites": len(left_sites if side == "left" else right_sites),
                   "missing_strata_counts": dict(sorted(missing_counts[side].items())),
                   "source_feature_missingness": {
                       field: {"count": missing_counts[side][field],
                               "submitted_scenes": len(scene_rows[side]),
                               "fraction": (missing_counts[side][field] / len(scene_rows[side])
                                            if scene_rows[side] else None)}
                       for field in _REQUIRED_STRATA},
                   "source_provenance": _provenance_audit(provenance_rows[side], len(scene_rows[side])),
                   "missing_source_provenance_fields": incomplete_provenance[side],
                   "unsupported_source_fields": unsupported[side]}
            for side in ("left", "right")},
        "matching": {"method": "exact frozen source-only strata; equal weight per matched stratum",
                     "required_strata": list(_REQUIRED_STRATA), "balance": balance,
                     "unmatched_scenes": unmatched,
                     "matched_stratum_count": len(matched_keys)},
        "metrics": metric_rows if protocol_compatible else [],
        "metric_comparison_status": metric_comparison_status,
        "paired_condition_diagnostics": paired_diagnostics,
        "precision_target": {
            "confidence_level": config["precision"]["confidence_level"],
            "target_ci_half_width_pooled_sd": config["precision"]["target_half_width_pooled_sd"],
            "minimum_independent_sites_per_domain": min_sites,
            "site_floor_is_power_claim": config["precision"]["site_floor_is_power_claim"],
            "status": "not_assessed",
            "reason": "requires blinded recording/site variance and adequate independent clusters; the site floor alone is not a power claim",
        },
        "baseline_not_ready_reasons": reasons,
        "source_only_acquisition_needs": config["readiness"]["source_only_acquisition_needs"],
        "limitations": [
            "A hash-checked trace or episode result cannot establish its own execution validity.",
            "The US fixtures are diagnostic interface/source-hold cases, not a geographic benchmark.",
            "Missing source-only fields and clusters remain unavailable; they are not imputed or interpreted as zero.",
            "Metric differences are descriptive and do not establish geographic causality.",
            "The proposed precision target is not a power calculation; cohort size must use blinded cluster/site variance.",
        ],
    }


def compare_saved_evaluations(left, right, output, *, config_path=None):
    """Run the frozen PE13 comparison against two hash-checked PE09 indexes."""
    config, manifests = load_comparison_config(config_path)
    left_root, left_index, left_records = _load_evaluation(left)
    right_root, right_index, right_records = _load_evaluation(right)
    if ((left_index.get("profile") or {}).get("effective_sha256")
            != (right_index.get("profile") or {}).get("effective_sha256")
            or (left_index.get("profile") or {}).get("definition_version")
            != (right_index.get("profile") or {}).get("definition_version")):
        raise ValueError("PE09 cohorts use different effective profiles or metric definitions")
    from geotransfer_gap.evaluation.aggregate import _profile_for_index

    _left_profile_path, left_profile = _profile_for_index(left_index)
    _right_profile_path, right_profile = _profile_for_index(right_index)
    if left_profile.effective_sha256 != right_profile.effective_sha256:
        raise ValueError("PE09 cohorts resolve to different effective profile content")
    config["_uncertainty"] = left_profile.values["uncertainty"]
    # Guard both evidence inputs and the frozen config using the existing output
    # containment owner. The new result cannot be placed inside either input.
    from geotransfer_gap.evaluation.commands import _output_path

    destination = Path(output).expanduser().resolve()
    config_file = Path(config_path or config["_config_path"]).resolve()
    for source in (left_root, right_root):
        _output_path(destination, source, config_file, None)
    report = compare_records(left_records, right_records,
                             manifests["left"]["rows"], manifests["right"]["rows"], config)
    report["inputs"] = {
        "left": {"evaluation": str(left_root), "index_sha256": sha256(left_root / "index.json"),
                 "profile": left_index.get("profile")},
        "right": {"evaluation": str(right_root), "index_sha256": sha256(right_root / "index.json"),
                  "profile": right_index.get("profile")},
        "config": {"path": str(config_file),
                   "raw_sha256": config["_raw_sha256"], "freeze_sha256": config["_freeze_sha256"]},
        "manifests": {side: {"path": str(manifests[side]["path"]),
                              "sha256": manifests[side]["sha256"],
                              "status": manifests[side].get("status", "valid")}
                      for side in ("left", "right")},
    }
    destination.mkdir(parents=True, exist_ok=False)
    write_json(destination / "comparison.json", report)
    return destination / "comparison.json"
