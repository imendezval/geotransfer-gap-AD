"""Deterministic summaries of hash-checked PE09 saved evaluation results.

This module consumes PE09's immutable index/result/event files.  It never loads a
planner, opens a simulator, or rewrites per-episode findings.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random

from geotransfer_gap.artifacts import read_json, sha256, write_json
from geotransfer_gap.config import settings
from geotransfer_gap.evaluation.profile import load_profile
from geotransfer_gap.evaluation.reporting import (
    INDEX_SCHEMA_VERSION,
    _dedupe,
    _evaluation_file,
    _read_indexed_results,
)


AGGREGATE_SCHEMA_VERSION = 1
SENSITIVITY_SCHEMA_VERSION = 1
_METRIC_STATUSES = ("valid", "unavailable", "not_applicable", "undefined", "invalid")
_EXECUTION_FAILURES = {"failed", "interrupted", "error", "crashed", "timeout",
                       "nonzero_exit", "signaled", "cancelled"}
_COMFORT_METRICS = {
    "trajectory.acceleration_longitudinal", "trajectory.acceleration_lateral",
    "trajectory.jerk_longitudinal", "trajectory.jerk_world_norm",
}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _summary(values):
    values = sorted(value for value in values if _number(value))
    if not values:
        return {"status": "unavailable", "count": 0, "mean": None,
                "median": None, "minimum": None, "maximum": None}
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    return {"status": "valid", "count": len(values), "mean": sum(values) / len(values),
            "median": median, "minimum": values[0], "maximum": values[-1]}


def _quantile(values, probability):
    if not values:
        return None
    position = probability * (len(values) - 1)
    low, high = math.floor(position), math.ceil(position)
    return values[low] if low == high else values[low] * (high - position) + values[high] * (position - low)


def _bootstrap(cluster_values, *, seed, resamples, confidence_level):
    """Equal-cluster mean interval; repeat every row from a sampled block together."""
    if any(cluster is None for cluster, _ in cluster_values):
        return {"status": "unavailable", "reason": "one or more source recording/sequence IDs are missing",
                "clusters": len({cluster for cluster, _ in cluster_values if cluster is not None}),
                "interval": None}
    grouped = defaultdict(list)
    for cluster, value in cluster_values:
        if _number(value):
            grouped[cluster].append(float(value))
    clusters = sorted(grouped)
    if len(clusters) < 2:
        return {"status": "unavailable", "reason": "fewer than two independent recording/sequence clusters",
                "clusters": len(clusters), "interval": None}
    cluster_means = [sum(grouped[key]) / len(grouped[key]) for key in clusters]
    if len(set(cluster_means)) == 1:
        return {"status": "degenerate_resamples", "reason": "bootstrap would have a zero-width interval; this is not certainty",
                "clusters": len(clusters), "interval": None}
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        sampled = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        estimates.append(sum(sum(grouped[key]) / len(grouped[key]) for key in sampled) / len(sampled))
    estimates.sort()
    alpha = (1 - confidence_level) / 2
    return {
        "status": "exploratory_few_clusters" if len(clusters) < 5 else "valid",
        "reason": ("fewer than five clusters; interval is exploratory" if len(clusters) < 5 else None),
        "clusters": len(clusters),
        "interval": {"confidence_level": confidence_level, "lower": _quantile(estimates, alpha),
                     "upper": _quantile(estimates, 1 - alpha)},
        "method": "percentile bootstrap resampling recording/sequence clusters; equal cluster weighting",
        "seed": seed,
        "resamples": resamples,
    }


def _bootstrap_ratio(cluster_rows, *, seed, resamples, confidence_level):
    if any(cluster is None for cluster, _, _ in cluster_rows):
        return {"status": "unavailable", "reason": "one or more source recording/sequence IDs are missing",
                "clusters": len({cluster for cluster, _, _ in cluster_rows if cluster is not None}),
                "interval": None}
    grouped = defaultdict(lambda: [0.0, 0.0])
    for cluster, count, exposure in cluster_rows:
        grouped[cluster][0] += count
        grouped[cluster][1] += exposure
    clusters = sorted(key for key, (_, exposure) in grouped.items() if exposure > 0)
    if len(clusters) < 2:
        return {"status": "unavailable", "reason": "fewer than two independent recording/sequence clusters",
                "clusters": len(clusters), "interval": None}
    if all(grouped[key][0] == 0 for key in clusters):
        return {"status": "degenerate_resamples", "reason": "all clusters have zero observed events; no zero-width interval is reported",
                "clusters": len(clusters), "interval": None}
    rates = [grouped[key][0] / grouped[key][1] for key in clusters]
    if len(set(rates)) == 1:
        return {"status": "degenerate_resamples", "reason": "all cluster ratios are identical; no zero-width interval is reported",
                "clusters": len(clusters), "interval": None}
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        sampled = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        events = sum(grouped[key][0] for key in sampled)
        exposure = sum(grouped[key][1] for key in sampled)
        estimates.append(events / exposure if exposure > 0 else 0.0)
    estimates.sort()
    alpha = (1 - confidence_level) / 2
    return {"status": "exploratory_few_clusters" if len(clusters) < 5 else "valid",
            "reason": "fewer than five clusters; interval is exploratory" if len(clusters) < 5 else None,
            "clusters": len(clusters),
            "interval": {"confidence_level": confidence_level,
                         "lower": _quantile(estimates, alpha), "upper": _quantile(estimates, 1 - alpha)},
            "method": "percentile cluster bootstrap of pooled event count / exposure ratio",
            "seed": seed, "resamples": resamples}


def paired_cluster_bootstrap(pairs, *, seed=0, resamples=2000, confidence_level=0.95):
    """Bootstrap paired differences while keeping every pair in its sampled cluster."""
    values = [(pair.get("cluster_id"), pair.get("difference")) for pair in pairs]
    return _bootstrap(values, seed=seed, resamples=resamples,
                      confidence_level=confidence_level)


def _identity(result):
    metrics = result.get("episode_metrics") or {}
    if not isinstance(metrics, dict):
        return {}, None
    task = metrics.get("task", {})
    context = task.get("context", {}) if isinstance(task, dict) else {}
    identity = context.get("identity", {}) if isinstance(context, dict) else {}
    if not isinstance(identity, dict):
        identity = {}
    location, recording = identity.get("location"), identity.get("recording")
    sequence = identity.get("source_route_sequence_sha256")
    if isinstance(sequence, str) and sequence:
        cluster = "sequence:" + sequence
    elif location is not None and recording is not None:
        cluster = f"recording:{location}:{recording}"
    else:
        cluster = None
    return identity, cluster


def _profile_identity(result):
    metrics = result.get("episode_metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    evaluator = metrics.get("evaluator") or {}
    if not isinstance(evaluator, dict):
        raise ValueError(f"Episode {result.get('episode_id')} evaluator identity is malformed")
    input_profile = result.get("input_profile") or {}
    if not isinstance(input_profile, dict):
        raise ValueError(f"Episode {result.get('episode_id')} profile identity is malformed")
    effective = evaluator.get("effective_profile_sha256")
    definition = (evaluator.get("definition_version")
                  or result.get("_verified_profile_definition_version"))
    if (effective and input_profile.get("effective_sha256")
            and effective != input_profile["effective_sha256"]):
        raise ValueError(f"Episode {result.get('episode_id')} has conflicting profile identities")
    return effective or input_profile.get("effective_sha256"), definition


def _stratum(result):
    metrics = result.get("episode_metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    inp = metrics.get("input") or {}
    if not isinstance(inp, dict):
        inp = {}
    input_protocol = inp.get("protocol") or {}
    if not isinstance(input_protocol, dict):
        input_protocol = {}
    protocol = result.get("protocol") or {}
    if not isinstance(protocol, dict):
        protocol = {}
    exposure = metrics.get("exposure") or {}
    if not isinstance(exposure, dict):
        exposure = {}
    censoring = exposure.get("censoring") or {}
    if not isinstance(censoring, dict):
        censoring = {}
    evidence = result.get("evidence") or {}
    if not isinstance(evidence, dict):
        raise ValueError(f"Episode {result.get('episode_id')} evidence identity is malformed")
    profile_hash, definition = _profile_identity(result)
    return {
        "planner": protocol.get("ego") or input_protocol.get("ego_controller"),
        "planner_layout": inp.get("planner_layout"),
        "checkpoint_sha256": inp.get("checkpoint_sha256"),
        "traffic": protocol.get("traffic") or input_protocol.get("traffic_controller"),
        "startup": protocol.get("startup") or input_protocol.get("traffic_startup"),
        "requested_horizon_observations": censoring.get("requested_observations"),
        "trace_schema_version": inp.get("trace_schema_version"),
        "live_validation_status": inp.get("live_validation_status"),
        "evidence_status": evidence.get("status"),
        "evidence_level": evidence.get("level"),
        "definition_version": definition,
        "effective_profile_sha256": profile_hash,
    }


def _metrics(result):
    metrics = result.get("episode_metrics")
    if metrics is None:
        return []
    if not isinstance(metrics, dict) or not isinstance(metrics.get("metrics", []), list):
        raise ValueError(f"Episode {result.get('episode_id')} metric result is malformed")
    rows = metrics.get("metrics", [])
    if any(not isinstance(row, dict) or not isinstance(row.get("metric_id"), str)
           or not isinstance(row.get("window"), str) for row in rows):
        raise ValueError(f"Episode {result.get('episode_id')} contains a malformed metric record")
    return rows


def _metric_map(result):
    indexed = {}
    for row in _metrics(result):
        key = row["metric_id"], row["window"]
        if key in indexed:
            raise ValueError(f"Episode {result.get('episode_id')} has duplicate metric/window {key}")
        indexed[key] = row
    return indexed


def _metric_value(metric):
    value = metric.get("value")
    if not isinstance(value, dict):
        return None
    metric_id = metric.get("metric_id")
    preferred = {
        "trajectory.route_progress": ("net_progress_m",),
        "trajectory.normalized_route_progress": ("raw_normalized_progress",),
        "safety.footprint_clearance": ("minimum_gap_m",),
        "efficiency.completion_time": ("elapsed_from_policy_start_s", "elapsed_from_first_observation_s"),
    }.get(metric_id, ())
    for key in (*preferred, "duration_s", "distance_m", "minimum_ttc_s", "observed_onset_count"):
        if _number(value.get(key)):
            return value[key]
    distribution = value.get("distribution")
    if isinstance(distribution, dict) and _number(distribution.get("mean")):
        return distribution["mean"]
    return None


def _sample_values(metric):
    value = metric.get("value") or {}
    samples = value.get("samples") if isinstance(value, dict) else None
    if not isinstance(samples, list):
        return []
    return [item["value"] for item in samples if isinstance(item, dict) and _number(item.get("value"))]


def _episode_outcome_rate(rows, metric_id, predicate, *, window="full", uncertainty_profile):
    assessed, events, clusters, missing_values = 0, 0, [], 0
    lower_bound = False
    for result, _ in rows:
        metric = _metric_map(result).get((metric_id, window))
        value = metric.get("value") if metric and metric.get("status") == "valid" else None
        if not isinstance(value, dict):
            continue
        if metric_id in {"safety.native_vehicle_collision_onsets", "safety.native_offroad_onsets"} and not _number(
                value.get("observed_onset_count")):
            missing_values += 1
            continue
        assessed += 1
        observed = bool(predicate(value))
        events += observed
        lower_bound |= value.get("count_is_lower_bound") is True
        clusters.append((_identity(result)[1], int(observed)))
    return {"status": "valid" if assessed else "unavailable", "events": events if assessed else None,
            "submitted": len(rows),
            "applicable_valid_episodes": assessed,
            "valid_metric_missing_quantity_episodes": missing_values,
            "missing_or_unavailable_metric_episodes": len(rows) - assessed - missing_values,
            "rate": events / assessed if assessed else None,
            "count_is_lower_bound": lower_bound,
            "uncertainty": (_bootstrap(clusters, **uncertainty_profile) if assessed else
                            {"status": "unavailable", "reason": "no valid episode event measures",
                             "clusters": 0, "interval": None}),
            "interpretation": "observed episode-level event rate; does not imply full-horizon absence"}


def _event_exposure(rows, event_metric_id, window, uncertainty_profile):
    known, observed_all, observed_with_exposure = [], 0, 0
    cluster_ratios = []
    valid_event_measures, observed_event_episodes, missing_event_quantities = 0, 0, 0
    count_lower_bound = False
    no_exposure_rows, missing_exposure_rows = 0, 0
    for result, _ in rows:
        metrics = _metric_map(result)
        event_metric = metrics.get((event_metric_id, window))
        if not event_metric or event_metric.get("status") != "valid":
            continue
        event_value = event_metric.get("value") or {}
        if not isinstance(event_value, dict):
            missing_event_quantities += 1
            continue
        count = event_value.get("observed_onset_count")
        if not _number(count):
            missing_event_quantities += 1
            continue
        valid_event_measures += 1
        observed_all += count
        observed_event_episodes += count > 0
        count_lower_bound |= event_value.get("count_is_lower_bound") is True
        exposure_metric = metrics.get(("exposure.controlled_duration", window))
        duration_value = ((exposure_metric or {}).get("value") or {})
        duration = duration_value.get("duration_s") if isinstance(duration_value, dict) else None
        if not exposure_metric or exposure_metric.get("status") != "valid":
            missing_exposure_rows += 1
            continue
        if not _number(duration):
            missing_exposure_rows += 1
            continue
        if duration <= 0:
            no_exposure_rows += 1
            continue
        observed_with_exposure += count
        known.append((count, duration))
        cluster_ratios.append((_identity(result)[1], count, duration))
    if not known:
        status = ("not_applicable" if valid_event_measures == len(rows)
                  and no_exposure_rows == valid_event_measures and missing_event_quantities == 0
                  else "unavailable")
        return {"status": status, "total_events": None, "total_exposure_s": None,
                "pooled_events_per_exposure_second": None, "mean_episode_events_per_exposure_second": None,
                "observed_onset_count_all_valid": observed_all if valid_event_measures else None,
                "observed_onset_count_with_positive_exposure": None,
                "submitted": len(rows),
                "episodes_with_valid_event_measure": valid_event_measures,
                "episodes_missing_or_unavailable_event_measure": len(rows) - valid_event_measures - missing_event_quantities,
                "valid_event_metrics_missing_quantity": missing_event_quantities,
                "episodes_with_observed_event": observed_event_episodes,
                "episodes_with_positive_exposure": 0,
                "episode_event_rate": (observed_event_episodes / valid_event_measures
                                       if valid_event_measures else None),
                "count_is_lower_bound": count_lower_bound,
                "uncertainty": {"status": status, "reason": "no valid positive-exposure cluster sample",
                                "clusters": 0, "interval": None},
                "missing_exposure_episodes": missing_exposure_rows,
                "zero_exposure_episodes": no_exposure_rows,
                "reason": "no positive supported controlled exposure" if status == "not_applicable"
                    else "event/exposure evidence unavailable"}
    total_events = sum(count for count, _ in known)
    total_exposure = sum(duration for _, duration in known)
    return {
        "status": "valid", "total_events": total_events, "total_exposure_s": total_exposure,
        "pooled_events_per_exposure_second": total_events / total_exposure,
        "mean_episode_events_per_exposure_second": sum(count / duration for count, duration in known) / len(known),
        "observed_onset_count_all_valid": observed_all,
        "observed_onset_count_with_positive_exposure": observed_with_exposure,
        "episodes_with_valid_event_measure": valid_event_measures,
        "episodes_with_observed_event": observed_event_episodes,
        "episodes_with_positive_exposure": len(known),
        "episodes_missing_or_unavailable_event_measure": len(rows) - valid_event_measures - missing_event_quantities,
        "valid_event_metrics_missing_quantity": missing_event_quantities,
        "missing_exposure_episodes": missing_exposure_rows,
        "zero_exposure_episodes": no_exposure_rows,
        "coverage_status": "complete" if not (len(rows) - valid_event_measures
                                                 or missing_event_quantities or missing_exposure_rows)
            else "partial",
        "episode_event_rate": (observed_event_episodes / valid_event_measures
                               if valid_event_measures else None),
        "count_is_lower_bound": count_lower_bound,
        "uncertainty": _bootstrap_ratio(cluster_ratios, **uncertainty_profile),
        "interpretation": "observed onset events over supported controlled time; report both pooled exposure ratio and mean episode ratio",
    }


def _aggregate_metric(rows, metric_id, window, definition_version, units, *, bootstrap_options):
    present, statuses = [], Counter()
    for result, _events in rows:
        metric = _metric_map(result).get((metric_id, window))
        if metric is None:
            statuses["not_emitted"] += 1
        elif (metric.get("definition_version"), json.dumps(metric.get("units"), sort_keys=True)) != (
                definition_version, json.dumps(units, sort_keys=True)):
            statuses["incompatible_definition_or_units"] += 1
            metric = None
        else:
            statuses[metric.get("status") or "status_missing"] += 1
        present.append((result, metric))
    for status in _METRIC_STATUSES:
        statuses.setdefault(status, 0)
    values, sample_values, clusters, criteria, categories = [], [], [], Counter(), defaultdict(Counter)
    for result, metric in present:
        if not metric:
            continue
        criteria[metric.get("criterion_outcome") or "not_recorded"] += 1
        if metric.get("status") != "valid":
            continue
        metric_value = metric.get("value")
        value = _metric_value(metric)
        if value is not None:
            values.append(value)
            _, cluster = _identity(result)
            clusters.append((cluster, value))
        if isinstance(metric_value, dict):
            for field in ("outcome", "candidate", "actual_realization", "realization"):
                category = metric_value.get(field)
                if type(category) in (str, bool):
                    categories[field][str(category)] += 1
        sample_values.extend(_sample_values(metric))
    applicable = sum(statuses[s] for s in ("valid", "unavailable", "undefined", "invalid"))
    boot = _bootstrap(clusters, **bootstrap_options) if clusters else {
        "status": "unavailable", "reason": "no valid scalar observations", "clusters": 0, "interval": None}
    return {
        "metric_id": metric_id, "window": window,
        "metric_definition_version": definition_version, "units": units,
        "submitted": len(rows), "emitted": len(rows) - statuses["not_emitted"],
        "applicable": applicable, "valid": statuses["valid"], "status_counts": dict(sorted(statuses.items())),
        "criterion_outcome_counts": dict(sorted(criteria.items())),
        "categorical_value_counts": {field: dict(sorted(counts.items()))
                                     for field, counts in sorted(categories.items())},
        "per_episode_scalar": _summary(values),
        "pooled_observation_samples": _summary(sample_values),
        "pooled_observation_sample_estimand": "each saved supported measurement sample has equal weight",
        "uncertainty": boot,
    }


def _outcomes(rows, uncertainty_profile):
    collision = {window: _episode_outcome_rate(
        rows, "safety.native_vehicle_collision_onsets",
        lambda value: value["observed_onset_count"] > 0,
        window=window, uncertainty_profile=uncertainty_profile)
        for window in ("full", "primary")}
    offroad = {window: _episode_outcome_rate(
        rows, "safety.native_offroad_onsets",
        lambda value: value["observed_onset_count"] > 0,
        window=window, uncertainty_profile=uncertainty_profile)
        for window in ("full", "primary")}
    completion_counts = Counter()
    encounter_statuses, driving_statuses, driving_outcomes = Counter(), Counter(), Counter()
    for result, _ in rows:
        task_result = result.get("task_result") or {}
        outcome = task_result.get("outcome") if isinstance(task_result, dict) else None
        if outcome in ("completed", "failed", "unresolved", "unassessable"):
            completion_counts[outcome] += 1
        encounter = result.get("encounter_result") or {}
        if not isinstance(encounter, dict):
            encounter = {}
        encounter_statuses[encounter.get("status") or "not_recorded"] += 1
        driving = result.get("driving_outcome") or {}
        if not isinstance(driving, dict):
            driving = {}
        driving_statuses[driving.get("status") or "not_recorded"] += 1
        driving_outcomes[driving.get("outcome") or "not_recorded"] += 1
    assessable = completion_counts["completed"] + completion_counts["failed"]
    return {
        "episode_collision_rate": collision,
        "episode_offroad_rate": offroad,
        "completion": {"outcome_counts": dict(sorted(completion_counts.items())),
                       "assessable_completed_or_failed": assessable,
                       "completion_rate": completion_counts["completed"] / assessable if assessable else None,
                       "status": "valid" if assessable else "unavailable",
                       "unresolved_is_not_failure": True},
        "encounter_realization_accounting": {"status_counts": dict(sorted(encounter_statuses.items())),
                                             "independent_of_driving_outcome": True},
        "driving_outcome_accounting": {"status_counts": dict(sorted(driving_statuses.items())),
                                       "outcome_counts": dict(sorted(driving_outcomes.items()))},
        "event_exposure": {
            f"{event}:{window}": _event_exposure(rows, event, window, uncertainty_profile)
            for event in ("safety.native_vehicle_collision_onsets", "safety.native_offroad_onsets")
            for window in ("full", "primary")
        },
    }


def _family_recurrence(rows):
    counts = defaultdict(Counter)
    locations = defaultdict(set)
    for result, _ in rows:
        identity, _cluster = _identity(result)
        location = identity.get("location")
        metrics = result.get("episode_metrics") or {}
        metrics = metrics.get("interactions") if isinstance(metrics, dict) else None
        for interaction in metrics.get("results", []) if isinstance(metrics, dict) else []:
            family = interaction.get("family") or "unknown"
            realization = interaction.get("actual_realization") or "not_recorded"
            counts[family][realization] += 1
            if location is not None:
                locations[family].add(str(location))
    return [{"family": family, "realization_counts": dict(sorted(statuses.items())),
             "location_count": len(locations[family])}
            for family, statuses in sorted(counts.items())]


def _failure_recurrence(rows):
    episodes = Counter()
    locations = defaultdict(set)
    for result, _ in rows:
        identity, _ = _identity(result)
        taxonomy = result.get("failure_taxonomy", [])
        labels = ({row.get("label") for row in taxonomy
                   if isinstance(row, dict) and row.get("label")}
                  if isinstance(taxonomy, list) else set())
        for label in labels:
            episodes[label] += 1
            if identity.get("location") is not None:
                locations[label].add(str(identity["location"]))
    return [{"failure_label": label, "episodes": count,
             "location_count": len(locations[label])}
            for label, count in sorted(episodes.items())]


def _tradeoff_summaries(rows, uncertainty_profile):
    categories = {
        "safety": {"safety.native_vehicle_collision_onsets", "safety.native_offroad_onsets",
                   "safety.footprint_overlap", "safety.footprint_clearance", "safety.ttc",
                   "safety.near_miss_exposure"},
        "progress": {"trajectory.route_progress", "trajectory.normalized_route_progress",
                     "efficiency.completion_time", "efficiency.stationary_duration",
                     "efficiency.low_progress_candidate", "task.outcome", "task.safe_completion"},
        "comfort": _COMFORT_METRICS | {"trajectory.speed", "trajectory.yaw_rate", "trajectory.yaw_acceleration"},
    }
    options = {"seed": uncertainty_profile["bootstrap_seed"],
               "resamples": uncertainty_profile["bootstrap_resamples"],
               "confidence_level": uncertainty_profile["confidence_level"]}
    output = {}
    for category, selected in categories.items():
        keys = set()
        for result, _ in rows:
            keys.update((metric.get("metric_id"), metric.get("window"),
                         metric.get("definition_version"),
                         json.dumps(metric.get("units"), sort_keys=True))
                        for metric in _metrics(result) if metric.get("metric_id") in selected)
        output[category] = [
            _aggregate_metric(rows, metric_id, window, definition, json.loads(units),
                              bootstrap_options=options)
            for metric_id, window, definition, units in sorted(keys)
        ]
    return output


def _accounting(rows):
    submitted, executed, failed, excluded = len(rows), 0, 0, 0
    for result, _ in rows:
        accounting = result.get("accounting") or {}
        execution = accounting.get("execution_status")
        if execution in _EXECUTION_FAILURES:
            failed += 1
        elif (result.get("evidence") or {}).get("status") == "valid":
            executed += 1
        else:
            excluded += 1
    return {"submitted": submitted, "executed_with_valid_saved_evidence": executed,
            "execution_failed": failed, "excluded_without_valid_saved_evidence": excluded,
            "partition_check": submitted == executed + failed + excluded}


def paired_condition_summary(records, *, dimension, left, right, metric_id, window,
                             definition_version, units, uncertainty_profile):
    """Return strict-nuisance-stratum intersections and paired right-minus-left estimates."""
    if dimension not in {"planner", "traffic", "startup", "checkpoint_sha256"}:
        raise ValueError("Unsupported paired condition dimension")
    if left == right:
        raise ValueError("Paired condition values must differ")
    uncertainty = uncertainty_profile.get("uncertainty", uncertainty_profile)
    nuisance_dimensions = ("planner", "planner_layout", "checkpoint_sha256", "traffic", "startup",
                           "requested_horizon_observations", "trace_schema_version",
                           "live_validation_status", "evidence_status", "evidence_level",
                           "definition_version", "effective_profile_sha256")
    nuisance_dimensions = tuple(key for key in nuisance_dimensions if key != dimension)
    sides = {left: defaultdict(lambda: defaultdict(list)),
             right: defaultdict(lambda: defaultdict(list))}
    for result, _ in records:
        stratum = _stratum(result)
        condition = stratum.get(dimension)
        if condition not in sides:
            continue
        scene = result.get("scene_id")
        if not isinstance(scene, str) or not scene:
            continue
        nuisance = tuple(json.dumps(stratum.get(key), sort_keys=True) for key in nuisance_dimensions)
        metric = _metric_map(result).get((metric_id, window))
        if (metric is None or metric.get("definition_version") != definition_version
                or json.dumps(metric.get("units"), sort_keys=True) != json.dumps(units, sort_keys=True)):
            metric = None
        sides[condition][nuisance][scene].append((result, metric))
    comparisons = []
    nuisances = set(sides[left]) | set(sides[right])
    for nuisance in sorted(nuisances):
        left_scenes, right_scenes = sides[left].get(nuisance, {}), sides[right].get(nuisance, {})
        shared = sorted(set(left_scenes) & set(right_scenes))
        output = []
        for scene in shared:
            left_records, right_records = left_scenes[scene], right_scenes[scene]
            if len(left_records) != 1 or len(right_records) != 1:
                raise ValueError(f"Ambiguous paired logical scene {scene!r} for {dimension} comparison")
            left_result, left_metric = left_records[0]
            right_result, right_metric = right_records[0]
            left_value = (_metric_value(left_metric) if left_metric and left_metric.get("status") == "valid" else None)
            right_value = (_metric_value(right_metric) if right_metric and right_metric.get("status") == "valid" else None)
            output.append({"scene_id": scene, "left_value": left_value, "right_value": right_value,
                           "difference": right_value - left_value
                               if _number(left_value) and _number(right_value) else None,
                           "cluster_id": _identity(left_result)[1]
                               if _identity(left_result)[1] == _identity(right_result)[1] else None})
        supported = [row for row in output if _number(row["difference"])]
        estimate_rows = [{"cluster_id": row["cluster_id"], "difference": row["difference"]}
                         for row in supported]
        comparisons.append({
            "nuisance_stratum": dict(zip(nuisance_dimensions, (json.loads(value) for value in nuisance))),
            "shared_logical_scene_ids": shared,
            "left_only_logical_scene_ids": sorted(set(left_scenes) - set(right_scenes)),
            "right_only_logical_scene_ids": sorted(set(right_scenes) - set(left_scenes)),
            "paired_valid_scene_ids": [row["scene_id"] for row in supported],
            "shared_scene_count": len(shared), "paired_valid_scene_count": len(supported),
            "paired_difference_summary": _summary([row["difference"] for row in supported]),
            "uncertainty": paired_cluster_bootstrap(
                estimate_rows, seed=uncertainty["bootstrap_seed"],
                resamples=uncertainty["bootstrap_resamples"],
                confidence_level=uncertainty["confidence_level"]),
            "missing_left_metric_count": sum(row["left_value"] is None for row in output),
            "missing_right_metric_count": sum(row["right_value"] is None for row in output),
        })
    return {
        "dimension": dimension, "left_condition": left, "right_condition": right,
        "metric_id": metric_id, "window": window, "metric_definition_version": definition_version,
        "units": units, "estimand": "right minus left; equal recording/sequence-cluster mean of paired scene differences",
        "comparisons": comparisons,
    }


def _paired_intersections(records, uncertainty_profile):
    values = defaultdict(set)
    metric_keys = set()
    for result, _ in records:
        stratum = _stratum(result)
        for dimension in ("planner", "checkpoint_sha256", "traffic", "startup"):
            if stratum[dimension] is not None:
                values[dimension].add(stratum[dimension])
        for metric in _metrics(result):
            if _number(_metric_value(metric)):
                metric_keys.add((metric.get("metric_id"), metric.get("window"),
                                 metric.get("definition_version"),
                                 json.dumps(metric.get("units"), sort_keys=True)))
    output = []
    for dimension in ("planner", "checkpoint_sha256", "traffic", "startup"):
        conditions = sorted(values[dimension])
        for index, left in enumerate(conditions):
            for right in conditions[index + 1:]:
                first = paired_condition_summary(
                    records, dimension=dimension, left=left, right=right,
                    metric_id="__cohort_intersection__", window="full",
                    definition_version=None, units=None, uncertainty_profile=uncertainty_profile)
                common = [item for item in first["comparisons"] if item["shared_scene_count"]]
                condition_row = {
                    "dimension": dimension, "left_condition": left, "right_condition": right,
                    "status": "valid" if common else "unavailable_no_matched_logical_scenes",
                    "matching_protocol_strata": len(common),
                    "shared_logical_scene_ids": sorted({scene for item in common
                                                         for scene in item["shared_logical_scene_ids"]}),
                    "unmatched_strata": [item for item in first["comparisons"]
                                         if not item["shared_scene_count"]],
                    "metric_pairs": [],
                }
                if not common:
                    output.append(condition_row)
                    continue
                for metric_id, window, version, units in sorted(metric_keys):
                    comparison = paired_condition_summary(
                        records, dimension=dimension, left=left, right=right,
                        metric_id=metric_id, window=window, definition_version=version,
                        units=json.loads(units), uncertainty_profile=uncertainty_profile)
                    matched = [item for item in comparison["comparisons"] if item["shared_scene_count"]]
                    if matched:
                        condition_row["metric_pairs"].append({
                            "metric_id": metric_id, "window": window,
                            "metric_definition_version": version, "units": json.loads(units),
                            "comparisons": matched,
                        })
                output.append(condition_row)
    return output


def aggregate_records(records, *, uncertainty_profile):
    """Aggregate already verified `(result, events)` rows; retained for synthetic tests."""
    uncertainty = uncertainty_profile["uncertainty"]
    bootstrap_options = {
        "seed": uncertainty["bootstrap_seed"],
        "resamples": uncertainty["bootstrap_resamples"],
        "confidence_level": uncertainty["confidence_level"],
    }
    strata = defaultdict(list)
    for result, events in records:
        dimensions = _stratum(result)
        key = tuple(json.dumps(dimensions[name], sort_keys=True) for name in dimensions)
        strata[key].append((result, events))
    output = []
    for rows in strata.values():
        dimensions = _stratum(rows[0][0])
        grouped_metrics = set()
        for result, _ in rows:
            grouped_metrics.update((row.get("metric_id"), row.get("window"),
                                    row.get("definition_version"),
                                    json.dumps(row.get("units"), sort_keys=True))
                                   for row in _metrics(result))
        metric_rows = [_aggregate_metric(rows, metric_id, window, definition_version,
                                         json.loads(units), bootstrap_options=bootstrap_options)
                       for metric_id, window, definition_version, units in sorted(grouped_metrics)]
        identities = [_identity(result)[0] for result, _ in rows]
        locations = {str(identity.get("location")) for identity in identities if identity.get("location") is not None}
        clusters = {_identity(result)[1] for result, _ in rows if _identity(result)[1] is not None}
        output.append({
            "stratum": dimensions,
            "accounting": _accounting(rows),
            "episode_count": len(rows),
            "recording_cluster_count": len(clusters),
            "location_count": len(locations),
            "metric_summaries": metric_rows,
            "outcomes": _outcomes(rows, bootstrap_options),
            "interaction_family_recurrence": _family_recurrence(rows),
            "failure_label_recurrence": _failure_recurrence(rows),
        })
    output.sort(key=lambda row: json.dumps(row["stratum"], sort_keys=True))
    return {"schema_version": AGGREGATE_SCHEMA_VERSION,
            "estimand": "episode summaries are descriptive; bootstrap statistic is an equal-source-cluster mean",
            "uncertainty_profile": {key: uncertainty[key] for key in
                                    ("cluster_unit", "bootstrap_seed", "bootstrap_resamples", "confidence_level")},
            "submitted": sum(len(rows) for rows in strata.values()),
            "strata": output,
            "paired_condition_intersections": _paired_intersections(records, uncertainty_profile),
            "limitations": ["No causal or geographic claim is implied.",
                            "Missing checkpoint identity remains null and is not inferred.",
                            "A valid observed-event count can be a lower bound."]}


def _metric_rows(result):
    by_id = defaultdict(list)
    for metric in _metrics(result):
        by_id[(metric.get("metric_id"), metric.get("window"))].append(metric)
    return by_id


def _threshold_variants(result, scales):
    """Yield saved/evaluable thresholds; comfort reuses PE02 samples, not traces or simulation."""
    outputs = []
    for (metric_id, window), metric_rows in _metric_rows(result).items():
        metric = metric_rows[0]
        if len(metric_rows) != 1 or metric.get("status") != "valid":
            continue
        value = metric.get("value") or {}
        if not isinstance(value, dict):
            continue
        if metric_id == "safety.ttc":
            for threshold, row in (value.get("horizon_sensitivity") or {}).items():
                interpretation = row.get("interpretation")
                if row.get("scene_coverage_complete") is not True:
                    interpretation = ("finite_future_overlap_partial_coverage"
                                      if interpretation == "finite_future_overlap"
                                      else "partial_coverage_no_overlap")
                outputs.append((f"ttc_horizon_s:{threshold}", metric_id, window,
                                row.get("minimum_ttc_s"), interpretation, "s"))
        elif metric_id == "safety.near_miss_exposure":
            for family, key in (("ttc", "ttc_thresholds"), ("clearance", "clearance_thresholds")):
                for name, row in (value.get(key) or {}).items():
                    amount = row.get("observed_lower_bound_duration_s")
                    status = "valid" if _number(amount) else row.get("observed_duration_status", "unavailable")
                    if not _number(amount) and row.get("window_wide_zero_supported") is True:
                        amount = row.get("complete_coverage_below_duration_s")
                        status = "valid_complete_coverage" if _number(amount) else status
                    outputs.append((f"{family}:{name}", metric_id, window, amount, status, "s"))
        elif metric_id == "efficiency.stationary_duration":
            for name, row in (value.get("threshold_sensitivity") or {}).items():
                outputs.append((f"stationary:{name}", metric_id, window, row.get("duration_s"),
                                "valid" if _number(row.get("duration_s")) else "unavailable", "s"))
        elif metric_id in _COMFORT_METRICS:
            base = value.get("threshold")
            samples = value.get("samples")
            supported = sum(sample.get("exposure_s", 0) for sample in samples or []
                            if isinstance(sample, dict) and _number(sample.get("exposure_s")))
            if not _number(base) or not isinstance(samples, list):
                continue
            for scale in scales:
                threshold = base * scale
                exceeded = sum(sample["exposure_s"] for sample in samples
                               if isinstance(sample, dict) and _number(sample.get("value"))
                               and _number(sample.get("exposure_s"))
                               and abs(sample["value"]) > threshold)
                outputs.append((f"comfort_scale:{scale:g}", metric_id, window, exceeded,
                                "valid" if supported > 0 else "not_applicable", "s"))
    return outputs


def _primary_variant_value(result, variant, metric_id, window, profile):
    metric = _metric_map(result).get((metric_id, window))
    if not metric or metric.get("status") != "valid":
        return None
    value = metric.get("value") or {}
    if not isinstance(value, dict):
        return None
    if metric_id == "safety.ttc":
        primary = (profile.get("safety", {}).get("ttc", {}).get("primary_horizon_s")
                   or value.get("primary_horizon_s"))
        row = (value.get("horizon_sensitivity") or {}).get(str(primary))
        return row.get("minimum_ttc_s") if isinstance(row, dict) else None
    if metric_id == "safety.near_miss_exposure":
        family = variant.split(":", 1)[0]
        if family == "ttc":
            primary = profile.get("safety", {}).get("near_miss", {}).get("ttc_below_s")
            collection = value.get("ttc_thresholds") or {}
            unit = "s"
        elif family == "clearance":
            primary = profile.get("safety", {}).get("near_miss", {}).get("footprint_clearance_below_m")
            collection = value.get("clearance_thresholds") or {}
            unit = "m"
        else:
            return None
        for row in collection.values():
            threshold = row.get("threshold_s" if unit == "s" else "threshold_m")
            if _number(primary) and threshold == primary:
                amount = row.get("observed_lower_bound_duration_s")
                if not _number(amount) and row.get("window_wide_zero_supported") is True:
                    amount = row.get("complete_coverage_below_duration_s")
                return amount
        return None
    if metric_id == "efficiency.stationary_duration":
        return value.get("duration_s")
    if metric_id in _COMFORT_METRICS:
        return value.get("exceedance_duration_s")
    return None


def sensitivity_records(records, *, uncertainty_profile, threshold_scales):
    """Summarize profile-frozen alternative thresholds from stored PE09 metric evidence."""
    uncertainty = uncertainty_profile.get("uncertainty", uncertainty_profile)
    bootstrap_options = {"seed": uncertainty["bootstrap_seed"],
                         "resamples": uncertainty["bootstrap_resamples"],
                         "confidence_level": uncertainty["confidence_level"]}
    evaluation_profile = uncertainty_profile
    cohorts = defaultdict(list)
    for result, _ in records:
        dimensions = _stratum(result)
        key = tuple(json.dumps(dimensions[name], sort_keys=True) for name in dimensions)
        cohorts[key].append((result, _))
    groups = []
    for cohort in cohorts.values():
        dimensions = _stratum(cohort[0][0])
        cohort_ids = {result.get("episode_id") for result, _ in cohort}
        variants = defaultdict(list)
        for result, _events in cohort:
            episode_id = result.get("episode_id")
            cluster = _identity(result)[1]
            for key, metric_id, window, amount, status, units in _threshold_variants(result, threshold_scales):
                variants[(key, metric_id, window, units)].append(
                    {"episode_id": episode_id, "cluster_id": cluster, "value": amount,
                     "status": status,
                     "primary_value": _primary_variant_value(
                         result, key, metric_id, window, evaluation_profile)})
        rows = []
        for (key, metric_id, window, units), observations in sorted(variants.items()):
            outcomes = Counter(item["status"] for item in observations)
            assessed = [item for item in observations if item["status"] in
                        ("valid", "finite_future_overlap", "finite_future_overlap_partial_coverage",
                         "no_overlap_predicted_within_horizon")]
            supported = [item for item in observations if _number(item["value"])
                         and item["status"] in ("valid", "finite_future_overlap",
                                                "finite_future_overlap_partial_coverage")]
            paired = []
            for item in supported:
                original = item.get("primary_value")
                if _number(original):
                    paired.append({"episode_id": item["episode_id"], "cluster_id": item["cluster_id"],
                                   "difference": item["value"] - original})
            represented = {item["episode_id"] for item in observations}
            rows.append({
                "variant": key, "metric_id": metric_id, "window": window, "units": units,
                "episodes_submitted": len(cohort), "episodes_with_variant_record": len(observations),
                "episodes_assessed_under_variant": len(assessed),
                "episodes_with_finite_value": len(supported),
                "episodes_missing_variant_record": len(cohort_ids - represented),
                "aligned_episode_ids": sorted(str(item) for item in represented if item is not None),
                "missing_episode_ids": sorted(str(item) for item in cohort_ids - represented if item is not None),
                "variant_status_counts": dict(sorted(outcomes.items())),
                "value_summary": _summary([item["value"] for item in supported]),
                "paired_episode_ids": [item["episode_id"] for item in paired],
                "paired_difference_summary": _summary([item["difference"] for item in paired]),
                "paired_difference_uncertainty": paired_cluster_bootstrap(
                    paired, seed=uncertainty["bootstrap_seed"],
                    resamples=uncertainty["bootstrap_resamples"],
                    confidence_level=uncertainty["confidence_level"]),
                "threshold_only_from_saved_evidence": True,
            })
        groups.append({
            "stratum": dimensions,
            "episode_ids": sorted(str(value) for value in cohort_ids if value is not None),
            "recording_cluster_count": len({_identity(result)[1] for result, _ in cohort
                                             if _identity(result)[1] is not None}),
            "location_count": len({str(_identity(result)[0].get("location")) for result, _ in cohort
                                    if _identity(result)[0].get("location") is not None}),
            "variants": rows,
            "safety_progress_comfort_context": {
                "accounting": _accounting(cohort),
                "outcomes": _outcomes(cohort, bootstrap_options),
                "tradeoff_metric_summaries": _tradeoff_summaries(cohort, uncertainty),
                "interaction_family_recurrence": _family_recurrence(cohort),
                "failure_label_recurrence": _failure_recurrence(cohort),
                "stationary_metric_id": "efficiency.stationary_duration",
                "low_progress_metric_id": "efficiency.low_progress_candidate",
            },
        })
    groups.sort(key=lambda row: json.dumps(row["stratum"], sort_keys=True))
    return {"schema_version": SENSITIVITY_SCHEMA_VERSION,
            "method": "reused PE09 stored sensitivity channels and PE02 saved continuous samples; no simulation or planner execution",
            "paired_estimand": "same logical episode; cluster-resampled equal recording/sequence-cluster mean difference",
            "threshold_scales": threshold_scales,
            "groups": groups,
            "limitations": ["Alternative values are reported only when the stored evidence supports them.",
                            "A missing threshold variant remains unavailable; it is not imputed.",
                            "Threshold sensitivity does not change episode outcomes or prove causality."]}


def _load_evaluation(evaluation):
    output = Path(evaluation).expanduser().resolve()
    index_path = _evaluation_file(output, "index.json", "evaluation index")
    index = read_json(index_path)
    if (not isinstance(index, dict) or index.get("schema_version") != INDEX_SCHEMA_VERSION
            or index.get("complete") is not True or not isinstance(index.get("episodes"), list)
            or index.get("expected_episodes") != len(index["episodes"])):
        raise ValueError("Saved PE09 evaluation index is unsupported or incomplete")
    _dedupe(index["episodes"])
    snapshot_ref = index.get("input_snapshot") or {}
    snapshot = _evaluation_file(output, snapshot_ref.get("file"), "input snapshot")
    if not snapshot.is_file() or sha256(snapshot) != snapshot_ref.get("sha256"):
        raise ValueError("Saved evaluation input snapshot is missing or has changed")
    records_by_id = _read_indexed_results(output, index)
    records = [records_by_id[row["episode_id"]] for row in index["episodes"]]
    expected_profile = (index.get("profile") or {}).get("effective_sha256")
    expected_definition = (index.get("profile") or {}).get("definition_version")
    for result, _ in records:
        effective, definition = _profile_identity(result)
        if effective != expected_profile:
            raise ValueError(f"Episode {result.get('episode_id')} profile does not match the PE09 index")
        if result.get("episode_metrics") is not None and definition != expected_definition:
            raise ValueError(f"Episode {result.get('episode_id')} definition does not match the PE09 index")
        if definition is None:
            result["_verified_profile_definition_version"] = expected_definition
    return output, index, records


def _prepare_output(output, evaluation, profile_path):
    from geotransfer_gap.evaluation.commands import _output_path

    destination = Path(output).expanduser().resolve()
    source = Path(evaluation).expanduser().resolve()
    _output_path(destination, source, profile_path, None)
    destination.mkdir(parents=True, exist_ok=False)
    return destination


def _profile_for_index(index):
    recorded = index.get("profile") or {}
    candidates = [Path(recorded["path"]).expanduser()] if recorded.get("path") else []
    candidates.append(settings().project / "configs/evaluation/default.toml")
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        profile = load_profile(candidate)
        if (profile.effective_sha256 == recorded.get("effective_sha256")
                and profile.definition_version == recorded.get("definition_version")):
            return candidate, profile
    raise ValueError("The validated PE09 profile definition is unavailable; refusing to guess its strata or sensitivity variants")


def aggregate_evaluation(evaluation, output):
    evaluation_root, index, records = _load_evaluation(evaluation)
    profile_path, profile = _profile_for_index(index)
    result = aggregate_records(records, uncertainty_profile=profile.values)
    result["source"] = {"evaluation": str(evaluation_root), "index_sha256": sha256(evaluation_root / "index.json"),
                         "profile_effective_sha256": profile.effective_sha256,
                         "profile_raw_sha256": (index.get("profile") or {}).get("raw_sha256"),
                         "episode_result_hashes": [row["result_sha256"] for row in index["episodes"]]}
    destination = _prepare_output(output, evaluation_root, profile_path)
    write_json(destination / "aggregate.json", result)
    return destination / "aggregate.json"


def sensitivity_evaluation(evaluation, output):
    evaluation_root, index, records = _load_evaluation(evaluation)
    profile_path, profile = _profile_for_index(index)
    result = sensitivity_records(records, uncertainty_profile=profile.values,
                                 threshold_scales=profile.values["comfort"]["threshold_scale_sensitivity"])
    result["source"] = {"evaluation": str(evaluation_root), "index_sha256": sha256(evaluation_root / "index.json"),
                         "profile_effective_sha256": profile.effective_sha256,
                         "profile_raw_sha256": (index.get("profile") or {}).get("raw_sha256"),
                         "episode_result_hashes": [row["result_sha256"] for row in index["episodes"]]}
    destination = _prepare_output(output, evaluation_root, profile_path)
    write_json(destination / "sensitivity.json", result)
    return destination / "sensitivity.json"
