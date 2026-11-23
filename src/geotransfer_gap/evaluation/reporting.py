"""Offline accounting and deterministic reports for existing saved executions."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile

from geotransfer_gap.artifacts import (
    read_json,
    reference,
    resolve_reference,
    sha256,
    write_json,
)
from geotransfer_gap.config import settings
from geotransfer_gap.evaluation.context import build_map_context
from geotransfer_gap.evaluation.episode import evaluate_episode
from geotransfer_gap.evaluation.profile import load_profile
from geotransfer_gap.runtime.trace_io import SavedEvidenceError, load_saved_trace


INDEX_SCHEMA_VERSION = 1
RESULT_SCHEMA_VERSION = 1
_CAMPAIGN_STATES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}


def _profile_path(path):
    return Path(path).expanduser().resolve() if path else (
        settings().project / "configs/evaluation/default.toml"
    ).resolve()


def _validate_output(output, inputs, scenes, profile_path):
    # Reuse the guard already used by evaluate episode. A ledger, each supplied
    # manifest/trace, and every selected scene gets the same protected-root and
    # run-ancestry checks before the output directory is created.
    from geotransfer_gap.evaluation.commands import _output_path

    destination = Path(output).expanduser().resolve()
    candidates = [Path(path).expanduser().resolve() for path in inputs]
    candidates.extend(Path(path).expanduser().resolve() for path in scenes)
    for path in candidates:
        _output_path(destination, path, profile_path,
                     path if path in scenes else None)
    return destination


def _scene_entries(manifest_path):
    manifest = read_json(manifest_path)
    if isinstance(manifest, dict):
        if manifest.get("schema_version") != 2 or not isinstance(manifest.get("scenes"), list):
            raise ValueError("Run manifest must be an existing schema-2 scene manifest")
        rows = manifest["scenes"]
    elif isinstance(manifest, list):
        rows = manifest
    else:
        raise ValueError("Run manifest must contain scene entries")
    scenes = {}
    roots = set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]
                or "root" not in row):
            raise ValueError("Run manifest contains a malformed scene entry")
        name = row["name"]
        root = resolve_reference(row["root"]).resolve()
        if name in scenes or root in roots:
            raise ValueError("Run manifest contains duplicate or ambiguous scene identities")
        roots.add(root)
        scenes[name] = {**row, "resolved_root": root}
    if not scenes:
        raise ValueError("Run manifest has no expected scenes")
    return scenes


def _same_scene(recorded, manifest_row):
    try:
        return resolve_reference(recorded).resolve() == manifest_row["resolved_root"]
    except (TypeError, KeyError, ValueError, OSError):
        return False


def _trace_scene(manifest_row):
    try:
        return reference(manifest_row["resolved_root"])
    except ValueError:
        return manifest_row.get("root")


def _identity(row, scene, *, protocol=None):
    protocol = protocol or {}
    name = row.get("name") or scene
    slot = row.get("slot_id")
    if slot:
        logical = slot
    else:
        ego = row.get("ego_controller", row.get("ego", row.get("planner", protocol.get("ego_controller"))))
        traffic = row.get("traffic_controller", row.get("traffic", protocol.get("traffic_controller")))
        startup = row.get("traffic_startup", row.get("startup", protocol.get("traffic_startup")))
        logical = ":".join(str(item) for item in (scene or name, ego or "unknown", traffic or "unknown",
                                                   startup or "unknown"))
    return logical


def _record_path(value, base):
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def _attempt_record(base, attempt):
    if not isinstance(attempt, dict):
        return None
    return _record_path(attempt.get("record"), base)


def _attempt_history(base, attempts):
    history = []
    trace_candidates = []
    if attempts is None:
        attempts = []
    elif not isinstance(attempts, list):
        attempts = [attempts]
    for ordinal, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict):
            history.append({"number": ordinal, "status": "invalid", "status_consistent": False,
                            "classification": "malformed_attempt_index_entry", "record": None,
                            "record_sha256": None, "evidence_files": {}, "trace_path": None,
                            "trace_sha256": None, "exit_code": None, "signal": None})
            continue
        record = _attempt_record(base, attempt)
        detail = None
        if record is not None and record.is_file():
            try:
                value = read_json(record)
                detail = value if isinstance(value, dict) else None
            except (OSError, ValueError, TypeError):
                detail = None
        folder = record.parent if record else None
        trace = folder / "trace.json" if folder else None
        if trace and trace.is_file():
            number = attempt.get("number")
            order = number if type(number) is int and number > 0 else ordinal
            trace_candidates.append((order, trace, detail))
        ledger_status = attempt.get("status")
        attempt_status = (detail or {}).get("status")
        evidence = (detail or {}).get("evidence")
        evidence_files = evidence.get("files", {}) if isinstance(evidence, dict) else {}
        status_consistent = (ledger_status is None or attempt_status is None
                             or ledger_status == attempt_status)
        if ((record is not None and (not record.is_file() or detail is None))
                or (ledger_status is not None and record is None)):
            status_consistent = False
        history.append({
            "number": attempt.get("number", ordinal),
            "status": ledger_status or attempt_status or "unknown",
            "status_consistent": status_consistent,
            "classification": ((detail or {}).get("classification") or attempt.get("class")),
            "record": str(record) if record else None,
            "record_sha256": sha256(record) if record and record.is_file() else None,
            "evidence_files": evidence_files if isinstance(evidence_files, dict) else {},
            "trace_path": str(trace) if trace and trace.is_file() else None,
            "trace_sha256": sha256(trace) if trace and trace.is_file() else None,
            "exit_code": (detail or {}).get("exit_code"),
            "signal": (detail or {}).get("signal"),
        })
    trace_candidates.sort(key=lambda item: item[0])
    return history, trace_candidates


def _run_input(run_dir, manifest_path):
    run_dir = Path(run_dir).expanduser().resolve()
    ledger_path = run_dir / "run.json"
    if not ledger_path.is_file():
        raise FileNotFoundError(f"Saved run ledger does not exist: {ledger_path}")
    ledger = read_json(ledger_path)
    if not isinstance(ledger, dict):
        raise ValueError("Saved run index must be a JSON object")
    if ledger.get("schema_version") == 4:
        manifest_scenes = _scene_entries(manifest_path)
        rows = ledger.get("results")
        if not isinstance(rows, list) or not rows:
            raise ValueError("Schema-4 run ledger has no expected result rows")
        seen = set()
        seen_protocols = set()
        episodes = []
        protocol = ledger.get("protocol", {})
        if not isinstance(protocol, dict):
            raise ValueError("Schema-4 run ledger protocol is malformed")
        protocol_fields = ("ego_controller", "traffic_controller", "traffic_startup")
        expected_protocol = {}
        for field in protocol_fields:
            nested = protocol.get(field)
            top_level = ledger.get(field)
            if nested is not None and top_level is not None and nested != top_level:
                raise ValueError(f"Schema-4 run ledger has conflicting {field} identities")
            expected_protocol[field] = top_level if top_level is not None else nested
        names = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Schema-4 run ledger contains a malformed result row")
            name = row.get("name")
            if not isinstance(row.get("inputs"), dict):
                raise ValueError("Schema-4 run ledger input identities are malformed")
            if not isinstance(name, str) or name not in manifest_scenes:
                raise ValueError("Run ledger scene is absent from supplied manifest")
            manifest_row = manifest_scenes[name]
            if not _same_scene(row.get("scene"), manifest_row):
                raise ValueError(f"Stale manifest scene root for {name}")
            binary_hash = (row.get("inputs") or {}).get("binary", {}).get("sha256")
            expected_hash = manifest_row.get("binary_sha256")
            if expected_hash is not None and binary_hash != expected_hash:
                raise ValueError(f"Stale manifest binary identity for {name}")
            logical = _identity(row, name, protocol=ledger)
            episode_protocol = (name, *(row.get(field, expected_protocol[field])
                                        for field in protocol_fields))
            if any(not isinstance(value, str) or not value for value in episode_protocol):
                raise ValueError(f"Schema-4 episode protocol identity is malformed: {name}")
            if logical in seen or episode_protocol in seen_protocols:
                raise ValueError(f"Duplicate logical episode identity: {logical}")
            seen.add(logical)
            seen_protocols.add(episode_protocol)
            if any(row.get(field, expected_protocol[field]) != expected_protocol[field]
                   for field in protocol_fields):
                raise ValueError(f"Schema-4 episode protocol differs from its run ledger: {name}")
            if row.get("slot_id") != ":".join(str(value) for value in episode_protocol):
                raise ValueError(f"Schema-4 slot ID differs from its logical episode identity: {name}")
            names.add(name)
            history, candidates = _attempt_history(run_dir, row.get("attempts", []))
            expected_scene = row.get("scene")
            episodes.append({
                "episode_id": logical, "scene_id": name, "scene_root": str(manifest_row["resolved_root"]),
                "expected_scene": expected_scene, "expected_binary_sha256": binary_hash,
                "ego": episode_protocol[1],
                "traffic": episode_protocol[2],
                "startup": episode_protocol[3],
                "execution_status": row.get("status", "unknown"),
                "execution_failure": (history[-1].get("classification") if history else
                                      row.get("blocked_reason")),
                "attempt_history": history, "trace_candidates": candidates,
                "expected_files": None, "campaign_status": None,
                "batch_replication": None, "scene_inputs": row.get("inputs", {}),
                "trace_required": True, "source_row": row,
            })
        if names != set(manifest_scenes):
            raise ValueError("Stale manifest selection: expected scenes differ from schema-4 ledger")
        return {
            "kind": "schema4_run", "root": run_dir, "source_files": [ledger_path, Path(manifest_path).resolve()],
            "manifest_scenes": manifest_scenes, "episodes": episodes,
            "producer_revision": None, "campaign": None,
        }
    if ledger.get("schema_version") != 2 or not isinstance(ledger.get("results"), list):
        raise ValueError("Supported saved run indexes are schema 2 and schema 4")
    manifest_scenes = _scene_entries(manifest_path)
    indexed = {}
    for row in ledger["results"]:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise ValueError("Legacy schema-2 run index has a malformed result")
        name = row["name"]
        if name in indexed:
            raise ValueError(f"Duplicate legacy result scene: {name}")
        if name not in manifest_scenes or not _same_scene(row.get("scene"), manifest_scenes[name]):
            raise ValueError(f"Stale manifest identity for legacy result {name}")
        indexed[name] = row
    episodes = []
    seen = set()
    for name, manifest_row in manifest_scenes.items():
        row = indexed.get(name)
        protocol = {"ego_controller": None, "traffic_controller": None, "traffic_startup": None}
        if row:
            planner = row.get("planner")
            logical = _identity({**row, "planner": planner}, name, protocol=protocol)
            output = _record_path(row.get("output"), run_dir)
            trace = output / "trace.json" if output else None
            candidates = [(1, trace, None)] if trace and trace.is_file() else []
            history = [{"number": 1, "status": "indexed", "classification": None,
                        "record": None, "record_sha256": None,
                        "trace_path": str(trace) if candidates else None,
                        "trace_sha256": sha256(trace) if candidates else None,
                        "exit_code": None, "signal": None}]
            status = "completed"
            failure = None
            trace_required = planner in {"expert", "smart"}
        else:
            logical = _identity({"name": name, "planner": "unknown"}, name)
            trace = None
            candidates = []
            history = []
            status, failure = "not_recorded", "manifest_entry_not_in_legacy_run_index"
            trace_required = False
            planner = None
        if logical in seen:
            raise ValueError(f"Duplicate logical episode identity: {logical}")
        seen.add(logical)
        episodes.append({
            "episode_id": logical, "scene_id": name, "scene_root": str(manifest_row["resolved_root"]),
            "expected_scene": _trace_scene(manifest_row),
            "expected_binary_sha256": manifest_row.get("binary_sha256"),
            "ego": planner, "traffic": None, "startup": None,
            "execution_status": status, "execution_failure": failure,
            "attempt_history": history, "trace_candidates": candidates,
            "expected_files": None, "campaign_status": None,
            "batch_replication": None, "scene_inputs": manifest_row.get("inputs", {}),
            "trace_required": trace_required,
            "source_row": row,
        })
    return {
        "kind": "legacy_schema2_run", "root": run_dir,
        "source_files": [run_dir / "run.json", Path(manifest_path).resolve()],
        "manifest_scenes": manifest_scenes, "episodes": episodes,
        "producer_revision": None, "campaign": None,
    }


def _campaign_input(campaign_dir):
    root = Path(campaign_dir).expanduser().resolve()
    manifest_path = root / "campaign.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Saved campaign manifest does not exist: {manifest_path}")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("Saved campaign manifest must be a JSON object")
    inventory = manifest.get("inventory")
    if (not isinstance(inventory, dict) or inventory.get("schema_version") != 1
            or not isinstance(inventory.get("slots"), list)):
        raise ValueError("Saved campaign manifest has no supported inventory")
    scenes = inventory.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("Saved campaign inventory has no scene table")
    scene_rows = {}
    scene_roots = set()
    for scene in scenes:
        if not isinstance(scene, dict):
            raise ValueError("Saved campaign contains a malformed scene row")
        name = scene.get("name")
        root_ref = scene.get("root")
        if not isinstance(name, str) or not name or not isinstance(root_ref, (str, dict)):
            raise ValueError("Saved campaign contains a malformed scene identity")
        resolved = resolve_reference(root_ref).resolve()
        if name in scene_rows or resolved in scene_roots:
            raise ValueError("Saved campaign contains duplicate scene identities")
        scene_roots.add(resolved)
        scene_rows[name] = scene
    report_path = root / "verification_matrix.json"
    report = read_json(report_path) if report_path.is_file() else None
    report_rows = {}
    if report is not None:
        if (not isinstance(report, dict)
                or report.get("schema_version") not in {None, 1}):
            raise ValueError("Saved campaign report has an unsupported schema")
        rows = report.get("slots")
        if not isinstance(rows, list):
            raise ValueError("Saved campaign report has no slot rows")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Saved campaign report contains a malformed slot row")
            slot_id = row.get("slot_id")
            if not isinstance(slot_id, str) or not slot_id or slot_id in report_rows:
                raise ValueError("Saved campaign report contains duplicate or malformed slots")
            if row.get("status") not in _CAMPAIGN_STATES:
                raise ValueError(f"Unsupported saved campaign status for {slot_id}")
            report_rows[slot_id] = row
    slots = {}
    slot_protocols = set()
    for row in inventory["slots"]:
        if not isinstance(row, dict):
            raise ValueError("Saved campaign inventory contains a malformed slot row")
        slot_id = row.get("slot_id")
        if not isinstance(slot_id, str) or not slot_id or slot_id in slots:
            raise ValueError("Saved campaign inventory contains duplicate or malformed slots")
        if row.get("scene") not in scene_rows:
            raise ValueError(f"Campaign slot references unknown scene: {slot_id}")
        protocol_key = (row.get("scene"), row.get("ego"), row.get("traffic"), row.get("startup"))
        if any(not isinstance(value, str) or not value for value in protocol_key):
            raise ValueError(f"Campaign episode protocol is malformed: {slot_id}")
        if slot_id != ":".join(protocol_key):
            raise ValueError(f"Campaign slot ID differs from its logical episode identity: {slot_id}")
        if protocol_key in slot_protocols:
            raise ValueError(f"Duplicate or ambiguous campaign episode protocol: {protocol_key}")
        slot_protocols.add(protocol_key)
        slots[slot_id] = row
    if report is not None and set(report_rows) - set(slots):
        raise ValueError("Saved campaign report contains slots outside its frozen inventory")
    episodes = []
    for slot_id, frozen_slot in slots.items():
        report_row = report_rows.get(slot_id)
        if report_row and any(report_row.get(key) != frozen_slot.get(key)
                              for key in ("scene", "ego", "traffic", "startup")):
            raise ValueError(f"Saved campaign slot differs from frozen inventory: {slot_id}")
        scene = scene_rows[frozen_slot["scene"]]
        report_row = report_row or {}
        single = report_row.get("single", {})
        batch = report_row.get("batch", {})
        if not isinstance(single, dict) or not isinstance(batch, dict):
            raise ValueError(f"Saved campaign job accounting is malformed for {slot_id}")
        campaign_status = report_row.get("status")
        if campaign_status is None and frozen_slot.get("status") == "blocked":
            campaign_status = "BLOCKED"
        history, candidates = _attempt_history(root, single.get("attempts", []))
        if not candidates and single.get("directory"):
            trace = Path(single["directory"]).expanduser().resolve() / "trace.json"
            if trace.is_file():
                candidates = [(len(history) + 1, trace, None)]
        batch_history, batch_candidates = _attempt_history(root, batch.get("attempts", []))
        if not batch_candidates and batch.get("directory"):
            trace = Path(batch["directory"]).expanduser().resolve() / "trace.json"
            if trace.is_file():
                batch_candidates = [(len(batch_history) + 1, trace, None)]
        if single.get("files") and candidates:
            for candidate in candidates:
                if candidate[1].parent == Path(single.get("directory", "")).resolve():
                    break
        episodes.append({
            "episode_id": slot_id, "scene_id": frozen_slot["scene"],
            "scene_root": str(resolve_reference(scene["root"]).resolve()),
            "expected_scene": scene["root"],
            "expected_binary_sha256": scene.get("expected_binary_sha256"),
            "ego": frozen_slot.get("ego"), "traffic": frozen_slot.get("traffic"),
            "startup": frozen_slot.get("startup"),
            "execution_status": single.get("status", "not_recorded"),
            "execution_failure": single.get("failure") or
                ("campaign_report_missing_slot" if not report_row else None),
            "attempt_history": history, "trace_candidates": candidates,
            "expected_files": single.get("files"),
            "campaign_status": campaign_status,
            "campaign_slot": report_row if report_row else None,
            "campaign_integration_validity": report_row.get("integration_validity"),
            "batch_replication": {
                "execution_status": batch.get("status", "not_recorded"),
                "attempt_history": batch_history,
                "trace_sha256": batch_candidates[-1][1] and sha256(batch_candidates[-1][1])
                    if batch_candidates else None,
                "evidence_level": None,
                "files": batch.get("files"),
            },
            "batch_trace_candidates": batch_candidates,
            "scene_inputs": {**scene.get("inputs", {}), **scene.get("protected_inputs", {})},
            "trace_required": single.get("status") == "passed" or campaign_status == "PASS",
            "source_row": report_row or frozen_slot,
        })
    return {
        "kind": "saved_campaign", "root": root,
        "source_files": [manifest_path] + ([report_path] if report_path.is_file() else []),
        "manifest_scenes": {name: {**row, "resolved_root": resolve_reference(row["root"]).resolve()}
                            for name, row in scene_rows.items()},
        "episodes": episodes, "producer_revision": manifest.get("freeze", {}).get("commit"),
        "campaign": {"scope": manifest.get("scope"), "inventory_schema": inventory.get("schema_version"),
                     "report_schema": report.get("schema_version") if report else None,
                     "report_present": report is not None},
    }


def _dedupe(episodes):
    seen = set()
    for episode in episodes:
        identity = episode["episode_id"]
        if identity in seen:
            raise ValueError(f"Duplicate logical episode identity: {identity}")
        seen.add(identity)


def _snapshot(selection, profile_path):
    paths = {}
    for source in [*selection["source_files"], profile_path]:
        path = Path(source).resolve()
        if path.is_file():
            paths[str(path)] = {"path": str(path), "sha256": sha256(path),
                                "role": "profile" if path == profile_path else "selection_manifest_or_ledger"}
    for episode in selection["episodes"]:
        for input_name, entry in episode.get("scene_inputs", {}).items():
            if not isinstance(entry, dict):
                continue
            recorded_ref = entry.get("reference")
            try:
                path = resolve_reference(recorded_ref).resolve() if recorded_ref is not None else None
            except (KeyError, TypeError, ValueError, OSError):
                path = None
            if path is None:
                paths[f"missing:{episode['episode_id']}:{input_name}"] = {
                    "path": None, "reference": recorded_ref, "expected_sha256": entry.get("sha256"),
                    "present": False, "role": "recorded_scene_input",
                }
            elif path.is_file():
                paths[str(path)] = {"path": str(path), "reference": recorded_ref,
                                    "expected_sha256": entry.get("sha256"),
                                    "sha256": sha256(path), "present": True,
                                    "role": "recorded_scene_input"}
            else:
                paths[f"missing:{path}"] = {"path": str(path), "reference": recorded_ref,
                                             "expected_sha256": entry.get("sha256"),
                                             "present": False, "role": "recorded_scene_input"}
        expected_sets = (
            (episode.get("expected_files"), episode.get("trace_candidates", [])),
            ((episode.get("batch_replication") or {}).get("files"),
             episode.get("batch_trace_candidates", [])),
        )
        for expected_files, candidates in expected_sets:
            if not isinstance(expected_files, dict):
                continue
            folder = candidates[-1][1].parent if candidates else None
            for key, entry in expected_files.items():
                name = entry.get("path") if isinstance(entry, dict) else None
                if not isinstance(name, str) or Path(name).name != name:
                    continue
                candidate = folder / name if folder else None
                if candidate and candidate.is_file():
                    paths[str(candidate)] = {"path": str(candidate), "sha256": sha256(candidate),
                                             "expected_sha256": entry.get("sha256"),
                                             "present": True, "role": f"bound_evidence_{key}"}
                elif candidate:
                    paths[f"missing:{candidate}"] = {"path": str(candidate),
                        "expected_sha256": entry.get("sha256"), "present": False,
                        "role": f"bound_evidence_{key}"}
        for attempt in episode.get("attempt_history", []):
            path = attempt.get("record")
            if path and Path(path).is_file():
                paths[path] = {"path": path, "sha256": sha256(path), "role": "attempt_record"}
                attempt_folder = Path(path).parent
                for key, entry in attempt.get("evidence_files", {}).items():
                    name = entry.get("path") if isinstance(entry, dict) else None
                    if not isinstance(name, str) or Path(name).name != name:
                        continue
                    bound_path = attempt_folder / name
                    if bound_path.is_file():
                        paths[str(bound_path)] = {"path": str(bound_path),
                            "sha256": sha256(bound_path), "expected_sha256": entry.get("sha256"),
                            "present": True, "role": f"bound_evidence_{key}"}
                    else:
                        paths[f"missing:{bound_path}"] = {"path": str(bound_path),
                            "expected_sha256": entry.get("sha256"), "present": False,
                            "role": f"bound_evidence_{key}"}
            for field in ("trace_path",):
                path = attempt.get(field)
                if path and Path(path).is_file():
                    paths[path] = {"path": path, "sha256": sha256(path), "role": "saved_trace"}
                    trace = Path(path)
                    for filename, role in (("verification.json", "verification_sidecar"),
                                           ("diagnostic.json", "diagnostic_sidecar"),
                                           ("evaluation_capture.json", "evaluation_capture")):
                        sidecar = trace.with_name(filename)
                        if sidecar.is_file():
                            paths[str(sidecar)] = {"path": str(sidecar), "sha256": sha256(sidecar),
                                                   "role": role}
        for _, trace, _ in episode.get("trace_candidates", []):
            if trace and trace.is_file():
                paths[str(trace)] = {"path": str(trace), "sha256": sha256(trace), "role": "saved_trace"}
    return {"schema_version": 1, "files": [paths[key] for key in sorted(paths)]}


def _verify_snapshot(snapshot):
    changed = []
    for item in snapshot["files"]:
        if not item.get("present", True):
            if item.get("path") and Path(item["path"]).exists():
                changed.append(item["path"])
            continue
        path = Path(item["path"])
        if not path.is_file() or sha256(path) != item["sha256"]:
            changed.append(item["path"])
    if changed:
        raise ValueError("Selected saved evidence changed while evaluation was running: "
                         + ", ".join(changed[:5]))


def _taxonomy(result, events, evidence_status, accounting):
    labels = {}

    def add(label, basis):
        labels.setdefault(label, []).append(basis)

    for event in events:
        channel = event.get("channel")
        if channel in {"native_vehicle_collision", "collision"}:
            add("collision_or_unsafe_interaction", {"event_id": event.get("event_id"),
                                                    "channel": channel})
        if channel in {"native_offroad", "off_road"}:
            add("road_boundary_or_rule_violation", {"event_id": event.get("event_id"),
                                                   "channel": channel})
    for metric in result.get("metrics", []):
        if metric.get("criterion_outcome") != "fail":
            continue
        metric_id = metric.get("metric_id", "")
        basis = {"metric_id": metric_id, "window": metric.get("window"),
                 "evidence_refs": metric.get("evidence_refs", [])}
        if metric_id.startswith("safety.") and not metric_id.startswith("safety.map_"):
            add("collision_or_unsafe_interaction", basis)
        if metric_id.startswith("safety.map_") or metric_id.startswith("semantics."):
            add("road_boundary_or_rule_violation", basis)
        if metric_id == "task.outcome":
            add("task_or_maneuver_failure", basis)
        if metric_id == "efficiency.low_progress_candidate":
            add("deadlock_or_excessive_conservatism_candidate", basis)
        if metric_id.startswith("trajectory.acceleration_") or metric_id.startswith("trajectory.jerk_"):
            add("aggressive_or_uncomfortable_behavior", basis)
        if metric_id == "interaction.outcome":
            add("interaction_specific_failure", basis)
    if evidence_status == "invalid":
        add("evaluation_artifact_or_invalid_test", {"reason": "supplied evidence failed integrity or coherence checks"})
    if (accounting.get("execution_status") in {"failed", "interrupted"}
            and accounting.get("execution_failure")):
        add("evaluation_artifact_or_invalid_test", {
            "execution_failure": accounting["execution_failure"],
            "driving_failure_inferred": False,
        })
    return [{"label": label, "evidence": evidence_rows, "cause_established": False}
            for label, evidence_rows in sorted(labels.items())]


def _driving_outcome(result, events=()):
    if result is None:
        return {"status": "unavailable", "outcome": None, "reason": "No usable saved trace was evaluated"}
    task = result.get("task", {}).get("bounded_task_completion", {})
    terminal = result.get("input", {}).get("terminal_reason")
    outcome = task.get("outcome")
    coverage = (result.get("exposure", {}).get("event_observation_coverage", {})
                .get("windows", {}).get("full", {}).get("channels", {}))

    def observed(event_channel, coverage_channel):
        if coverage.get(coverage_channel, {}).get("status") != "valid":
            return None
        return any(row.get("channel") == event_channel for row in events)

    return {
        "status": ("assessed" if outcome in {"completed", "failed"} else
                   "unresolved" if outcome == "unresolved" else "unassessable"),
        "outcome": outcome,
        "reason": task.get("reason"),
        "terminal_reason": terminal,
        "collision_observed": observed("native_vehicle_collision", "collision_state"),
        "offroad_observed": observed("native_offroad", "collision_state"),
        "goal_event_observed": observed("goal_reached", "reached_goal"),
        "exposure": result.get("exposure", {}).get("windows", {}).get("full"),
        "is_campaign_integration_status": False,
    }


def _check_trace_protocol(episode, trace):
    protocol = ((episode.get("ego"), "ego_controller"),
                (episode.get("traffic"), "traffic_controller"),
                (episode.get("startup"), "traffic_startup"))
    for expected, field in protocol:
        actual = trace.get(field)
        if field == "ego_controller" and actual is None and trace.get("planner") != "controller_matrix":
            actual = trace.get("planner")
        if expected is not None and actual != expected:
            raise SavedEvidenceError(f"Trace {field} differs from selected ledger identity")


def _load_evidence(selection, episode, trace_path):
    if _attempt_status_mismatch(episode.get("attempt_history", []), trace_path):
        raise SavedEvidenceError("Attempt ledger status disagrees with its saved attempt record")
    kwargs = {
        "expected_files": episode.get("expected_files"),
        "expected_binary_sha256": episode.get("expected_binary_sha256"),
        "expected_scene": episode.get("expected_scene"),
        "producer_revision": selection.get("producer_revision"),
        "input_paths": _recorded_input_paths(episode, trace_path),
    }
    if (episode.get("campaign_slot") and episode.get("campaign_status") == "PASS"
            and episode.get("campaign_parity_verified")):
        kwargs["campaign_slot"] = episode["campaign_slot"]
    # The trace reader verifies the recorded sidecar bindings. Binary data is
    # optional for trace-only diagnostics; absence lowers context capability.
    saved = load_saved_trace(trace_path, **kwargs)
    _check_trace_protocol(episode, saved.playback.report)
    return saved, saved.playback.report


def _attempt_status_mismatch(history, trace_path):
    selected = [row for row in history if row.get("trace_path") == str(Path(trace_path).resolve())]
    return any(row.get("status_consistent") is False for row in selected)


def _recorded_input_paths(episode, trace_path):
    """Supply only currently available, identity-named inputs to the shared reader."""
    sidecar = Path(trace_path).with_name("verification.json")
    if not sidecar.is_file():
        return None
    try:
        verification = read_json(sidecar)
    except (OSError, ValueError, TypeError):
        return None  # The shared reader reports malformed supplied sidecars explicitly.
    inputs = verification.get("inputs", {}) if isinstance(verification, dict) else {}
    paths = {}
    scene_root = Path(episode["scene_root"]) if episode.get("scene_root") else None
    configured = episode.get("scene_inputs", {})
    for name, entry in inputs.items():
        selected = configured.get(name, {}) if isinstance(configured, dict) else {}
        candidate = None
        try:
            recorded_ref = selected.get("reference") or entry.get("reference")
            if recorded_ref is not None:
                candidate = resolve_reference(recorded_ref).resolve()
            elif name == "binary" and scene_root is not None:
                candidate = scene_root / "testing/map_000000.bin"
        except (KeyError, TypeError, ValueError, OSError):
            candidate = None
        if candidate is not None and candidate.is_file():
            paths[name] = candidate
    return paths or None


def _verify_campaign_parity(selection, episode):
    """Recheck persisted PASS using the unchanged canonical single/batch comparator."""
    if episode.get("campaign_status") != "PASS":
        return
    slot = episode.get("campaign_slot") or {}
    if (slot.get("exact_parity") is not True
            or slot.get("integration_validity") != "validated_exact"
            or slot.get("single", {}).get("status") != "passed"
            or slot.get("batch", {}).get("status") != "passed"):
        raise SavedEvidenceError("Campaign PASS status disagrees with its recorded integration fields")
    single = episode.get("trace_candidates", [])
    batch = episode.get("batch_trace_candidates", [])
    if not single or not batch:
        raise SavedEvidenceError("Campaign PASS has no saved single and batch traces")
    if (_attempt_status_mismatch(episode.get("attempt_history", []), single[-1][1])
            or _attempt_status_mismatch(episode.get("batch_replication", {}).get("attempt_history", []),
                                       batch[-1][1])):
        raise SavedEvidenceError("Campaign attempt ledger disagrees with a saved attempt record")
    from geotransfer_gap.runtime.run_trace import compare, load_bundle

    kwargs = {
        "expected_binary_sha256": episode.get("expected_binary_sha256"),
        "expected_scene": episode.get("expected_scene"),
        "producer_revision": selection.get("producer_revision"),
    }
    load_saved_trace(single[-1][1], expected_files=episode.get("expected_files"),
                     input_paths=_recorded_input_paths(episode, single[-1][1]), **kwargs)
    load_saved_trace(batch[-1][1], expected_files=episode["batch_replication"].get("files"),
                     input_paths=_recorded_input_paths(episode, batch[-1][1]), **kwargs)
    difference = compare(load_bundle(single[-1][1].parent), load_bundle(batch[-1][1].parent))
    if difference is not None:
        raise SavedEvidenceError("Persisted campaign PASS disagrees with canonical single/batch parity")
    episode["campaign_parity_verified"] = True


def _batch_evidence_status(episode, selection):
    candidates = episode.get("batch_trace_candidates", [])
    if not candidates:
        return "unavailable"
    if _attempt_status_mismatch(episode.get("batch_replication", {}).get("attempt_history", []),
                                candidates[-1][1]):
        episode["batch_replication"]["evidence_error"] = (
            "Attempt ledger status disagrees with its saved attempt record")
        return "invalid"
    trace_path = candidates[-1][1]
    try:
        batch = load_saved_trace(
            trace_path, expected_files=episode["batch_replication"].get("files"),
            expected_binary_sha256=episode.get("expected_binary_sha256"),
            expected_scene=episode.get("expected_scene"),
            producer_revision=selection.get("producer_revision"),
            input_paths=_recorded_input_paths(episode, trace_path),
        )
        episode["batch_replication"]["evidence_level"] = batch.evidence_level.value
        episode["batch_replication"]["trace_sha256"] = batch.playback.hashes["trace"]
        return "valid"
    except SavedEvidenceError as exc:
        episode["batch_replication"]["evidence_error"] = str(exc)
        return "invalid"


def _metric_summary(result):
    if result is None:
        return {"status": "unavailable", "count": 0, "valid": 0, "invalid": 0}
    metrics = result.get("metrics", [])
    return {
        "status": "computed",
        "count": len(metrics),
        "valid": sum(row.get("status") == "valid" for row in metrics),
        "unavailable": sum(row.get("status") == "unavailable" for row in metrics),
        "not_applicable": sum(row.get("status") == "not_applicable" for row in metrics),
        "undefined": sum(row.get("status") == "undefined" for row in metrics),
        "invalid": sum(row.get("status") == "invalid" for row in metrics),
        "failed_criteria": sum(row.get("criterion_outcome") == "fail" for row in metrics),
    }


def _episode_result(selection, episode, profile, profile_path):
    candidates = episode.get("trace_candidates", [])
    selected_trace = candidates[-1][1] if candidates else None
    account = {
        "execution_status": episode.get("execution_status", "unknown"),
        "execution_failure": episode.get("execution_failure"),
        "campaign_status": episode.get("campaign_status"),
        "campaign_integration_validity": episode.get("campaign_integration_validity"),
        "attempt_history": episode.get("attempt_history", []),
        "primary_view": "single" if selection["kind"] == "saved_campaign" else "run_entry",
        "batch_replication": episode.get("batch_replication"),
    }
    result, events, evidence_level = None, [], None
    evidence_status, evidence_reason, trace_hash = "unavailable", "No trace was produced", None
    if (selected_trace is None and
            (episode.get("execution_status") == "passed" or episode.get("campaign_status") == "PASS"
             or episode.get("trace_required") and episode.get("execution_status") == "completed")):
        evidence_status = "invalid"
        evidence_reason = "Saved execution status claims a pass but no primary trace is available"
    if selected_trace is not None:
        try:
            _verify_campaign_parity(selection, episode)
            saved, trace = _load_evidence(selection, episode, selected_trace)
            map_root = None
            try:
                map_root = resolve_reference(trace.get("scene")).resolve() if trace.get("scene") else None
            except (KeyError, TypeError, ValueError):
                map_root = None
            map_context = build_map_context(map_root, trace.get("binary_sha256"))
            scene_info = {
                "root": trace.get("scene"), "binary_sha256": trace.get("binary_sha256"),
                "status": "saved_scene_identity_checked" if map_context.status == "valid"
                    else "trace_identity_checked_map_context_" + map_context.status,
            }
            result, events = evaluate_episode(saved, profile, scene=scene_info,
                                              map_context=map_context, scene_root=map_root)
            result["input"]["trace_filename"] = selected_trace.name
            trace_hash = saved.playback.hashes["trace"]
            evidence_level = saved.evidence_level.value
            evidence_status, evidence_reason = "valid", "Saved trace and supplied binding passed the shared evidence reader"
            if episode.get("batch_replication"):
                account["batch_replication"]["evidence_status"] = _batch_evidence_status(episode, selection)
        except SavedEvidenceError as exc:
            evidence_status, evidence_reason = "invalid", str(exc)
            trace_hash = sha256(selected_trace) if selected_trace.is_file() else None
        if result is not None:
            result["input"]["trace_filename"] = selected_trace.name
            result["reporting"] = {
                "logical_episode_id": episode["episode_id"],
                "execution_status": account["execution_status"],
                "campaign_status": account["campaign_status"],
                "evidence_level": evidence_level,
                "metric_validity": _metric_summary(result),
                "task_result": result.get("task", {}).get("bounded_task_completion"),
                "encounter_result": {
                    "status": result.get("interactions", {}).get("status"),
                    "reason": result.get("interactions", {}).get("reason"),
                },
                "driving_outcome": _driving_outcome(result, events),
                "campaign_status_is_integration_only": True,
            }
    taxonomy = _taxonomy(result or {}, events, evidence_status, account)
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "episode_id": episode["episode_id"],
        "scene_id": episode.get("scene_id"),
        "protocol": {key: episode.get(key) for key in ("ego", "traffic", "startup")},
        "accounting": account,
        "evidence": {"status": evidence_status, "level": evidence_level,
                     "reason": evidence_reason, "trace_sha256": trace_hash,
                     "trace_path": str(selected_trace) if selected_trace else None,
                     "producer_revision": selection.get("producer_revision")},
        "metric_validity": _metric_summary(result),
        "task_result": result.get("task", {}).get("bounded_task_completion") if result else None,
        "encounter_result": ({"status": result.get("interactions", {}).get("status"),
                              "reason": result.get("interactions", {}).get("reason")}
                             if result else {"status": "unavailable", "reason": evidence_reason}),
        "driving_outcome": _driving_outcome(result, events),
        "failure_taxonomy": taxonomy,
        "event_accounting": {
            "status": result.get("observed_events", {}).get("status", "unavailable") if result else "unavailable",
            "count": len(events) if result and result.get("observed_events", {}).get("status") == "valid" else None,
            "first_observed_event": events[0] if events else None,
            "subsequent_events": events[1:] if events else [],
            "co_occurring_events_retained": True,
            "cause_established": False,
            "limitations": ["Event ordering is observational and does not establish causal responsibility."],
        },
        "episode_metrics": result,
        "event_records": events,
        "input_profile": {"raw_sha256": profile.raw_sha256,
                           "effective_sha256": profile.effective_sha256,
                           "path": str(profile_path)},
    }


def _slug(episode_id):
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", episode_id).strip("_.-")[:48] or "episode"
    digest = hashlib.sha256(episode_id.encode("utf-8")).hexdigest()[:12]
    return f"{label}-{digest}"


def _write_evaluation(output, selection, profile, profile_path, snapshot):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "input_snapshot.json", snapshot)
    episode_entries = []
    for episode in selection["episodes"]:
        record = _episode_result(selection, episode, profile, profile_path)
        slug = _slug(episode["episode_id"])
        episode_dir = output / "episodes" / slug
        episode_dir.mkdir(parents=True, exist_ok=False)
        events_path = episode_dir / "events.json"
        result_path = episode_dir / "result.json"
        write_json(events_path, {"schema_version": 1, "events": record.pop("event_records")})
        if record.get("episode_metrics") is not None:
            record["episode_metrics"]["observed_events"]["sha256"] = sha256(events_path)
            record["episode_metrics"]["observed_events"]["file"] = str(events_path.relative_to(output))
        record["events_file"] = str(events_path.relative_to(output))
        record["events_sha256"] = sha256(events_path)
        write_json(result_path, record)
        episode_entries.append({
            "episode_id": episode["episode_id"], "result_file": str(result_path.relative_to(output)),
            "result_sha256": sha256(result_path), "events_file": str(events_path.relative_to(output)),
            "events_sha256": sha256(events_path),
            "trace_sha256": record["evidence"].get("trace_sha256"),
            "trace_path": record["evidence"].get("trace_path"),
            "execution_status": record["accounting"].get("execution_status"),
            "campaign_status": record["accounting"].get("campaign_status"),
            "evidence_status": record["evidence"].get("status"),
            "evidence_level": record["evidence"].get("level"),
            "metric_status": record["metric_validity"].get("status"),
            "task_outcome": (record.get("task_result") or {}).get("outcome"),
            "encounter_status": (record.get("encounter_result") or {}).get("status"),
            "driving_outcome": record.get("driving_outcome", {}).get("outcome"),
            "failure_labels": [item["label"] for item in record.get("failure_taxonomy", [])],
        })
    _verify_snapshot(snapshot)
    index = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "selection": {"kind": selection["kind"], "root": str(selection["root"]),
                      "campaign": selection.get("campaign")},
        "profile": {"path": str(profile_path), "raw_sha256": profile.raw_sha256,
                    "effective_sha256": profile.effective_sha256,
                    "definition_version": profile.definition_version},
        "implementation": {"reporting_code_sha256": sha256(Path(__file__).resolve())},
        "input_snapshot": {"file": "input_snapshot.json", "sha256": sha256(output / "input_snapshot.json")},
        "expected_episodes": len(episode_entries),
        "accounting_counts": _counts(episode_entries),
        "episodes": episode_entries,
        "complete": True,
    }
    write_json(output / "index.json", index)
    render_report(output)
    return index


def _counts(episodes):
    keys = ("execution_status", "campaign_status", "evidence_status", "evidence_level", "metric_status")
    counts = {}
    for key in keys:
        result = {}
        for episode in episodes:
            value = episode.get(key) or "not_recorded"
            result[value] = result.get(value, 0) + 1
        counts[key] = dict(sorted(result.items()))
    return counts


_CSV_COLUMNS = ("episode_id", "scene_id", "ego", "traffic", "startup", "execution_status",
                "campaign_status", "evidence_status", "evidence_level", "metric_status",
                "task_outcome", "encounter_status", "driving_outcome", "failure_labels",
                "trace_sha256", "trace_path", "result_file")


def _presentation_rows(output, index):
    rows = []
    for episode in index["episodes"]:
        path = _evaluation_file(output, episode.get("result_file"), "saved evaluation result")
        if not path.is_file() or sha256(path) != episode["result_sha256"]:
            raise ValueError(f"Saved evaluation result is missing or has changed: {path}")
        event_path = _evaluation_file(output, episode.get("events_file"), "saved evaluation events")
        if not event_path.is_file() or sha256(event_path) != episode["events_sha256"]:
            raise ValueError(f"Saved evaluation events are missing or have changed: {event_path}")
        result = read_json(path)
        if result.get("episode_id") != episode["episode_id"]:
            raise ValueError("Saved evaluation result episode identity disagrees with its index")
        account = result.get("accounting", {})
        rows.append({
            "episode_id": episode["episode_id"], "scene_id": result.get("scene_id"),
            "ego": result.get("protocol", {}).get("ego"),
            "traffic": result.get("protocol", {}).get("traffic"),
            "startup": result.get("protocol", {}).get("startup"),
            "execution_status": account.get("execution_status"),
            "campaign_status": account.get("campaign_status"),
            "evidence_status": result.get("evidence", {}).get("status"),
            "evidence_level": result.get("evidence", {}).get("level"),
            "metric_status": result.get("metric_validity", {}).get("status"),
            "task_outcome": (result.get("task_result") or {}).get("outcome"),
            "encounter_status": (result.get("encounter_result") or {}).get("status"),
            "driving_outcome": result.get("driving_outcome", {}).get("outcome"),
            "failure_labels": ";".join(item["label"] for item in result.get("failure_taxonomy", [])),
            "trace_sha256": result.get("evidence", {}).get("trace_sha256"),
            "trace_path": result.get("evidence", {}).get("trace_path"),
            "result_file": episode["result_file"],
        })
    return rows


def _evaluation_file(output, value, label):
    """Resolve an index path while keeping both its spelling and target in output."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} path is missing or malformed")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} path must be relative to its evaluation directory")
    candidate = output / relative
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Unable to resolve {label} path: {value}") from exc
    if not resolved.is_relative_to(output):
        raise ValueError(f"{label} path escapes its evaluation directory: {value}")
    return candidate


def _render_csv(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _render_markdown(index, rows):
    lines = ["# Offline performance evaluation", "",
             f"Selection: `{index['selection']['kind']}`.",
             f"Accounted logical episodes: {index['expected_episodes']}.",
             "Execution, archived evidence, metric validity, task/encounter findings, and driving outcomes are reported separately. "
             "Campaign status records integration/parity only.", "",
             "## Accounting", "", "| Dimension | Status | Episodes |", "| --- | --- | ---: |"]
    for dimension, statuses in index["accounting_counts"].items():
        for status, count in statuses.items():
            lines.append(f"| {dimension.replace('_', ' ')} | {status} | {count} |")
    lines += ["", "## Episodes", "",
              "| Episode | Execution | Campaign integration | Evidence | Metrics | Task | Encounter | Driving | Failure labels |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        values = [row["episode_id"], row["execution_status"], row["campaign_status"],
                  f"{row['evidence_status']} / {row['evidence_level']}", row["metric_status"],
                  row["task_outcome"], row["encounter_status"], row["driving_outcome"], row["failure_labels"]]
        cells = [str(value or "unknown").replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "Failure labels are non-exclusive observations supported by the linked metric/event evidence. "
              "Event order does not prove root cause.", ""]
    return "\n".join(lines)


def _atomic_write_text(path, content):
    """Replace a report inside its evaluation directory without following links."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def render_report(output):
    output = Path(output).expanduser().resolve()
    runs = settings().runs.resolve()
    if not output.is_relative_to(runs):
        raise ValueError(f"Saved evaluation reports must remain beneath configured runs: {runs}")
    index_path = _evaluation_file(output, "index.json", "evaluation index")
    if not index_path.is_file():
        raise FileNotFoundError(f"Evaluation index does not exist: {index_path}")
    index = read_json(index_path)
    if not isinstance(index, dict):
        raise ValueError("Saved evaluation index must be an object")
    if index.get("schema_version") != INDEX_SCHEMA_VERSION or not isinstance(index.get("episodes"), list):
        raise ValueError("Unsupported saved evaluation index")
    if index.get("complete") is not True:
        raise ValueError("Saved evaluation index is incomplete")
    if index.get("expected_episodes") != len(index["episodes"]):
        raise ValueError("Evaluation index episode count is inconsistent")
    snapshot_ref = index.get("input_snapshot", {})
    if not isinstance(snapshot_ref, dict):
        raise ValueError("Saved evaluation input snapshot reference is malformed")
    snapshot_path = _evaluation_file(output, snapshot_ref.get("file"), "input snapshot")
    if (not snapshot_path.is_file() or not snapshot_ref.get("sha256")
            or sha256(snapshot_path) != snapshot_ref["sha256"]):
        raise ValueError("Selected input snapshot is missing or has changed")
    _dedupe(index["episodes"])
    rows = _presentation_rows(output, index)
    csv_text = _render_csv(rows)
    markdown = _render_markdown(index, rows)
    csv_path = _evaluation_file(output, "episodes.csv", "CSV report")
    markdown_path = _evaluation_file(output, "report.md", "Markdown report")
    _atomic_write_text(csv_path, csv_text)
    _atomic_write_text(markdown_path, markdown)
    return {"episodes": len(rows), "csv": str(output / "episodes.csv"),
            "markdown": str(output / "report.md")}


def evaluate_run(*, run=None, manifest=None, campaign=None, output, profile=None):
    if (run is None) == (campaign is None):
        raise ValueError("Choose exactly one of --run or --campaign")
    if run is not None and manifest is None:
        raise ValueError("An existing scene manifest is required with --run")
    if campaign is not None and manifest is not None:
        raise ValueError("--manifest applies to --run, not --campaign")
    profile_path = _profile_path(profile)
    if not profile_path.is_file():
        raise FileNotFoundError(f"Evaluation profile does not exist: {profile_path}")
    selection = (_campaign_input(campaign) if campaign is not None else _run_input(run, manifest))
    _dedupe(selection["episodes"])
    if not selection["episodes"]:
        raise ValueError("Selected saved input has no expected logical episodes")
    input_paths = list(selection["source_files"]) + [profile_path]
    scenes = [episode["scene_root"] for episode in selection["episodes"] if episode.get("scene_root")]
    for episode in selection["episodes"]:
        input_paths.extend(attempt["record"] for attempt in episode.get("attempt_history", [])
                           if attempt.get("record"))
        input_paths.extend(str(path) for _, path, _ in episode.get("trace_candidates", []))
        input_paths.extend(str(path) for _, path, _ in episode.get("batch_trace_candidates", []))
    destination = _validate_output(output, input_paths, scenes, profile_path)
    profile_values = load_profile(profile_path)
    if sha256(profile_path) != profile_values.raw_sha256:
        raise ValueError("Evaluation profile changed while its effective identity was being loaded")
    snapshot = _snapshot(selection, profile_path)
    return _write_evaluation(destination, selection, profile_values, profile_path, snapshot)
