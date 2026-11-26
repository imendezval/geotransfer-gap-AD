"""Reproduce the German-200 source-supply census and freeze the next queue.

This reads the frozen source-only protocol and the measured first-batch ledger.
It does not run scene conversion, admission, planner, or rollout validation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from geotransfer_gap.config import PROJECT_ROOT
from geotransfer_gap.corpus import freeze_random_interactive_v1 as freeze
from geotransfer_gap.corpus.source_only_protocol import independence_conflicts

DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "german_200_v1_workstream_d"
QUEUE_PATH = PROJECT_ROOT / "artifacts" / "german_200_v1" / "queues.json"
FIRST_BATCH_PATH = PROJECT_ROOT / "artifacts" / "german_200_v1" / "first_batch.json"
B_DIR = PROJECT_ROOT / "artifacts" / "german_200_v1_workstream_b"
LEDGER_PATH = B_DIR / "batch_ledger.json"
RUN_REPORT_PATH = B_DIR / "batch_run_report.json"
REVIEW_PATH = B_DIR / "human_review_manifest.json"
ARMS = ("Interactive100", "Random100")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def recording_concentration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(int(row["recording"]) for row in rows)
    n = len(rows)
    hhi = sum((count / n) ** 2 for count in counts.values()) if n else None
    return {
        "distinct_recordings": len(counts),
        "recording_counts": {str(key): counts[key] for key in sorted(counts)},
        "top_5_recordings": [
            {"recording": recording, "count": count, "share": count / n}
            for recording, count in counts.most_common(5)
        ],
        "largest_recording_count": max(counts.values(), default=0),
        "largest_recording_share": max(counts.values(), default=0) / n if n else None,
        "recording_hhi": hhi,
        "effective_recording_count_1_over_hhi": (1 / hhi) if hhi else None,
    }


def distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_arm: dict[str, Any] = {}
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        locations = Counter(int(row["location"]) for row in arm_rows)
        splits = Counter(row.get("split", "unknown") for row in arm_rows)
        families = Counter(
            family
            for row in arm_rows
            for family in (row.get("source_task_families") or ["unreviewed_random_source_candidate"])
        )
        moving_counts = [len(set(map(int, row.get("moving_track_ids", ())))) for row in arm_rows]
        context_counts = [len(row.get("source_context_actors", ())) for row in arm_rows]
        sorted_moving = sorted(moving_counts)
        per_arm[arm] = {
            "rows": len(arm_rows),
            "by_location": {str(loc): locations.get(loc, 0) for loc in (1, 2, 3, 4)},
            "by_split": dict(sorted(splits.items())),
            "family_row_memberships": dict(sorted(families.items())),
            "rows_without_interaction_family": sum(not row.get("source_task_families") for row in arm_rows),
            "recording_concentration": recording_concentration(arm_rows),
            "moving_actor_list_size": {
                "minimum": min(moving_counts, default=0),
                "median": sorted_moving[(len(sorted_moving) - 1) // 2] if sorted_moving else None,
                "maximum": max(moving_counts, default=0),
                "mean": sum(moving_counts) / len(moving_counts) if moving_counts else None,
            },
            "full_source_context_actor_list_size": {
                "minimum": min(context_counts, default=0),
                "maximum": max(context_counts, default=0),
            },
        }
    location_counts = Counter(int(row["location"]) for row in rows)
    return {
        "rows": len(rows),
        "by_location": {str(loc): location_counts.get(loc, 0) for loc in (1, 2, 3, 4)},
        "by_arm": per_arm,
        "all_arm_recording_concentration": recording_concentration(rows),
    }


def independence_audit(rows: list[dict[str, Any]], anchors: list[dict[str, Any]]) -> dict[str, Any]:
    """Check exact complete moving lists, inclusive intervals, and shared actors."""
    identity_counts = Counter(row["source_window_identity_sha256"] for row in rows)
    list_mismatches = []
    retained = list(anchors)
    conflicts_found = []
    for row in rows:
        exact_moving = sorted(
            int(actor["track_id"])
            for actor in row.get("source_context_actors", ())
            if actor.get("moving") is True
        )
        frozen_moving = sorted(set(map(int, row.get("moving_track_ids", ()))))
        if exact_moving != frozen_moving:
            list_mismatches.append(row["source_window_identity_sha256"])
        conflicts = independence_conflicts(row, retained)
        if conflicts:
            conflicts_found.append({
                "source_window_identity_sha256": row["source_window_identity_sha256"],
                "conflicts": conflicts,
            })
        retained.append(row)
    return {
        "queue_unique_source_window_identities": len(identity_counts) == len(rows),
        "duplicate_identity_count": sum(count - 1 for count in identity_counts.values() if count > 1),
        "moving_actor_lists_exactly_match_full_source_context": not list_mismatches,
        "moving_actor_list_mismatch_identities": list_mismatches,
        "inclusive_interval_and_all_moving_actor_conflict_count_vs_16_anchors_and_each_other": len(conflicts_found),
        "conflicts": conflicts_found,
        "window_contract": {
            "bounds": "inclusive first_frame through first_frame + 225 source frames",
            "sample_count": 91,
            "sample_spacing_source_frames": 2.5,
            "moving_context_scope": "all supported converted-context actors whose exact source path over the inclusive crop is >= 1.0m; no actor cap",
        },
    }


def source_context_reconstruction_audit(
    rows: list[dict[str, Any]],
    random_pool: dict,
    interactive_pool: dict,
) -> dict[str, Any]:
    """Compare frozen actor contexts to a fresh reconstruction from source CSVs."""
    expected: dict[tuple[str, str], tuple[list[int], list[dict[str, Any]]]] = {}
    for arm, pool in (("Random100", random_pool), ("Interactive100", interactive_pool)):
        for phases in pool.values():
            for candidate in phases:
                key = (arm, candidate["source_window_identity_sha256"])
                context = candidate.get("source_context_actors", [])
                moving = sorted(int(actor["track_id"]) for actor in context if actor.get("moving") is True)
                previous = expected.get(key)
                if previous is not None and previous != (moving, context):
                    raise ValueError(f"reconstructed source context is inconsistent for {key}")
                expected[key] = (moving, context)
    missing = []
    actor_list_mismatches = []
    full_context_mismatches = []
    for row in rows:
        key = (row["arm"], row["source_window_identity_sha256"])
        reconstructed = expected.get(key)
        if reconstructed is None:
            missing.append(key[1])
            continue
        moving, context = reconstructed
        if sorted(set(map(int, row.get("moving_track_ids", ())))) != moving:
            actor_list_mismatches.append(key[1])
        if row.get("source_context_actors", []) != context:
            full_context_mismatches.append(key[1])
    return {
        "rows_reconstructed_from_raw_source": len(rows) - len(missing),
        "frozen_rows_missing_from_reconstructed_population": missing,
        "moving_actor_list_mismatch_count": len(actor_list_mismatches),
        "moving_actor_list_mismatch_identities": actor_list_mismatches,
        "full_source_context_mismatch_count": len(full_context_mismatches),
        "full_source_context_mismatch_identities": full_context_mismatches,
        "reconstruction_method": "freeze_random_interactive_v1._prepare_candidates and _make_row, sourcing all supported converted-context actors from raw source track CSVs; moving actor IDs are exact context actors with the source path threshold applied; no actor cap",
    }


def conflict_rollup(rejections: list[dict[str, Any]]) -> dict[str, Any]:
    phase_counts = Counter()
    pair_counts = Counter()
    exhausted_units = 0
    conflict_phase_count = 0
    for record in rejections:
        if record.get("reason") == "no_independent_eligible_source_phase":
            exhausted_units += 1
            continue
        if record.get("reason") != "source_independence_conflict":
            continue
        conflict_phase_count += 1
        conflicts = record.get("conflicts", ())
        any_interval = any(item.get("inclusive_window_overlap") is True for item in conflicts)
        any_shared = any(bool(item.get("shared_moving_track_ids")) for item in conflicts)
        if any_interval and any_shared:
            phase_counts["both_interval_and_shared_actor"] += 1
        elif any_interval:
            phase_counts["interval_only"] += 1
        elif any_shared:
            phase_counts["shared_actor_only"] += 1
        for item in conflicts:
            overlap = item.get("inclusive_window_overlap") is True
            shared = bool(item.get("shared_moving_track_ids"))
            if overlap and shared:
                pair_counts["both_interval_and_shared_actor"] += 1
            elif overlap:
                pair_counts["interval_only"] += 1
            elif shared:
                pair_counts["shared_actor_only"] += 1
    return {
        "conflicting_candidate_phases": conflict_phase_count,
        "units_with_no_independent_phase": exhausted_units,
        "phase_classification": dict(sorted(phase_counts.items())),
        "conflicting_retained_row_pair_classification": dict(sorted(pair_counts.items())),
        "classification_note": "Phase classes indicate any interval and/or shared-actor reason among all conflicts logged for that candidate phase; pair classes are per prior-row conflict. These are not additive distinct-unit loss counts.",
    }


def selector_coverage(eligible_windows: dict) -> dict[str, Any]:
    catalog_keys: set[tuple[int, int, int]] = set()
    references = Counter()
    unique_windows: dict[str, set[tuple[int, int, int]]] = {}
    for name in freeze.CATALOG_FILES:
        data = load(freeze.AUDITS / name)
        for row in data["windows"]:
            catalog_keys.add((int(row["recording"]), int(row["ego_track_id"]), int(row["first_frame"])))
    for name in freeze.SELECTOR_FILES:
        data = load(freeze.AUDITS / name)
        if name == "third_family_event_fine_selection_v1.json":
            rows = data.get("jobs", [])
        elif "source_positive_pairs" in data:
            rows = data["source_positive_pairs"]
        else:
            rows = data.get("jobs", [])
        for row in rows:
            if "actor" not in row:
                continue
            key = (
                int(row["recording"]),
                int(row.get("ego", row.get("ego_track_id"))),
                int(row["first_frame"]),
            )
            if key in eligible_windows:
                label = "on_stride_catalog_and_source_map_eligible"
            elif key in catalog_keys:
                label = "on_stride_catalog_but_not_source_map_eligible"
            elif key[2] % 50 == 0:
                label = "on_stride_not_in_catalog"
            else:
                label = "off_stride_outside_stride50_catalog"
            references[label] += 1
            unique_windows.setdefault(label, set()).add(key)
    return {
        "basis": "selector-positive actor rows in the seven source-only selectors used by the frozen protocol; these are evidence references, not all source interactions",
        "stride_source_frames": 50,
        "row_references_by_category": dict(sorted(references.items())),
        "unique_source_window_keys_by_category": {
            key: len(value) for key, value in sorted(unique_windows.items())
        },
        "interpretation": "Missing selector-to-eligible-catalog joins show sampling or catalog/source/map coverage gaps. Absence does not establish incompatibility.",
    }


def wilson_interval(successes: int, trials: int) -> list[float]:
    if not trials:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = successes / trials
    den = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / den
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / den
    return [max(0.0, center - half), min(1.0, center + half)]


def first_batch_supply(ledger: dict, run_report: dict, review: dict) -> dict[str, Any]:
    results = ledger.get("results", ())
    primary_statuses = Counter(result.get("status", "unknown") for result in results)
    fallbacks = [
        result.get("phase_fallback", {}).get("result")
        for result in results
        if isinstance(result.get("phase_fallback", {}).get("result"), dict)
    ]
    fallback_statuses = Counter(result.get("status", "unknown") for result in fallbacks)
    tech_passes = sum(
        result.get("technical_admission", {}).get("technical_admitted") is True
        for result in results
    )
    by_arm: dict[str, Any] = {}
    for arm in ARMS:
        arm_rows = [result for result in results if result.get("frozen_row", {}).get("arm") == arm]
        n = len(arm_rows)
        passed = sum(result.get("technical_admission", {}).get("technical_admitted") is True for result in arm_rows)
        source_rejected = sum(
            result.get("status") in {"source_geometry_rejection", "source_physical_rejection"}
            for result in arm_rows
        )
        eligible = n - source_rejected
        statuses = Counter(result.get("status", "unknown") for result in arm_rows)
        interval = wilson_interval(passed, n)
        p = passed / n if n else 0.0
        by_arm[arm] = {
            "primary_attempts": n,
            "primary_status_counts": dict(sorted(statuses.items())),
            "source_rejected": source_rejected,
            "non_source_rejected_denominator_including_review_blocked": eligible,
            "technical_gate_passes_pending_human_review": passed,
            "raw_technical_gate_pass_fraction_of_attempts": passed / n if n else None,
            "technical_gate_pass_fraction_of_non_source_rejected": passed / eligible if eligible else None,
            "illustrative_wilson_95_rate_interval_raw_attempts": interval,
            "point_scaled_to_all_100_frozen_rows": 100 * p,
            "illustrative_rate_interval_scaled_to_all_100_rows": [100 * value for value in interval],
            "point_scaled_to_88_unattempted_rows": 88 * p,
            "illustrative_rate_interval_scaled_to_88_unattempted_rows": [88 * value for value in interval],
        }
    review_rows = review.get("review_candidates", ())
    return {
        "first_batch_only": True,
        "primary_frozen_count": run_report.get("primary_frozen_count"),
        "primary_attempted_count": len(results),
        "unattempted_frozen_primary_rows_deferred": max(0, 200 - len(results)),
        "primary_status_counts": dict(sorted(primary_statuses.items())),
        "primary_source_rejected_count": primary_statuses.get("source_geometry_rejection", 0) + primary_statuses.get("source_physical_rejection", 0),
        "primary_technical_gate_pass_count_pending_human_review": tech_passes,
        "primary_final_manual_admissions_recorded": 0,
        "manual_reviews_created": review.get("manual_reviews_created", False),
        "human_review_manifest_rows_primary_and_fallback": len(review_rows),
        "primary_awaiting_human_review": primary_statuses.get("awaiting_human_review", 0),
        "primary_review_blocked": primary_statuses.get("review_blocked", 0),
        "prespecified_fallbacks_total": run_report.get("fallback_prespecified_count"),
        "fallback_attempted": len(fallbacks),
        "fallback_unattempted_prespecified": max(0, int(run_report.get("fallback_prespecified_count", 0)) - len(fallbacks)),
        "fallback_status_counts": dict(sorted(fallback_statuses.items())),
        "fallback_technical_gate_pass_count": sum(
            result.get("technical_admission", {}).get("technical_admitted") is True
            for result in fallbacks
        ),
        "fallback_policy": run_report.get("fallback_policy"),
        "per_arm": by_arm,
        "descriptive_supply_scenarios": {
            "assumption": "Only the 12 measured first-batch attempts per arm are used as a deliberately stratified, nonrepresentative descriptive rate. Wilson intervals illustrate small-sample rate uncertainty under an iid simplification; deterministic selection and source/family/site mix can violate iid. Not a forecast.",
            "rates_are_not_pooled": True,
            "counted_outcome": "technical gate pass awaiting human review, not final human-approved admission",
            "fallbacks_excluded_from_rates": True,
        },
        "counts_definition": {
            "source_rejected": "source_geometry_rejection + source_physical_rejection",
            "technical_gate_pass": "technical_admission.technical_admitted == true; all such first-batch primaries await human review",
            "review_blocked": "not counted as a technical pass or final admission",
            "deferred": "frozen primary rows not attempted in the 24-row first batch; human-review-pending rows are reported separately",
        },
    }


def make_next_queue(queue: dict, first_batch: dict, size_per_arm: int, output_dir: Path) -> dict[str, Any]:
    first_ids = {row["source_window_identity_sha256"] for row in first_batch.get("candidates", ())}
    envelopes = {}
    candidates = []
    for arm in ARMS:
        ranked = [row for row in queue.get("candidates", ()) if row.get("arm") == arm]
        remaining = [row for row in ranked if row["source_window_identity_sha256"] not in first_ids]
        selected = remaining[:size_per_arm]
        arm_candidates = [dict(row, next_queue_order=i + 1) for i, row in enumerate(selected)]
        envelopes[arm] = {
            "protocol_version": queue["protocol_version"],
            "selection": f"First {size_per_arm} frozen primary rows in original deterministic {arm} rank order after excluding only immutable first-batch source-window identities.",
            "outcome_conditioned_selection": False,
            "candidate_count": len(arm_candidates),
            "ordered_source_window_identity_sha256": [row["source_window_identity_sha256"] for row in arm_candidates],
        }
        candidates.extend(dict(row, queue_order=len(candidates) + i + 1) for i, row in enumerate(arm_candidates))
    legacy_path = output_dir / "next_validation_queue_v1_arm_envelopes.json"
    return {
        "schema_version": 1,
        "protocol": "german_200_next_source_only_validation_queue_v1",
        "source_queue_path": str(QUEUE_PATH.relative_to(PROJECT_ROOT)),
        "source_queue_sha256": sha256(QUEUE_PATH),
        "frozen_first_batch_path": str(FIRST_BATCH_PATH.relative_to(PROJECT_ROOT)),
        "frozen_first_batch_sha256": sha256(FIRST_BATCH_PATH),
        "selection_scope": "Top-level candidates are ordered Interactive100 first, then Random100, preserving each arm's frozen rank order. No filtering beyond excluding immutable first-batch identities; no outcome-conditioned selection.",
        "total_candidate_count": sum(value["candidate_count"] for value in envelopes.values()),
        "candidates": candidates,
        "envelopes": envelopes,
        "previous_envelope_queue_archive": {
            "path": str(legacy_path.relative_to(PROJECT_ROOT)),
            "sha256": sha256(legacy_path) if legacy_path.is_file() else None,
            "preserved_before_flattening": legacy_path.is_file(),
        },
    }


def build_report(output_dir: Path, next_per_arm: int = 12) -> dict[str, Any]:
    queue = load(QUEUE_PATH)
    first_batch = load(FIRST_BATCH_PATH)
    ledger = load(LEDGER_PATH)
    run_report = load(RUN_REPORT_PATH)
    review = load(REVIEW_PATH)
    rows = queue["candidates"]
    anchors = queue["frozen_16_identity_rows"]

    # Rebuild the complete source-only candidate pools with frozen helpers.
    # This creates uncapped standalone and cross-arm greedy witnesses using
    # exact source contexts and complete moving-actor lists.
    eligible_windows, catalog_summary, preflight_summary = freeze._eligible_sources()
    interaction_pool, selector_inputs, selector_row_counts, exact_selector_rows = freeze._load_interaction_pool(eligible_windows)
    random_pool, interactive_pool = freeze._prepare_candidates(eligible_windows, interaction_pool)
    interactive_alone, interactive_units_alone, interactive_rejections_alone = freeze._choose_arm(
        interactive_pool, "Interactive100", list(anchors), "task_key"
    )
    random_alone, random_units_alone, random_rejections_alone = freeze._choose_arm(
        random_pool, "Random100", list(anchors), "recording_ego_key"
    )
    interactive_cross, interactive_units_cross, interactive_rejections_cross = freeze._choose_arm(
        interactive_pool, "Interactive100", list(anchors), "task_key"
    )
    random_cross, random_units_cross, random_rejections_cross = freeze._choose_arm(
        random_pool, "Random100", list(anchors) + interactive_cross, "recording_ego_key"
    )

    next_path = output_dir / "next_validation_queue.json"
    legacy_path = output_dir / "next_validation_queue_v1_arm_envelopes.json"
    if next_path.is_file():
        existing_bytes = next_path.read_bytes()
        existing = json.loads(existing_bytes)
        if isinstance(existing.get("envelopes"), dict) and not isinstance(existing.get("candidates"), list):
            if legacy_path.is_file() and legacy_path.read_bytes() != existing_bytes:
                raise ValueError("Versioned arm-envelope queue archive already exists with different bytes")
            if not legacy_path.exists():
                legacy_path.write_bytes(existing_bytes)
    next_queue = make_next_queue(queue, first_batch, next_per_arm, output_dir)
    write_json(next_path, next_queue)
    source_path = PROJECT_ROOT / "src" / "geotransfer_gap" / "corpus" / "freeze_random_interactive_v1.py"
    helper_path = PROJECT_ROOT / "src" / "geotransfer_gap" / "corpus" / "source_only_protocol.py"
    census_path = PROJECT_ROOT / "src" / "geotransfer_gap" / "corpus" / "census_german_200_v1.py"
    return {
        "schema_version": 1,
        "protocol": "german_200_v1_source_supply_census_v1",
        "analysis_only": True,
        "source_queue": {
            "path": str(QUEUE_PATH.relative_to(PROJECT_ROOT)),
            "sha256": sha256(QUEUE_PATH),
            "protocol_version": queue.get("protocol_version"),
            "seed": queue.get("seed"),
            "candidate_rows": len(rows),
            "candidates_by_arm": dict(Counter(row.get("arm") for row in rows)),
            "population_ledger": queue["source_population_ledger"],
            "baseline_anchor_count": len(anchors),
        },
        "reproducibility_inputs": {
            "census_script": {"path": str(census_path.relative_to(PROJECT_ROOT)), "sha256": sha256(census_path)},
            "producer": {"path": str(source_path.relative_to(PROJECT_ROOT)), "sha256": sha256(source_path)},
            "identity_and_independence_helpers": {"path": str(helper_path.relative_to(PROJECT_ROOT)), "sha256": sha256(helper_path)},
            "catalogs": catalog_summary,
            "map_preflights": preflight_summary,
            "interaction_selectors": selector_inputs,
            "selector_input_row_counts": selector_row_counts,
            "selector_exact_eligible_row_counts": exact_selector_rows,
        },
        "queue_distribution": distribution(rows),
        "frozen_queue_independence_audit": independence_audit(rows, anchors),
        "source_context_reconstruction_audit": source_context_reconstruction_audit(rows, random_pool, interactive_pool),
        "greedy_source_only_witnesses": {
            "standalone_by_arm_against_only_frozen_16_anchors": {
                "Interactive100": {
                    "eligible_task_units": len(interactive_pool),
                    "greedy_independent_units": len(interactive_units_alone),
                    "greedy_source_window_witness_rows": len(interactive_alone),
                    "loss_rollup": conflict_rollup(interactive_rejections_alone),
                },
                "Random100": {
                    "eligible_recording_ego_units": len(random_pool),
                    "greedy_independent_units": len(random_units_alone),
                    "greedy_source_window_witness_rows": len(random_alone),
                    "loss_rollup": conflict_rollup(random_rejections_alone),
                },
            },
            "cross_arm_interactive_first_against_frozen_16_anchors": {
                "Interactive100": {
                    "greedy_independent_units": len(interactive_units_cross),
                    "greedy_source_window_witness_rows": len(interactive_cross),
                    "loss_rollup": conflict_rollup(interactive_rejections_cross),
                },
                "Random100": {
                    "eligible_recording_ego_units": len(random_pool),
                    "greedy_independent_units": len(random_units_cross),
                    "greedy_source_window_witness_rows": len(random_cross),
                    "loss_rollup": conflict_rollup(random_rejections_cross),
                },
                "combined_greedy_source_window_witness_rows": len(interactive_cross) + len(random_cross),
                "interpretation": "Order-dependent greedy witness under the frozen arm priority and full actor/interval rules; not a maximum independent-set estimate. Frozen v1 keeps 100 rows per arm, whose exact independence is separately checked.",
            },
            "production_frozen_rejection_ledger": {
                arm: conflict_rollup(queue["source_independence_rejections"].get(arm, []))
                for arm in ARMS
            },
        },
        "selector_coverage_gaps": selector_coverage(eligible_windows),
        "first_batch_supply_observation": first_batch_supply(ledger, run_report, review),
        "next_validation_queue": {
            "path": str(next_path.relative_to(PROJECT_ROOT)),
            "sha256": sha256(next_path),
            "candidate_count": next_queue["total_candidate_count"],
            "by_arm": {arm: envelope["candidate_count"] for arm, envelope in next_queue["envelopes"].items()},
            "selection_is_outcome_conditioned": False,
        },
        "workstream_c": {
            "status": "not integrated in this census; protocol-specific proofs were in progress",
            "unrun_candidates": "unknown until scoped C evidence is available; no inference of pass, failure, or incompatibility from absence",
        },
        "limits": [
            "Catalog coverage is stride-50; off-stride selector evidence is reported as a sampling gap, not as ineligibility or incompatibility.",
            "The source-only greedy witness is order-dependent and does not establish a maximum.",
            "The first batch was small, arm-balanced, source-stratified, and nonrepresentative. Per-arm rate scenarios are descriptive only; historical rates are not pooled.",
            "Technical gate passes await human review; manual_reviews_created is false, so no final manually approved admission is counted.",
            "No conversion, admission, planner, rollout, or new live validation was run by this census.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    dist = report["queue_distribution"]
    witness = report["greedy_source_only_witnesses"]
    standalone = witness["standalone_by_arm_against_only_frozen_16_anchors"]
    cross = witness["cross_arm_interactive_first_against_frozen_16_anchors"]
    supply = report["first_batch_supply_observation"]
    coverage = report["selector_coverage_gaps"]
    sites = ", ".join(f"L{loc}: {count}" for loc, count in dist["by_location"].items())
    interactive_families = ", ".join(
        f"{family}: {count}"
        for family, count in dist["by_arm"]["Interactive100"]["family_row_memberships"].items()
    )
    cross_losses = report["greedy_source_only_witnesses"]["cross_arm_interactive_first_against_frozen_16_anchors"]
    interactive_pair_loss = cross_losses["Interactive100"]["loss_rollup"]["conflicting_retained_row_pair_classification"]
    random_pair_loss = cross_losses["Random100"]["loss_rollup"]["conflicting_retained_row_pair_classification"]
    interactive_recordings = dist["by_arm"]["Interactive100"]["recording_concentration"]
    random_recordings = dist["by_arm"]["Random100"]["recording_concentration"]
    combined_recordings = dist["all_arm_recording_concentration"]
    lines = [
        "# German-200 v1 source supply census",
        "",
        "Reproduce with PYTHONPATH=src .venv/bin/python -m geotransfer_gap.corpus.census_german_200_v1. This reads frozen source artifacts and runs source-only selection analysis; it does not execute scene validation.",
        "",
        "## Frozen queue and source-only witness",
        "",
        f"The frozen queue contains {dist['rows']} primaries: {dist['by_arm']['Interactive100']['rows']} Interactive100 and {dist['by_arm']['Random100']['rows']} Random100. Location counts are {sites}. Interactive family row memberships are {interactive_families}. Random rows are unreviewed source candidates, not interaction positives. Interactive candidates span {interactive_recordings['distinct_recordings']} recordings (largest recording: {interactive_recordings['largest_recording_count']}/100); Random spans {random_recordings['distinct_recordings']} (largest: {random_recordings['largest_recording_count']}/100). Combined, the 200 rows span {combined_recordings['distinct_recordings']} recordings, with {combined_recordings['largest_recording_count']} rows from the most represented recording.",
        "",
        "All 200 frozen primaries were rebuilt from raw source tracks with the frozen helper. The census verifies each frozen full context and moving-actor ID list against that fresh reconstruction, then checks every inclusive interval/shared moving actor against the 16 anchors and all retained primaries.",
        "",
        f"No-cap greedy runs against the 16 anchors give standalone witnesses of {standalone['Interactive100']['greedy_source_window_witness_rows']} Interactive and {standalone['Random100']['greedy_source_window_witness_rows']} Random rows. Interactive-first cross-arm greedy selection gives {cross['Interactive100']['greedy_source_window_witness_rows']} + {cross['Random100']['greedy_source_window_witness_rows']} = {cross['combined_greedy_source_window_witness_rows']}. These are order-dependent witnesses, not maximum independent-set sizes.",
        "",
        "## Independence losses and coverage gaps",
        "",
        f"In the uncapped cross-arm greedy run, Interactive loses {cross_losses['Interactive100']['loss_rollup']['units_with_no_independent_phase']} task units and Random loses {cross_losses['Random100']['loss_rollup']['units_with_no_independent_phase']} recording/ego units after Interactive is retained. Pair-level reason counts are Interactive {interactive_pair_loss} and Random {random_pair_loss}. No interval-only pair was observed; all logged pair conflicts shared moving actors, with some also overlapping intervals. The machine report also separates conflicting phases and exhausted units. These categories are not additive distinct-unit losses.",
        "",
        f"Selector-positive evidence includes {coverage['row_references_by_category'].get('off_stride_outside_stride50_catalog', 0)} off-stride row references ({coverage['unique_source_window_keys_by_category'].get('off_stride_outside_stride50_catalog', 0)} unique windows) and {coverage['row_references_by_category'].get('on_stride_not_in_catalog', 0)} on-stride references absent from the stride-50 catalog inputs. These indicate sampling/catalog coverage gaps; absence is not incompatibility.",
        "",
        "## First-batch supply observation",
        "",
        f"B attempted 24 primaries and {supply['fallback_attempted']} prespecified alternates. Primary outcomes: {supply['primary_status_counts']}; alternate outcomes: {supply['fallback_status_counts']}. Six primaries passed the technical gate but await human review, three are review-blocked, no manual review was created, and no final manual admission is recorded. {supply['unattempted_frozen_primary_rows_deferred']} frozen primary rows are unattempted.",
        "",
        "The rates below scale only the measured 12 attempts per arm. They are deliberately nonrepresentative descriptive scenarios. Wilson intervals illustrate small-sample uncertainty under an iid simplification, not inferential guarantees. Fallbacks and historical rates are not pooled.",
        "",
        "| Arm | Technical gate passes / 12 | Raw rate | Scaled to 100 frozen rows | Illustrative Wilson range |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        row = supply["per_arm"][arm]
        interval = row["illustrative_rate_interval_scaled_to_all_100_rows"]
        lines.append(
            f"| {arm} | {row['technical_gate_passes_pending_human_review']}/12 | {row['raw_technical_gate_pass_fraction_of_attempts']:.1%} | {row['point_scaled_to_all_100_frozen_rows']:.1f} | {interval[0]:.1f}–{interval[1]:.1f} |"
        )
    lines += [
        "",
        "## Next deterministic source-only queue",
        "",
        f"The machine queue at {report['next_validation_queue']['path']} contains {report['next_validation_queue']['candidate_count']} rows in separate 12-row arm envelopes. Each envelope takes the next frozen ranks after excluding only immutable first-batch source-window identities; outcome fields do not affect selection.",
        "",
        "Workstream C evidence was not yet available when this report was produced. Unrun candidate outcomes remain unknown.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--next-per-arm", type=int, default=12)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(args.output_dir, args.next_per_arm)
    report_path = args.output_dir / "supply_census.json"
    write_json(report_path, report)
    markdown_path = args.output_dir / "assessment.md"
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    summary = {
        "report_path": str(report_path.relative_to(PROJECT_ROOT)),
        "report_sha256": sha256(report_path),
        "assessment_path": str(markdown_path.relative_to(PROJECT_ROOT)),
        "assessment_sha256": sha256(markdown_path),
        "next_queue_path": report["next_validation_queue"]["path"],
        "next_queue_sha256": report["next_validation_queue"]["sha256"],
        "source_queue_rows": report["source_queue"]["candidate_rows"],
        "next_queue_rows": report["next_validation_queue"]["candidate_count"],
        "cross_arm_greedy_witness_rows": report["greedy_source_only_witnesses"]["cross_arm_interactive_first_against_frozen_16_anchors"]["combined_greedy_source_window_witness_rows"],
    }
    write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
