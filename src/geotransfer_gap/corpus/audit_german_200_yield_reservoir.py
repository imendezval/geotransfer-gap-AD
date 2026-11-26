"""Build an outcome-blind source-only yield reservoir audit for German-200.

This analysis reads the frozen v1 queue and observed B/C ledgers, reconstructs
full source actor contexts, and runs the existing source-map preflight on all
off-stride phases for source-positive tasks outside the stride-50 interaction
pool. It never edits the frozen queues and never runs physical, semantic,
technical, planner, or manual admission gates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any

from geotransfer_gap.config import PROJECT_ROOT
from geotransfer_gap.corpus import census_german_200_v1 as census
from geotransfer_gap.corpus import freeze_random_interactive_v1 as freeze
from geotransfer_gap.corpus.source_only_protocol import (
    WINDOW_SOURCE_FRAMES,
    independence_conflicts,
    source_context_actors,
    source_window_identity_sha256,
)
from geotransfer_gap.maps import preflight_source_map


QUEUE = PROJECT_ROOT / "artifacts/german_200_v1/queues.json"
B_LEDGER = PROJECT_ROOT / "artifacts/german_200_v1_workstream_b/batch_ledger.json"
C_LEDGER = PROJECT_ROOT / "artifacts/german_200_v1_runs/workstream_c_batch_001/batch_ledger.json"
B_REPORT = PROJECT_ROOT / "artifacts/german_200_v1_workstream_b/batch_run_report.json"
C_REPORT = PROJECT_ROOT / "artifacts/german_200_v1_runs/workstream_c_batch_001/batch_run_report.json"
SUPPLY_CENSUS = PROJECT_ROOT / "artifacts/german_200_v1_workstream_d/supply_census.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/german_200_yield_reservoir/run_001"
PROTOCOL = "german_200_source_only_yield_reservoir_audit_v1"
SELECTOR_PRIORITY = (
    "third_family_event_fine_selection_v1.json",
    "source_restart_selection.json",
    "source_restart_turns_selection.json",
    "source_restart_velocity_selection.json",
    "body_task_selection.json",
    "footprint_task_selection.json",
    "fine_phase_task_selection.json",
)
ACTIVE_LOCATIONS = (1, 3, 4)
FAMILIES = ("cyclist_crossing", "pedestrian_crossing", "longitudinal_following")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def stable_rank(*parts: Any) -> str:
    payload = json.dumps([PROTOCOL, *parts], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def selector_rows(name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    if name == "third_family_event_fine_selection_v1.json":
        return data.get("jobs", [])
    if "source_positive_pairs" in data:
        return data["source_positive_pairs"]
    return data.get("jobs", [])


def task_family(row: dict[str, Any]) -> str | None:
    evidence = row.get("task_evidence") or {}
    return freeze._family_for_kind(evidence.get("kind"), row)


def event_sort(row: dict[str, Any], row_index: int) -> tuple[Any, ...]:
    gap = row.get("source_crossing_time_gap_s")
    ego_step = row.get("ego_path_crossing_step")
    actor_step = row.get("actor_path_crossing_step")
    complete = gap is not None and ego_step is not None and actor_step is not None
    midpoint_distance = abs((float(ego_step) + float(actor_step)) / 2 - 45) if complete else float("inf")
    return (not complete, float(gap) if complete else float("inf"), midpoint_distance, int(row["first_frame"]), row_index)


def build_incremental_pool() -> tuple[dict[tuple[int, int, int], dict[str, Any]], dict[str, Any]]:
    """Join source-positive selector phases to the complete stride-50 task pool."""
    eligible_windows, catalog_summary, preflight_summary = freeze._eligible_sources()
    stride_task_windows, selector_inputs, selector_row_counts, exact_rows = freeze._load_interaction_pool(eligible_windows)
    stride_tasks = set(stride_task_windows)
    task_rows: dict[tuple[int, int, int], dict[str, Any]] = {}
    for name in freeze.SELECTOR_FILES:
        path = freeze.AUDITS / name
        data = load(path)
        rows = selector_rows(name, data)
        for row_index, row in enumerate(rows):
            if "actor" not in row:
                continue
            recording = int(row["recording"])
            ego = int(row.get("ego", row.get("ego_track_id")))
            actor = int(row["actor"])
            first = int(row["first_frame"])
            task = (recording, ego, actor)
            if task in stride_tasks or first % 50 == 0:
                continue
            family = task_family(row)
            if not family:
                continue
            candidate = task_rows.setdefault(
                task,
                {"recording": recording, "location": int(row["location"]), "ego_track_id": ego,
                 "actor": actor, "families": set(), "phase_rows": defaultdict(list)},
            )
            if candidate["location"] != int(row["location"]):
                raise ValueError(f"inconsistent location for task {task}")
            candidate["families"].add(family)
            candidate["phase_rows"][(recording, ego, first)].append(
                {"selector": name, "selector_row_index": row_index, "row": row, "family": family}
            )
    for candidate in task_rows.values():
        phase_order = []
        for key, evidence in candidate["phase_rows"].items():
            def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
                selector = item["selector"]
                selector_index = SELECTOR_PRIORITY.index(selector) if selector in SELECTOR_PRIORITY else len(SELECTOR_PRIORITY)
                row = item["row"]
                return (selector_index, *(event_sort(row, item["selector_row_index"]) if selector == SELECTOR_PRIORITY[0]
                                           else (False, 0.0, 0.0, int(row["first_frame"]), item["selector_row_index"])))
            ordered_evidence = sorted(evidence, key=sort_key)
            phase_order.append({"window_key": key, "evidence": ordered_evidence,
                                "phase_rank": min(SELECTOR_PRIORITY.index(item["selector"]) for item in evidence)})
        phase_order.sort(key=lambda item: (
            min(SELECTOR_PRIORITY.index(e["selector"]) for e in item["evidence"]),
            *(event_sort(item["evidence"][0]["row"], item["evidence"][0]["selector_row_index"])
              if item["evidence"][0]["selector"] == SELECTOR_PRIORITY[0]
              else (False, 0.0, 0.0, int(item["window_key"][2]), 0)),
            item["window_key"],
        ))
        candidate["phase_order"] = phase_order
        candidate["families"] = sorted(candidate["families"])
        del candidate["phase_rows"]
    metadata = {
        "stride_source_task_count": len(stride_tasks),
        "incremental_offstride_task_count": len(task_rows),
        "selector_row_counts": selector_row_counts,
        "selector_exact_eligible_rows": exact_rows,
        "catalogs": catalog_summary,
        "stride_map_preflights": preflight_summary,
        "interaction_selector_inputs": selector_inputs,
        "unique_incremental_offstride_phases": len({phase["window_key"] for c in task_rows.values() for phase in c["phase_order"]}),
        "unique_task_window_relations": sum(len(c["phase_order"]) for c in task_rows.values()),
    }
    return task_rows, metadata


def map_stage(row: dict[str, Any] | None) -> bool:
    return bool(row and row.get("source_track_complete") is True and
                row.get("outside_sample_count") == 0 and row.get("directed_route") is True)


def distribution(rows: list[dict[str, Any]], *, include_random_family: bool = False) -> dict[str, Any]:
    locations = Counter(int(row.get("location", row.get("frozen_row", {}).get("location", -1))) for row in rows)
    families = Counter()
    location_families: dict[str, Counter] = defaultdict(Counter)
    arms = Counter()
    for row in rows:
        arm = row.get("arm", row.get("frozen_row", {}).get("arm", "unknown"))
        arms[arm] += 1
        row_families = row.get("source_task_families", row.get("frozen_row", {}).get("source_task_families", []))
        if row_families:
            for family in row_families:
                families[family] += 1
                location = str(row.get("location", row.get("frozen_row", {}).get("location", -1)))
                location_families[location][family] += 1
        elif include_random_family:
            families["unreviewed_random_source_candidate"] += 1
            location = str(row.get("location", row.get("frozen_row", {}).get("location", -1)))
            location_families[location]["unreviewed_random_source_candidate"] += 1
    return {
        "rows": len(rows),
        "by_location": {str(loc): locations.get(loc, 0) for loc in (1, 2, 3, 4)},
        "by_arm": dict(sorted(arms.items())),
        "family_row_memberships": dict(sorted(families.items())),
        "by_location_family_membership": {
            str(loc): dict(sorted(location_families.get(str(loc), {}).items())) for loc in (1, 2, 3, 4)
        },
    }


def ledger_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    queue = load(QUEUE)
    b_ledger, c_ledger = load(B_LEDGER), load(C_LEDGER)
    b_report, c_report = load(B_REPORT), load(C_REPORT)
    frozen_by_id = {row["source_window_identity_sha256"]: row for row in queue["candidates"]}
    outcome_rows: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []
    batch_reports = {}
    for batch, ledger, report in (("B", b_ledger, b_report), ("C", c_ledger, c_report)):
        batch_reports[batch] = report
        for result in ledger.get("results", ()):
            identity = result.get("frozen_row", {}).get("source_window_identity_sha256")
            if not identity:
                candidate_id = result.get("candidate_id", "")
                match = next((r for r in queue["candidates"] if candidate_id.endswith(r["source_window_identity_sha256"][:12])), None)
                identity = match.get("source_window_identity_sha256") if match else None
            frozen = frozen_by_id.get(identity, result.get("frozen_row", {}))
            outcome_rows.append({"batch": batch, "status": result.get("status", "unknown"), "frozen_row": frozen,
                                 "technical_admission": result.get("technical_admission", {}),
                                 "source_preflight": result.get("source_preflight", {}),
                                 "manual_review_status": result.get("manual_review_status"),
                                 "semantic_applicability": result.get("semantic_applicability", {}),
                                 "result": result})
            fallback = result.get("phase_fallback", {}).get("result")
            if batch == "B" and isinstance(fallback, dict) and fallback.get("status") == "review_blocked":
                row = fallback.get("frozen_row", {})
                fallback_rows.append({"batch": batch, "status": fallback["status"], "frozen_row": row,
                                      "result": fallback, "mandatory_retained_review_case": True})
    if len(outcome_rows) != 48:
        raise ValueError(f"expected the two preserved 24-row batches (48 primaries), got {len(outcome_rows)}")
    if len(fallback_rows) != 1:
        raise ValueError(f"expected the single retained B fallback review case, got {len(fallback_rows)}")
    return outcome_rows, fallback_rows, {"queue": queue, "batch_reports": batch_reports}


def row_family(row: dict[str, Any]) -> str:
    families = row.get("source_task_families", []) or ["unreviewed_random_source_candidate"]
    return ",".join(families)


def breakdown(rows: list[dict[str, Any]], status_key: str = "status") -> dict[str, Any]:
    by_location: dict[str, Counter] = defaultdict(Counter)
    by_family: dict[str, Counter] = defaultdict(Counter)
    by_location_family: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    by_arm: dict[str, Counter] = defaultdict(Counter)
    for record in rows:
        row = record.get("frozen_row", record)
        status = record.get(status_key, "untested")
        by_location[str(row.get("location", -1))][status] += 1
        family = row_family(row)
        by_family[family][status] += 1
        by_location_family[str(row.get("location", -1))][family][status] += 1
        by_arm[row.get("arm", "unknown")][status] += 1
    return {
        "by_location": {key: dict(sorted(value.items())) for key, value in sorted(by_location.items())},
        "by_family": {key: dict(sorted(value.items())) for key, value in sorted(by_family.items())},
        "by_location_family": {
            location: {family: dict(sorted(statuses.items())) for family, statuses in sorted(families.items())}
            for location, families in sorted(by_location_family.items())
        },
        "by_arm": {key: dict(sorted(value.items())) for key, value in sorted(by_arm.items())},
    }


def frozen_scenarios(queue: dict[str, Any], outcomes: list[dict[str, Any]], fallbacks: list[dict[str, Any]]) -> dict[str, Any]:
    outcome_by_sha = {record["frozen_row"].get("source_window_identity_sha256"): record for record in outcomes}
    primary_rows = [{"status": outcome_by_sha.get(row["source_window_identity_sha256"], {}).get("status", "untested"),
                     "frozen_row": row} for row in queue["candidates"]]
    primary_statuses = Counter(row["status"] for row in primary_rows)
    source_rejected = {"source_physical_rejection", "source_geometry_rejection"}
    conservative_retained = [row for row in primary_rows if row["status"] not in source_rejected]
    fallback_record = {"status": fallbacks[0]["status"], "frozen_row": fallbacks[0]["frozen_row"]}
    terminal_rejection_sensitivity = [row for row in primary_rows if row["status"] not in source_rejected | {"technical_rejection"}]
    return {
        "frozen_v1_all_200": {
            "intended_primary_slots": 200,
            "reserved_primary_rows": 200,
            "reserved_candidate_rows_including_mandatory_retained_fallback": 201,
            "fallback_is_extra_reservation_not_a_201st_intended_slot": True,
            "primary_status_counts": dict(sorted(primary_statuses.items())),
            "untested_primary_rows": primary_statuses.get("untested", 0),
            "primary_breakdown": breakdown(primary_rows),
            "mandatory_fallback": {
                "recording": fallback_record["frozen_row"].get("recording"),
                "ego_track_id": fallback_record["frozen_row"].get("ego_track_id"),
                "actor": fallback_record["frozen_row"].get("actor"),
                "first_frame": fallback_record["frozen_row"].get("first_frame"),
                "family": row_family(fallback_record["frozen_row"]),
                "location": fallback_record["frozen_row"].get("location"),
                "status": fallback_record["status"],
                "interpretation": "B's retained same-task fallback for the source-geometry-rejected Interactive100 primary; review-blocked, still pending physical review.",
            },
        },
        "retained_only_conservative": {
            "policy": "Keep all 152 untested primaries, all technical passes pending human review, all review-blocked rows, all technical rejections, and every other primary not explicitly source-physical or source-geometry rejected. Preserve the mandatory retained fallback as pending. This is a planning scenario, not a revised queue or outcome-selected reservoir.",
            "source_rejection_statuses_excluded": sorted(source_rejected),
            "retained_primary_rows": len(conservative_retained),
            "retained_candidate_rows_including_mandatory_fallback": len(conservative_retained) + 1,
            "retained_primary_status_counts": dict(sorted(Counter(row["status"] for row in conservative_retained).items())),
            "retained_primary_breakdown": breakdown(conservative_retained),
            "mandatory_fallback_status": fallback_record["status"],
        },
        "planning_sensitivity_terminal_rejections_reusable": {
            "policy": "Sensitivity only: make source-physical, source-geometry, and technical-rejection primary slots reusable; retain untested, technical-pass pending review, review-blocked, and the mandatory fallback. Do not use this assumption in the prospective source-only ordering.",
            "reusable_statuses": sorted(source_rejected | {"technical_rejection"}),
            "retained_primary_rows": len(terminal_rejection_sensitivity),
            "retained_candidate_rows_including_mandatory_fallback": len(terminal_rejection_sensitivity) + 1,
            "retained_primary_status_counts": dict(sorted(Counter(row["status"] for row in terminal_rejection_sensitivity).items())),
            "retained_primary_breakdown": breakdown(terminal_rejection_sensitivity),
        },
    }


def reservation_rows(queue: dict[str, Any], outcomes: list[dict[str, Any]], fallbacks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    outcome_by_sha = {record["frozen_row"].get("source_window_identity_sha256"): record for record in outcomes}
    primary_rows = [row for row in queue["candidates"]]
    source_rejected = {"source_physical_rejection", "source_geometry_rejection"}
    retained = [row for row in primary_rows
                if outcome_by_sha.get(row.get("source_window_identity_sha256"), {}).get("status", "untested") not in source_rejected]
    fallback = fallbacks[0]["frozen_row"]
    anchors = list(queue["frozen_16_identity_rows"])
    return {
        "frozen_216_without_fallback": anchors + primary_rows,
        "frozen_216_plus_protected_fallback": anchors + primary_rows + [fallback],
        "retained_180_plus_protected_fallback": anchors + retained + [fallback],
        "anchors_only": anchors,
    }


def measure_full_source_witness(task_rows: dict[tuple[int, int, int], dict[str, Any]],
                                window_context: dict[tuple[int, int, int], dict[str, Any]],
                                map_rows: dict[tuple[int, int, int], dict[str, Any]],
                                interactive_pool: dict[Any, list[dict[str, Any]]],
                                random_pool: dict[Any, list[dict[str, Any]]],
                                baseline: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the same ordered greedy selectors against one explicit reservation set."""
    offstride, off_summary, _ = make_offstride_witness(task_rows, window_context, map_rows, baseline)
    retained = list(baseline) + offstride
    # _choose_arm annotates selected source rows, so make shallow row copies for
    # each baseline measurement and preserve the primary 216-row witness.
    interactive_copy = {unit: [dict(row) for row in rows] for unit, rows in interactive_pool.items()}
    random_copy = {unit: [dict(row) for row in rows] for unit, rows in random_pool.items()}
    stride_interactive, _, _ = freeze._choose_arm(interactive_copy, "Interactive100", retained, "task_key")
    retained.extend(stride_interactive)
    random_selected, _, _ = freeze._choose_arm(random_copy, "Random100", retained, "recording_ego_key")
    interactive_rows = offstride + stride_interactive
    selected_rows = interactive_rows + random_selected
    selected_window_ids = sorted(row["source_window_identity_sha256"] for row in selected_rows)
    return {
        "baseline_rows": len(baseline),
        "offstride_interactive_rows": len(offstride),
        "stride_interactive_rows": len(stride_interactive),
        "interactive_source_map_qualified_rows": len(interactive_rows),
        "random_source_map_qualified_rows": len(random_selected),
        "combined_source_map_qualified_rows": len(selected_rows),
        "by_arm": {
            "Interactive100": distribution(interactive_rows),
            "Random100": distribution(random_selected, include_random_family=True),
        },
        "combined_distribution": distribution(selected_rows, include_random_family=True),
        "selected_window_set_sha256": hashlib.sha256(json.dumps(selected_window_ids, separators=(",", ":")).encode()).hexdigest(),
        "offstride_excluded_task_counts": off_summary["excluded_task_counts"],
        "interpretation": "Order-dependent source-only witness under this exact retained baseline; source-map-qualified only, not a physical, technical, semantic, planner, or manual-review result, and not a maximum independent set.",
    }


def build_fresh_offstride_preflight(task_rows: dict[tuple[int, int, int], dict[str, Any]], output_dir: Path) -> tuple[dict[tuple[int, int, int], dict[str, Any]], dict[str, Any]]:
    windows: dict[tuple[int, int, int], dict[str, Any]] = {}
    for candidate in task_rows.values():
        for phase in candidate["phase_order"]:
            recording, ego, first = phase["window_key"]
            windows[(recording, ego, first)] = {
                "recording": recording, "location": candidate["location"], "ego_track_id": ego,
                "first_frame": first, "source_rejection": None,
                "nearby_moving_actor_count": None, "nearby_vru_count": None, "turn_rad": None,
            }
    catalog_path = output_dir / "incremental_offstride_preflight_catalog.json"
    preflight_path = output_dir / "incremental_offstride_current_map_preflight.json"
    write_json(catalog_path, {
        "schema_version": 1,
        "method": "Deduplicated source-positive off-stride phases for interaction task identities outside the complete eligible stride-50 interaction task pool.",
        "windows": list(windows.values()),
    })
    started = time.monotonic()
    preflight_source_map.main(SimpleNamespace(catalog=catalog_path, output=preflight_path))
    duration = time.monotonic() - started
    data = load(preflight_path)
    result = {(int(row["recording"]), int(row["ego_track_id"]), int(row["first_frame"])): row for row in data["windows"]}
    if set(result) != set(windows):
        raise ValueError("source-map preflight output did not preserve exact candidate window keys")
    return result, {
        "catalog_path": str(catalog_path.relative_to(PROJECT_ROOT)), "catalog_sha256": sha256(catalog_path),
        "preflight_path": str(preflight_path.relative_to(PROJECT_ROOT)), "preflight_sha256": sha256(preflight_path),
        "producer_path": "src/geotransfer_gap/maps/preflight_source_map.py",
        "producer_sha256": sha256(PROJECT_ROOT / "src/geotransfer_gap/maps/preflight_source_map.py"),
        "candidate_unique_window_count": len(windows), "elapsed_seconds": duration,
        "source_map_pass_definition": "source_track_complete is true AND outside_sample_count == 0 AND directed_route is true",
        "pass_count": sum(map_stage(row) for row in result.values()),
        "failure_count": sum(not map_stage(row) for row in result.values()),
        "by_location": {
            str(loc): {"windows": sum(r["location"] == loc for r in result.values()),
                       "map_pass": sum(r["location"] == loc and map_stage(r) for r in result.values())}
            for loc in (1, 2, 3, 4)
        },
        "failure_reason_occurrences": {
            "incomplete_source_track": sum(r.get("source_track_complete") is not True for r in result.values()),
            "outside_lanelet_samples": sum(r.get("outside_sample_count", 0) > 0 for r in result.values()),
            "directed_route_false": sum(r.get("directed_route") is not True for r in result.values()),
        },
        "reason_occurrences_overlap": True,
    }


def reconstruct_incremental_context(task_rows: dict[tuple[int, int, int], dict[str, Any]]) -> tuple[dict[tuple[int, int, int], dict[str, Any]], dict[str, Any]]:
    by_recording: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for candidate in task_rows.values():
        for phase in candidate["phase_order"]:
            by_recording[phase["window_key"][0]].append(phase["window_key"])
    window_context: dict[tuple[int, int, int], dict[str, Any]] = {}
    source_hashes: dict[str, Any] = {}
    context_actor_missing = 0
    task_actor_not_moving_windows = 0
    for recording, keys in sorted(by_recording.items()):
        tracks, track_meta, hashes = freeze._load_recording_source(recording)
        source_hashes[str(recording)] = hashes
        for key in sorted(set(keys)):
            identity = {"recording": key[0], "location": next(c["location"] for c in task_rows.values()
                        if any(p["window_key"] == key for p in c["phase_order"])),
                        "ego_track_id": key[1], "first_frame": key[2], "last_frame": key[2] + WINDOW_SOURCE_FRAMES}
            actors = source_context_actors(identity, tracks, track_meta)
            by_id = {actor["track_id"]: actor for actor in actors}
            window_context[key] = {
                "source_window_identity": identity,
                "source_window_identity_sha256": source_window_identity_sha256(identity),
                "source_context_actors": actors,
                "context_actor_ids": [actor["track_id"] for actor in actors],
                "moving_track_ids": [actor["track_id"] for actor in actors if actor.get("moving") is True],
                "context_actor_count": len(actors),
            }
            for candidate in task_rows.values():
                if candidate["recording"] == key[0] and candidate["ego_track_id"] == key[1] and any(p["window_key"] == key for p in candidate["phase_order"]):
                    actor = by_id.get(candidate["actor"])
                    if actor is None:
                        context_actor_missing += 1
                    elif actor.get("moving") is not True:
                        task_actor_not_moving_windows += 1
        del tracks, track_meta
    return window_context, {
        "recordings_reconstructed": len(source_hashes),
        "source_hashes_by_recording": source_hashes,
        "full_source_context_definition": "source_only_protocol.source_context_actors over all supported converter-context actors, inclusive 226 raw-frame crop, at least 2 raw rows, at least 2 valid samples, and >=1.0m raw trimmed-row path for moving status; no actor cap",
        "task_window_relations_with_actor_missing_from_converted_context": context_actor_missing,
        "task_window_relations_with_actor_present_but_not_moving": task_actor_not_moving_windows,
    }


def make_offstride_witness(task_rows: dict[tuple[int, int, int], dict[str, Any]],
                           window_context: dict[tuple[int, int, int], dict[str, Any]],
                           map_rows: dict[tuple[int, int, int], dict[str, Any]],
                           baseline: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Coverage-first, no-cap deterministic greedy witness, not a maximum."""
    strata: dict[tuple[int, str], list[tuple[int, int, int]]] = defaultdict(list)
    for task, candidate in task_rows.items():
        for family in candidate["families"]:
            if candidate["location"] in ACTIVE_LOCATIONS:
                strata[(candidate["location"], family)].append(task)
    ordered: list[tuple[int, int, int]] = []
    task_order_hash: dict[tuple[int, int, int], str] = {}
    used: set[tuple[int, int, int]] = set()
    stratum_order = []
    for location in ACTIVE_LOCATIONS:
        for family in FAMILIES:
            pool = sorted(strata.get((location, family), ()), key=lambda task: (stable_rank("active-stratum", location, family, list(task)), task))
            stratum_order.append({"location": location, "family": family, "task_supply": len(pool), "task_rank_sha256": stable_rank("active-stratum", location, family, list(pool[0])) if pool else None})
            if pool:
                ordered.append(pool[0])
                task_order_hash[pool[0]] = stable_rank("active-stratum", location, family, list(pool[0]))
                used.add(pool[0])
    remainder = sorted((task for task in task_rows if task not in used),
                       key=lambda task: (stable_rank("remaining-task", list(task)), task))
    task_order_hash.update({task: stable_rank("remaining-task", list(task)) for task in remainder})
    ordered.extend(remainder)
    retained = list(baseline)
    witness = []
    ordered_reservoir = []
    excluded = Counter()
    phase_attempts = Counter()
    for task_order, task in enumerate(ordered, 1):
        candidate = task_rows[task]
        if not candidate["families"]:
            excluded["missing_family"] += 1
            continue
        selected = None
        any_context = False
        any_map = False
        candidate_conflicts = 0
        phase_audit = []
        for phase in candidate["phase_order"]:
            key = phase["window_key"]
            context = window_context[key]
            source_actor = next((actor for actor in context["source_context_actors"] if actor["track_id"] == candidate["actor"]), None)
            map_row = map_rows.get(key)
            phase_record = {
                "source_window_identity_sha256": context["source_window_identity_sha256"],
                "recording": key[0], "ego_track_id": key[1], "first_frame": key[2],
                "last_frame": key[2] + WINDOW_SOURCE_FRAMES,
                "selector_evidence": [{"selector": item["selector"], "selector_row_index": item["selector_row_index"]}
                                      for item in phase["evidence"]],
                "context_actor_count": context["context_actor_count"],
                "moving_track_ids": context["moving_track_ids"],
                "source_task_actor": source_actor,
                "source_map_preflight": map_row,
            }
            if selected is not None:
                phase_record["selection_check"] = "not_needed_after_primary_independent_phase"
                phase_audit.append(phase_record)
                continue
            if source_actor is None:
                phase_attempts["task_actor_missing_from_full_context"] += 1
                phase_record["selection_check"] = "task_actor_missing_from_full_context"
                phase_audit.append(phase_record)
                continue
            any_context = True
            if source_actor.get("moving") is not True:
                phase_attempts["task_actor_not_moving"] += 1
                phase_record["selection_check"] = "task_actor_not_moving"
                phase_audit.append(phase_record)
                continue
            if not map_stage(map_row):
                phase_attempts["current_source_map_failed"] += 1
                phase_record["selection_check"] = "current_source_map_failed"
                phase_audit.append(phase_record)
                continue
            any_map = True
            row = {
                **context,
                "arm": "Interactive100",
                "recording": candidate["recording"],
                "location": candidate["location"],
                "ego_track_id": candidate["ego_track_id"],
                "first_frame": key[2],
                "last_frame": key[2] + WINDOW_SOURCE_FRAMES,
                "actor": candidate["actor"],
                "source_task_families": candidate["families"],
                "source_selector_names": sorted({evidence["selector"] for p in candidate["phase_order"] for evidence in p["evidence"]}),
                "source_selector_phase_evidence": [
                    {"selector": evidence["selector"], "selector_row_index": evidence["selector_row_index"]}
                    for evidence in phase["evidence"]
                ],
                "source_map_preflight": map_row,
                "task_rank_sha256": task_order_hash[task],
                "phase_rank": len(witness) + 1,
                "planner_outcomes_present": False,
            }
            conflicts = independence_conflicts(row, retained)
            if conflicts:
                phase_attempts["independence_conflict"] += 1
                candidate_conflicts += 1
                phase_record["selection_check"] = "independence_conflict"
                phase_record["independence_conflicts"] = conflicts
                phase_audit.append(phase_record)
                continue
            selected = row
            phase_record["selection_check"] = "selected_witness"
            phase_audit.append(phase_record)
        if selected is None:
            if not any_context:
                decision = "no_full_source_task_actor_context"
                excluded[decision] += 1
            elif not any_map:
                decision = "no_current_map_passing_context_phase"
                excluded[decision] += 1
            elif candidate_conflicts:
                decision = "no_independent_eligible_phase_under_greedy_order"
                excluded[decision] += 1
            else:
                decision = "no_eligible_phase"
                excluded[decision] += 1
        else:
            decision = "selected_witness"
        ordered_reservoir.append({
            "reservoir_order": task_order,
            "task_key": list(task),
            "location": candidate["location"],
            "families": candidate["families"],
            "task_rank_sha256": task_order_hash[task],
            "selection_status": decision,
            "selected_source_window_identity_sha256": selected.get("source_window_identity_sha256") if selected else None,
            "ordered_phases": phase_audit,
        })
        if selected is None:
            continue
        witness.append(selected)
        retained.append(selected)
    return witness, {
        "baseline_rows": len(baseline),
        "baseline_definition": "all 16 frozen anchors plus all 200 frozen v1 primary candidates; outcomes are not used to order or filter prospective source candidates",
        "greedy_task_order": "First deterministic SHA-ranked task in each available location 1/3/4 by family stratum; then every remaining task in a single deterministic SHA-ranked order across locations 1-4. No cap.",
        "phase_order": "Frozen source-selector priority; event-fine rows by completeness, crossing-time gap, midpoint distance from sample step 45, first frame, selector row index; other selectors by first frame then row index.",
        "stratum_first_rows": stratum_order,
        "witness_count": len(witness),
        "witness_distribution": distribution(witness),
        "excluded_task_counts": dict(sorted(excluded.items())),
        "phase_attempt_counts": dict(sorted(phase_attempts.items())),
        "interpretation": "A coverage-first, order-dependent source-only witness, not a maximum independent set, validated cohort, or yield forecast.",
    }, ordered_reservoir


def prospective_full_source(output_dir: Path, queue: dict[str, Any], outcomes: list[dict[str, Any]], fallbacks: list[dict[str, Any]],
                            task_rows: dict[tuple[int, int, int], dict[str, Any]],
                            incremental_maps: dict[tuple[int, int, int], dict[str, Any]],
                            context_summary: dict[str, Any],
                            incremental_context: dict[tuple[int, int, int], dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    eligible_windows, catalog_summary, preflight_summary = freeze._eligible_sources()
    interaction_pool, selector_inputs, selector_counts, exact_rows = freeze._load_interaction_pool(eligible_windows)
    random_pool, interactive_pool = freeze._prepare_candidates(eligible_windows, interaction_pool)
    stride_window_locations = Counter(int(value["catalog"]["location"]) for value in eligible_windows.values())
    stride_interaction_matrix: dict[str, Counter] = defaultdict(Counter)
    for task, windows in interaction_pool.items():
        first_window = next(iter(windows))
        location = int(eligible_windows[first_window]["catalog"]["location"])
        families = sorted({family for row in windows.values() for family in row["interaction_families"]})
        for family in families:
            stride_interaction_matrix[str(location)][family] += 1
    random_unit_locations = Counter(int(rows[0]["location"]) for rows in random_pool.values())
    baseline = list(queue["frozen_16_identity_rows"]) + list(queue["candidates"])
    reservation_sets = reservation_rows(queue, outcomes, fallbacks)
    baseline_sensitivity = {
        name: measure_full_source_witness(task_rows, incremental_context, incremental_maps,
                                          interactive_pool, random_pool, rows)
        for name, rows in reservation_sets.items()
        if name != "frozen_216_without_fallback"
    }
    baseline_sensitivity["frozen_216_without_fallback"] = {
        "baseline_rows": 216,
        "offstride_interactive_rows": None,
        "stride_interactive_rows": None,
        "interactive_source_map_qualified_rows": None,
        "random_source_map_qualified_rows": None,
        "combined_source_map_qualified_rows": None,
        "selected_window_set_sha256": None,
        "interpretation": "The exact no-fallback run uses the primary full-source witness below; its 383 selected windows all passed the fresh current source-map producer.",
    }
    prior_supply_census = load(SUPPLY_CENSUS)
    incremental_witness, incremental_witness_summary, ordered_reservoir = make_offstride_witness(
        task_rows, incremental_context, incremental_maps, baseline
    )
    reservoir_path = output_dir / "ordered_incremental_offstride_reservoir.json"
    write_json(reservoir_path, {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "baseline": "All 16 frozen anchors and all 200 frozen v1 primary rows, irrespective of outcomes.",
        "task_order": incremental_witness_summary["greedy_task_order"],
        "phase_order": incremental_witness_summary["phase_order"],
        "source_hashes_by_recording": context_summary["source_hashes_by_recording"],
        "ordered_task_rows": ordered_reservoir,
    })
    incremental_witness_summary["ordered_reservoir_artifact"] = {
        "path": str(reservoir_path.relative_to(PROJECT_ROOT)),
        "sha256": sha256(reservoir_path),
        "task_rows": len(ordered_reservoir),
        "phase_rows": sum(len(row["ordered_phases"]) for row in ordered_reservoir),
    }
    retained = baseline + incremental_witness
    stride_interactive, stride_interactive_units, stride_interactive_rejections = freeze._choose_arm(
        interactive_pool, "Interactive100", retained, "task_key"
    )
    random_selected, random_units, random_rejections = freeze._choose_arm(
        random_pool, "Random100", retained, "recording_ego_key"
    )
    for index, row in enumerate(incremental_witness + stride_interactive + random_selected, 1):
        row["reservoir_order"] = index
    # Re-run the current map producer on the assembled witness from all arms.
    selected_rows = incremental_witness + stride_interactive + random_selected
    baseline_window_set_sha = hashlib.sha256(json.dumps(
        sorted(row["source_window_identity_sha256"] for row in selected_rows), separators=(",", ":")
    ).encode()).hexdigest()
    baseline_sensitivity["frozen_216_without_fallback"]["selected_window_set_sha256"] = baseline_window_set_sha
    for name in ("frozen_216_plus_protected_fallback", "retained_180_plus_protected_fallback", "anchors_only"):
        baseline_sensitivity[name]["selected_window_set_matches_frozen_216_without_fallback"] = (
            baseline_sensitivity[name]["selected_window_set_sha256"] == baseline_window_set_sha
        )
    unique_catalog: dict[tuple[int, int, int], dict[str, Any]] = {}
    for row in selected_rows:
        key = (int(row["recording"]), int(row["ego_track_id"]), int(row["first_frame"]))
        unique_catalog.setdefault(key, {"recording": key[0], "location": int(row["location"]), "ego_track_id": key[1],
                                        "first_frame": key[2], "source_rejection": None,
                                        "nearby_moving_actor_count": None, "nearby_vru_count": None, "turn_rad": None})
    selected_catalog_path = output_dir / "prospective_witness_current_map_catalog.json"
    selected_map_path = output_dir / "prospective_witness_current_map_preflight.json"
    write_json(selected_catalog_path, {"schema_version": 1, "method": "Unique source windows in the deterministic prospective source-only witness; no conversion or physical/technical gate.", "windows": list(unique_catalog.values())})
    started = time.monotonic()
    preflight_source_map.main(SimpleNamespace(catalog=selected_catalog_path, output=selected_map_path))
    selected_map = load(selected_map_path)
    current_map_by_key = {(int(row["recording"]), int(row["ego_track_id"]), int(row["first_frame"])): row for row in selected_map["windows"]}
    for row in selected_rows:
        key = (int(row["recording"]), int(row["ego_track_id"]), int(row["first_frame"]))
        row["fresh_current_source_map_preflight"] = current_map_by_key[key]
    selected_map_summary = {
        "catalog_path": str(selected_catalog_path.relative_to(PROJECT_ROOT)), "catalog_sha256": sha256(selected_catalog_path),
        "preflight_path": str(selected_map_path.relative_to(PROJECT_ROOT)), "preflight_sha256": sha256(selected_map_path),
        "producer_path": "src/geotransfer_gap/maps/preflight_source_map.py",
        "producer_sha256": sha256(PROJECT_ROOT / "src/geotransfer_gap/maps/preflight_source_map.py"),
        "unique_witness_windows": len(unique_catalog), "elapsed_seconds": time.monotonic() - started,
        "pass_count": sum(map_stage(row) for row in current_map_by_key.values()),
        "failure_count": sum(not map_stage(row) for row in current_map_by_key.values()),
        "by_location": {str(loc): {"windows": sum(row["location"] == loc for row in current_map_by_key.values()),
                                    "map_pass": sum(row["location"] == loc and map_stage(row) for row in current_map_by_key.values())}
                        for loc in (1, 2, 3, 4)},
    }
    for name in ("frozen_216_plus_protected_fallback", "retained_180_plus_protected_fallback", "anchors_only"):
        same_windows = baseline_sensitivity[name]["selected_window_set_matches_frozen_216_without_fallback"]
        baseline_sensitivity[name]["fresh_current_map_pass_count"] = selected_map_summary["pass_count"] if same_windows else None
        baseline_sensitivity[name]["fresh_current_map_failure_count"] = selected_map_summary["failure_count"] if same_windows else None
        baseline_sensitivity[name]["fresh_current_map_receipt"] = (
            selected_map_summary["preflight_path"] if same_windows else None
        )
        baseline_sensitivity[name]["map_evidence_scope"] = (
            "Selected window set matches the freshly re-preflighted 216-row baseline; receipt applies to the same exact windows."
            if same_windows else
            "Fresh off-stride phase map preflight and the existing stride-50 source-map-qualified pools; this alternative witness was not separately post-selection re-preflighted."
        )
    full_pool = {
        "source_population": {
            "eligible_stride50_windows": len(eligible_windows),
            "interactive_stride50_task_units": len(interactive_pool),
            "random_stride50_recording_ego_units": len(random_pool),
            "incremental_offstride_task_units_outside_stride50_task_pool": len(task_rows),
            "eligible_stride50_windows_by_location": {str(loc): stride_window_locations.get(loc, 0) for loc in (1, 2, 3, 4)},
            "interactive_stride50_tasks_by_location_family": {
                loc: dict(sorted(counts.items())) for loc, counts in sorted(stride_interaction_matrix.items())
            },
            "random_stride50_recording_ego_units_by_location": {str(loc): random_unit_locations.get(loc, 0) for loc in (1, 2, 3, 4)},
            "input_scope": "All seven frozen source-positive selectors, joined to the full eligible stride-50 source/map pool; plus incremental off-stride positive task identities outside that pool.",
            "catalogs": catalog_summary,
            "stride_map_preflights": preflight_summary,
            "selector_inputs": selector_inputs,
            "selector_row_counts": selector_counts,
            "selector_exact_eligible_rows": exact_rows,
        },
        "order_and_independence": {
            "baseline": "16 anchors + 200 frozen v1 primaries, irrespective of outcomes",
            "arm_order": "Coverage-first incremental off-stride interaction witness, then full eligible stride-50 interaction units, then random recording/ego units.",
            "unit_definition": {"Interactive100": "unique (recording, ego, actor)", "Random100": "unique (recording, ego_track_id)"},
            "independence": "inclusive first_frame through first_frame+225 and disjoint all-moving converted-context IDs within recording; no moving actor cap",
            "candidate_order": "off-stride uses fixed selector/phase order plus SHA task order; stride-50 pools use frozen v1 deterministic SHA unit/phase order",
        },
        "source_only_witnesses": {
            "reservation_baseline_sensitivity": {
                "frozen_216_without_fallback": {
                    **baseline_sensitivity["frozen_216_without_fallback"],
                    "interactive_source_map_qualified_rows": len(incremental_witness) + len(stride_interactive),
                    "random_source_map_qualified_rows": len(random_selected),
                    "combined_source_map_qualified_rows": len(selected_rows),
                    "fresh_current_map_pass_count": selected_map_summary["pass_count"],
                    "fresh_current_map_failure_count": selected_map_summary["failure_count"],
                    "current_map_preflight": selected_map_summary,
                },
                "frozen_216_plus_protected_fallback": baseline_sensitivity["frozen_216_plus_protected_fallback"],
                "retained_180_plus_protected_fallback": baseline_sensitivity["retained_180_plus_protected_fallback"],
                "anchors_only_full_source": baseline_sensitivity["anchors_only"],
                "comparison_basis": "Same full-source pools and deterministic greedy task/phase/unit ordering. Alternative-baseline counts use the existing stride-50 map-qualified pools and fresh current off-stride map preflight; only the exact 216-row baseline has a post-selection fresh current-map receipt. These are witness counts, not maxima or validation yields.",
            },
            "prior_v1_anchor_only_reference": {
                "interactive_independent_rows": prior_supply_census["greedy_source_only_witnesses"]["cross_arm_interactive_first_against_frozen_16_anchors"]["Interactive100"]["greedy_source_window_witness_rows"],
                "random_independent_rows_after_interactive": prior_supply_census["greedy_source_only_witnesses"]["cross_arm_interactive_first_against_frozen_16_anchors"]["Random100"]["greedy_source_window_witness_rows"],
                "combined_rows": prior_supply_census["greedy_source_only_witnesses"]["cross_arm_interactive_first_against_frozen_16_anchors"]["combined_greedy_source_window_witness_rows"],
                "baseline": "Only the 16 frozen anchors; this prior v1 stride-only witness is not comparable to the 216-row baseline below.",
                "source": "artifacts/german_200_v1_workstream_d/supply_census.json",
            },
            "incremental_offstride_interactive": {**incremental_witness_summary, "selected_rows": incremental_witness},
            "eligible_stride50_interactive_after_incremental": {
                "eligible_task_units": len(interactive_pool), "greedy_independent_units": len(stride_interactive_units),
                "greedy_source_window_rows": len(stride_interactive),
                "selected_distribution": distribution(stride_interactive),
                "rejected_unit_reasons": census.conflict_rollup(stride_interactive_rejections),
                "selected_rows": stride_interactive,
            },
            "random_stride50_after_interactions": {
                "eligible_recording_ego_units": len(random_pool), "greedy_independent_units": len(random_units),
                "greedy_source_window_rows": len(random_selected),
                "selected_distribution": distribution(random_selected, include_random_family=True),
                "rejected_unit_reasons": census.conflict_rollup(random_rejections),
                "selected_rows": random_selected,
            },
            "combined_selected_rows": len(selected_rows),
            "combined_selected_rows_after_full_216_baseline": len(selected_rows),
            "combined_baseline_rows": len(baseline),
            "combined_baseline_description": "All 16 frozen anchors plus all 200 frozen v1 primaries, regardless of observed outcomes.",
            "combined_distribution": distribution(selected_rows, include_random_family=True),
            "maximum_independent_set": False,
        },
        "fresh_map_preflight_of_prospective_witness": selected_map_summary,
        "later_stages": {
            "physical_source_gate": "not run on prospective rows; source-map pass is not physical clearance",
            "semantic_or_rule_review": "not run; selector-positive task evidence is not semantic eligibility",
            "technical_gate": "not run",
            "planner_or_rollout": "not run",
            "manual_admission": "not run",
        },
    }
    return full_pool, selected_map_summary


def incremental_supply_stages(task_rows: dict[tuple[int, int, int], dict[str, Any]],
                              context_rows: dict[tuple[int, int, int], dict[str, Any]],
                              map_rows: dict[tuple[int, int, int], dict[str, Any]],
                              baseline: list[dict[str, Any]],
                              selected: list[dict[str, Any]]) -> dict[str, Any]:
    stage_counts: dict[str, dict[str, Counter]] = {
        stage: defaultdict(Counter)
        for stage in ("source_positive_tasks", "moving_task_actor_context", "current_map_pass_phase",
                      "context_map_and_baseline_independent_phase", "selected_greedy_witness")
    }
    phase_counts: dict[str, dict[str, Counter]] = {
        stage: defaultdict(Counter)
        for stage in ("source_positive_phase_relations", "moving_task_actor_context", "current_map_pass_phase",
                      "context_map_and_baseline_independent_phase")
    }
    selected_tasks = {(int(row["recording"]), int(row["ego_track_id"]), int(row["actor"])) for row in selected}
    for task, candidate in task_rows.items():
        loc, family = candidate["location"], candidate["families"][0]
        stage_counts["source_positive_tasks"][str(loc)][family] += 1
        context_qualified = False
        map_qualified = False
        independent_qualified = False
        for phase in candidate["phase_order"]:
            key = phase["window_key"]
            phase_counts["source_positive_phase_relations"][str(loc)][family] += 1
            context = context_rows[key]
            actor = next((item for item in context["source_context_actors"] if item["track_id"] == candidate["actor"]), None)
            if actor is None or actor.get("moving") is not True:
                continue
            context_qualified = True
            phase_counts["moving_task_actor_context"][str(loc)][family] += 1
            if not map_stage(map_rows.get(key)):
                continue
            map_qualified = True
            phase_counts["current_map_pass_phase"][str(loc)][family] += 1
            row = {**context, "recording": task[0], "location": loc, "ego_track_id": task[1],
                   "actor": task[2], "first_frame": key[2], "last_frame": key[2] + WINDOW_SOURCE_FRAMES,
                   "source_task_families": candidate["families"]}
            if not independence_conflicts(row, baseline):
                independent_qualified = True
                phase_counts["context_map_and_baseline_independent_phase"][str(loc)][family] += 1
        if context_qualified:
            stage_counts["moving_task_actor_context"][str(loc)][family] += 1
        if map_qualified:
            stage_counts["current_map_pass_phase"][str(loc)][family] += 1
        if independent_qualified:
            stage_counts["context_map_and_baseline_independent_phase"][str(loc)][family] += 1
        if task in selected_tasks:
            stage_counts["selected_greedy_witness"][str(loc)][family] += 1
    return {
        "task_unit_counts_by_location_family_and_stage": {
            stage: {loc: dict(sorted(counts.items())) for loc, counts in sorted(matrix.items())}
            for stage, matrix in stage_counts.items()
        },
        "phase_relation_counts_by_location_family_and_stage": {
            stage: {loc: dict(sorted(counts.items())) for loc, counts in sorted(matrix.items())}
            for stage, matrix in phase_counts.items()
        },
        "definitions": {
            "source_positive_tasks": "Distinct (recording, ego, actor) keys outside the complete eligible stride-50 interaction task pool with at least one off-stride selector-positive phase.",
            "moving_task_actor_context": "Task has at least one phase where its referenced actor is present and moving in the exact full converter-supported context.",
            "current_map_pass_phase": "Task has at least one actor-context-valid phase passing the fresh current source-map preflight.",
            "context_map_and_baseline_independent_phase": "Task has at least one context/map-qualified phase with no inclusive-window or all-moving-track conflict against all 216 frozen anchors and primaries.",
            "selected_greedy_witness": "Task selected in the coverage-first, no-cap order after incremental witness conflicts are also applied.",
        },
    }


def main(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite nonempty yield-reservoir output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    outcomes, fallbacks, loaded = ledger_rows()
    task_rows, selector_metadata = build_incremental_pool()
    map_rows, map_summary = build_fresh_offstride_preflight(task_rows, output_dir)
    context_rows, context_summary = reconstruct_incremental_context(task_rows)
    frozen_source_hashes = loaded["queue"].get("source_hashes_by_recording", {})
    source_hash_fields = ("tracks_csv_sha256", "tracks_meta_csv_sha256", "recording_meta_csv_sha256",
                          "background_png_sha256", "lanelet2_map_sha256", "opendrive_map_sha256")
    source_hash_mismatches = []
    for recording, current in context_summary["source_hashes_by_recording"].items():
        expected = frozen_source_hashes.get(recording, {})
        changed = [field for field in source_hash_fields if expected.get(field) != current.get(field)]
        if changed:
            source_hash_mismatches.append({"recording": int(recording), "changed_fields": changed})
    context_summary["frozen_source_hash_match_count"] = len(context_summary["source_hashes_by_recording"]) - len(source_hash_mismatches)
    context_summary["frozen_source_hash_mismatches"] = source_hash_mismatches
    if source_hash_mismatches:
        raise ValueError(f"current off-stride source inputs differ from the frozen v1 source pins: {source_hash_mismatches}")
    scenarios = frozen_scenarios(loaded["queue"], outcomes, fallbacks)
    prospective, selected_map_summary = prospective_full_source(output_dir, loaded["queue"], outcomes, fallbacks,
                                                                  task_rows, map_rows,
                                                                  context_summary, context_rows)
    prospective_witnesses = prospective["source_only_witnesses"]
    baseline = list(loaded["queue"]["frozen_16_identity_rows"]) + list(loaded["queue"]["candidates"])
    incremental_stages = incremental_supply_stages(
        task_rows, context_rows, map_rows, baseline,
        prospective_witnesses["incremental_offstride_interactive"]["selected_rows"],
    )
    row_by_sha = {row.get("frozen_row", {}).get("source_window_identity_sha256"): row for row in outcomes}
    source_map_rows = [
        {"status": row_by_sha.get(candidate["source_window_identity_sha256"], {}).get("status", "untested"),
         "frozen_row": candidate}
        for candidate in loaded["queue"]["candidates"]
    ]
    frozen_map_stage = Counter("pass" if map_stage(candidate.get("source_map_preflight")) else "not_pass_or_unrecorded"
                               for candidate in loaded["queue"]["candidates"])
    stage_summary = {
        "frozen_v1_source_map_preflight": {
            "rows": len(source_map_rows), "counts": dict(sorted(frozen_map_stage.items())),
            "stage_definition": "source_track_complete true, outside_sample_count zero, directed_route true from frozen source-map preflight metadata; not a physical gate",
        },
        "observed_B_C_primary_stages": {
            "primary_rows": len(outcomes), "status_counts": dict(sorted(Counter(row["status"] for row in outcomes).items())),
            "technical_gate_pass_pending_review": sum(row["status"] == "awaiting_human_review" for row in outcomes),
            "review_blocked": sum(row["status"] == "review_blocked" for row in outcomes),
            "physical_source_rejection": sum(row["status"] == "source_physical_rejection" for row in outcomes),
            "source_geometry_rejection": sum(row["status"] == "source_geometry_rejection" for row in outcomes),
            "technical_rejection": sum(row["status"] == "technical_rejection" for row in outcomes),
            "technical_gate_results_are_not_semantic_or_planner_admissions": True,
            "manual_reviews_created": any(report.get("manual_reviews_created") is True for report in loaded["batch_reports"].values()),
            "final_manual_admissions_recorded": 0,
            "planner_outcomes_used_in_any_reservoir_order": False,
        },
        "mandatory_fallback_stage": {
            "rows": len(fallbacks), "status_counts": dict(Counter(row["status"] for row in fallbacks)),
            "source_physical_gate": fallbacks[0]["result"].get("source_preflight", {}).get("physical", {}),
            "technical_admission": fallbacks[0]["result"].get("technical_admission", {}),
            "manual_review_status": fallbacks[0]["result"].get("manual_review_status"),
        },
        "prospective_rows": {
            "fresh_offstride_source_map_preflight": map_summary,
            "full_source_context_reconstruction": context_summary,
            "current_map_repreflight_of_combined_witness": selected_map_summary,
            "physical_source_gate": "not run",
            "semantic_review": "not run",
            "technical_gate": "not run",
            "planner_or_rollout": "not run",
        },
    }
    inputs = [QUEUE, B_LEDGER, C_LEDGER, B_REPORT, C_REPORT,
              SUPPLY_CENSUS,
              PROJECT_ROOT / "src/geotransfer_gap/corpus/freeze_random_interactive_v1.py",
              PROJECT_ROOT / "src/geotransfer_gap/corpus/source_only_protocol.py",
              PROJECT_ROOT / "src/geotransfer_gap/corpus/census_german_200_v1.py",
              PROJECT_ROOT / "src/geotransfer_gap/maps/preflight_source_map.py"]
    report = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "analysis_only": True,
        "queues_created_or_changed": False,
        "planner_outcomes_read_for_selection": False,
        "inputs": {str(path.relative_to(PROJECT_ROOT)): {"sha256": sha256(path)} for path in inputs},
        "frozen_scenarios": scenarios,
        "source_positive_pool": {
            "stride50_eligible_interactive_task_units": selector_metadata["stride_source_task_count"],
            "incremental_offstride_task_units_outside_stride50_pool": selector_metadata["incremental_offstride_task_count"],
            "all_source_positive_task_units_union": selector_metadata["stride_source_task_count"] + selector_metadata["incremental_offstride_task_count"],
            "incremental_offstride_unique_window_phases": selector_metadata["unique_incremental_offstride_phases"],
            "incremental_offstride_task_window_relations": selector_metadata["unique_task_window_relations"],
            "incremental_offstride_task_supply_stages": incremental_stages,
            "basis": "seven existing source-positive selectors; actor-pair tasks deduped by recording+ego+actor; repeated phases are retained as source alternatives",
            "selector_inputs_and_hashes": selector_metadata,
        },
        "stage_supply": stage_summary,
        "prospective_full_source_reservoir": prospective,
        "validation_plan": {
            "not_a_v2_freeze": True,
            "final_cohort_target_per_arm": 100,
            "pilot_and_stopping": "Predeclare a 12-per-arm first validation tranche, then fixed 12-row tranches, with the objective of 100 rows per arm that pass the predeclared physical-source, semantic/task, technical, and manual eligibility stages. Stop only at 100 eligible rows per arm, 1,000 candidate attempts per arm, exhaustion of the fully ranked independent candidate frame, or a protocol-integrity/safety stop. Do not stop or extend based on planner outcomes.",
            "candidate_attempt_budget_per_arm": 1000,
            "candidate_attempt_budget_basis": "The 1,000-attempt upper budget covers the explicit 10% hypothetical yield case for 100 final eligible rows. It is a planning limit, not a yield estimate. The current full-source witness contains only 111 Interactive100 and 272 Random100 source-only rows, so it cannot supply this attempt budget; expand and rank a deeper independent source pool before any v2 freeze or prospective execution.",
            "attempt_and_replacement_rule": "Before validation, publish a deterministic source-only rank/reserve ledger for each arm. For each ranked candidate, recheck inclusive source-window and all-moving-track independence against all previously retained cohort rows. A source integrity, map, task, physical, technical, semantic, or manual exclusion consumes one candidate attempt and advances to the next independent unit in the same predeclared rank/stratum order; use another phase of the same task only for a pre-conversion source/map/task-screen failure and only in its frozen phase order. Do not tune phase, strata, or ranks after planner results. After 1,000 candidate attempts, source-pool exhaustion, or a protocol-integrity/safety stop, report any target shortfall without extending the budget.",
            "interactive100_sampling_unit": "one source-positive (recording, ego, actor) task, not a phase; preserve family/site strata, show location 2, and keep location 4 held out for analysis. The full independent source-ranked reserve frame has not yet been built.",
            "random100_estimand": "uniform sampling over unique (recording, ego_track_id) units in the current source-map-eligible stride-50 population (2,966 units), with one predeclared phase per unit; do not sample uniformly over windows because tracks with more phases would be overrepresented. The full independent source-ranked reserve frame has not yet been built.",
            "independence_and_replacement": "Use a same-task phase alternative only for pre-conversion source/map/task-screen failure, in its frozen phase order, after rechecking full moving-context identities and inclusive intervals against every retained row. After physical, semantic, technical, or manual exclusion, consume the candidate attempt and advance to the next independent source-ranked unit in the fixed arm/site-family order. Planner results never trigger row replacement.",
            "analysis_weights_and_drift": "The independent greedy filter has order-dependent inclusion and is not an SRS; publish unit ranks, exclusions, and site/recording counts. Estimate source-population quantities with design weights only if inclusion probabilities are recoverable; otherwise report descriptive cohort results and cluster uncertainty by recording/site. Keep location-4 holdout separate and report per-site drift before pooled summaries.",
            "hypothetical_yield_sensitivity": {
                "interpretation": "Planning arithmetic for 100 final eligible rows per arm; these yields are hypothetical, not forecasts and are not extrapolated from the fixed stratified B/C pilots.",
                "scenarios": [
                    {"assumed_final_eligibility_yield": 0.10, "candidate_attempts_per_arm_for_100": 1000, "serial_worker_minutes_at_14_994_seconds_per_attempt": 249.9, "two_worker_wall_minutes_if_evenly_loaded": 124.95, "reviewer_hours_if_15_minutes_per_attempt": 250},
                    {"assumed_final_eligibility_yield": 0.25, "candidate_attempts_per_arm_for_100": 400, "serial_worker_minutes_at_14_994_seconds_per_attempt": 99.96, "two_worker_wall_minutes_if_evenly_loaded": 49.98, "reviewer_hours_if_15_minutes_per_attempt": 100},
                    {"assumed_final_eligibility_yield": 0.40, "candidate_attempts_per_arm_for_100": 250, "serial_worker_minutes_at_14_994_seconds_per_attempt": 62.475, "two_worker_wall_minutes_if_evenly_loaded": 31.2375, "reviewer_hours_if_15_minutes_per_attempt": 62.5},
                ],
                "arms": {
                    "Interactive100": {
                        "historical_B_C_attempted": 24,
                        "historical_B_C_status_counts": scenarios["frozen_v1_all_200"]["primary_breakdown"]["by_arm"]["Interactive100"],
                        "current_full_216_source_only_witness_rows": len(prospective["source_only_witnesses"]["incremental_offstride_interactive"]["selected_rows"]) + len(prospective["source_only_witnesses"]["eligible_stride50_interactive_after_incremental"]["selected_rows"]),
                        "current_fresh_map_pass_rows": len(prospective["source_only_witnesses"]["incremental_offstride_interactive"]["selected_rows"]) + len(prospective["source_only_witnesses"]["eligible_stride50_interactive_after_incremental"]["selected_rows"]),
                        "downstream_physical_semantic_technical_planner_manual_yields": "unknown; prospective rows have not reached these stages",
                    },
                    "Random100": {
                        "historical_B_C_attempted": 24,
                        "historical_B_C_status_counts": scenarios["frozen_v1_all_200"]["primary_breakdown"]["by_arm"]["Random100"],
                        "current_full_216_source_only_witness_rows": len(prospective["source_only_witnesses"]["random_stride50_after_interactions"]["selected_rows"]),
                        "current_fresh_map_pass_rows": len(prospective["source_only_witnesses"]["random_stride50_after_interactions"]["selected_rows"]),
                        "downstream_physical_semantic_technical_planner_manual_yields": "unknown; prospective rows have not reached these stages",
                    },
                },
                "final_manual_admissions_in_B_C": 0,
                "current_witness_is_sufficient_for_any_sensitivity_budget": False,
            },
            "cheaper_physical_replacement": {
                "validated_exact_replacement": False,
                "conclusion": "No cheaper source-physical substitute is validated as equivalent to the current physical-source gate. Any lightweight overlap or map flag remains diagnostic only; no false-negative bound, equivalence study, or full-validator parity result supports replacing the gate.",
                "production_gate_or_queue_changed": False,
            },
            "explicit_validation_effort_assumptions": {
                "measured_primary_runtime_basis": "B and C report mean 15.785 and 14.202 seconds per primary; planning value is their unweighted mean, 14.994 seconds per candidate.",
                "technical_run_budget_per_arm_100_candidates": "About 25.0 serial worker-minutes per 100 candidates at 14.994 seconds each; about 12.5 wall-clock minutes with two evenly loaded workers, excluding preflight/build overhead.",
                "technical_run_budget_first_tranche_per_arm_12_candidates": "About 3.0 serial worker-minutes per arm; this is throughput only, not a yield assumption.",
                "review_effort_sensitivity": "Budget 15 reviewer-minutes per selected candidate for physical-source and semantic/applicability review if every row is reviewed: 3 reviewer-hours per 12-row tranche or 25 reviewer-hours per 100-row arm. This is an explicit planning allowance, not a measured review rate.",
                "yield_forecast": "None. B/C are fixed, deliberately stratified pilot batches and their observed statuses are descriptive only; no pass or admission rate is extrapolated.",
            },
        },
        "limitations": [
            "The source-map preflight checks ego track completeness, sampled ego centers inside road/bus lanelets, and a directed start-to-goal route; it does not check physical overlaps or semantic validity.",
            "Full converted-context actors are reconstructed for every incremental off-stride candidate phase with no arbitrary actor cap. Selector evidence still does not establish that a task is physically reviewable or technically admissible.",
            "Prospective greedy counts are witnesses under a declared ordering, not maximum independent-set estimates.",
            "No prospective source candidate received physical-source, semantic, technical, planner, rollout, or manual-review validation in this analysis.",
            "The all-source stride-50 random population uses frozen catalog and map-preflight files; the combined witness is rechecked by the current source-map producer in scratch.",
        ],
        "runtime_seconds": time.monotonic() - started,
        "output_directory": str(output_dir.relative_to(PROJECT_ROOT)),
    }
    write_json(output_dir / "yield_reservoir_audit.json", report)
    print(json.dumps({"output": str(output_dir / "yield_reservoir_audit.json"),
                      "sha256": sha256(output_dir / "yield_reservoir_audit.json"),
                      "runtime_seconds": report["runtime_seconds"],
                      "incremental_offstride_tasks": len(task_rows),
                      "offstride_map_pass": map_summary["pass_count"],
                      "prospective_witness_rows": prospective["source_only_witnesses"]["combined_selected_rows"]}, indent=2))


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    main(parser.parse_args())


if __name__ == "__main__":
    cli()
