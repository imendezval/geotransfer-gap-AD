"""Compose one saved episode into a finite, versioned offline result."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from geotransfer_gap.artifacts import sha256
from geotransfer_gap.evaluation.context import MapContext, build_task_context
from geotransfer_gap.evaluation.kinematics import measure_kinematics
from geotransfer_gap.evaluation.map_metrics import measure_map_metrics
from geotransfer_gap.evaluation.safety import measure_safety
from geotransfer_gap.evaluation.interactions import measure_interactions
from geotransfer_gap.evaluation.semantics import measure_semantics
from geotransfer_gap.evaluation.compatibility import measure_secondary
from geotransfer_gap.evaluation.tasks import (
    _load_annotation,
    finalize_safe_completion,
    measure_tasks,
)


RESULT_SCHEMA_VERSION = 1


def _code_identity():
    package = Path(__file__).parent
    owners = ("contracts.py", "profile.py", "kinematics.py", "capture.py", "safety.py",
              "context.py", "map_metrics.py", "tasks.py", "interactions.py",
              "semantics.py", "compatibility.py", "episode.py", "commands.py")
    files = {f"evaluation/{name}": sha256(package / name) for name in owners}
    files["runtime/trace_io.py"] = sha256(package.parent / "runtime/trace_io.py")
    files["maps/lanelet.py"] = sha256(package.parent / "maps/lanelet.py")
    files["validation/audit_physical_source.py"] = sha256(
        package.parent / "validation/audit_physical_source.py"
    )
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"files": files, "sha256": hashlib.sha256(canonical).hexdigest()}


def evaluate_episode(saved, profile, *, scene=None, map_context=None, scene_root=None,
                     task_context=None):
    """Read a saved trace and calculate supported exposure and driving metrics."""
    report = saved.playback.report
    frames = list(saved.frames())
    measured = measure_kinematics(
        frames, saved.ego_source_id, report, profile,
        evaluation_capture=saved.playback.evaluation_capture,
        evaluation_capture_bound=saved.playback.evaluation_capture_bound,
    )
    safety = measure_safety(
        frames, saved.ego_source_id, report, profile, measured["events"],
        measured["exposure"],
        evaluation_capture=saved.playback.evaluation_capture,
        evaluation_capture_bound=saved.playback.evaluation_capture_bound,
    )
    measured["metrics"].extend(safety["metrics"])
    spatial = measure_map_metrics(
        frames, saved.ego_source_id, profile, measured["exposure"],
        map_context or MapContext(
            status="unavailable",
            reason="No selected scene or hash-bound source-map context was supplied",
        ),
    )
    measured["metrics"].extend(spatial["metrics"])
    metric_refs = [{"kind": "trace", "sha256": saved.playback.hashes["trace"]}]
    if saved.playback.bound:
        metric_refs.extend({"kind": key, "sha256": digest}
                           for key, digest in saved.playback.hashes.items()
                           if key != "trace")
    selected_task = task_context or build_task_context(
        scene_root, report.get("binary_sha256"), saved.ego_source_id, map_context,
        expected_ego_binary_index=report.get("ego_binary_index"),
    )
    annotation = _load_annotation(selected_task, profile)
    task_measurement = measure_tasks(
        frames, saved.ego_source_id, report, profile, measured["exposure"],
        measured["events"], selected_task, evidence_refs=metric_refs,
        evaluation_capture=saved.playback.evaluation_capture,
        evaluation_capture_bound=saved.playback.evaluation_capture_bound,
        annotation=annotation,
    )
    measured["metrics"].extend(task_measurement["metrics"])
    interactions = measure_interactions(
        frames, saved.ego_source_id, report, profile, measured["exposure"],
        selected_task, map_context, measured["events"], scene_root=scene_root,
        risk_metrics=safety["metrics"],
    )
    measured["metrics"].extend(interactions["metrics"])
    lane_assignment = next((row for row in spatial["metrics"]
                            if row["metric_id"] == "trajectory.lane_lateral_offset"
                            and row["window"] == "primary"), None)
    lane_assignment_samples = (
        lane_assignment.get("value", {}).get("samples", ())
        if lane_assignment and isinstance(lane_assignment.get("value"), dict) else ())
    semantics = measure_semantics(
        frames, saved.ego_source_id, profile,
        map_context or MapContext(status="unavailable",
                                  reason="No hash-bound directed map was supplied"),
        annotation,
        lane_assignment_samples=lane_assignment_samples,
        evidence_refs=(tuple(metric_refs) + tuple(selected_task.evidence_refs)
                       + tuple(map_context.evidence_refs if map_context else ())),
        trace_horizon_complete=(report.get("terminal_reason") == "horizon"
                                and len(frames) == report.get("requested_observation_frames")),
    )
    measured["metrics"].extend(semantics["metrics"])
    finalize_safe_completion(
        task_measurement,
        annotation=annotation,
        map_metrics=spatial["metrics"],
        interactions=interactions,
        semantics=semantics,
        lane_assignment_samples=lane_assignment_samples,
        profile=profile,
    )
    task_measurement["task"]["encounter_completion"] = {
        "status": interactions["status"],
        "reason": interactions["reason"],
        "interactions": interactions["interactions"],
        "separate_from_bounded_task_completion": True,
    }
    map_evidence_refs = [dict(item) for item in
                         (map_context.evidence_refs if map_context else ())]
    for metric in measured["metrics"]:
        refs = list(metric_refs)
        if (metric["metric_id"].startswith("safety.map_")
                or metric["metric_id"].startswith("trajectory.lane_")):
            refs.extend(map_evidence_refs)
        if metric["metric_id"] in {
                "trajectory.route_progress", "trajectory.normalized_route_progress",
                "efficiency.stationary_duration", "efficiency.low_progress_candidate",
                "efficiency.completion_time", "task.outcome", "task.safe_completion"}:
            refs.extend(dict(item) for item in selected_task.evidence_refs)
        metric["evidence_refs"] = refs
    secondary = measure_secondary(
        frames, saved.ego_source_id, report, profile,
        task_context=selected_task, task_result=task_measurement["task"],
        task_metrics=task_measurement["metrics"], safety_metrics=safety["metrics"],
    )
    secondary["provenance"].update({
        "trace_sha256": saved.playback.hashes["trace"],
        "bound_sidecar_sha256": {
            key: value for key, value in saved.playback.hashes.items() if key != "trace"},
        "evidence_level": saved.evidence_level.value,
        "trace_sidecar_bound": saved.playback.bound,
        "producer_revision": saved.producer_revision,
        "effective_profile_sha256": profile.effective_sha256,
    })
    event_channels = measured["exposure"]["event_observation_coverage"]["windows"]["full"]["channels"]
    has_event_channel = any(row["status"] == "valid" for row in event_channels.values())
    event_coverage_incomplete = any(
        row["status"] != "valid" or row["fraction"] != 1.0
        for row in event_channels.values()
    )
    event_evidence_present = has_event_channel or bool(measured["events"])
    checkpoint_identity = getattr(saved, "model_checkpoint_identity", None)
    if not isinstance(checkpoint_identity, dict):
        checkpoint_identity = {
            role: {"status": "not_recorded", "sha256": None}
            for role in ("ego", "traffic")
        }
    result = {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "input": {
            "trace_sha256": saved.playback.hashes["trace"],
            "evidence_sha256": {key: digest for key, digest in saved.playback.hashes.items()
                                 if key != "trace"},
            "trace_schema_version": report["schema_version"],
            "planner_layout": report["planner"],
            "trace_filename": None,
            "evidence_level": saved.evidence_level.value,
            "trace_sidecar_bound": saved.playback.bound,
            "live_validation_status": "not_run_offline_evaluation",
            "producer_revision": saved.producer_revision,
            "producer_revision_status": (
                "recorded" if saved.producer_revision else "not_recorded_by_saved_trace_contract"
            ),
            "binary_sha256": report["binary_sha256"],
            "scene": report.get("scene"),
            "protocol": {
                key: report.get(key) for key in
                ("ego_controller", "traffic_controller", "traffic_startup", "warmup_replay_frames")
                if key in report
            },
            "checkpoint_identity": {
                role: checkpoint_identity.get(role, {"status": "not_recorded", "sha256": None})
                for role in ("ego", "traffic")
            },
            "traffic_protocol": report.get("traffic_protocol"),
            "startup_policy": report.get("startup_policy"),
            "terminal_reason": report.get("terminal_reason"),
        },
        "evaluator": {
            "profile_id": profile.values["profile"]["id"],
            "definition_version": profile.definition_version,
            "effective_profile_sha256": profile.effective_sha256,
            "raw_profile_sha256": profile.raw_sha256,
            "evaluator_code": _code_identity(),
        },
        "ego": {"source_id": saved.ego_source_id,
                "binary_index": report["ego_binary_index"]},
        "metrics": measured["metrics"],
        "secondary_metrics": secondary,
        "exposure": measured["exposure"],
        "observed_events": {
            "status": "valid" if event_evidence_present else "unavailable",
            "count": len(measured["events"]) if event_evidence_present else None,
            "file": "events.json" if measured["events"] else None,
            "sha256": None,
            "count_is_lower_bound": event_coverage_incomplete,
            "cause_inferred": False,
        },
        "context_limitations": ([
            "No validated task context was supplied; task outcomes are unassessable."
        ] if selected_task.status != "valid" else [
            "Task bounds come from the hash-bound source evaluation contract and converted scene."
        ] + (["No sparse task annotation was supplied; source-owned bounds are used."]
             if task_measurement["task"]["context"]["annotation"]["status"] == "absent" else [])) + [
            "Map metrics are supported only by hash-bound mapped Lanelet surfaces; legal access and map completeness are not assessed.",
            "Native collision partner and detector-center details require a hash-bound evaluation capture.",
        ],
        "task": task_measurement["task"],
        "interactions": {
            "status": interactions["status"],
            "reason": interactions["reason"],
            "timebase": interactions["timebase"],
            "results": interactions["interactions"],
            "source_admission_decision_used": interactions.get("source_admission_decision_used", False),
            "compliance_criterion": interactions.get("compliance_criterion"),
        },
        "semantic_compliance": {
            key: value for key, value in semantics.items() if key != "metrics"
        },
        "scene_context": (scene if scene is not None else
                          {"status": "trace_only_no_map_or_task_context"}),
        "map_context": spatial["context"],
        "limitations": [
            "A readable trace does not attest to its execution; evidence level is reported separately.",
            "Observed event timing does not establish root cause or responsibility.",
            "Missing task/map annotations are unavailable and are not treated as zero or pass.",
            "Interaction realization is measured separately from source opportunity, task completion, and core driving events.",
        ],
    }
    return result, measured["events"]
