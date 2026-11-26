"""Freeze the source-only Random100 and Interactive100 German cohort queues.

This selector reads source catalogs, source interaction selectors, map
preflights and the frozen 16-scene identity manifest. It never reads planner
outcomes or grants scene admission.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import random

import numpy as np
import pandas as pd

from geotransfer_gap.config import PROJECT_ROOT, settings
from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.corpus.source_only_protocol import (
    WINDOW_SOURCE_FRAMES,
    independence_conflicts,
    source_context_actors,
    source_window_identity,
    source_window_identity_sha256,
    split_label,
)


ARTIFACTS = PROJECT_ROOT / "artifacts"
AUDITS = ARTIFACTS / "audits"
OUTPUT_DIR = ARTIFACTS / "german_200_v1"
SEED = 20261126
PROTOCOL_VERSION = "german_random100_interactive100_source_only_v1"

CATALOG_FILES = (
    "all_moving_windows_loc1_stride50.json",
    "all_moving_windows_loc23_stride50.json",
    "all_moving_windows_loc4_stride50.json",
)
PREFLIGHT_FILES = (
    "source_map_preflight_loc1_oriented_v3.json",
    "source_map_preflight_loc23_oriented_v3.json",
    "source_map_preflight_loc4_oriented_v3.json",
)
SELECTOR_FILES = (
    "third_family_event_fine_selection_v1.json",
    "body_task_selection.json",
    "footprint_task_selection.json",
    "fine_phase_task_selection.json",
    "source_restart_selection.json",
    "source_restart_turns_selection.json",
    "source_restart_velocity_selection.json",
)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_rank(*parts):
    payload = canonical_json([PROTOCOL_VERSION, SEED, *parts])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _window_key(recording, ego, first_frame):
    return (int(recording), int(ego), int(first_frame))


def _eligible_sources():
    catalogs, preflights = {}, {}
    catalog_summary = {}
    for name in CATALOG_FILES:
        path = AUDITS / name
        data = json.loads(path.read_text())
        catalog_summary[name] = {
            "sha256": file_sha256(path),
            "schema_version": data.get("schema_version"),
            "input_window_count": len(data["windows"]),
            "source_pass_count": sum(r.get("source_rejection") is None for r in data["windows"]),
        }
        for row in data["windows"]:
            key = _window_key(row["recording"], row["ego_track_id"], row["first_frame"])
            catalogs[key] = row
    preflight_summary = {}
    for name in PREFLIGHT_FILES:
        path = AUDITS / name
        data = json.loads(path.read_text())
        preflight_summary[name] = {
            "sha256": file_sha256(path),
            "schema_version": data.get("schema_version"),
            "input_window_count": len(data["windows"]),
        }
        for row in data["windows"]:
            key = _window_key(row["recording"], row["ego_track_id"], row["first_frame"])
            preflights[key] = row

    windows = {}
    for key, catalog in catalogs.items():
        preflight = preflights.get(key)
        if (
            catalog.get("source_rejection") is not None
            or not catalog.get("source_window_complete")
            or not preflight
            or preflight.get("outside_sample_count") != 0
            or preflight.get("directed_route") is not True
            or preflight.get("source_track_complete") is not True
        ):
            continue
        windows[key] = {"catalog": catalog, "preflight": preflight}
    return windows, catalog_summary, preflight_summary


def _load_interaction_pool(eligible_windows):
    task_windows = defaultdict(dict)
    selector_inputs = []
    selector_row_counts = {}
    exact_candidate_rows = Counter()
    for name in SELECTOR_FILES:
        path = AUDITS / name
        data = json.loads(path.read_text())
        if name == "third_family_event_fine_selection_v1.json":
            rows = data.get("jobs", [])
        elif "source_positive_pairs" in data:
            rows = data["source_positive_pairs"]
        else:
            rows = data.get("jobs", [])
        selector_inputs.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(path),
                "schema_version": data.get("schema_version"),
                "selection": data.get("selection"),
            }
        )
        selector_row_counts[name] = len(rows)
        for row_index, source_row in enumerate(rows):
            if "actor" not in source_row:
                continue
            key = _window_key(
                source_row["recording"], source_row.get("ego", source_row.get("ego_track_id")), source_row["first_frame"]
            )
            if key not in eligible_windows:
                continue
            exact_candidate_rows[name] += 1
            task = (key[0], key[1], int(source_row["actor"]))
            window = task_windows[task].setdefault(
                key,
                {
                    "selector_rows": [],
                    "selector_names": set(),
                    "interaction_families": set(),
                    "interaction_source_kinds": set(),
                },
            )
            evidence = source_row.get("task_evidence") or {}
            kind = evidence.get("kind")
            family = _family_for_kind(kind, source_row)
            window["selector_rows"].append(
                {
                    "selector": name,
                    "source_row_index": int(row_index),
                    "source_row": source_row,
                }
            )
            window["selector_names"].add(name)
            if family:
                window["interaction_families"].add(family)
            if kind:
                window["interaction_source_kinds"].add(kind)
    return task_windows, selector_inputs, selector_row_counts, dict(exact_candidate_rows)


def _family_for_kind(kind, row):
    text = str(kind or "")
    if text.startswith("cyclist") or row.get("actor_class") == "bicycle":
        return "cyclist_crossing"
    if text.startswith("pedestrian") or row.get("actor_class") == "pedestrian":
        return "pedestrian_crossing"
    if text.startswith("lead_vehicle") or row.get("actor_class") in ("car", "truck_bus"):
        return "longitudinal_following"
    return None


def _load_recording_source(recording):
    source = settings().source
    stem = source / "data" / f"{recording:02d}"
    tracks_path = stem.with_name(stem.name + "_tracks.csv")
    meta_path = stem.with_name(stem.name + "_tracksMeta.csv")
    recording_path = stem.with_name(stem.name + "_recordingMeta.csv")
    frame = pd.read_csv(
        tracks_path,
        usecols=["frame", "trackId", "xCenter", "yCenter", "heading", "xVelocity", "yVelocity"],
    )
    tracks = {
        int(track_id): group[["frame", "xCenter", "yCenter", "heading", "xVelocity", "yVelocity"]].to_numpy(dtype=float)
        for track_id, group in frame.groupby("trackId", sort=False)
    }
    with meta_path.open(newline="") as stream:
        track_meta = {int(row["trackId"]): row for row in csv.DictReader(stream)}
    with recording_path.open(newline="") as stream:
        recording_meta = next(csv.DictReader(stream))
    osm, xodr = map_geometry.map_paths(recording_meta, recording)
    background = source / "data" / f"{recording:02d}_background.png"
    hashes = {
        "tracks_csv_sha256": file_sha256(tracks_path),
        "tracks_meta_csv_sha256": file_sha256(meta_path),
        "recording_meta_csv_sha256": file_sha256(recording_path),
        "background_png_sha256": file_sha256(background) if background.is_file() else None,
        "lanelet2_map_sha256": file_sha256(osm) if osm.is_file() else None,
        "opendrive_map_sha256": file_sha256(xodr) if xodr.is_file() else None,
        "source_paths": {
            "tracks_csv": str(tracks_path),
            "tracks_meta_csv": str(meta_path),
            "recording_meta_csv": str(recording_path),
            "background_png": str(background),
            "lanelet2_map": str(osm),
            "opendrive_map": str(xodr),
        },
    }
    return tracks, track_meta, hashes


def _make_row(arm, window_key, eligible_windows, actor, recording_data, selector_window=None):
    recording, ego, first_frame = window_key
    catalog = eligible_windows[window_key]["catalog"]
    preflight = eligible_windows[window_key]["preflight"]
    tracks, track_meta, source_hashes = recording_data[recording]
    source_identity = {
        "recording": recording,
        "location": int(catalog["location"]),
        "ego_track_id": ego,
        "first_frame": first_frame,
        "last_frame": first_frame + WINDOW_SOURCE_FRAMES,
    }
    context = source_context_actors(source_identity, tracks, track_meta)
    context_by_id = {a["track_id"]: a for a in context}
    moving_track_ids = [a["track_id"] for a in context if a["moving"]]
    source_actor_id = int(actor) if actor is not None else None
    if source_actor_id is not None:
        source_actor = context_by_id.get(source_actor_id)
        if source_actor is None:
            source_actor = {
                "track_id": source_actor_id,
                "class": track_meta.get(source_actor_id, {}).get("class"),
                "included_in_converted_context": False,
                "moving": False,
            }
        else:
            source_actor = dict(source_actor, included_in_converted_context=True)
    else:
        source_actor = None
    identity_sha = source_window_identity_sha256(source_identity)
    selector_rows = selector_window.get("selector_rows", []) if selector_window else []
    families = sorted(selector_window.get("interaction_families", ())) if selector_window else []
    row = {
        "arm": arm,
        "source_window_identity": source_identity,
        "source_window_identity_sha256": identity_sha,
        "recording": recording,
        "location": int(catalog["location"]),
        "ego_track_id": ego,
        "actor": source_actor_id,
        "first_frame": first_frame,
        "last_frame": first_frame + WINDOW_SOURCE_FRAMES,
        "split": split_label(catalog["location"], recording),
        "source_task_families": families,
        "source_interaction_kinds": sorted(selector_window.get("interaction_source_kinds", ())) if selector_window else [],
        "source_selector_names": sorted(selector_window.get("selector_names", ())) if selector_window else [],
        "selector_evidence": selector_rows,
        "source_actor": source_actor,
        "context_actor_ids": [a["track_id"] for a in context],
        "moving_track_ids": moving_track_ids,
        "source_context_actors": context,
        "source_context_actor_count": len(context),
        "source_moving_context_actor_count": len(moving_track_ids),
        "source_context_reconstruction": {
            "coverage": "exact_source_reconstruction_from_converter_definition",
            "definition": "supported class; at least 2 raw rows and 2 valid samples of 91; raw trimmed-row path length >=1.0m",
            "raw_frame_crop_inclusive": [first_frame, first_frame + WINDOW_SOURCE_FRAMES],
            "movement_threshold_m": 1.0,
        },
        "source_catalog_metadata": {
            "ego_class": catalog.get("ego_class"),
            "ego_path_m": catalog.get("ego_path_m"),
            "ego_displacement_m": catalog.get("ego_displacement_m"),
            "turn_rad": catalog.get("turn_rad"),
            "maneuver_stratum": "turning_candidate" if abs(float(catalog.get("turn_rad") or 0.0)) >= 0.35 else "straight_or_mild_turn",
            "first_goal_radius_step": catalog.get("first_goal_radius_step"),
            "nearby_actor_count_within_12m": catalog.get("nearby_actor_count"),
            "nearby_moving_actor_count_within_12m": catalog.get("nearby_moving_actor_count"),
            "nearby_vru_count_within_12m": catalog.get("nearby_vru_count"),
            "catalog_nearest_actors_within_12m": catalog.get("nearest_actors", []),
        },
        "source_map_preflight": {
            "outside_sample_count": preflight.get("outside_sample_count"),
            "directed_route": preflight.get("directed_route"),
            "source_track_complete": preflight.get("source_track_complete"),
            "nearest_start_lane": preflight.get("nearest_start_lane"),
            "nearest_goal_lane": preflight.get("nearest_goal_lane"),
            "source_nearby_moving_actors": preflight.get("source_nearby_moving_actors"),
            "source_nearby_vrus": preflight.get("source_nearby_vrus"),
        },
        "source_hashes": source_hashes,
        "rule_applicability": "pending_source_review",
        "planner_outcomes_present": False,
    }
    return row


def _prepare_candidates(eligible_windows, interaction_pool):
    recordings = sorted({key[0] for key in eligible_windows})
    recording_data = {recording: _load_recording_source(recording) for recording in recordings}
    random_groups = defaultdict(list)
    for key in eligible_windows:
        random_groups[(key[0], key[1])].append(key)
    random_candidates = {}
    for unit, keys in random_groups.items():
        keys = sorted(keys, key=lambda key: (key[2], key[0], key[1]))
        random_candidates[unit] = [
            _make_row("Random100", key, eligible_windows, None, recording_data)
            for key in keys
        ]
    interactive_candidates = {}
    for task, windows in interaction_pool.items():
        rows = []
        for key, selector_window in sorted(windows.items()):
            rows.append(_make_row("Interactive100", key, eligible_windows, task[2], recording_data, selector_window))
        if rows:
            interactive_candidates[task] = rows
    return random_candidates, interactive_candidates


def _choose_arm(candidates, arm, retained, key_kind):
    units = sorted(candidates, key=lambda unit: (stable_rank(arm, "unit", list(unit)), list(unit)))
    selected = []
    selected_units = []
    rejected = []
    for unit in units:
        phases = sorted(
            candidates[unit],
            key=lambda row: (
                stable_rank(arm, "phase", list(unit), row["source_window_identity_sha256"]),
                row["first_frame"],
            ),
        )
        chosen = None
        for phase_index, row in enumerate(phases):
            conflicts = independence_conflicts(row, retained)
            if conflicts:
                rejected.append(
                    {
                        "arm": arm,
                        "unit": list(unit),
                        "source_window_identity_sha256": row["source_window_identity_sha256"],
                        "reason": "source_independence_conflict",
                        "conflicts": conflicts,
                    }
                )
                continue
            chosen = row
            alternate_rows = []
            for alternate_order, alternate in enumerate(
                (phase for phase in phases if phase is not row), 1
            ):
                alternate_rows.append(
                    {
                        "replacement_order": alternate_order,
                        "replacement_rule": "pre-execution only; require unchanged source/task eligibility and recheck inclusive-window plus all-moving-track independence against retained primaries",
                        "candidate": alternate,
                    }
                )
            chosen["alternate_source_windows"] = alternate_rows
            chosen["selection_unit"] = {key_kind: list(unit)}
            chosen["selection_rank_sha256"] = stable_rank(arm, "unit", list(unit))
            chosen["randomized_phase_order_sha256"] = stable_rank(arm, "phase-order", list(unit))
            break
        if chosen is None:
            rejected.append(
                {"arm": arm, "unit": list(unit), "reason": "no_independent_eligible_source_phase"}
            )
            continue
        selected.append(chosen)
        selected_units.append(list(unit))
        retained.append(chosen)
    return selected, selected_units, rejected


def _batch_rows(candidates, count=24):
    """Select a fixed, source-diverse initial run batch from the frozen queues."""
    random_rows = [r for r in candidates if r["arm"] == "Random100"]
    interactive_rows = [r for r in candidates if r["arm"] == "Interactive100"]
    chosen = []
    used = set()

    def add_best(pool, target_arm, location=None, family=None):
        eligible = [
            r for r in pool
            if r["source_window_identity_sha256"] not in used
            and (location is None or r["location"] == location)
            and (family is None or family in r["source_task_families"])
        ]
        if not eligible:
            return False
        eligible.sort(
            key=lambda r: (
                stable_rank("first-batch", target_arm, location, family, r["source_window_identity_sha256"]),
                r["recording"], r["ego_track_id"], r["first_frame"],
            )
        )
        chosen.append(eligible[0])
        used.add(eligible[0]["source_window_identity_sha256"])
        return True

    # Twelve random windows: three per location where capacity allows.
    for loc in (1, 2, 3, 4):
        for _ in range(3):
            add_best(random_rows, "Random100", location=loc)
    # Twelve interaction candidates, spread across family and location strata.
    families = ("cyclist_crossing", "pedestrian_crossing", "longitudinal_following")
    for loc in (1, 2, 3, 4):
        for family in families:
            add_best(interactive_rows, "Interactive100", location=loc, family=family)
    # Fill remaining slots in deterministic round-robin arm order if a stratum is sparse.
    while len(chosen) < min(count, len(candidates)):
        before = len(chosen)
        for pool, arm in ((random_rows, "Random100"), (interactive_rows, "Interactive100")):
            add_best(pool, arm)
            if len(chosen) >= min(count, len(candidates)):
                break
        if len(chosen) == before:
            break
    # Balance the artifacts: exactly half each when both arms have enough rows.
    # The stratum pass above may be imbalanced; use order-preserving arm quotas.
    if len(random_rows) >= count // 2 and len(interactive_rows) >= count // 2:
        chosen = []
        used = set()
        for pool, arm, quota in ((random_rows, "Random100", count // 2), (interactive_rows, "Interactive100", count - count // 2)):
            strata = []
            if arm == "Random100":
                for loc in (1, 2, 3, 4):
                    strata.extend([(loc, None)] * 3)
            else:
                for loc in (1, 2, 3, 4):
                    for family in families:
                        strata.append((loc, family))
            for loc, family in strata:
                if len([r for r in chosen if r["arm"] == arm]) >= quota:
                    break
                eligible = [
                    r for r in pool
                    if r["source_window_identity_sha256"] not in used
                    and (loc is None or r["location"] == loc)
                    and (family is None or family in r["source_task_families"])
                ]
                eligible.sort(key=lambda r: (stable_rank("first-batch", arm, loc, family, r["source_window_identity_sha256"]), r["source_window_identity_sha256"]))
                if eligible:
                    chosen.append(eligible[0])
                    used.add(eligible[0]["source_window_identity_sha256"])
            while len([r for r in chosen if r["arm"] == arm]) < quota:
                if not add_best(pool, arm):
                    break
        return chosen[:count]
    return chosen[:count]


def build_protocol(output_dir=OUTPUT_DIR, target_per_arm=100, batch_size=24):
    eligible_windows, catalog_summary, preflight_summary = _eligible_sources()
    interaction_pool, selector_inputs, selector_row_counts, selector_exact_counts = _load_interaction_pool(eligible_windows)

    random_groups = defaultdict(list)
    for key in eligible_windows:
        random_groups[(key[0], key[1])].append(key)
    random_candidates, interactive_candidates = _prepare_candidates(eligible_windows, interaction_pool)

    manifest_path = AUDITS / "step2_expanded_current_manifest.json"
    baseline = json.loads(manifest_path.read_text())
    baseline_rows = []
    for row in baseline:
        baseline_rows.append(
            {
                "recording": int(row["recording"]),
                "location": int(row["location"]),
                "ego_track_id": int(row.get("ego_track_id", row.get("ego"))),
                "first_frame": int(row["first_frame"]),
                "last_frame": int(row.get("last_frame", int(row["first_frame"]) + WINDOW_SOURCE_FRAMES)),
                "moving_track_ids": list(map(int, row.get("moving_track_ids", ()))),
                "source_window_identity_sha256": source_window_identity_sha256(row),
                "split": row.get("split"),
            }
        )

    retained = list(baseline_rows)
    interactive, interactive_units, interactive_rejections = _choose_arm(
        interactive_candidates, "Interactive100", retained, "task_key"
    )
    interactive = interactive[:target_per_arm]
    # `_choose_arm` retains all selected candidates in place; trim the retained
    # set to the actual target before selecting Random100.
    retained = list(baseline_rows) + interactive
    random_selected, random_units, random_rejections = _choose_arm(
        random_candidates, "Random100", retained, "recording_ego_key"
    )
    random_selected = random_selected[:target_per_arm]

    # The selector above is greedy and emits one row per independent task/key.
    # If targets are reduced by a caller, the queues still keep deterministic order.
    candidates = interactive + random_selected
    batch = _batch_rows(candidates, batch_size)

    interactive_universe = len(interactive_candidates)
    random_universe = len(random_candidates)
    population = {
        "eligible_stride50_source_windows": len(eligible_windows),
        "random_canonical_rec_ego_population": [
            {
                "recording": unit[0],
                "ego_track_id": unit[1],
                "eligible_phase_identities": [
                    source_window_identity_sha256(
                        {
                            "recording": key[0], "location": eligible_windows[key]["catalog"]["location"],
                            "ego_track_id": key[1], "first_frame": key[2],
                        }
                    )
                    for key in sorted(keys, key=lambda k: k[2])
                ],
            }
            for unit, keys in sorted(random_groups.items())
        ],
        "interactive_canonical_task_population": [
            {
                "recording": task[0],
                "ego_track_id": task[1],
                "actor_track_id": task[2],
                "eligible_phase_identities": [r["source_window_identity_sha256"] for r in rows],
                "families": sorted({family for row in rows for family in row["source_task_families"]}),
                "selectors": sorted({name for row in rows for name in row["source_selector_names"]}),
            }
            for task, rows in sorted(interactive_candidates.items())
        ],
        "interactive_exact_selector_rows_by_file": selector_exact_counts,
        "selector_input_row_counts": selector_row_counts,
    }
    counts_by_arm = {}
    for arm, rows in (("Interactive100", interactive), ("Random100", random_selected)):
        counts_by_arm[arm] = {
            "selected": len(rows),
            "by_location": dict(sorted(Counter(str(r["location"]) for r in rows).items())),
            "by_split": dict(sorted(Counter(r["split"] for r in rows).items())),
            "by_family": dict(sorted(Counter(f for r in rows for f in (r["source_task_families"] or ["unreviewed_random_source_candidate"])).items())),
            "distinct_source_tasks": len({(r["recording"], r["ego_track_id"], r["actor"]) for r in rows}) if arm == "Interactive100" else len({(r["recording"], r["ego_track_id"]) for r in rows}),
        }

    raw_p = {
        "Random100": min(1.0, target_per_arm / random_universe) if random_universe else None,
        "Interactive100": min(1.0, target_per_arm / interactive_universe) if interactive_universe else None,
        "interpretation": "Equal-unit raw draw probability before source-independence constraints and source-phase replacement. Final inclusion is constrained, recorded by the selected/population counts and rejection ledger; it is not asserted to equal this raw probability.",
    }
    inputs = {
        "catalogs": catalog_summary,
        "map_preflights": preflight_summary,
        "interaction_selectors": selector_inputs,
        "frozen_16_manifest": {
            "path": str(manifest_path.relative_to(PROJECT_ROOT)),
            "sha256": file_sha256(manifest_path),
            "rows": len(baseline_rows),
        },
    }
    source_hashes = {}
    for row in candidates:
        source_hashes[str(row["recording"])] = row["source_hashes"]
    result = {
        "schema_version": 1,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_status": "frozen_source_only_candidate_queues_pending_admission",
        "seed": SEED,
        "randomization": {
            "algorithm": "SHA256 ranking over canonical JSON [protocol_version, seed, arm, stage, unit-or-window-identity]; canonical populations sorted numerically before ranking",
            "random_unit": "unique (recording, ego_track_id), with one source phase selected from its SHA-ranked eligible phases",
            "interactive_unit": "unique (recording, ego_track_id, actor_track_id), with one exact selector-positive source phase selected from its SHA-ranked eligible phases",
            "replacement": "A unit whose every eligible phase conflicts with the frozen 16 or already retained primaries is rejected; continue in frozen unit-rank order until target or pool exhaustion. Alternate phases are frozen in randomized order and may replace a primary only before any planner run, after unchanged source/map/task checks and a fresh independence check. No planner outcome may trigger replacement.",
            "priority": "Interactive100 then Random100, preserving the rarer established interaction task pool before equal-key random-window selection.",
            "raw_draw_probability": raw_p,
        },
        "selection_contract": {
            "window_source_frames": WINDOW_SOURCE_FRAMES,
            "window_bounds": "inclusive first_frame through first_frame+225; 91 sampled states at 2.5 source-frame spacing",
            "independence": "For every selected primary, same-recording source windows are non-overlapping under inclusive bounds and all moving converted-context track IDs are disjoint from every other primary and all frozen 16 anchors.",
            "moving_context_definition": "Use converter's `sources.ind.interpolate_actor`: supported class; at least 2 raw rows in the inclusive source crop; at least 2 valid samples among 91; source path length over trimmed raw rows >=1.0m marks moving.",
            "all_locations": [1, 2, 3, 4],
            "location_2": "Retained as annotated candidate data; semantic applicability remains pending source review.",
            "split_policy": "location 4 held out; other recordings divisible by 5 validation; all other recordings adaptation.",
            "recording_cap": None,
            "outcomes_read": False,
        },
        "inputs": inputs,
        "source_population_ledger": population,
        "selected_counts": counts_by_arm,
        "source_independence_rejections": {
            "Interactive100": interactive_rejections,
            "Random100": random_rejections,
        },
        "frozen_16_identity_rows": baseline_rows,
        "source_hashes_by_recording": source_hashes,
        "candidates": candidates,
        "first_batch": {
            "immutable": True,
            "batch_size": len(batch),
            "selection": "Fixed SHA-ranked round-robin across both arms, all available locations, and interactive family strata; chosen only from already frozen independent primary rows.",
            "source_hashes": inputs,
            "candidates": [
                dict(row, first_batch_order=i + 1)
                for i, row in enumerate(batch)
            ],
        },
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "queues.json").write_text(json.dumps(result, indent=2) + "\n")
    (output_dir / "first_batch.json").write_text(
        json.dumps(result["first_batch"], indent=2) + "\n"
    )
    summary = {
        "protocol_version": PROTOCOL_VERSION,
        "seed": SEED,
        "selected_counts": counts_by_arm,
        "first_batch_size": len(batch),
        "first_batch_by_arm": dict(Counter(row["arm"] for row in batch)),
        "first_batch_by_location": dict(Counter(row["location"] for row in batch)),
        "first_batch_interaction_families": dict(Counter(f for row in batch for f in row["source_task_families"])),
        "first_batch_includes_location_2": any(row["location"] == 2 for row in batch),
        "queue_path": str(output_dir / "queues.json"),
        "first_batch_path": str(output_dir / "first_batch.json"),
        "queue_sha256": file_sha256(output_dir / "queues.json"),
        "first_batch_sha256": file_sha256(output_dir / "first_batch.json"),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return result, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--target-per-arm", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=24)
    args = parser.parse_args()
    _, summary = build_protocol(args.output_dir, args.target_per_arm, args.batch_size)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
