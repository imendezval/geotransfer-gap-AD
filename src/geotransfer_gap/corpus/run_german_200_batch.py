"""Run a frozen source-candidate batch through conversion and technical admission.

This runner preserves the input queue as-is. It records semantic applicability
for human interpretation, while technical decisions come only from the current
``validation.admit_scene`` gate. Outputs belong in a separate artifact namespace.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any

import numpy as np

from geotransfer_gap.artifacts import sha256 as sha
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.conversion.pipeline import SOURCE
from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.provenance import converter_fingerprint
from geotransfer_gap.sources.ind import load_tracks
from geotransfer_gap.conversion.pipeline import ConversionConfig
from geotransfer_gap.corpus.source_only_protocol import (
    source_window_identity,
    source_window_identity_sha256,
    source_context_actors,
    independence_conflicts,
)


RUNNER_VERSION = 1
PROTOCOL = "german_200_frozen_mixed_arm_v1"
CONVERSION_ARGS = (
    "--goal-sample",
    "85",
    "--late-mode",
    "runtime_spawn",
    "--static-crop-radius",
    "1000000",
    "--parked-as-static-expert",
    "--emit-crosswalks",
)
PIPELINE_TOOLS = (
    "pilot_ind.py",
    "admit_scene.py",
    "audit_scene.py",
    "audit_map_semantics.py",
    "audit_rule_applicability.py",
    "audit_physical_source.py",
    "validate_replay.py",
    "probe_eval_replay.py",
    "validate_spawn.py",
    "validate_parked.py",
    "trace_eval_lifecycle.py",
    "audit_interaction_fidelity.py",
    "probe_counterfactual.py",
    "probe_hybrid_protocol_parity.py",
    "source_lane_changes.py",
    "register_background.py",
    "render_rule_review.py",
    "scene_contract.py",
    "late_spawn_runtime.py",
    "hybrid_traffic.py",
    "background_route_intent.py",
    "binary.py",
    "ind.py",
    "lanelet.py",
    "config.py",
    "artifacts.py",
    "provenance.py",
    "source_only_protocol.py",
)


def canonical_source_identity(row: dict[str, Any]) -> dict[str, int]:
    return source_window_identity(row)


def identity_digest(identity: dict[str, int]) -> str:
    return source_window_identity_sha256(identity)


def producer_path(name: str) -> Path:
    try:
        return tool_path(name)
    except KeyError:
        local = PROJECT_ROOT / "src/geotransfer_gap/corpus" / name
        if local.is_file():
            return local
        raise


def source_paths(recording: int) -> dict[str, Path]:
    data = SOURCE / "data"
    metadata = data / f"{recording:02d}_recordingMeta.csv"
    paths = {
        "tracks": data / f"{recording:02d}_tracks.csv",
        "tracks_meta": data / f"{recording:02d}_tracksMeta.csv",
        "recording_meta": metadata,
        "background": data / f"{recording:02d}_background.png",
    }
    if metadata.is_file():
        import csv

        with metadata.open() as stream:
            row = next(csv.DictReader(stream))
        osm, xodr = map_geometry.map_paths(row, recording)
        paths["lanelet_map"] = Path(osm)
        paths["opendrive_map"] = Path(xodr)
    else:
        paths["lanelet_map"] = SOURCE / "maps/missing_lanelet_map.osm"
        paths["opendrive_map"] = SOURCE / "maps/missing_opendrive_map.xodr"
    return paths


SOURCE_ALIASES = {
    "tracks": {"tracks", "track", "tracks_csv", "source_tracks", "source_tracks_csv"},
    "tracks_meta": {"tracks_meta", "tracksmeta", "tracks_meta_csv", "source_tracks_meta"},
    "recording_meta": {"recording_meta", "recordingmeta", "recording_meta_csv"},
    "lanelet_map": {"lanelet_map", "lanelet2_map", "source_lanelet2_map", "source_map", "osm"},
    "opendrive_map": {"opendrive_map", "source_opendrive_map", "xodr"},
    "background": {"background", "background_png", "background_image"},
}


def expected_source_hashes(recording: int) -> dict[str, str | None]:
    return {
        name: sha(path) if path.is_file() else None
        for name, path in source_paths(recording).items()
    }


def normalized_hash_name(name: str) -> str | None:
    key = name.lower().replace("-", "_").replace(".", "_")
    for suffix in ("_sha256", "_hash", "_file"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    for canonical, aliases in SOURCE_ALIASES.items():
        if key in aliases:
            return canonical
    return None


def frozen_hash_values(row: dict[str, Any]) -> dict[str, str]:
    raw = row.get("source_hashes", {})
    flattened: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict):
                for inner_key in ("sha256", "hash", "digest"):
                    if inner_key in value:
                        flattened[str(key)] = str(value[inner_key])
                        break
            elif isinstance(value, str):
                flattened[str(key)] = value
    # Accept the same hashes as first-level fields for schema resilience.
    for key, value in row.items():
        if isinstance(value, str) and ("sha256" in key.lower() or "hash" in key.lower()):
            flattened.setdefault(key, value)
    result = {}
    for key, value in flattened.items():
        canonical = normalized_hash_name(key)
        if canonical and len(value) == 64:
            result[canonical] = value
    return result


def verify_source_identity(row: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    try:
        identity = canonical_source_identity(row)
        digest = identity_digest(identity)
        if identity["last_frame"] != identity["first_frame"] + 225:
            problems.append("source_window_not_91_sample_bounds")
        frozen_identity = row.get("source_window_identity")
        if isinstance(frozen_identity, dict) and frozen_identity != identity:
            problems.append("source_window_identity_object_mismatch")
        frozen_digest = row.get("source_window_identity_sha256")
        if frozen_digest != digest:
            problems.append("source_window_identity_hash_mismatch")
    except (KeyError, TypeError, ValueError):
        return ["missing_or_invalid_source_identity_fields"]

    expected = expected_source_hashes(identity["recording"])
    frozen = frozen_hash_values(row)
    for name in ("tracks", "tracks_meta", "recording_meta", "background", "lanelet_map", "opendrive_map"):
        if name not in frozen:
            problems.append(f"frozen_source_hash_missing:{name}")
        elif frozen[name] != expected.get(name):
            problems.append(f"source_bytes_changed:{name}")
    if expected.get("background") is None:
        problems.append("source_background_missing")
    return problems


def get_rows(queue: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("candidates", "rows", "jobs", "scenes"):
        if isinstance(queue.get(key), list):
            return queue[key]
    for key in ("queue", "next_validation_queue", "validation_queue"):
        nested = queue.get(key)
        if isinstance(nested, dict):
            try:
                return get_rows(nested)
            except ValueError:
                continue
    raise ValueError("Frozen queue must contain a candidates/rows/jobs/scenes array")


def independence_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    identity_seen: dict[str, int] = {}
    by_recording: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    problems: dict[int, list[str]] = {i: [] for i in range(len(rows))}
    for i, row in enumerate(rows):
        try:
            identity = canonical_source_identity(row)
            identity_hash = identity_digest(identity)
            if identity_hash in identity_seen:
                prior = identity_seen[identity_hash]
                problems[i].append(f"duplicate_source_window:{prior}")
                problems[prior].append(f"duplicate_source_window:{i}")
            else:
                identity_seen[identity_hash] = i
            rec = identity["recording"]
            by_recording.setdefault(rec, []).append((i, row))
        except (KeyError, TypeError, ValueError):
            problems[i].append("invalid_identity_for_independence_audit")
    conflict_rows: list[dict[str, Any]] = []
    for recording, members in by_recording.items():
        prior: list[tuple[int, dict[str, Any]]] = []
        for i, row in members:
            prior_by_hash = {
                source_window_identity_sha256(old): old_index
                for old_index, old in prior
            }
            for conflict in independence_conflicts(row, [old for _, old in prior]):
                old_index = prior_by_hash.get(conflict["source_window_identity_sha256"])
                if old_index is None:
                    continue
                problems[i].append(f"independence_conflict:{old_index}")
                problems[old_index].append(f"independence_conflict:{i}")
                conflict_rows.append({
                    "recording": recording,
                    "rows": [old_index, i],
                    "inclusive_window_overlap": conflict["inclusive_window_overlap"],
                    "shared_moving_track_ids": conflict["shared_moving_track_ids"],
                })
            prior.append((i, row))
    return {
        "passed": not any(problems.values()),
        "row_count": len(rows),
        "unique_source_windows": len(identity_seen),
        "independence_conflicts": conflict_rows,
        "row_problems": {str(i): p for i, p in problems.items() if p},
    }


def runtime_fingerprint() -> dict[str, Any]:
    packages = {}
    for name in ("numpy", "pandas", "lanelet2", "shapely"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    executable = Path(sys.executable).resolve()
    return {
        "python": sys.version,
        "implementation": sys.implementation.name,
        "platform": platform.platform(),
        "executable": str(executable),
        "executable_sha256": sha(executable) if executable.is_file() else None,
        "packages": packages,
        "environment": {k: os.environ.get(k) for k in ("PATH", "LD_LIBRARY_PATH", "PYTHONPATH", "GDAL_DATA")},
    }


def configuration_fingerprint(cfg, output_root: Path) -> dict[str, Any]:
    config_path = Path(
        os.environ.get("GEOTRANSFER_CONFIG", cfg.project / "configs/local.toml")
    ).expanduser().resolve()
    return {
        "paths": {
            name: str(getattr(cfg, name))
            for name in ("project", "source", "bench", "runs", "cache", "weights", "reference_data")
        },
        "artifact_namespace": str(output_root.resolve()),
        "config_path": str(config_path),
        "config_sha256": sha(config_path) if config_path.is_file() else None,
    }


def build_global_fingerprint(cfg, output_root: Path, support: dict[str, Any], runtime_sha: str) -> dict[str, Any]:
    registry_path = PROJECT_ROOT / "src/geotransfer_gap/tool_registry.json"
    finalizer_path = PROJECT_ROOT / "src/geotransfer_gap/corpus/finalize_german_200_batch.py"
    return {
        "runner_version": RUNNER_VERSION,
        "runner_sha256": sha(Path(__file__)),
        "finalizer_sha256": sha(finalizer_path),
        "tool_sha256": {name: sha(producer_path(name)) for name in PIPELINE_TOOLS},
        "tool_registry_sha256": sha(registry_path),
        "converter_fingerprint": converter_fingerprint(),
        "runtime": runtime_fingerprint(),
        "runtime_source_sha256": runtime_sha,
        "benchmark_ini_sha256": sha(cfg.bench / "pufferlib/config/evaluation.ini"),
        "weight_sha256": sha(cfg.weights) if cfg.weights.is_file() else None,
        "configuration": configuration_fingerprint(cfg, output_root),
        "artifact_namespace": str(output_root.resolve()),
        "support_sha256": {
            "lane_change_oracle": support["lane_change_oracle"]["copied_sha256"],
            "us_protocol_parity": support["us_protocol_parity"]["copied_sha256"],
        },
    }


def output_namespace(cfg, queue_path: Path, requested: Path | None) -> Path:
    default = (cfg.artifacts / "german_200_v1_workstream_b").resolve()
    root = (requested or default).resolve()
    runs_root = (cfg.artifacts / "german_200_v1_runs").resolve()
    allowed = root == default or (
        root.is_relative_to(runs_root)
        and root != runs_root
        and len(root.relative_to(runs_root).parts) == 1
    )
    if not allowed:
        raise ValueError(f"Output root must be the pilot namespace or a named child of {runs_root}")
    if root == queue_path.parent or root.is_relative_to(queue_path.parent) or queue_path.is_relative_to(root):
        raise ValueError("Output root overlaps the frozen queue artifact tree")
    if not root.is_relative_to(PROJECT_ROOT):
        raise ValueError("Output root must remain inside this repository's ignored artifacts tree")
    return root


def batch_owner(queue_path: Path, queue_sha: str, output_root: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "queue_path": str(queue_path.resolve()),
        "queue_sha256": queue_sha,
        "output_root": str(output_root.resolve()),
    }


def validate_existing_ledger(ledger: dict[str, Any], rows: list[dict[str, Any]], queue_sha: str, support: dict[str, Any], global_fp: dict[str, Any]) -> None:
    if ledger.get("queue_sha256") != queue_sha or ledger.get("queue_row_count") != len(rows):
        raise ValueError("Existing output ledger belongs to a different frozen queue; choose a new named namespace")
    for result in ledger.get("results", []):
        index = int(result.get("queue_index", -1))
        fingerprint = result.get("input_fingerprint")
        if not (0 <= index < len(rows)) or not isinstance(fingerprint, dict):
            raise ValueError("Existing output ledger has an unbound result; choose a new named namespace")
        if fingerprint.get("global") != global_fp:
            raise ValueError("Existing ledger has different producer/runtime/config stamps; choose a new named namespace; prior output is preserved")
        expected = candidate_fingerprint(rows[index], queue_sha, support, global_fp)
        if fingerprint != expected:
            raise ValueError(f"Existing ledger row {index} has stale source/input stamps; choose a new named namespace; prior output is preserved")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}-{threading.get_ident()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, path)


def source_support(output_root: Path, lane_oracle: Path, parity: Path, runtime_sha: str) -> dict[str, Any]:
    """Copy and bind current native and US-mechanics evidence into this namespace."""
    support = output_root / "audits"
    support.mkdir(parents=True, exist_ok=True)
    oracle = json.loads(lane_oracle.read_text())
    expected_oracle = {
        "lane_change_tool_sha256": sha(tool_path("source_lane_changes.py")),
        "converter_sha256": converter_fingerprint(),
        "probe_sha256": sha(PROJECT_ROOT / "tests/integration/probe_source_lane_changes.py"),
    }
    for field, expected in expected_oracle.items():
        if oracle.get(field) != expected:
            raise ValueError(f"Lane-change oracle is stale: {field}")
    if not oracle.get("passed"):
        raise ValueError("Lane-change native oracle did not pass")
    # Its map evidence must cover every currently configured source map.
    oracle_maps = {r.get("source_sha256") for r in oracle.get("maps", [])}
    distinct_maps = {
        sha(p["lanelet_map"])
        for rec in range(33)
        if (p := source_paths(rec))["lanelet_map"].is_file()
    }
    if not distinct_maps.issubset(oracle_maps):
        raise ValueError("Lane-change oracle does not cover current source map set")

    parity_data = json.loads(parity.read_text())
    required_parity = {
        "mechanical_parity_pass": True,
        "hybrid_protocol_sha256": sha(tool_path("hybrid_traffic.py")),
        "runtime_source_sha256": runtime_sha,
        "evaluator_ini_sha256": sha(settings().bench / "pufferlib/config/evaluation.ini"),
    }
    for field, expected in required_parity.items():
        if parity_data.get(field) != expected:
            raise ValueError(f"US protocol parity is stale: {field}")
    for field in ("us_source_json", "us_binary_path"):
        path = Path(parity_data.get(field, "/missing"))
        if not path.is_file():
            raise ValueError(f"US parity input is missing: {field}")
        hash_field = "us_source_sha256" if field == "us_source_json" else "us_binary_sha256"
        if parity_data.get(hash_field) != sha(path):
            raise ValueError(f"US parity input changed: {field}")

    oracle_target = support / "source_lane_change_native_oracle.json"
    parity_target = support / "hybrid_protocol_us_parity.json"
    shutil.copy2(lane_oracle, oracle_target)
    shutil.copy2(parity, parity_target)
    return {
        "lane_change_oracle": {
            "source_path": str(lane_oracle.resolve()),
            "source_sha256": sha(lane_oracle),
            "copied_path": str(oracle_target.resolve()),
            "copied_sha256": sha(oracle_target),
            "validated_fields": expected_oracle,
        },
        "us_protocol_parity": {
            "source_path": str(parity.resolve()),
            "source_sha256": sha(parity),
            "copied_path": str(parity_target.resolve()),
            "copied_sha256": sha(parity_target),
            "validated_fields": required_parity,
            "us_source_sha256": parity_data["us_source_sha256"],
            "us_binary_sha256": parity_data["us_binary_sha256"],
        },
    }


def validate_copied_support(output_root: Path, support: dict[str, Any], runtime_sha: str) -> None:
    """Verify copied oracle/parity bytes and dependencies without writing outputs."""
    expected_oracle_fields = {
        "lane_change_tool_sha256": sha(tool_path("source_lane_changes.py")),
        "converter_sha256": converter_fingerprint(),
        "probe_sha256": sha(PROJECT_ROOT / "tests/integration/probe_source_lane_changes.py"),
    }
    oracle_record = support.get("lane_change_oracle", {})
    oracle_copy = output_root / "audits/source_lane_change_native_oracle.json"
    oracle_source = Path(oracle_record.get("source_path", "/missing"))
    if (
        Path(oracle_record.get("copied_path", "/missing")).resolve() != oracle_copy.resolve()
        or not oracle_copy.is_file()
        or sha(oracle_copy) != oracle_record.get("copied_sha256")
        or not oracle_source.is_file()
        or sha(oracle_source) != oracle_record.get("source_sha256")
    ):
        raise ValueError("Copied native lane-change oracle provenance is stale")
    oracle = json.loads(oracle_copy.read_text())
    if not oracle.get("passed") or any(oracle.get(k) != v for k, v in expected_oracle_fields.items()):
        raise ValueError("Copied native lane-change oracle does not match current producers")
    distinct_maps = {
        sha(paths["lanelet_map"])
        for recording in range(33)
        if (paths := source_paths(recording))["lanelet_map"].is_file()
    }
    if not distinct_maps.issubset({row.get("source_sha256") for row in oracle.get("maps", [])}):
        raise ValueError("Copied lane-change oracle does not cover current source maps")

    expected_parity_fields = {
        "mechanical_parity_pass": True,
        "hybrid_protocol_sha256": sha(tool_path("hybrid_traffic.py")),
        "runtime_source_sha256": runtime_sha,
        "evaluator_ini_sha256": sha(settings().bench / "pufferlib/config/evaluation.ini"),
    }
    parity_record = support.get("us_protocol_parity", {})
    parity_copy = output_root / "audits/hybrid_protocol_us_parity.json"
    parity_source = Path(parity_record.get("source_path", "/missing"))
    if (
        Path(parity_record.get("copied_path", "/missing")).resolve() != parity_copy.resolve()
        or not parity_copy.is_file()
        or sha(parity_copy) != parity_record.get("copied_sha256")
        or not parity_source.is_file()
        or sha(parity_source) != parity_record.get("source_sha256")
    ):
        raise ValueError("Copied US mechanics parity provenance is stale")
    parity = json.loads(parity_copy.read_text())
    if any(parity.get(k) != v for k, v in expected_parity_fields.items()):
        raise ValueError("Copied US mechanics parity does not match current runtime/protocol")
    for field, digest_field in (("us_source_json", "us_source_sha256"), ("us_binary_path", "us_binary_sha256")):
        path = Path(parity.get(field, "/missing"))
        if not path.is_file() or sha(path) != parity.get(digest_field):
            raise ValueError(f"Copied US parity has stale/missing input: {field}")


def scene_key(row: dict[str, Any]) -> tuple[int, int, int]:
    ident = canonical_source_identity(row)
    return ident["recording"], ident["ego_track_id"], ident["first_frame"]


def candidate_fingerprint(row: dict[str, Any], queue_sha: str, support: dict[str, Any], global_fp: dict[str, Any]) -> dict[str, Any]:
    return {
        "queue_sha256": queue_sha,
        "source_window_identity": row.get("source_window_identity"),
        "source_window_identity_sha256": row.get("source_window_identity_sha256"),
        "source_hashes": expected_source_hashes(int(row["recording"])),
        "support_sha256": {
            "lane_change_oracle": support["lane_change_oracle"]["copied_sha256"],
            "us_protocol_parity": support["us_protocol_parity"]["copied_sha256"],
        },
        "global": global_fp,
        "row_sha256": hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }


def output_tree_fingerprint(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    testing = root / "testing"
    required = {
        "conversion.log",
        "admit_scene.py.log",
        "testing/validation.json",
        "testing/manifest.csv",
        "testing/map_000000.bin",
        "testing/admission_hybrid_startup.json",
        "testing/map_audit.json",
        "testing/map_semantics_audit.json",
        "testing/rule_applicability_audit.json",
        "testing/physical_source_audit.json",
        "testing/interaction_fidelity_audit_hybrid_startup.json",
        "testing/evaluation_contract_expert.json",
        "testing/evaluation_contract_idm.json",
        "testing/evaluation_contract_hybrid_startup.json",
        "testing/replay_validation.json",
        "testing/evaluation_replay_probe.json",
        "testing/spawn_evaluation_validation.json",
        "testing/parked_evaluation_validation.json",
        "testing/lifecycle_trace_expert.json",
        "testing/lifecycle_trace_idm.json",
        "testing/lifecycle_trace_hybrid_startup.json",
        "testing/counterfactual_probe.json",
        "testing/counterfactual_hybrid_probe.json",
        "testing/source_image_registration.json",
        "testing/rule_review_montage.png",
    }
    paths = {root / name for name in required}
    paths.update(testing.glob("ind_*.json"))
    return {
        p.relative_to(root).as_posix(): sha(p)
        for p in sorted(paths)
        if p.is_file()
    }


def reusable(previous: dict[str, Any], fingerprint: dict[str, Any]) -> bool:
    if previous.get("input_fingerprint") != fingerprint:
        return False
    status = previous.get("status")
    conclusive = {
        "awaiting_human_review",
        "technical_rejection",
        "source_geometry_rejection",
        "source_physical_rejection",
        "review_blocked",
    }
    if status not in conclusive:
        return False
    root = Path(previous.get("root", "/missing"))
    tree = previous.get("output_tree_sha256", {})
    actual = output_tree_fingerprint(root)
    required = {
        "conversion.log",
        "testing/validation.json",
        "testing/manifest.csv",
        "testing/map_000000.bin",
        "testing/map_audit.json",
        "testing/map_semantics_audit.json",
        "testing/rule_applicability_audit.json",
        "testing/physical_source_audit.json",
    }
    if status in {"technical_rejection", "awaiting_human_review", "review_blocked"}:
        required.update({
            "testing/admission_hybrid_startup.json",
            "testing/interaction_fidelity_audit_hybrid_startup.json",
        })
    if status in {"awaiting_human_review", "review_blocked"}:
        required.update({"testing/source_image_registration.json", "testing/rule_review_montage.png"})
    return (
        bool(tree)
        and actual == tree
        and required.issubset(actual)
        and any(name.startswith("testing/ind_") and name.endswith(".json") for name in actual)
    )


def semantic_annotation(root: Path) -> dict[str, Any] | None:
    path = root / "testing/rule_applicability_audit.json"
    if not path.is_file():
        return None
    audit = json.loads(path.read_text())
    flags = []
    if any(
        sign.get("subtype") == "de206"
        for rule in audit.get("governing_regulatory_elements", [])
        if any(m.get("role") == "yield" for m in rule.get("ego_members", []))
        for sign in rule.get("signs", [])
    ):
        flags.append("ego_stop_sign_requires_stop_even_without_conflicting_traffic")
    for rule in audit.get("governing_regulatory_elements", []):
        if not any(m.get("role") == "yield" for m in rule.get("ego_members", [])):
            continue
        for actor in audit.get("priority_lane_traffic", []):
            if (
                actor.get("actor_source_path_m", 0) > 1
                and actor.get("minimum_spatial_box_gap_m", float("inf")) <= 2
                and any(actor.get("priority_lanelet_steps", {}).get(str(lid)) for lid in rule.get("priority_lanelets", []))
            ):
                flags.append(f"rule_{rule['id']}_priority_{actor['type']}_{actor['track_id']}_spatial_conflict")
    for key, prefix in (
        ("oncoming_turn_conflicts", "implicit_oncoming_turn_priority"),
        ("slow_ego_fast_crosspath_conflicts", "slow_ego_fast_crosspath"),
        ("yield_lane_fast_crosspath_conflicts", "yield_lane_fast_crosspath"),
    ):
        flags.extend(f"{prefix}_{x['type']}_{x['track_id']}" for x in audit.get(key, []))
    flags.extend(
        f"crosswalk_{cw['lanelet_id']}_vru_{vru['track_id']}"
        for cw in audit.get("ego_box_crosswalk_contacts", [])
        if cw.get("ego_box_contact_steps")
        for vru in cw.get("nearby_vrus", [])
        if vru.get("minimum_distance_to_crosswalk_m", float("inf")) <= 5
    )
    return {
        "status": "annotation_only_pending_human_review",
        "rule_audit_schema_version": audit.get("schema_version"),
        "rule_audit_sha256": sha(path),
        "governing_rule_count": len(audit.get("governing_regulatory_elements", [])),
        "nearby_sign_count": len(audit.get("nearby_source_signs", [])),
        "ego_crosswalk_contact_count": len(audit.get("ego_box_crosswalk_contacts", [])),
        "applicability_flags": sorted(set(flags)),
        "technical_gate_effect": "none",
    }


def actor_context_check(row: dict[str, Any], root: Path) -> dict[str, Any]:
    scene_files = sorted((root / "testing").glob("ind_*.json"))
    if len(scene_files) != 1:
        return {"passed": False, "reason": "converted_scene_missing_or_ambiguous"}
    scene = json.loads(scene_files[0].read_text())
    objects = scene.get("objects", [])
    actual_ids = {int(obj["id"]) for obj in objects}
    actual_moving = {
        int(obj["id"])
        for obj in objects
        if float(obj.get("source_window_path_length_m", 0)) >= 1.0
    }
    expected_moving = set(map(int, row.get("moving_track_ids", [])))
    context = set(map(int, row.get("context_actor_ids", [])))
    missing_context = sorted(context - actual_ids)
    unexpected_moving = sorted(actual_moving - expected_moving)
    moving_mismatch = sorted(actual_moving ^ expected_moving)
    config = ConversionConfig(
        recording=int(row["recording"]),
        ego=int(row.get("ego_track_id", row.get("ego"))),
        first_frame=int(row["first_frame"]),
        goal_sample=85,
        late_mode="runtime_spawn",
        static_crop_radius=1000000,
        exclude_track_ids=(),
        parked_as_static_expert=True,
        background_goal_mode="continue",
        emit_crosswalks=True,
    )
    frames = int(row["first_frame"]) + np.arange(91) * 2.5
    source_tracks, source_meta, _ = load_tracks(config, frames)
    source_arrays = {
        int(track_id): np.asarray(
            [
                [
                    int(sample["frame"]),
                    float(sample["xCenter"]),
                    float(sample["yCenter"]),
                    float(sample["heading"]),
                    float(sample["xVelocity"]),
                    float(sample["yVelocity"]),
                ]
                for sample in samples
            ],
            dtype=float,
        )
        for track_id, samples in source_tracks.items()
    }
    source_context = source_context_actors(row, source_arrays, source_meta)
    source_context_ids = {item["track_id"] for item in source_context}
    source_moving = {
        item["track_id"] for item in source_context if item["moving"]
    }
    context_metadata = row.get(
        "source_context_actors",
        row.get("context_actor_metadata", row.get("per_actor_metadata", [])),
    )
    frozen_context_metadata = []
    if isinstance(context_metadata, list):
        frozen_context_metadata = context_metadata
    elif isinstance(context_metadata, dict):
        frozen_context_metadata = list(context_metadata.values())
    frozen_context_ids = {
        int(item.get("track_id", item.get("actor_id")))
        for item in frozen_context_metadata
        if isinstance(item, dict) and item.get("track_id", item.get("actor_id")) is not None
    }
    frozen_context_metadata_missing = sorted(frozen_context_ids - source_context_ids)
    frozen_context_by_id = {
        int(item.get("track_id", item.get("actor_id"))): item
        for item in frozen_context_metadata
        if isinstance(item, dict) and item.get("track_id", item.get("actor_id")) is not None
    }
    source_context_by_id = {item["track_id"]: item for item in source_context}
    metadata_mismatches = []
    comparable_context_fields = (
        "class",
        "raw_rows_in_window",
        "valid_samples",
        "source_window_path_m",
        "moving",
        "source_window_max_speed_mps",
        "source_track_start_frame",
        "source_track_end_frame",
    )
    for actor_id in sorted(source_context_ids & frozen_context_by_id.keys()):
        frozen_actor = frozen_context_by_id[actor_id]
        current_actor = source_context_by_id[actor_id]
        for field in comparable_context_fields:
            if field not in frozen_actor:
                metadata_mismatches.append({"track_id": actor_id, "field": field, "reason": "missing_frozen_field"})
                continue
            left, right = frozen_actor[field], current_actor[field]
            equal = (
                abs(float(left) - float(right)) <= 1e-9
                if field in ("source_window_path_m", "source_window_max_speed_mps") and left is not None and right is not None
                else left == right
            )
            if not equal:
                metadata_mismatches.append({"track_id": actor_id, "field": field, "frozen": left, "current": right})
    converted_by_id = {int(obj["id"]): obj for obj in objects}
    converted_mismatches = []
    for actor_id, source_actor in source_context_by_id.items():
        converted_actor = converted_by_id.get(actor_id)
        if converted_actor is None:
            converted_mismatches.append({"track_id": actor_id, "reason": "missing_from_converted_scene"})
            continue
        if abs(float(converted_actor.get("source_window_path_length_m", float("inf"))) - float(source_actor["source_window_path_m"])) > 1e-9:
            converted_mismatches.append({"track_id": actor_id, "field": "source_window_path_length_m"})
        converted_speed = converted_actor.get("source_window_max_speed_mps")
        source_speed = source_actor["source_window_max_speed_mps"]
        if (converted_speed is None) != (source_speed is None) or (
            converted_speed is not None
            and source_speed is not None
            and abs(float(converted_speed) - float(source_speed)) > 1e-9
        ):
            converted_mismatches.append({"track_id": actor_id, "field": "source_window_max_speed_mps"})
    return {
        "passed": (
            not missing_context
            and not moving_mismatch
            and source_moving == expected_moving
            and context == source_context_ids
            and not frozen_context_metadata_missing
            and not metadata_mismatches
            and not converted_mismatches
        ),
        "converted_actor_ids": sorted(actual_ids),
        "converted_moving_actor_ids": sorted(actual_moving),
        "frozen_moving_actor_ids": sorted(expected_moving),
        "source_recomputed_actor_ids": sorted(source_context_ids),
        "source_recomputed_moving_actor_ids": sorted(source_moving),
        "source_recomputed_actor_metadata": source_context,
        "frozen_context_actor_ids": sorted(context),
        "missing_context_actor_ids": missing_context,
        "frozen_context_metadata_missing_ids": frozen_context_metadata_missing,
        "context_actor_id_mismatch_ids": sorted(context ^ source_context_ids),
        "frozen_context_metadata_mismatches": metadata_mismatches,
        "converted_actor_metadata_mismatches": converted_mismatches,
        "unexpected_converted_moving_actor_ids": unexpected_moving,
        "moving_actor_mismatch_ids": moving_mismatch,
    }


def run_command(script: str, root: Path, env: dict[str, str], extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(tool_path(script)), "--root", str(root), *extra],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    (root / f"{script}.log").write_text(proc.stdout + proc.stderr)
    return proc


def current_source_preflight(root: Path, env: dict[str, str]) -> dict[str, Any]:
    """Run the existing cheap source checks before the expensive full gate."""
    scripts = (
        "audit_scene.py",
        "audit_map_semantics.py",
        "audit_rule_applicability.py",
        "audit_physical_source.py",
    )
    commands = {}
    for script in scripts:
        proc = run_command(script, root, env)
        commands[script] = {"returncode": proc.returncode, "stderr": (proc.stderr or "")[-1200:]}
        expected = {
            "audit_scene.py": "map_audit.json",
            "audit_map_semantics.py": "map_semantics_audit.json",
            "audit_rule_applicability.py": "rule_applicability_audit.json",
            "audit_physical_source.py": "physical_source_audit.json",
        }[script]
        if proc.returncode or not (root / "testing" / expected).is_file():
            return {"status": "transient_error", "failed_stage": script, "commands": commands}

    testing = root / "testing"
    geometry = json.loads((testing / "map_audit.json").read_text())
    physical = json.loads((testing / "physical_source_audit.json").read_text())
    validation = json.loads((testing / "validation.json").read_text())
    ego_id = str(validation.get("ego_track", validation.get("ego_track_id")))
    overlaps = physical.get("source_box_actor_overlap_details", {})
    structural_reasons = []
    if geometry.get("ego_samples_outside_lanelet_polygons"):
        structural_reasons.append("ego_samples_outside_lanelet_polygons")
    if not geometry.get("occupied_start_to_occupied_goal_reachable"):
        structural_reasons.append("occupied_start_to_occupied_goal_unreachable")
    physical_reasons = []
    if ego_id in physical.get("source_box_boundary_contacts", {}):
        physical_reasons.append("source_ego_box_boundary_contact")
    if any(not item.get("reviewable_annotation_overlap") for item in overlaps.values()):
        physical_reasons.append("unreviewable_source_box_overlap")
    return {
        "status": "source_screened",
        "commands": commands,
        "geometry": {
            "outside_lanelet_steps": geometry.get("ego_samples_outside_lanelet_polygons", []),
            "occupied_start_to_occupied_goal_reachable": geometry.get("occupied_start_to_occupied_goal_reachable"),
            "map_audit_sha256": sha(testing / "map_audit.json"),
        },
        "physical": {
            "ego_boundary_contact": ego_id in physical.get("source_box_boundary_contacts", {}),
            "overlap_pair_count": len(overlaps),
            "unreviewable_overlap_count": sum(not item.get("reviewable_annotation_overlap") for item in overlaps.values()),
            "physical_audit_sha256": sha(testing / "physical_source_audit.json"),
        },
        "structural_reasons": structural_reasons,
        "physical_reasons": physical_reasons,
        "semantic_applicability": semantic_annotation(root),
    }


def process_row(index: int, row: dict[str, Any], row_problems: list[str], root: Path, env: dict[str, str], fingerprint: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "queue_index": index,
        "frozen_row": row,
        "input_fingerprint": fingerprint,
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        identity = canonical_source_identity(row)
    except (KeyError, TypeError, ValueError) as error:
        result.update(status="deferred_integrity", reasons=[f"invalid_identity:{error}"])
        result["completed_utc"] = datetime.now(timezone.utc).isoformat()
        return result
    result["source_identity"] = identity
    result["candidate_id"] = str(row.get("candidate_id") or f"{row.get('arm','arm')}-{row.get('arm_index',index)}-{identity_digest(identity)[:12]}")
    if row_problems:
        result.update(status="deferred_independence", reasons=row_problems)
        result["completed_utc"] = datetime.now(timezone.utc).isoformat()
        return result
    source_problems = verify_source_identity(row)
    if source_problems:
        result.update(status="deferred_source_integrity", reasons=source_problems)
        result["completed_utc"] = datetime.now(timezone.utc).isoformat()
        return result

    root.mkdir(parents=True, exist_ok=False)
    result["root"] = str(root.resolve())
    command = [
        sys.executable,
        str(tool_path("pilot_ind.py")),
        "--recording",
        str(identity["recording"]),
        "--ego",
        str(identity["ego_track_id"]),
        "--first-frame",
        str(identity["first_frame"]),
        *CONVERSION_ARGS,
        "--output-root",
        str(root),
    ]
    conversion = subprocess.run(command, cwd=PROJECT_ROOT, env=env, capture_output=True, text=True)
    (root / "conversion.log").write_text(conversion.stdout + conversion.stderr)
    if conversion.returncode:
        result.update(status="transient_error", stage="conversion", returncode=conversion.returncode, error=(conversion.stderr or conversion.stdout)[-1800:])
        result["completed_utc"] = datetime.now(timezone.utc).isoformat()
        return result

    context_report = actor_context_check(row, root)
    result["context_identity"] = context_report
    if not context_report["passed"]:
        result.update(status="deferred_context_mismatch", reasons=["converted_actor_context_differs_from_frozen_context"])
        result["semantic_applicability"] = semantic_annotation(root)
        result["completed_utc"] = datetime.now(timezone.utc).isoformat()
        return result

    preflight = current_source_preflight(root, env)
    result["source_preflight"] = preflight
    if preflight["status"] == "transient_error":
        result.update(status="transient_error", stage=preflight.get("failed_stage"), reasons=["current_source_audit_failed"])
        result["semantic_applicability"] = semantic_annotation(root)
        result["completed_utc"] = datetime.now(timezone.utc).isoformat()
        return result
    if preflight["structural_reasons"]:
        result.update(status="source_geometry_rejection", reasons=preflight["structural_reasons"])
        result["semantic_applicability"] = preflight["semantic_applicability"]
        result["completed_utc"] = datetime.now(timezone.utc).isoformat()
        return result
    if preflight["physical_reasons"]:
        result.update(status="source_physical_rejection", reasons=preflight["physical_reasons"])
        result["semantic_applicability"] = preflight["semantic_applicability"]
        result["completed_utc"] = datetime.now(timezone.utc).isoformat()
        return result

    admission = run_command("admit_scene.py", root, env, ("--traffic-protocol", "hybrid_startup"))
    gate_path = root / "testing/admission_hybrid_startup.json"
    if not gate_path.is_file():
        result.update(status="transient_error", stage="technical_gate", returncode=admission.returncode, error=(admission.stderr or admission.stdout)[-1800:])
        result["semantic_applicability"] = semantic_annotation(root)
        result["completed_utc"] = datetime.now(timezone.utc).isoformat()
        return result
    gate = json.loads(gate_path.read_text())
    result["technical_admission"] = {
        "technical_admitted": bool(gate.get("technical_admitted")),
        "research_admitted": bool(gate.get("research_admitted")),
        "exclusion_reasons": gate.get("exclusion_reasons", []),
        "gate_sha256": sha(gate_path),
        "refresh_commands_passed": bool(gate.get("checks", {}).get("refresh_commands")),
        "gate_returncode": admission.returncode,
    }
    result["semantic_applicability"] = semantic_annotation(root)
    if not gate.get("checks", {}).get("refresh_commands"):
        result.update(status="transient_error", stage="technical_gate_refresh", reasons=gate.get("details", {}).get("refresh_commands", []))
    elif gate.get("technical_admitted"):
        result["status"] = "awaiting_human_review"
        interaction_path = root / "testing/interaction_fidelity_audit_hybrid_startup.json"
        if interaction_path.is_file():
            interaction = json.loads(interaction_path.read_text())
            actor_id = row.get("actor")
            actor_row = next((a for a in interaction.get("actor_opportunities", []) if actor_id is not None and int(a.get("track_id", -1)) == int(actor_id)), None)
            result["candidate_actor_fidelity"] = actor_row
            result["preserved_actor_ids"] = [
                int(a["track_id"])
                for a in interaction.get("actor_opportunities", [])
                if a.get("preserved_for_claimed_interaction")
            ]
        # Source registration and rule review are evidence for a human, never an
        # automated review or semantic-admission decision.
        rendered = {}
        for script, extra in (("register_background.py", ()), ("render_rule_review.py", ("--steps", "10", "30", "50", "75"))):
            proc = run_command(script, root, env, extra)
            rendered[script] = {
                "returncode": proc.returncode,
                "log": str((root / f"{script}.log").resolve()),
                "error": (proc.stderr or "")[-1000:] if proc.returncode else None,
            }
        result["review_assets"] = rendered
        result["manual_review_status"] = "pending"
        result["manual_review_created"] = False
    else:
        result["status"] = "technical_rejection"
    result["completed_utc"] = datetime.now(timezone.utc).isoformat()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True, help="Immutable frozen JSON batch")
    parser.add_argument("--output-root", type=Path, help="New, isolated artifact namespace")
    parser.add_argument("--lane-oracle", type=Path, required=True, help="Fresh native source lane-change oracle")
    parser.add_argument("--us-parity", type=Path, help="Current pinned US hybrid mechanics report")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int, help="Bound this invocation without changing queue order")
    args = parser.parse_args()
    if args.workers < 1 or (args.limit is not None and args.limit < 1):
        raise ValueError("workers and limit must be positive")

    cfg = settings()
    queue_path = args.queue.resolve()
    if not queue_path.is_file():
        raise FileNotFoundError(queue_path)
    output_root = output_namespace(cfg, queue_path, args.output_root)
    frozen = json.loads(queue_path.read_text())
    rows = get_rows(frozen)
    queue_hash = sha(queue_path)
    owner_path = output_root / "batch_owner.json"
    owner = batch_owner(queue_path, queue_hash, output_root)
    owner_exists = owner_path.is_file()
    if owner_path.is_file():
        existing_owner = json.loads(owner_path.read_text())
        if existing_owner != owner:
            raise ValueError("Output namespace is owned by another frozen batch; refusing to resume or overwrite it")
    elif output_root.exists() and any(output_root.iterdir()):
        raise ValueError("Output namespace is nonempty and has no ownership marker")
    os.environ["GEOTRANSFER_ARTIFACTS"] = str(output_root)
    env = dict(os.environ, GEOTRANSFER_ARTIFACTS=str(output_root), OMP_NUM_THREADS="2", MPLCONFIGDIR=os.environ.get("MPLCONFIGDIR", "/tmp/geotransfer_mpl"))

    # Runtime source fingerprint is the same one embedded by admit_scene.
    from geotransfer_gap.runtime import late_spawn_runtime

    runtime_sha = late_spawn_runtime.load()["runtime_source_sha256"]
    ledger_path = output_root / "batch_ledger.json"
    prior = json.loads(ledger_path.read_text()) if ledger_path.is_file() else {"results": []}
    if ledger_path.is_file():
        support_path = output_root / "source_support_provenance.json"
        if not owner_exists or not support_path.is_file():
            raise ValueError("Existing ledger lacks owner/support provenance; choose a new named namespace; prior output is preserved")
        support = json.loads(support_path.read_text())
        validate_copied_support(output_root, support, runtime_sha)
        global_fp = build_global_fingerprint(cfg, output_root, support, runtime_sha)
        validate_existing_ledger(prior, rows, queue_hash, support, global_fp)
    else:
        # For a fresh namespace, bind ownership before copying any support evidence.
        output_root.mkdir(parents=True, exist_ok=True)
        if not owner_exists:
            atomic_json(owner_path, owner)
        parity_path = (args.us_parity or cfg.artifacts / "audits/hybrid_protocol_us_parity.json").resolve()
        support = source_support(output_root, args.lane_oracle.resolve(), parity_path, runtime_sha)
        global_fp = build_global_fingerprint(cfg, output_root, support, runtime_sha)
    independent = independence_audit(rows)
    independence_path = output_root / "batch_independence_audit.json"
    support_path = output_root / "source_support_provenance.json"
    if ledger_path.is_file():
        if not independence_path.is_file() or json.loads(independence_path.read_text()) != independent:
            raise ValueError("Existing ledger independence provenance is stale; choose a new named namespace; prior output is preserved")
        if json.loads(support_path.read_text()) != support:
            raise ValueError("Existing ledger support provenance changed; choose a new named namespace; prior output is preserved")
    else:
        atomic_json(independence_path, independent)
        atomic_json(support_path, support)
    prior_by_index = {int(r["queue_index"]): r for r in prior.get("results", []) if "queue_index" in r}
    selected_indices = list(range(len(rows)))
    if args.limit is not None:
        selected_indices = selected_indices[: args.limit]
    jobs = []
    for index in selected_indices:
        row = rows[index]
        problems = list(independent.get("row_problems", {}).get(str(index), []))
        fingerprint = candidate_fingerprint(row, queue_hash, support, global_fp)
        prior_row = prior_by_index.get(index)
        if prior_row and reusable(prior_row, fingerprint):
            continue
        identity_hash = row.get("source_window_identity_sha256") or f"invalid-{index}"
        safe_id = hashlib.sha256(f"{index}:{identity_hash}".encode()).hexdigest()[:16]
        candidate_root = output_root / "candidate_runs" / f"{index:03d}_{safe_id}"
        if candidate_root.exists():
            suffix = 1
            while candidate_root.with_name(candidate_root.name + f"_attempt{suffix:02d}").exists():
                suffix += 1
            candidate_root = candidate_root.with_name(candidate_root.name + f"_attempt{suffix:02d}")
        jobs.append((index, row, problems, candidate_root, fingerprint))

    results = dict(prior_by_index)
    print(f"Frozen batch rows: {len(rows)}; invocation bound: {len(selected_indices)}; runnable: {len(jobs)}; reused: {len(selected_indices) - len(jobs)}", flush=True)
    def persist() -> None:
        out_rows = [results[i] for i in sorted(results)]
        atomic_json(ledger_path, {
            "schema_version": 1,
            "protocol": PROTOCOL,
            "queue_path": str(queue_path),
            "queue_sha256": queue_hash,
            "queue_row_count": len(rows),
            "frozen_input_untouched": True,
            "started_or_resumed_utc": datetime.now(timezone.utc).isoformat(),
            "results": out_rows,
        })
        summaries = summarize(out_rows, rows)
        atomic_json(output_root / "batch_summary.json", summaries)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {
            pool.submit(process_row, i, row, problems, root, env, fp): i
            for i, row, problems, root, fp in jobs
        }
        for future in as_completed(pending):
            index = pending[future]
            try:
                result = future.result()
            except Exception as error:  # A row exception is transient, with identity retained.
                result = {
                    "queue_index": index,
                    "frozen_row": rows[index],
                    "status": "transient_error",
                    "stage": "runner_exception",
                    "error": f"{type(error).__name__}: {error}",
                    "completed_utc": datetime.now(timezone.utc).isoformat(),
                }
            result["output_tree_sha256"] = output_tree_fingerprint(Path(result["root"])) if result.get("root") else {}
            results[index] = result
            persist()
            print(f"[{index + 1}/{len(rows)}] {result.get('candidate_id', index)}: {result['status']}", flush=True)

    persist()
    print(json.dumps(summarize([results[i] for i in sorted(results)], rows), indent=2), flush=True)


def summarize(results: list[dict[str, Any]], frozen_rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in results:
        status = row.get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
    eligible = sum(row.get("status") in ("awaiting_human_review", "technical_rejection") for row in results)
    passes = sum(row.get("status") == "awaiting_human_review" and row.get("technical_admission", {}).get("technical_admitted") is True for row in results)
    source_flags: dict[str, int] = {}
    for row in results:
        for flag in (row.get("semantic_applicability") or {}).get("applicability_flags", []):
            source_flags[flag] = source_flags.get(flag, 0) + 1
    arms = {}
    for index, frozen in enumerate(frozen_rows):
        arm = str(frozen.get("arm", "unknown"))
        item = arms.setdefault(arm, {"frozen": 0, "processed": 0, "technical_pass": 0, "technical_rejection": 0, "awaiting_human_review": 0, "transient_or_deferred": 0})
        item["frozen"] += 1
        result = next((r for r in results if int(r.get("queue_index", -1)) == index), None)
        if result:
            item["processed"] += 1
            if result.get("technical_admission", {}).get("technical_admitted") is True:
                item["technical_pass"] += 1
            if result.get("status") == "technical_rejection":
                item["technical_rejection"] += 1
            if result.get("status") == "awaiting_human_review":
                item["awaiting_human_review"] += 1
            if result.get("status") in ("transient_error", "deferred_independence", "deferred_source_integrity", "deferred_context_mismatch", "deferred_integrity"):
                item["transient_or_deferred"] += 1
    return {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "frozen_candidate_count": len(frozen_rows),
        "recorded_result_count": len(results),
        "status_counts": counts,
        "eligible_technical_denominator": eligible,
        "technical_pass_count": passes,
        "technical_pass_fraction_of_eligible": (passes / eligible if eligible else None),
        "technical_pass_fraction_of_all_frozen_rows": (passes / len(frozen_rows) if frozen_rows else None),
        "semantic_applicability_flag_counts_annotation_only": dict(sorted(source_flags.items())),
        "arms": arms,
        "alternate_window_count": sum(len(row.get("alternate_source_windows", [])) for row in frozen_rows),
        "structural_fallback_policy": (
            "No prespecified alternate windows exist in this frozen batch; source geometry/physical rejections remain labelled, with no post-screen replacement."
            if not any(row.get("alternate_source_windows") for row in frozen_rows)
            else "Prespecified alternates are recorded in the frozen batch; this Workstream B runner does not promote alternates into the primary batch."
        ),
        "result_scope": "Current frozen batch only; transient/deferred rows remain in the all-frozen denominator and are separately labelled. No historic ledger pooling.",
    }


if __name__ == "__main__":
    main()
