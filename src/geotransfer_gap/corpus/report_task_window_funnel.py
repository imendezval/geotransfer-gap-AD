"""Build an auditable source-task/window funnel from retained candidate evidence.

The output deliberately keeps actor-paired candidate evidence apart from
scene-level admission evidence. It counts retained records and identities, not
admission rates.
"""

from __future__ import annotations

import collections
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from ..artifacts import read_json, resolve_reference, sha256 as artifact_sha256, write_json as write_evidence_json
from ..config import settings


AUDITS = settings().artifacts / "audits"
OUTPUT = AUDITS / "task_window_funnel"

# These are parsed task/window selectors, including earlier and later snapshots.
# Repeated rows across selectors are preserved as origins and deduplicated only
# by recording + ego + frame + actor for the combined identity table.
SOURCE_SELECTOR_NAMES = (
    "body_task_additions",
    "body_task_remaining_selection",
    "body_task_selection",
    "fine_phase_additions",
    "fine_phase_source_selection",
    "fine_phase_task_selection",
    "footprint_source_selection",
    "footprint_task_additions",
    "footprint_task_selection",
    "slow_approach_source_selection",
    "slow_approach_task_selection",
    "source_following_phase_selection",
    "source_following_scope_retry_selection",
    "source_moving_queue_additions",
    "source_moving_queue_selection",
    "source_refined_phase_remaining_selection",
    "source_refined_phase_selection",
    "source_restart_selection",
    "source_restart_turns_additions",
    "source_restart_turns_selection",
    "source_restart_velocity_selection",
    "source_variant_selection",
    "step2_oriented_source_selection",
    "step2_oriented_source_selection_before_task_first_selection",
    "step2_source_task_additions",
    "step2_source_task_selection",
    "step2_source_task_selection_before_task_first_selection",
    "third_family_directed_supported_candidates",
    "third_family_event_additions_v1",
    "third_family_event_fine_selection_v1",
    "third_family_event_selection_v1",
    "third_family_fine_straight_additions",
    "third_family_r02e40_phase_selection",
    "third_family_source_selection_v1",
)

# Exhaustive/scan outputs are inventoried by their own row counts. Their rows
# describe ego windows or map preflight, not a qualified actor-paired task.
RAW_CATALOG_NAMES = (
    "all_moving_windows",
    "all_moving_windows_loc1_stride50",
    "all_moving_windows_loc23_stride50",
    "all_moving_windows_loc4_stride50",
    "fine_phase_source_catalog",
    "fine_phase_map_preflight",
    "slow_approach_source_catalog",
    "slow_approach_map_preflight",
    "source_map_preflight",
    "source_map_preflight_loc1_oriented_v3",
    "source_map_preflight_loc23_oriented_v3",
    "source_map_preflight_loc4_oriented_v3",
    "source_map_preflight_loc1_stride50",
    "source_map_preflight_loc23_stride50",
    "source_map_preflight_loc4_stride50",
    "unscreened_interactive_map_pass_catalog",
)

# These are useful scene screens and queued scene candidates whose rows do not
# represent a single verified actor-pair task. Their sizes and hashes remain
# visible while their rows stay outside task-level counts.
UNPAIRED_SCAN_NAMES = (
    "step2_first_screen",
    "step2_loc1_interaction_priority",
    "step2_loc1_stride50_screen",
    "step2_loc23_stride50_screen",
    "step2_loc23_stride50_screen_v2",
    "step2_loc2_stride50_screen",
    "step2_map14_interaction_priority",
    "step2_map14_screen",
    "step2_map_screen",
    "step2_remaining_interactive_screen",
    "step2_source_following_screen",
    "step2_expansion_source_queue",
)

SCENE_LEDGER_NAMES = (
    "step2_candidate_ledger",
    "step2_candidate_ledger_hybrid_startup",
)

PRODUCER_KEYS = ("pilot_ind.py", "late_spawn_runtime.py", "hybrid_traffic.py")

STATUS_CLASS = {
    "unresolved_semantics_screen": "hard_semantic_exclusion",
    "awaiting_manual_review": "awaiting_review",
    "technical_rejection": "technical_failure",
    "source_geometry_rejection": "source_failure",
    "source_ego_boundary_rejection": "source_failure",
    "unreviewable_source_overlap": "source_failure",
}


def sha256(path: Path) -> str:
    return artifact_sha256(path)


def relpath(path: Path) -> str:
    try:
        return path.resolve().relative_to(settings().project.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def load_json(path: Path) -> Any:
    return read_json(path)


def write_json(path: Path, value: Any) -> None:
    write_evidence_json(path, value)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True, ensure_ascii=False)
                    if isinstance(value, (dict, list, tuple, set))
                    else value
                    for key, value in row.items()
                }
            )


def input_record(path: Path, role: str, **extra: Any) -> dict[str, Any]:
    return {"path": relpath(path), "sha256": sha256(path), "role": role, **extra}


def read_named(name: str) -> tuple[Path, Any]:
    path = AUDITS / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path, load_json(path)


def actor_value(row: dict[str, Any]) -> Any:
    for key in ("actor", "actor_id", "actor_track_id"):
        if row.get(key) is not None:
            return row[key]
    return None


def ego_value(row: dict[str, Any]) -> Any:
    for key in ("ego", "ego_track_id"):
        if row.get(key) is not None:
            return row[key]
    return None


def scene_key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (row.get("recording"), ego_value(row), row.get("first_frame"))


def window_key(row: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (*scene_key(row), actor_value(row))


def key_text(key: tuple[Any, ...]) -> str:
    return json.dumps(list(key), separators=(",", ":"), ensure_ascii=False)


def task_kind(row: dict[str, Any]) -> str | None:
    evidence = row.get("task_evidence")
    if isinstance(evidence, dict) and evidence.get("kind"):
        return str(evidence["kind"])
    return None


def task_family(kind: str | None) -> str:
    if kind == "cyclist_crossing":
        return "cyclist_crossing"
    if kind == "pedestrian_crossing":
        return "pedestrian_crossing"
    if kind and kind.startswith("lead_vehicle_"):
        return "vehicle_response"
    if kind:
        return "other_task"
    return "unclassified"


def identity_scope(key: tuple[Any, Any, Any, Any]) -> str:
    return "actor_pair" if key[3] is not None else "scene_window_only"


def provenance(row: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    fingerprints = row.get("screen_fingerprints")
    if not isinstance(fingerprints, dict) or not fingerprints:
        return "unknown", "unknown", {}
    fingerprints = dict(sorted(fingerprints.items()))
    has_primary = [key for key in PRODUCER_KEYS if fingerprints.get(key)]
    if len(has_primary) == len(PRODUCER_KEYS):
        state = "complete_primary_versions"
    elif has_primary:
        state = "partial_primary_versions"
    else:
        state = "other_or_partial_versions"
    version_hash = hashlib.sha256(
        json.dumps(fingerprints, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return state, version_hash, fingerprints


def status_class(status: Any) -> str:
    if status is None:
        return "unspecified"
    return STATUS_CLASS.get(str(status), "unclassified_status")


def reason_details(row: dict[str, Any]) -> list[dict[str, Any]]:
    details = []
    for field, value in sorted(row.items()):
        name = field.lower()
        is_reason_field = any(token in name for token in ("reason", "rejection", "exclusion", "failure"))
        is_rule_flag_field = "flag" in name and "rule" in name
        if not (is_reason_field or is_rule_flag_field) or value in (None, [], {}, ""):
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item in (None, ""):
                continue
            details.append({"field": field, "value": item})
    return details


def reason_count_key(detail: dict[str, Any], status: Any) -> str:
    value = json.dumps(detail["value"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"{status or 'unspecified'}::{detail['field']}={value}"


def rejection_inventory(data: dict[str, Any]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    counts = {}
    reasons = {}
    for field in ("source_rejections", "source_task_screen_rejections"):
        value = data.get(field)
        if isinstance(value, list):
            counts[field] = len(value)
            reason_counts = collections.Counter(
                str(row.get("reason", "unspecified"))
                for row in value
                if isinstance(row, dict)
            )
            reasons[field] = dict(sorted(reason_counts.items()))
        elif isinstance(value, int):
            counts[field] = value
            reasons[field] = {"reason_details_not_retained": value}
    return counts, reasons


def counts_for_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    windows = {window_key(row) for row in rows}
    actor_tasks = {
        (row.get("recording"), ego_value(row), actor_value(row))
        for row in rows
        if actor_value(row) is not None
    }
    kinds = collections.Counter(task_kind(row) or "no_task_evidence_kind" for row in rows)
    locations = collections.Counter(str(row.get("location", "unknown")) for row in rows)
    recordings = collections.Counter(str(row.get("recording", "unknown")) for row in rows)
    return {
        "rows": len(rows),
        "unique_windows_recording_ego_frame_actor": len(windows),
        "unique_actor_pair_tasks_recording_ego_actor": len(actor_tasks),
        "rows_with_actor_pair": sum(actor_value(row) is not None for row in rows),
        "rows_without_actor_pair": sum(actor_value(row) is None for row in rows),
        "rows_with_task_evidence": sum(task_kind(row) is not None for row in rows),
        "task_kind_counts_by_row": dict(sorted(kinds.items())),
        "rows_by_location": dict(sorted(locations.items())),
        "rows_by_recording": dict(sorted(recordings.items(), key=lambda x: (x[0] == "unknown", x[0]))),
    }


def qualified_breakdowns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    windows_by: dict[str, set[tuple[Any, ...]]] = collections.defaultdict(set)
    tasks_by: dict[str, set[tuple[Any, ...]]] = collections.defaultdict(set)
    for row in rows:
        kind = task_kind(row)
        if not kind:
            continue
        key = window_key(row)
        task = (row.get("recording"), ego_value(row), actor_value(row))
        family = task_family(kind)
        groups = [f"family:{family}"]
        if row.get("location") is not None:
            groups.extend((f"location:{row['location']}", f"family_location:{family}:{row['location']}"))
        if row.get("recording") is not None:
            groups.extend((f"recording:{row['recording']}", f"family_recording:{family}:{row['recording']}"))
        for group in groups:
            windows_by[group].add(key)
            if task[2] is not None:
                tasks_by[group].add(task)
    return {
        "qualified_unique_windows_by_family_location_recording": {
            group: len(values) for group, values in sorted(windows_by.items())
        },
        "qualified_unique_actor_tasks_by_family_location_recording": {
            group: len(values) for group, values in sorted(tasks_by.items())
        },
    }


def build_catalogs(inputs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    summaries = []
    candidate_map: dict[str, dict[str, Any]] = {}
    for name in SOURCE_SELECTOR_NAMES:
        path, data = read_named(name)
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        if not isinstance(jobs, list):
            raise TypeError(f"{path}: jobs is not a list")
        if any(not isinstance(row, dict) for row in jobs):
            raise TypeError(f"{path}: jobs contains a non-object row")
        summary = counts_for_rows(jobs)
        summary.update(qualified_breakdowns(jobs))
        source_pair_count = sum(actor_value(row) is not None for row in jobs)
        qualified = sum(task_kind(row) is not None for row in jobs)
        source_rejection_counts, source_rejection_reasons = rejection_inventory(data)
        positive_pairs = data.get("source_positive_pairs")
        remaining_queue = data.get("remaining_source_queue")
        summaries.append(
            {
                "catalog": name,
                "path": relpath(path),
                "sha256": sha256(path),
                "catalog_type": "parsed_source_selector",
                "qualified_task_evidence_rows": qualified,
                "source_pair_rows": source_pair_count,
                "source_positive_pair_metadata_count": len(positive_pairs) if isinstance(positive_pairs, list) else positive_pairs,
                "remaining_source_queue_count": len(remaining_queue) if isinstance(remaining_queue, list) else remaining_queue,
                "source_rejection_record_counts": source_rejection_counts,
                "source_rejection_reason_counts": source_rejection_reasons,
                **summary,
            }
        )
        inputs.append(input_record(path, "parsed_source_selector", rows=len(jobs)))
        for row_index, row in enumerate(jobs):
            key = window_key(row)
            if key[0] is None or key[1] is None or key[2] is None:
                # Preserve an incomplete identity as a separate row below.
                unique_id = f"incomplete:{name}:{row_index}"
            else:
                unique_id = key_text(key)
            record = candidate_map.setdefault(
                unique_id,
                {
                    "candidate_key": unique_id,
                    "recording": key[0],
                    "ego": key[1],
                    "first_frame": key[2],
                    "actor": key[3],
                    "identity_scope": identity_scope(key),
                    "source_catalogs": set(),
                    "task_kinds": set(),
                    "task_families": set(),
                    "roles": set(),
                    "locations": set(),
                    "source_evidence_rows": 0,
                    "qualified_source_evidence_rows": 0,
                },
            )
            record["source_catalogs"].add(name)
            kind = task_kind(row)
            if kind:
                record["task_kinds"].add(kind)
                record["task_families"].add(task_family(kind))
                record["qualified_source_evidence_rows"] += 1
            if row.get("role"):
                record["roles"].add(str(row["role"]))
            if row.get("location") is not None:
                record["locations"].add(row["location"])
            record["source_evidence_rows"] += 1

    # Raw catalogs can be extremely large and overlap by sweep. Their rows are
    # counted by file, never added to the qualified source-task/window universe.
    raw_summaries = []
    for name in RAW_CATALOG_NAMES:
        path, data = read_named(name)
        rows = data.get("windows", []) if isinstance(data, dict) else []
        raw_summaries.append(
            {
                "catalog": name,
                "path": relpath(path),
                "sha256": sha256(path),
                "catalog_type": "raw_or_preflight_window_scan",
                "row_count_this_file_only": len(rows),
                "identity_use": "inventory_only_no_qualified_actor_task_join",
            }
        )
        inputs.append(input_record(path, "raw_window_scan_inventory", rows=len(rows)))

    for name in UNPAIRED_SCAN_NAMES:
        path, data = read_named(name)
        array_name = next(
            (field for field in ("results", "candidates", "windows") if isinstance(data.get(field), list)),
            None,
        )
        rows = data.get(array_name, []) if array_name else []
        nested_events = sum(len(row.get("events", [])) for row in rows if isinstance(row, dict) and isinstance(row.get("events"), list))
        raw_summaries.append(
            {
                "catalog": name,
                "path": relpath(path),
                "sha256": sha256(path),
                "catalog_type": "scene_screen_or_unpaired_queue",
                "array_name": array_name,
                "row_count_this_file_only": len(rows),
                "nested_event_rows": nested_events,
                "identity_use": "inventory_only_no_task_pair_join",
            }
        )
        inputs.append(input_record(path, "scene_screen_inventory", rows=len(rows), array=array_name))

    return summaries, candidate_map, raw_summaries


def add_attempts(inputs: list[dict[str, Any]], flow: dict[str, Any], candidate_map: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    ledger_summaries = []
    version_summary: dict[tuple[str, str, str], dict[str, Any]] = {}
    for ledger_info in flow["historical_ledgers"]:
        name = Path(ledger_info["path"]).stem
        path = AUDITS / f"{name}.json"
        actual_sha = sha256(path)
        if actual_sha != ledger_info["sha256"]:
            raise ValueError(f"Historical ledger SHA mismatch for {relpath(path)}")
        data = load_json(path)
        rows = data.get("results", []) if isinstance(data, dict) else []
        statuses = collections.Counter(str(row.get("status") or "unspecified") for row in rows)
        status_classes = collections.Counter(status_class(row.get("status")) for row in rows)
        technical_passes = sum(row.get("technical_admitted") is True or row.get("technical_pass") is True for row in rows)
        ledger_reason_counts: collections.Counter[str] = collections.Counter()
        per_version: dict[tuple[str, str], dict[str, Any]] = {}
        for row_index, row in enumerate(rows):
            state, version_hash, fingerprints = provenance(row)
            version_tag = version_hash if state != "unknown" else "unknown"
            version_key = (name, state, version_tag)
            v = version_summary.setdefault(
                version_key,
                {
                    "ledger": name,
                    "provenance_state": state,
                    "version_id": version_tag,
                    "producer_fingerprints": fingerprints,
                    "attempt_rows": 0,
                    "status_counts": collections.Counter(),
                    "failure_reason_counts": collections.Counter(),
                    "technical_admitted_rows": 0,
                },
            )
            v["attempt_rows"] += 1
            v["status_counts"][str(row.get("status") or "unspecified")] += 1
            v["technical_admitted_rows"] += int(row.get("technical_admitted") is True or row.get("technical_pass") is True)
            pv = per_version.setdefault((state, version_tag), {"rows": 0, "statuses": collections.Counter(), "technical_admitted_rows": 0})
            pv["rows"] += 1
            pv["statuses"][str(row.get("status") or "unspecified")] += 1
            pv["technical_admitted_rows"] += int(row.get("technical_admitted") is True or row.get("technical_pass") is True)
            details = reason_details(row)
            for detail in details:
                reason = reason_count_key(detail, row.get("status"))
                ledger_reason_counts[reason] += 1
                v["failure_reason_counts"][reason] += 1
                pv.setdefault("failure_reason_counts", collections.Counter())[reason] += 1

            key = window_key(row)
            usable_key = all(value is not None for value in key[:3])
            pair_key = key_text(key) if usable_key and key[3] is not None else None
            scene_key_value = key_text(key[:3]) if usable_key else None
            status = row.get("status")
            attempt = {
                "ledger": name,
                "ledger_path": relpath(path),
                "ledger_sha256": actual_sha,
                "row_index": row_index,
                "recording": key[0],
                "location": row.get("location"),
                "ego": key[1],
                "first_frame": key[2],
                "actor": key[3],
                "identity_scope": "actor_pair" if key[3] is not None else "scene_window_only",
                "candidate_key": pair_key or (key_text((*key[:3], None)) if usable_key else None),
                "scene_key": scene_key_value,
                "role": row.get("role"),
                "task_kind": task_kind(row),
                "status": status,
                "status_class": status_class(status),
                "technical_admitted": row.get("technical_admitted"),
                "technical_pass_recorded": row.get("technical_admitted") is True or row.get("technical_pass") is True,
                "planner_admitted_in_this_row": row.get("research_admitted"),
                "independent_selected_in_this_row": row.get("independent_selected", row.get("corpus_selected")),
                "provenance_state": state,
                "producer_version_id": version_tag,
                "screen_fingerprints": fingerprints,
                "failure_reasons": details,
                "reason_detail_available": bool(details),
            }
            attempts.append(attempt)
            if usable_key:
                target_key = key_text(key)
                record = candidate_map.get(target_key)
                if record is None:
                    record = {
                        "candidate_key": target_key,
                        "recording": key[0],
                        "ego": key[1],
                        "first_frame": key[2],
                        "actor": key[3],
                        "identity_scope": identity_scope(key),
                        "source_catalogs": set(),
                        "task_kinds": set(),
                        "task_families": set(),
                        "roles": set(),
                        "locations": set(),
                        "source_evidence_rows": 0,
                        "qualified_source_evidence_rows": 0,
                    }
                    candidate_map[target_key] = record
                if row.get("location") is not None:
                    record["locations"].add(row["location"])
                if row.get("role"):
                    record["roles"].add(str(row["role"]))
                kind = task_kind(row)
                if kind:
                    record["task_kinds"].add(kind)
                    record["task_families"].add(task_family(kind))

        ledger_summaries.append(
            {
                "ledger": name,
                "path": relpath(path),
                "sha256": actual_sha,
                "attempt_rows": len(rows),
                "distinct_pair_windows": len({window_key(row) for row in rows if actor_value(row) is not None and all(value is not None for value in window_key(row)[:3])}),
                "distinct_scene_windows": len({scene_key(row) for row in rows if all(value is not None for value in scene_key(row))}),
                "status_counts": dict(sorted(statuses.items())),
                "status_class_record_counts": dict(sorted(status_classes.items())),
                "technical_admitted_rows": technical_passes,
                "failure_reason_counts": dict(sorted(ledger_reason_counts.items())),
                "version_groups": [
                    {
                        "provenance_state": state,
                        "version_id": version_id,
                        "attempt_rows": values["rows"],
                        "status_counts": dict(sorted(values["statuses"].items())),
                        "failure_reason_counts": dict(sorted(values.get("failure_reason_counts", {}).items())),
                        "technical_admitted_rows": values["technical_admitted_rows"],
                    }
                    for (state, version_id), values in sorted(per_version.items())
                ],
            }
        )
        inputs.append(input_record(path, "historical_pair_candidate_ledger", rows=len(rows), declared_sha256=ledger_info["sha256"]))

    version_rows = []
    for (_ledger, _state, _version), item in sorted(version_summary.items()):
        version_rows.append(
            {
                **item,
                "status_counts": dict(sorted(item["status_counts"].items())),
                "failure_reason_counts": dict(sorted(item["failure_reason_counts"].items())),
            }
        )
    return attempts, ledger_summaries, {"groups": version_rows}


def add_scene_ledgers(inputs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summaries = []
    rows_out = []
    for name in SCENE_LEDGER_NAMES:
        path, rows = read_named(name)
        if not isinstance(rows, list):
            raise TypeError(f"{path}: expected a list of scene rows")
        protocol_counts = collections.Counter(str(row.get("traffic_protocol", "unknown")) for row in rows)
        conversion = collections.Counter(str(row.get("conversion_pass", "unknown")) for row in rows)
        full_gate_ever = collections.Counter(str(row.get("full_gate_ever_run", "unknown")) for row in rows)
        full_gate_current = collections.Counter(str(row.get("full_gate_current", "unknown")) for row in rows)
        technical = collections.Counter(str(row.get("technical_admitted", "unknown")) for row in rows)
        reasons = collections.Counter(reason for row in rows for reason in row.get("rejection_reasons", []))
        summary = {
            "ledger": name,
            "path": relpath(path),
            "sha256": sha256(path),
            "evidence_scope": "scene_window_only_actor_pair_not_identified",
            "row_count": len(rows),
            "distinct_scene_windows": len({(row.get("recording"), ego_value(row), row.get("first_frame")) for row in rows}),
            "traffic_protocol_counts": dict(sorted(protocol_counts.items())),
            "conversion_pass_counts": dict(sorted(conversion.items())),
            "full_gate_ever_run_counts": dict(sorted(full_gate_ever.items())),
            "full_gate_current_counts": dict(sorted(full_gate_current.items())),
            "technical_admitted_counts": dict(sorted(technical.items())),
            "rejection_reason_counts": dict(sorted(reasons.items())),
            "producer_provenance": "unknown_in_ledger_rows",
        }
        summaries.append(summary)
        inputs.append(input_record(path, "legacy_scene_candidate_ledger", rows=len(rows)))
        for index, row in enumerate(rows):
            rows_out.append(
                {
                    "ledger": name,
                    "ledger_path": relpath(path),
                    "ledger_sha256": summary["sha256"],
                    "row_index": index,
                    "recording": row.get("recording"),
                    "location": row.get("location"),
                    "ego": ego_value(row),
                    "first_frame": row.get("first_frame"),
                    "actor": None,
                    "identity_scope": "scene_window_only",
                    "traffic_protocol": row.get("traffic_protocol"),
                    "conversion_pass": row.get("conversion_pass"),
                    "full_gate_ever_run": row.get("full_gate_ever_run"),
                    "full_gate_current": row.get("full_gate_current"),
                    "technical_admitted": row.get("technical_admitted"),
                    "research_admitted": row.get("research_admitted"),
                    "rejection_reasons": row.get("rejection_reasons", []),
                    "producer_provenance": "unknown_in_ledger_rows",
                }
            )
    return summaries, rows_out


def current_scene_decisions(inputs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selection_path, selection = read_named("step2_expanded_current_selection")
    manifest_path, manifest = read_named("step2_expanded_current_manifest")
    summary_path, current_summary = read_named("step2_expanded_current_summary")
    inputs.extend(
        [
            input_record(selection_path, "current_scene_selection"),
            input_record(manifest_path, "independently_selected_scene_manifest"),
            input_record(summary_path, "current_scene_selection_summary"),
        ]
    )
    selection_rows = selection.get("jobs", [])
    manifest_rows = manifest if isinstance(manifest, list) else manifest.get("scenes", [])
    manifest_by_root = {str(resolve_reference(row["root"])): row for row in manifest_rows}
    manifest_actor_pairs = []
    for selected in manifest_rows:
        scene_root = str(resolve_reference(selected["root"]))
        for actor in selected.get("interaction_actor_ids", []):
            if any(selected.get(field) is None for field in ("recording", "ego_track_id", "first_frame")):
                continue
            manifest_actor_pairs.append(
                {
                    "recording": selected["recording"],
                    "ego": selected["ego_track_id"],
                    "first_frame": selected["first_frame"],
                    "actor": actor,
                    "candidate_key": key_text((selected["recording"], selected["ego_track_id"], selected["first_frame"], actor)),
                    "scene_root": scene_root,
                    "scene_name": selected.get("name"),
                    "claim": "manifest_declared_independent_selected_actor_pair_as_recorded",
                    "manifest_path": relpath(manifest_path),
                    "manifest_sha256": sha256(manifest_path),
                }
            )
    output = []
    for row in selection_rows:
        root = resolve_reference(row["root"])
        technical_path = root / "testing/admission_hybrid_startup.json"
        planner_path = root / "testing/admission_smart_hybrid_startup.json"
        technical = load_json(technical_path) if technical_path.is_file() else {}
        planner = load_json(planner_path) if planner_path.is_file() else {}
        selected_manifest_row = manifest_by_root.get(str(root.resolve()))
        inputs.extend(
            [
                input_record(technical_path, "scene_level_technical_admission", exists=technical_path.is_file()),
                input_record(planner_path, "scene_level_planner_admission", exists=planner_path.is_file()),
            ]
        )
        technical_admitted = technical.get("technical_admitted")
        planner_admitted = planner.get("research_admitted")
        output.append(
            {
                "scene_root": str(root),
                "scene_name": root.name,
                "recording": (technical.get("contract") or {}).get("recording"),
                "ego_track_id": (technical.get("contract") or {}).get("ego_track_id"),
                "first_frame_from_scene_name": root.name.split("_f")[-1] if "_f" in root.name else None,
                "role": row.get("role"),
                "technical_admitted_scene_level_as_recorded": technical_admitted,
                "technical_gate_path": relpath(technical_path),
                "technical_gate_sha256": sha256(technical_path) if technical_path.is_file() else None,
                "planner_admitted_scene_level_as_recorded": planner_admitted,
                "planner_gate_path": relpath(planner_path),
                "planner_gate_sha256": sha256(planner_path) if planner_path.is_file() else None,
                "independent_selected_scene_level_as_recorded": selected_manifest_row is not None,
                "manifest_path": relpath(manifest_path),
                "manifest_interaction_types": (selected_manifest_row or {}).get("interaction_types", []),
                "manifest_interaction_actor_ids": (selected_manifest_row or {}).get("interaction_actor_ids", []),
                "task_pair_join": "not_joined_scene_proof_is_not_task_pair_proof",
                "exclusion_reasons": planner.get("exclusion_reasons", technical.get("exclusion_reasons", [])),
            }
        )
    summary = {
        "selection_scene_rows_as_recorded": len(output),
        "technical_admitted_scene_rows_as_recorded": sum(row["technical_admitted_scene_level_as_recorded"] is True for row in output),
        "planner_admitted_scene_rows_as_recorded": sum(row["planner_admitted_scene_level_as_recorded"] is True for row in output),
        "independent_selected_scene_rows_as_recorded": sum(row["independent_selected_scene_level_as_recorded"] for row in output),
        "manifest_declared_independent_selected_actor_pair_rows_as_recorded": len(manifest_actor_pairs),
        "manifest_declared_independent_selected_actor_pair_memberships": manifest_actor_pairs,
        "selection_summary_source": relpath(summary_path),
        "selection_summary_sha256": sha256(summary_path),
        "declared_summary": current_summary,
        "evidence_scope": "saved_as_recorded_scene_level_only_not_joined_to_actor_paired_source_candidates",
        "live_revalidation": "not performed because saved admission fields are historical claims and code or input hashes may have changed",
    }
    return output, summary


def deferred_keys(flow: dict[str, Any]) -> dict[str, str]:
    deferred = {}
    for selection in flow.get("deferred_source_candidates", []):
        for row in selection.get("candidates", []):
            key = window_key(row)
            if all(value is not None for value in key[:3]) and key[3] is not None:
                deferred[key_text(key)] = f"{selection.get('selection')}: {selection.get('reason')}"
    return deferred


def finalize_candidates(
    candidate_map: dict[str, dict[str, Any]],
    attempts: list[dict[str, Any]],
    flow: dict[str, Any],
    current: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    attempts_by_key: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for attempt in attempts:
        if attempt.get("candidate_key") is not None:
            attempts_by_key[attempt["candidate_key"]].append(attempt)
    deferred = deferred_keys(flow)
    manifest_claims: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for membership in current.get("manifest_declared_independent_selected_actor_pair_memberships", []):
        manifest_claims[membership["candidate_key"]].append(membership)
    rows = []
    for key, item in sorted(candidate_map.items()):
        exact_attempts = attempts_by_key.get(key, [])
        is_deferred = key in deferred
        selected_claims = manifest_claims.get(key, [])
        is_source_positive = item["qualified_source_evidence_rows"] > 0 or any(
            attempt.get("task_kind") for attempt in exact_attempts
        )
        if exact_attempts:
            observed_state = "attempted"
        elif selected_claims:
            observed_state = "manifest_selected_no_exact_pair_gate"
        elif is_deferred:
            observed_state = "deferred_unattempted"
        elif is_source_positive:
            observed_state = "unattempted"
        else:
            observed_state = "source_pair_without_task_evidence"
        statuses = collections.Counter(str(row.get("status") or "unspecified") for row in exact_attempts)
        classes = collections.Counter(row["status_class"] for row in exact_attempts)
        technical_pass_rows = sum(row["technical_pass_recorded"] for row in exact_attempts)
        location_values = sorted(item["locations"], key=lambda v: str(v))
        task_kinds = sorted(item["task_kinds"])
        families = sorted(item["task_families"])
        if len(families) == 1:
            family = families[0]
        elif len(families) > 1:
            family = "multiple_families_preserved"
        elif item["identity_scope"] == "scene_window_only":
            family = "scene_only_unclassified"
        else:
            family = "unclassified"
        stage_flags = []
        if not exact_attempts and not is_deferred and is_source_positive:
            stage_flags.append("unattempted_no_exact_gate_record")
        if is_deferred and not exact_attempts:
            stage_flags.append("explicitly_deferred_unattempted")
        elif is_deferred and exact_attempts:
            stage_flags.append("declared_deferred_then_later_attempted")
        if selected_claims:
            stage_flags.append("manifest_declared_independent_selection_as_recorded")
        if technical_pass_rows:
            stage_flags.append("technical_admitted_recorded")
        if statuses.get("awaiting_manual_review", 0):
            stage_flags.append("awaiting_manual_review")
        if statuses.get("unresolved_semantics_screen", 0):
            stage_flags.append("hard_semantic_exclusion_under_recorded_producer")
        if statuses.get("technical_rejection", 0):
            stage_flags.append("technical_failure_recorded")
        if any(statuses.get(value, 0) for value in ("source_geometry_rejection", "source_ego_boundary_rejection", "unreviewable_source_overlap")):
            stage_flags.append("source_failure_recorded")
        rows.append(
            {
                "candidate_key": key,
                "recording": item["recording"],
                "location_values": location_values,
                "ego": item["ego"],
                "first_frame": item["first_frame"],
                "actor": item["actor"],
                "identity_scope": item["identity_scope"],
                "task_family": family,
                "task_kinds": task_kinds,
                "task_evidence_qualified": is_source_positive,
                "source_catalogs": sorted(item["source_catalogs"]),
                "source_evidence_rows": item["source_evidence_rows"],
                "qualified_source_evidence_rows": item["qualified_source_evidence_rows"],
                "roles": sorted(item["roles"]),
                "observed_state": observed_state,
                "stage_flags_nonexclusive": stage_flags,
                "deferred_reason": deferred.get(key),
                "declared_deferred_in_flow": is_deferred,
                "exact_attempt_rows": len(exact_attempts),
                "attempt_status_counts": dict(sorted(statuses.items())),
                "attempt_status_class_counts": dict(sorted(classes.items())),
                "technical_pass_pair_rows": technical_pass_rows,
                "awaiting_review_pair_rows": sum(row.get("status") == "awaiting_manual_review" for row in exact_attempts),
                "hard_semantic_exclusion_pair_rows": statuses.get("unresolved_semantics_screen", 0),
                "technical_failure_pair_rows": sum(row["status_class"] == "technical_failure" for row in exact_attempts),
                "source_failure_pair_rows": sum(row["status_class"] == "source_failure" for row in exact_attempts),
                "planner_admitted": "not_joined_scene_level_evidence",
                "independent_selected": "see exact manifest_declared_independent_selected_actor_pair_as_recorded field; no other candidate is inferred selected",
                "manifest_declared_independent_selected_actor_pair_as_recorded": bool(selected_claims),
                "manifest_declared_scene_roots": sorted({row["scene_root"] for row in selected_claims}),
                "manifest_membership_claim_scope": "exact recording+ego+first_frame+actor manifest claim; not a technical or planner proof",
            }
        )

    eligible = [row for row in rows if row["task_evidence_qualified"]]
    backlog = collections.Counter(row["observed_state"] for row in eligible)
    eligible_actor = [row for row in eligible if row["identity_scope"] == "actor_pair"]
    declared_deferred = deferred_keys(flow)
    attempted_keys = set(attempts_by_key)
    deferred_later_attempted = set(declared_deferred) & attempted_keys
    family_windows = collections.Counter()
    family_tasks: dict[str, set[tuple[Any, Any, Any]]] = collections.defaultdict(set)
    location_windows: dict[str, set[str]] = collections.defaultdict(set)
    location_tasks: dict[str, set[tuple[Any, Any, Any]]] = collections.defaultdict(set)
    recording_windows: dict[str, set[str]] = collections.defaultdict(set)
    recording_tasks: dict[str, set[tuple[Any, Any, Any]]] = collections.defaultdict(set)
    for row in eligible_actor:
        family_windows[row["task_family"]] += 1
        family_tasks[row["task_family"]].add((row["recording"], row["ego"], row["actor"]))
        for location in row["location_values"]:
            location_key = str(location)
            location_windows[location_key].add(row["candidate_key"])
            location_tasks[location_key].add((row["recording"], row["ego"], row["actor"]))
        recording_key = str(row["recording"])
        recording_windows[recording_key].add(row["candidate_key"])
        recording_tasks[recording_key].add((row["recording"], row["ego"], row["actor"]))
    summary = {
        "candidate_identity_policy": "recording+ego+first_frame+actor where actor is identified; actorless rows remain scene_window_only and are not joined to actor-paired candidates",
        "source_selector_union": {
            "distinct_candidate_window_keys_all_scopes": len(rows),
            "distinct_actor_pair_window_keys": sum(row["identity_scope"] == "actor_pair" for row in rows),
            "distinct_scene_window_only_keys": sum(row["identity_scope"] == "scene_window_only" for row in rows),
            "qualified_task_evidence_candidate_windows": len(eligible),
            "qualified_actor_pair_windows": sum(row["task_evidence_qualified"] and row["identity_scope"] == "actor_pair" for row in rows),
            "qualified_actor_pair_tasks_recording_ego_actor": len({(row["recording"], row["ego"], row["actor"]) for row in eligible if row["actor"] is not None}),
            "qualified_actor_pair_tasks_with_any_unattempted_window": len({(row["recording"], row["ego"], row["actor"]) for row in eligible_actor if row["observed_state"] in ("unattempted", "deferred_unattempted")}),
            "qualified_candidates_by_observed_state": dict(sorted(backlog.items())),
            "conservative_unattempted_backlog_windows": backlog["unattempted"],
            "explicitly_deferred_unattempted_windows": backlog["deferred_unattempted"],
            "declared_deferred_candidate_rows_in_flow_index": sum(len(item.get("candidates", [])) for item in flow.get("deferred_source_candidates", [])),
            "declared_deferred_unique_actor_pair_windows": len(declared_deferred),
            "declared_deferred_windows_with_later_exact_attempt": len(deferred_later_attempted),
            "manifest_declared_independent_selected_actor_pair_windows_as_recorded": sum(bool(row["manifest_declared_independent_selected_actor_pair_as_recorded"]) for row in eligible_actor),
            "manifest_declared_independent_selected_actor_pair_tasks_as_recorded": len({(row["recording"], row["ego"], row["actor"]) for row in eligible_actor if row["manifest_declared_independent_selected_actor_pair_as_recorded"]}),
            "qualified_windows_by_family": dict(sorted(family_windows.items())),
            "qualified_tasks_by_family": {family: len(tasks) for family, tasks in sorted(family_tasks.items())},
            "qualified_windows_by_location": {location: len(keys) for location, keys in sorted(location_windows.items())},
            "qualified_tasks_by_location": {location: len(tasks) for location, tasks in sorted(location_tasks.items())},
            "qualified_windows_by_recording": {recording: len(keys) for recording, keys in sorted(recording_windows.items(), key=lambda item: int(item[0]))},
            "qualified_tasks_by_recording": {recording: len(tasks) for recording, tasks in sorted(recording_tasks.items(), key=lambda item: int(item[0]))},
            "task_level_planner_admission_evidence": "not recorded for these actor-paired candidates; saved planner admissions remain scene-only",
            "scope_note": "This is a bounded count of source-positive windows from the listed selectors that lack an exact actor-paired gate row. It excludes raw window scans, incomplete identities, and scene-only ledgers. These candidates can still be unusable because of known scene or actor overlaps, stale contracts, semantic exclusions, and later gates. It is not an admission or usability count.",
        },
    }
    return rows, summary


def build_task_rows(candidate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in candidate_rows:
        if row["identity_scope"] == "actor_pair" and row["recording"] is not None and row["ego"] is not None and row["actor"] is not None:
            grouped[(row["recording"], row["ego"], row["actor"])].append(row)
    tasks = []
    for key, windows in sorted(grouped.items(), key=lambda item: tuple(str(value) for value in item[0])):
        qualified = [row for row in windows if row["task_evidence_qualified"]]
        attempted = [row for row in qualified if row["exact_attempt_rows"]]
        unattempted = [row for row in qualified if row["observed_state"] == "unattempted"]
        deferred = [row for row in qualified if row["observed_state"] == "deferred_unattempted"]
        statuses = collections.Counter()
        status_windows: dict[str, set[str]] = collections.defaultdict(set)
        for row in windows:
            for status, count in row["attempt_status_counts"].items():
                statuses[status] += int(count)
                if int(count):
                    status_windows[status].add(row["candidate_key"])
        families = sorted({row["task_family"] for row in windows if row["task_family"] != "unclassified"})
        locations = sorted({value for row in windows for value in row["location_values"]}, key=lambda value: str(value))
        catalogs = sorted({catalog for row in windows for catalog in row["source_catalogs"]})
        task_flags = []
        if unattempted:
            task_flags.append("has_unattempted_source_positive_window")
        if deferred:
            task_flags.append("has_explicitly_deferred_window")
        if any(row["declared_deferred_in_flow"] for row in windows):
            task_flags.append("has_window_declared_deferred_in_flow")
        if attempted:
            task_flags.append("has_exact_historical_gate_attempt")
        if any(row["manifest_declared_independent_selected_actor_pair_as_recorded"] for row in windows):
            task_flags.append("manifest_declared_independent_selection_as_recorded")
        for flag in (
            "technical_admitted_recorded",
            "awaiting_manual_review",
            "hard_semantic_exclusion_under_recorded_producer",
            "technical_failure_recorded",
            "source_failure_recorded",
        ):
            if any(flag in row["stage_flags_nonexclusive"] for row in windows):
                task_flags.append(flag)
        tasks.append(
            {
                "task_key": key_text(key),
                "recording": key[0],
                "ego": key[1],
                "actor": key[2],
                "locations": locations,
                "task_families": families,
                "source_catalogs": catalogs,
                "candidate_window_rows_all": len(windows),
                "source_positive_windows": len(qualified),
                "attempted_source_positive_windows": len(attempted),
                "unattempted_source_positive_windows": len(unattempted),
                "explicitly_deferred_unattempted_windows": len(deferred),
                "declared_deferred_windows_in_flow_including_later_attempts": sum(row["declared_deferred_in_flow"] for row in windows),
                "technical_admitted_windows_recorded": len({row["candidate_key"] for row in windows if "technical_admitted_recorded" in row["stage_flags_nonexclusive"]}),
                "manifest_declared_independent_selected_windows": len({row["candidate_key"] for row in windows if row["manifest_declared_independent_selected_actor_pair_as_recorded"]}),
                "manifest_declared_independent_selected_as_recorded": any(row["manifest_declared_independent_selected_actor_pair_as_recorded"] for row in windows),
                "manifest_declared_scene_roots": sorted({root for row in windows for root in row["manifest_declared_scene_roots"]}),
                "awaiting_review_windows": len(status_windows["awaiting_manual_review"]),
                "hard_semantic_exclusion_windows": len(status_windows["unresolved_semantics_screen"]),
                "technical_failure_windows": len(status_windows["technical_rejection"]),
                "source_failure_windows": len(set().union(*(status_windows[name] for name in ("source_geometry_rejection", "source_ego_boundary_rejection", "unreviewable_source_overlap")))),
                "attempt_status_counts_nonexclusive": dict(sorted(statuses.items())),
                "attempt_status_window_counts_nonexclusive": {name: len(keys) for name, keys in sorted(status_windows.items())},
                "task_stage_flags_nonexclusive": task_flags,
                "planner_admission_evidence": "no task-level planner admission attached; scene-level evidence kept separate",
                "candidate_window_keys": [row["candidate_key"] for row in windows],
            }
        )
    return tasks


def third_family_funnel(
    source_catalogs: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    selector_name = "third_family_event_fine_selection_v1"
    selector = next(item for item in source_catalogs if item["catalog"] == selector_name)
    windows = [row for row in candidate_rows if selector_name in row["source_catalogs"]]
    task_rows_for_family = build_task_rows(windows)
    by_state = collections.Counter(row["observed_state"] for row in windows if row["task_evidence_qualified"])
    status_window_counts: dict[str, int] = collections.defaultdict(int)
    status_record_counts: collections.Counter[str] = collections.Counter()
    for row in windows:
        for status, count in row["attempt_status_counts"].items():
            if int(count) > 0:
                status_window_counts[status] += 1
                status_record_counts[status] += int(count)
    stage_window_counts = {
        "technical_admitted_recorded": sum("technical_admitted_recorded" in row["stage_flags_nonexclusive"] for row in windows),
        "manifest_declared_independent_selected_as_recorded": sum(row["manifest_declared_independent_selected_actor_pair_as_recorded"] for row in windows),
        "awaiting_manual_review": sum("awaiting_manual_review" in row["stage_flags_nonexclusive"] for row in windows),
        "hard_semantic_exclusion_under_recorded_producer": sum("hard_semantic_exclusion_under_recorded_producer" in row["stage_flags_nonexclusive"] for row in windows),
        "technical_failure_recorded": sum("technical_failure_recorded" in row["stage_flags_nonexclusive"] for row in windows),
        "source_failure_recorded": sum("source_failure_recorded" in row["stage_flags_nonexclusive"] for row in windows),
    }
    status_tasks = {}
    for status in sorted(status_window_counts):
        status_tasks[status] = sum(
            any(status in window["attempt_status_counts"] for window in windows if window["candidate_key"] in task["candidate_window_keys"])
            for task in task_rows_for_family
        )
    tasks_with_attempt = sum(row["attempted_source_positive_windows"] > 0 for row in task_rows_for_family)
    result = {
        "catalog": selector_name,
        "path": selector["path"],
        "sha256": selector["sha256"],
        "source_positive_windows": selector["rows"],
        "unique_actor_pair_windows": selector["unique_windows_recording_ego_frame_actor"],
        "source_positive_actor_pair_tasks": selector["unique_actor_pair_tasks_recording_ego_actor"],
        "windows_by_observed_state": dict(sorted(by_state.items())),
        "tasks_with_any_matching_gate_attempt": tasks_with_attempt,
        "tasks_with_no_matching_gate_attempt": len(task_rows_for_family) - tasks_with_attempt,
        "tasks_with_any_unattempted_window": sum(row["unattempted_source_positive_windows"] + row["explicitly_deferred_unattempted_windows"] > 0 for row in task_rows_for_family),
        "tasks_with_any_explicitly_deferred_window": sum(row["explicitly_deferred_unattempted_windows"] > 0 for row in task_rows_for_family),
        "tasks_with_any_declared_deferred_window_including_later_attempts": sum(row["declared_deferred_windows_in_flow_including_later_attempts"] > 0 for row in task_rows_for_family),
        "manifest_declared_independent_selected_actor_pair_windows_as_recorded": sum(row["manifest_declared_independent_selected_actor_pair_as_recorded"] for row in windows),
        "manifest_declared_independent_selected_actor_pair_tasks_as_recorded": sum(row["manifest_declared_independent_selected_as_recorded"] for row in task_rows_for_family),
        "windows_by_nonexclusive_gate_stage": stage_window_counts,
        "attempt_rows_by_exact_status_for_these_windows": dict(sorted(status_record_counts.items())),
        "windows_with_exact_status": dict(sorted(status_window_counts.items())),
        "tasks_with_exact_status": status_tasks,
        "task_level_planner_admission_evidence": "not joined; saved planner admissions remain scene-level",
        "counting_note": "The five-frame selector rows are source-positive windows, not distinct admissions. Exact actor-pair attempts are linked by recording + ego + first_frame + actor. Status/stage counts are nonexclusive across windows and attempts.",
    }
    return result, windows, task_rows_for_family


def summarize_stage_counts(attempts: list[dict[str, Any]], scene_summaries: list[dict[str, Any]], current: dict[str, Any]) -> dict[str, Any]:
    status_rows = collections.Counter(row["status_class"] for row in attempts)
    status_values = collections.Counter(str(row.get("status") or "unspecified") for row in attempts)
    pair_rows = [row for row in attempts if row["identity_scope"] == "actor_pair"]
    scene_rows = [row for row in attempts if row["identity_scope"] == "scene_window_only"]
    return {
        "historical_pair_or_scene_gate_attempt_rows": len(attempts),
        "historical_attempt_rows_by_identity_scope": {"actor_pair": len(pair_rows), "scene_window_only": len(scene_rows)},
        "historical_attempt_rows_by_status_class_descriptive_only": dict(sorted(status_rows.items())),
        "historical_attempt_rows_by_status_descriptive_only": dict(sorted(status_values.items())),
        "historical_pair_technical_admitted_rows_as_recorded": sum(row["technical_pass_recorded"] and row["identity_scope"] == "actor_pair" for row in attempts),
        "historical_pair_unique_windows_technical_admitted_as_recorded": len({row["candidate_key"] for row in attempts if row["technical_pass_recorded"] and row["identity_scope"] == "actor_pair"}),
        "historical_scene_technical_admitted_rows_not_task_joined_as_recorded": sum(row["technical_pass_recorded"] and row["identity_scope"] == "scene_window_only" for row in attempts),
        "historical_pair_awaiting_review_rows": sum(row["status"] == "awaiting_manual_review" and row["identity_scope"] == "actor_pair" for row in attempts),
        "historical_pair_hard_semantic_exclusion_rows": sum(row["status"] == "unresolved_semantics_screen" and row["identity_scope"] == "actor_pair" for row in attempts),
        "historical_pair_technical_failure_rows": sum(row["status_class"] == "technical_failure" and row["identity_scope"] == "actor_pair" for row in attempts),
        "historical_pair_source_failure_rows": sum(row["status_class"] == "source_failure" and row["identity_scope"] == "actor_pair" for row in attempts),
        "legacy_scene_ledger_rows": sum(item["row_count"] for item in scene_summaries),
        "current_scene_decision_counts": {
            key: current[key]
            for key in (
                "selection_scene_rows_as_recorded",
                "technical_admitted_scene_rows_as_recorded",
                "planner_admitted_scene_rows_as_recorded",
                "independent_selected_scene_rows_as_recorded",
                "manifest_declared_independent_selected_actor_pair_rows_as_recorded",
            )
        },
        "counting_warning": "Historical attempts repeat candidate identities across gate stages and producer versions. Counts are records or explicitly deduplicated identities; no pooled admission rate is computed. unresolved_semantics_screen is a hard semantic exclusion under that recorded producer, not an unattempted candidate or a generic missing-evidence label.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    third = next(item for item in report["source_catalogs"] if item["catalog"] == "third_family_event_fine_selection_v1")
    candidate = report["candidate_universe"]
    stages = report["stage_counts"]
    backlog = candidate["source_selector_union"]
    third_window_location = third["qualified_unique_windows_by_family_location_recording"]
    third_task_location = third["qualified_unique_actor_tasks_by_family_location_recording"]
    family_rows = [
        (family, backlog["qualified_windows_by_family"].get(family, 0), backlog["qualified_tasks_by_family"].get(family, 0))
        for family in ("cyclist_crossing", "pedestrian_crossing", "vehicle_response")
    ]
    lines = [
        "# Task/window candidate funnel census",
        "",
        "Generated from retained source selectors, gate ledgers, and current scene decisions. Counts preserve recording + ego + frame + actor identities when available. Scene-only evidence remains scene-only.",
        "",
        "## Source selectors",
        "",
        f"- Third-family event-fine selector: {third['rows']:,} rows, {third['unique_actor_pair_tasks_recording_ego_actor']:,} actor-pair tasks, {third['sha256']}.",
        f"- For that 4,982 / 394 cohort, {report['third_family_funnel']['windows_by_observed_state'].get('attempted', 0):,} windows have an exact retained gate attempt, {report['third_family_funnel']['windows_by_observed_state'].get('unattempted', 0):,} have no matching gate row, and {report['third_family_funnel']['windows_by_observed_state'].get('deferred_unattempted', 0):,} remain explicitly deferred. {report['third_family_funnel']['tasks_with_any_matching_gate_attempt']:,} tasks have an exact gate attempt; {report['third_family_funnel']['tasks_with_any_unattempted_window']:,} retain at least one unattempted window. Exact manifest actor-pair membership is reported as a separate as-recorded claim.",
        f"- Across the parsed selector snapshots: {backlog['qualified_task_evidence_candidate_windows']:,} distinct task-evidence-qualified windows, {backlog['qualified_actor_pair_tasks_recording_ego_actor']:,} actor-pair tasks. Selector revisions overlap and are deduplicated by the four-part identity.",
        f"- Bounded unattempted backlog: {backlog['conservative_unattempted_backlog_windows']:,} exact-identity qualified windows have no matching retained gate row or exact manifest selection claim. The flow index declared {backlog['declared_deferred_unique_actor_pair_windows']:,} deferred windows. {backlog['declared_deferred_windows_with_later_exact_attempt']:,} later received an exact gate attempt and {backlog['explicitly_deferred_unattempted_windows']:,} remain deferred and unattempted.",
        f"- The task table has {report['task_rows']['actor_pair_source_positive_task_count']:,} source-positive tasks. {report['task_rows']['source_positive_tasks_with_any_exact_gate_attempt']:,} have an exact attempt, and {report['task_rows']['source_positive_tasks_with_any_unattempted_window']:,} have an unattempted window. These task stages overlap across alternate windows.",
        "- Source-positive candidate windows remain candidates. The backlog can contain scene or actor overlaps, stale contracts, and candidates that fail later gates.",
        "- Raw exhaustive ego-window and map-preflight files are inventoried by file and SHA. They do not contribute actor-paired task counts or backlog.",
        "",
        "| Family in the combined selector union | Source-positive windows | Actor-pair tasks |",
        "| --- | ---: | ---: |",
        *[f"| {family} | {windows:,} | {tasks:,} |" for family, windows, tasks in family_rows],
        "",
        "Third-family event-fine selector by location",
        "",
        "| Location | Windows | Tasks |",
        "| --- | ---: | ---: |",
        *[
            f"| {location} | {third_window_location.get(f'location:{location}', 0):,} | {third_task_location.get(f'location:{location}', 0):,} |"
            for location in (1, 2, 3, 4)
        ],
        "",
        "## Gate evidence",
        "",
        f"- Historical gate ledger records: {stages['historical_pair_or_scene_gate_attempt_rows']:,} retained rows. These include repeated windows, gate stages, and producer versions.",
        f"- Actor-paired technical-admitted rows: {stages['historical_pair_technical_admitted_rows_as_recorded']:,} across {stages['historical_pair_unique_windows_technical_admitted_as_recorded']:,} distinct windows. Awaiting-review rows: {stages['historical_pair_awaiting_review_rows']:,}. The {stages['historical_pair_hard_semantic_exclusion_rows']:,} `unresolved_semantics_screen` rows are hard semantic exclusions under their recorded producer. Source failures: {stages['historical_pair_source_failure_rows']:,}; technical failures: {stages['historical_pair_technical_failure_rows']:,}.",
        f"- Saved scene-level decisions: {stages['current_scene_decision_counts']['selection_scene_rows_as_recorded']} candidates, {stages['current_scene_decision_counts']['technical_admitted_scene_rows_as_recorded']} technical admissions, {stages['current_scene_decision_counts']['planner_admitted_scene_rows_as_recorded']} planner/research admissions, and {stages['current_scene_decision_counts']['independent_selected_scene_rows_as_recorded']} independently selected scenes, all as recorded in saved gates and manifests.",
        f"- Frozen manifest actor IDs explicitly claim {stages['current_scene_decision_counts']['manifest_declared_independent_selected_actor_pair_rows_as_recorded']} selected actor-pair memberships. The generator joins only exact recording + ego + frame + actor matches and labels these as manifest claims. It does not infer selection for other actors or phases, and it does not use these claims as technical or planner proof.",
        "- Saved scene gate fields are historical values. The generator does not revalidate them against changed code or inputs. A review after later viewer changes found a `tool_artifacts.py` hash mismatch in seven saved hybrid technical contracts. Historical producer provenance is reported separately. Unknown version rows remain in their own groups.",
        "",
        "## Reproduction and detailed outputs",
        "",
        "Run `PYTHONPATH=src python -m geotransfer_gap.corpus.report_task_window_funnel` from the repository root. The generator verifies the 4,982-window / 394-task third-family source count and writes the full JSON, CSV tables, and generated Markdown under `artifacts/audits/task_window_funnel/`.",
        "",
        "`census.json` records every input path and SHA256. `candidate_windows.csv` retains selector origins and exact attempt status history. `tasks.csv` gives one row per recording + ego + actor. `attempts.csv` preserves gate stage and producer fingerprints. `current_scene_decisions.csv` and `legacy_scene_ledgers.csv` remain scene-scoped.",
        "",
        "No pooled admission rate is reported. Attempt counts are descriptive records, not independent trials.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    inputs: list[dict[str, Any]] = []
    flow_path, flow = read_named("step2_candidate_flow")
    inputs.append(input_record(flow_path, "historical_flow_index_and_explicit_deferred_candidates"))

    source_catalogs, candidate_map, raw_catalogs = build_catalogs(inputs)
    attempts, ledger_summaries, versions = add_attempts(inputs, flow, candidate_map)
    scene_summaries, scene_ledger_rows = add_scene_ledgers(inputs)
    current_rows, current_summary = current_scene_decisions(inputs)
    candidate_rows, candidate_summary = finalize_candidates(candidate_map, attempts, flow, current_summary)
    task_rows = build_task_rows(candidate_rows)
    third_funnel, third_windows, third_tasks = third_family_funnel(source_catalogs, candidate_rows)
    candidate_key_set = {row["candidate_key"] for row in candidate_rows}
    manifest_pair_keys = [row["candidate_key"] for row in current_summary["manifest_declared_independent_selected_actor_pair_memberships"]]
    candidate_summary["manifest_membership_reconciliation"] = {
        "manifest_declared_actor_pair_membership_rows": len(manifest_pair_keys),
        "exact_actor_pair_memberships_matching_catalog_or_attempt_candidate": sum(key in candidate_key_set for key in manifest_pair_keys),
        "manifest_declared_actor_pair_memberships_without_matching_candidate_row": sum(key not in candidate_key_set for key in manifest_pair_keys),
        "matching_policy": "recording + ego_track_id + first_frame + actor_id exact match only",
        "scope": "manifest-declared independent selection claim, not technical or planner proof",
    }
    stages = summarize_stage_counts(attempts, scene_summaries, current_summary)

    # This number is a fixed source-catalog fact for the event-centred refinement.
    third = next(item for item in source_catalogs if item["catalog"] == "third_family_event_fine_selection_v1")
    if third["rows"] != 4982 or third["unique_actor_pair_tasks_recording_ego_actor"] != 394:
        raise ValueError(
            "Expected the third-family event-fine selector to contain 4,982 windows / 394 tasks, "
            f"found {third['rows']} / {third['unique_actor_pair_tasks_recording_ego_actor']}"
        )

    report = {
        "schema_version": 1,
        "generator": relpath(Path(__file__)),
        "generator_sha256": sha256(Path(__file__)),
        "counting_policy": {
            "actor_pair_window_key": ["recording", "ego", "first_frame", "actor"],
            "actor_pair_task_key": ["recording", "ego", "actor"],
            "scene_only_key": ["recording", "ego", "first_frame"],
            "scene_only_evidence_is_never_joined_to_actor_pair": True,
            "selector_snapshots_deduplicated_by_exact_key_for_combined_candidate_table": True,
            "historical_attempts_counted_as_retained_rows_and_not_pooled_as_admission_rate": True,
            "unknown_or_partial_producer_fingerprints_retained_separately": True,
        },
        "inputs": sorted(inputs, key=lambda row: (row["role"], row["path"])),
        "source_catalogs": source_catalogs,
        "raw_catalog_inventory": raw_catalogs,
        "historical_gate_ledgers": ledger_summaries,
        "producer_version_groups": versions["groups"],
        "legacy_scene_ledgers": scene_summaries,
        "candidate_universe": candidate_summary,
        "task_rows": {
            "actor_pair_task_count_all_catalogued_and_attempted_pairs": len(task_rows),
            "actor_pair_source_positive_task_count": candidate_summary["source_selector_union"]["qualified_actor_pair_tasks_recording_ego_actor"],
            "source_positive_tasks_with_any_exact_gate_attempt": sum(int(row["attempted_source_positive_windows"]) > 0 for row in task_rows if int(row["source_positive_windows"]) > 0),
            "source_positive_tasks_with_no_exact_gate_attempt": sum(int(row["attempted_source_positive_windows"]) == 0 for row in task_rows if int(row["source_positive_windows"]) > 0),
            "source_positive_tasks_with_any_unattempted_window": sum(int(row["unattempted_source_positive_windows"]) > 0 or int(row["explicitly_deferred_unattempted_windows"]) > 0 for row in task_rows if int(row["source_positive_windows"]) > 0),
            "source_positive_tasks_with_hard_semantic_exclusion": sum(int(row["hard_semantic_exclusion_windows"]) > 0 for row in task_rows if int(row["source_positive_windows"]) > 0),
            "source_positive_tasks_with_technical_admission_recorded": sum(int(row["technical_admitted_windows_recorded"]) > 0 for row in task_rows if int(row["source_positive_windows"]) > 0),
            "source_positive_tasks_with_manifest_selection_as_recorded": sum(bool(row["manifest_declared_independent_selected_as_recorded"]) for row in task_rows if int(row["source_positive_windows"]) > 0),
            "tasks_with_any_unattempted_source_positive_window": sum(int(row["unattempted_source_positive_windows"]) > 0 or int(row["explicitly_deferred_unattempted_windows"]) > 0 for row in task_rows),
            "tasks_with_hard_semantic_exclusion": sum(int(row["hard_semantic_exclusion_windows"]) > 0 for row in task_rows),
            "tasks_with_technical_admission_recorded": sum(int(row["technical_admitted_windows_recorded"]) > 0 for row in task_rows),
            "task_level_planner_admission_evidence": "not attached; planner admissions are scene-level only",
        },
        "third_family_funnel": third_funnel,
        "current_scene_decisions": current_summary,
        "stage_counts": stages,
        "known_schema_limits": [
            "Raw exhaustive ego-window and map-preflight catalogs do not identify a qualified actor-paired task and are inventory-only.",
            "The two legacy 1,030-row candidate ledgers are scene-window records without an actor-paired task identity and have no per-row producer fingerprints.",
            "Current technical/planner admissions and independent selection are saved scene-level composites. They are not live-revalidated or assigned to actor-paired source candidates.",
            "The backlog includes source-positive rows that may still fail because of known scene or actor overlap, stale contracts, or later gates. It is not a usability or admission count.",
            "Historical ledger rows are repeated across stages and versions. Row counts describe retained records and are not independent sample counts.",
        ],
    }

    write_json(OUTPUT / "census.json", report)
    write_csv(
        OUTPUT / "catalogs.csv",
        list(source_catalogs[0].keys()),
        source_catalogs,
    )
    write_csv(
        OUTPUT / "candidate_windows.csv",
        list(candidate_rows[0].keys()) if candidate_rows else [],
        candidate_rows,
    )
    write_csv(OUTPUT / "tasks.csv", list(task_rows[0].keys()) if task_rows else [], task_rows)
    write_csv(OUTPUT / "third_family_windows.csv", list(third_windows[0].keys()) if third_windows else [], third_windows)
    write_csv(OUTPUT / "third_family_tasks.csv", list(third_tasks[0].keys()) if third_tasks else [], third_tasks)
    write_csv(OUTPUT / "attempts.csv", list(attempts[0].keys()) if attempts else [], attempts)
    write_csv(OUTPUT / "legacy_scene_ledgers.csv", list(scene_ledger_rows[0].keys()) if scene_ledger_rows else [], scene_ledger_rows)
    write_csv(OUTPUT / "current_scene_decisions.csv", list(current_rows[0].keys()) if current_rows else [], current_rows)
    manifest_pairs = current_summary["manifest_declared_independent_selected_actor_pair_memberships"]
    write_csv(OUTPUT / "manifest_actor_pair_memberships.csv", list(manifest_pairs[0].keys()) if manifest_pairs else [], manifest_pairs)
    compact_version_rows = []
    for index, group in enumerate(versions["groups"]):
        compact = {key: value for key, value in group.items() if key != "failure_reason_counts"}
        reason_counts = group.get("failure_reason_counts", {})
        compact["failure_reason_entry_count"] = sum(reason_counts.values())
        compact["failure_reason_unique_labels"] = len(reason_counts)
        compact["failure_reason_detail_ref"] = f"census.json#/producer_version_groups/{index}/failure_reason_counts"
        compact_version_rows.append(compact)
    write_csv(
        OUTPUT / "producer_versions.csv",
        list(compact_version_rows[0].keys()) if compact_version_rows else [],
        compact_version_rows,
    )
    markdown = render_markdown(report)
    (OUTPUT / "report.md").write_text(markdown)
    print(
        json.dumps(
            {
                "output": relpath(OUTPUT),
                "third_family_windows": third["rows"],
                "third_family_tasks": third["unique_actor_pair_tasks_recording_ego_actor"],
                "third_family_attempted_windows": third_funnel["windows_by_observed_state"].get("attempted", 0),
                "third_family_unattempted_windows": third_funnel["windows_by_observed_state"].get("unattempted", 0),
                "third_family_deferred_windows": third_funnel["windows_by_observed_state"].get("deferred_unattempted", 0),
                "selector_union_qualified_windows": candidate_summary["source_selector_union"]["qualified_task_evidence_candidate_windows"],
                "selector_union_qualified_actor_pair_tasks": candidate_summary["source_selector_union"]["qualified_actor_pair_tasks_recording_ego_actor"],
                "conservative_unattempted_windows": candidate_summary["source_selector_union"]["conservative_unattempted_backlog_windows"],
                "explicit_deferred_windows": candidate_summary["source_selector_union"]["explicitly_deferred_unattempted_windows"],
                "historical_attempt_rows": len(attempts),
                "pair_technical_admitted_rows_as_recorded": stages["historical_pair_technical_admitted_rows_as_recorded"],
                "pair_technical_admitted_unique_windows_as_recorded": stages["historical_pair_unique_windows_technical_admitted_as_recorded"],
                "scene_planner_admitted_as_recorded": current_summary["planner_admitted_scene_rows_as_recorded"],
                "independent_scenes_as_recorded": current_summary["independent_selected_scene_rows_as_recorded"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
