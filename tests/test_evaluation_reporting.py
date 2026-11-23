"""Synthetic saved ledgers exercise offline cohort accounting and rerendering."""

import json

import pytest

from geotransfer_gap.artifacts import reference, sha256, write_json
from geotransfer_gap.evaluation import reporting


def _environment(monkeypatch, tmp_path):
    artifacts = tmp_path / "artifacts"
    runs = tmp_path / "runs"
    source = tmp_path / "source"
    reference_data = tmp_path / "reference-data"
    bench = tmp_path / "bench"
    for path in (artifacts, runs, source, reference_data, bench):
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GEOTRANSFER_ARTIFACTS", str(artifacts))
    monkeypatch.setenv("GEOTRANSFER_RUNS", str(runs))
    monkeypatch.setenv("GEOTRANSFER_SOURCE", str(source))
    monkeypatch.setenv("GEOTRANSFER_REFERENCE_DATA", str(reference_data))
    monkeypatch.setenv("GEOTRANSFER_BENCH", str(bench))
    return artifacts, runs


def _trace(scene, binary_hash, *, count=13, planner="controller_matrix",
           collision_step=None, goal_step=None):
    frames = []
    for step in range(count):
        actor = {"id": 41, "binary_index": 0, "present": True,
                 "x": float(step), "y": 0.0, "vx": 10.0, "vy": 0.0,
                 "heading": 0.0, "length": 4.5, "width": 1.8,
                 "collision_state": 1 if step == collision_step else 0,
                 "reached_goal": step == goal_step}
        state = {"step": step, "time_s": step / 10, "actors": [actor]}
        if planner == "controller_matrix":
            frames.append({"step": step, "time_s": step / 10, "state": state,
                           "actors": [{"source_id": 41, "binary_index": 0,
                                       "lifetime_generation": 0,
                                       "effective_owner": "ego:expert"}],
                           "transition_applied": step < count - 1})
        else:
            frames.append(state)
    result = {"schema_version": 3 if planner == "controller_matrix" else 2,
              "planner": planner, "scene": scene, "binary_sha256": binary_hash,
              "ego_binary_index": 0, "ego_source_id": 41, "frames": frames,
              "terminal_reason": "horizon", "requested_observation_frames": count,
              "observation_frames": count, "transitions": count - 1}
    if planner == "controller_matrix":
        result.update(ego_controller="expert", traffic_controller="idm",
                      traffic_startup="immediate", warmup_replay_frames=10,
                      steps_semantics="observation_frames")
    return result


def _scene_and_manifest(artifacts, tmp_path, *, name="synthetic"):
    root = artifacts / name
    testing = root / "testing"
    testing.mkdir(parents=True)
    binary = testing / "map_000000.bin"
    binary.write_bytes(b"synthetic scene binary")
    scene_ref = reference(root)
    manifest = tmp_path / f"{name}-manifest.json"
    write_json(manifest, {"schema_version": 2, "scenes": [
        {"name": name, "root": scene_ref, "binary_sha256": sha256(binary)}
    ]})
    return root, testing, binary, scene_ref, manifest


def _batch_run(run_dir, name, scene_ref, binary, trace_path=None, *, status="failed",
               attempts=None, slot_id=None):
    row = {"slot_id": slot_id or f"{name}:expert:idm:immediate", "name": name,
           "scene": scene_ref, "inputs": {"binary": {"reference": reference(binary),
                                                          "sha256": sha256(binary)}},
           "ego_controller": "expert", "traffic_controller": "idm",
           "traffic_startup": "immediate", "steps": 13,
           "status": status, "blocked_reason": "source_hold_missing" if status == "blocked" else None,
           "attempts": attempts or []}
    write_json(run_dir / "run.json", {"schema_version": 4, "protocol": {
        "ego_controller": "expert", "traffic_controller": "idm",
        "traffic_startup": "immediate", "steps": 13}, "results": [row]})
    return row


def _evaluation_output(runs, suffix):
    return runs / f"evaluation-{suffix}"


def _saved_legacy_evaluation(monkeypatch, tmp_path, suffix):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    _, _, binary, scene_ref, manifest = _scene_and_manifest(artifacts, tmp_path)
    run_dir = runs / f"{suffix}-run"
    run_dir.mkdir()
    trace_folder = run_dir / "synthetic"
    trace_folder.mkdir()
    write_json(trace_folder / "trace.json", _trace(scene_ref, sha256(binary), planner="expert"))
    write_json(run_dir / "run.json", {"schema_version": 2, "results": [{
        "scene": scene_ref, "name": "synthetic", "output": str(trace_folder), "planner": "expert"
    }]})
    output = _evaluation_output(runs, suffix)
    reporting.evaluate_run(run=run_dir, manifest=manifest, output=output)
    return runs, output


def _attested_matrix(folder, scene_ref, binary):
    folder.mkdir(parents=True, exist_ok=True)
    trace_path = folder / "trace.json"
    trace = _trace(scene_ref, sha256(binary))
    write_json(trace_path, trace)
    verification = {
        "schema_version": 2, "scene": scene_ref, "ego": "expert", "traffic": "idm",
        "startup": "immediate", "driving_outcome": "horizon",
        "inputs": {"binary": {"sha256": sha256(binary)}},
        "trace_sha256": sha256(trace_path),
        "lifecycle": [{"step": step, "actors": [{"source_id": 41, "binary_index": 0,
            "lifetime_generation": 0, "source_valid": True}]} for step in range(len(trace["frames"]))],
        "software": {"code_sha256": {"old.py": "c" * 64}},
    }
    write_json(folder / "verification.json", verification)
    files = {key: {"path": filename, "sha256": sha256(folder / filename)}
             for key, filename in (("trace", "trace.json"), ("provenance", "verification.json"))}
    attempt = {"schema_version": 1, "status": "passed", "exit_code": 0, "signal": None,
               "scene_config": {"scene": scene_ref, "ego_controller": "expert",
                                "traffic_controller": "idm", "traffic_startup": "immediate",
                                "steps": len(trace["frames"]),
                                "inputs": {"binary": {"sha256": sha256(binary)}}},
               "evidence": {"integration_validity": "validated_trace_and_provenance", "files": files}}
    write_json(folder / "attempt.json", attempt)
    return trace_path, files


def test_schema4_accounts_retry_failure_block_and_not_run_without_losing_trace_bytes(
        monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    root, testing, binary, scene_ref, manifest = _scene_and_manifest(artifacts, tmp_path)
    run_dir = runs / "matrix-run"
    run_dir.mkdir()
    first = run_dir / "attempts" / "0001" / "attempt.json"
    first.parent.mkdir(parents=True)
    write_json(first, {"schema_version": 1, "status": "failed", "classification": "worker_exit"})
    second = run_dir / "attempts" / "0002"
    second.mkdir(parents=True)
    trace = second / "trace.json"
    write_json(trace, _trace(scene_ref, sha256(binary)))
    attempt = second / "attempt.json"
    write_json(attempt, {"schema_version": 1, "status": "failed", "classification": "worker_exit",
                         "exit_code": 7})
    attempts = [{"number": 1, "status": "failed", "record": "attempts/0001/attempt.json"},
                {"number": 2, "status": "failed", "record": "attempts/0002/attempt.json"}]
    row = _batch_run(run_dir, "synthetic", scene_ref, binary, trace,
                     status="failed", attempts=attempts)
    # Add separately submitted blocked and not-run entries to the same schema-4 ledger.
    ledger = json.loads((run_dir / "run.json").read_text())
    for name, row_status in (("blocked", "blocked"), ("pending", "not_run")):
        scene_root, _, scene_binary, ref, _ = _scene_and_manifest(artifacts, tmp_path, name=name)
        ledger["results"].append({
            **row, "slot_id": f"{name}:expert:idm:immediate", "name": name, "scene": ref,
            "inputs": {"binary": {"reference": reference(scene_binary), "sha256": sha256(scene_binary)}},
            "status": row_status,
            "blocked_reason": "source_hold_missing" if row_status == "blocked" else None,
            "attempts": [],
        })
    write_json(run_dir / "run.json", ledger)
    # The complete cohort manifest must match all expected ledger scenes.
    write_json(manifest, {"schema_version": 2, "scenes": [
        {"name": name, "root": reference(artifacts / name),
         "binary_sha256": sha256(artifacts / name / "testing/map_000000.bin")}
        for name in ("synthetic", "blocked", "pending")
    ]})
    before = trace.read_bytes()

    index = reporting.evaluate_run(run=run_dir, manifest=manifest,
                                   output=_evaluation_output(runs, "ledger"))
    assert index["expected_episodes"] == 3
    assert index["accounting_counts"]["execution_status"] == {"blocked": 1, "failed": 1, "not_run": 1}
    evaluated = _evaluation_output(runs, "ledger")
    episode_rows = [json.loads((evaluated / item["result_file"]).read_text()) for item in index["episodes"]]
    failed = next(item for item in episode_rows if item["episode_id"] == row["slot_id"])
    blocked = next(item for item in episode_rows if item["scene_id"] == "blocked")
    pending = next(item for item in episode_rows if item["scene_id"] == "pending")
    assert failed["accounting"]["execution_status"] == "failed"
    assert [attempt["status"] for attempt in failed["accounting"]["attempt_history"]] == ["failed", "failed"]
    assert failed["evidence"]["level"] == "trace_only_diagnostic"
    assert failed["metric_validity"]["status"] == "computed"
    assert failed["episode_metrics"]["map_context"]["status"] == "unavailable"
    assert blocked["evidence"]["status"] == pending["evidence"]["status"] == "unavailable"
    assert failed["episode_metrics"]["task"]["bounded_task_completion"]["outcome"] == "unassessable"
    assert trace.read_bytes() == before


def test_legacy_schema2_partial_index_keeps_manifest_only_not_run_rows(monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    root, testing, binary, scene_ref, manifest = _scene_and_manifest(artifacts, tmp_path)
    missing_root, _, missing_binary, missing_ref, _ = _scene_and_manifest(
        artifacts, tmp_path, name="not-yet-run")
    absent_root, _, absent_binary, absent_ref, _ = _scene_and_manifest(
        artifacts, tmp_path, name="trace-missing")
    output_dir = runs / "legacy" / "synthetic"
    output_dir.mkdir(parents=True)
    trace = output_dir / "trace.json"
    write_json(trace, _trace(scene_ref, sha256(binary), planner="expert"))
    absent_output = runs / "legacy" / "trace-missing"
    absent_output.mkdir()
    run_dir = runs / "legacy"
    write_json(run_dir / "run.json", {"schema_version": 2, "results": [{
        "scene": scene_ref, "name": "synthetic", "output": str(output_dir), "planner": "expert"
    }, {"scene": absent_ref, "name": "trace-missing", "output": str(absent_output), "planner": "expert"}]})
    write_json(manifest, {"schema_version": 2, "scenes": [
        {"name": "synthetic", "root": scene_ref, "binary_sha256": sha256(binary)},
        {"name": "trace-missing", "root": absent_ref, "binary_sha256": sha256(absent_binary)},
        {"name": "not-yet-run", "root": missing_ref, "binary_sha256": sha256(missing_binary)},
    ]})
    index = reporting.evaluate_run(run=run_dir, manifest=manifest,
                                   output=_evaluation_output(runs, "legacy"))
    assert index["expected_episodes"] == 3
    assert index["accounting_counts"]["execution_status"] == {"completed": 2, "not_recorded": 1}
    rows = [json.loads((_evaluation_output(runs, "legacy") / row["result_file"]).read_text())
            for row in index["episodes"]]
    selected = next(row for row in rows if row["scene_id"] == "synthetic")
    assert selected["evidence"]["level"] == "trace_only_diagnostic"
    assert selected["episode_metrics"]["input"]["planner_layout"] == "expert"
    missing_trace = next(row for row in rows if row["scene_id"] == "trace-missing")
    assert missing_trace["accounting"]["execution_status"] == "completed"
    assert missing_trace["evidence"]["status"] == "invalid"
    assert missing_trace["metric_validity"]["status"] == "unavailable"
    assert next(row for row in rows if row["scene_id"] == "not-yet-run")["metric_validity"]["status"] == "unavailable"


def test_saved_campaign_counts_single_once_and_keeps_batch_as_replication(monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    _, _, binary, scene_ref, _ = _scene_and_manifest(artifacts, tmp_path)
    campaign = runs / "campaign"
    campaign.mkdir()
    single = campaign / "single" / "trace.json"
    batch = campaign / "batch" / "trace.json"
    single.parent.mkdir()
    batch.parent.mkdir()
    write_json(single, _trace(scene_ref, sha256(binary)))
    write_json(batch, _trace(scene_ref, sha256(binary)))
    slot_id = "synthetic:expert:idm:immediate"
    slot = {"slot_id": slot_id, "scene": "synthetic", "group": "german",
            "ego": "expert", "traffic": "idm", "startup": "immediate",
            "status": "not_run", "reason": None}
    write_json(campaign / "campaign.json", {"scope": "synthetic test", "freeze": {
        "commit": "a" * 40}, "inventory": {"schema_version": 1,
        "scenes": [{"name": "synthetic", "root": scene_ref,
                    "expected_binary_sha256": sha256(binary)}], "slots": [slot]}})
    write_json(campaign / "verification_matrix.json", {"slots": [{
        **slot, "status": "FAIL", "integration_validity": "failed", "exact_parity": False,
        "single": {"status": "passed", "directory": str(single.parent), "attempts": []},
        "batch": {"status": "failed", "directory": str(batch.parent), "attempts": []},
    }]})
    index = reporting.evaluate_run(campaign=campaign,
                                   output=_evaluation_output(runs, "campaign"))
    assert index["expected_episodes"] == 1
    record = json.loads((_evaluation_output(runs, "campaign") / index["episodes"][0]["result_file"]).read_text())
    assert record["accounting"]["primary_view"] == "single"
    assert record["accounting"]["campaign_status"] == "FAIL"
    assert record["accounting"]["batch_replication"]["trace_sha256"] == sha256(batch)
    assert record["accounting"]["batch_replication"]["evidence_status"] == "valid"


def test_passing_campaign_rechecks_historical_attestation_and_canonical_parity(monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    _, _, binary, scene_ref, _ = _scene_and_manifest(artifacts, tmp_path)
    campaign = runs / "attested-campaign"
    campaign.mkdir()
    single_path, single_files = _attested_matrix(campaign / "single", scene_ref, binary)
    batch_path, batch_files = _attested_matrix(campaign / "batch", scene_ref, binary)
    # Byte-identical evidence makes the existing canonical comparator pass.
    assert sha256(single_path) == sha256(batch_path)
    slot_id = "synthetic:expert:idm:immediate"
    slot = {"slot_id": slot_id, "scene": "synthetic", "group": "german",
            "ego": "expert", "traffic": "idm", "startup": "immediate",
            "status": "not_run", "reason": None}
    write_json(campaign / "campaign.json", {"scope": "synthetic test", "freeze": {
        "commit": "504218cb9ecd7fd64d2952630b9f10f56d80f923"},
        "inventory": {"schema_version": 1, "scenes": [{"name": "synthetic", "root": scene_ref,
                    "expected_binary_sha256": sha256(binary)}], "slots": [slot]}})
    report_row = {**slot, "status": "PASS", "integration_validity": "validated_exact",
                  "exact_parity": True,
                  "single": {"status": "passed", "directory": str(single_path.parent),
                             "files": single_files,
                             "attempts": [{"number": 1, "status": "passed",
                                           "record": str(single_path.parent / "attempt.json")}]},
                  "batch": {"status": "passed", "directory": str(batch_path.parent),
                            "files": batch_files,
                            "attempts": [{"number": 1, "status": "passed",
                                          "record": str(batch_path.parent / "attempt.json")}]}}
    write_json(campaign / "verification_matrix.json", {"schema_version": 1, "slots": [report_row]})
    index = reporting.evaluate_run(campaign=campaign,
                                   output=_evaluation_output(runs, "attested-campaign"))
    result = json.loads((_evaluation_output(runs, "attested-campaign") /
                         index["episodes"][0]["result_file"]).read_text())
    assert result["accounting"]["campaign_status"] == "PASS"
    assert result["evidence"]["level"] == "archived_attested"
    assert result["evidence"]["producer_revision"] == "504218cb9ecd7fd64d2952630b9f10f56d80f923"
    assert result["accounting"]["attempt_history"][0]["status_consistent"] is True
    assert result["accounting"]["batch_replication"]["evidence_level"] == "archived_attested"


def test_failed_campaign_retains_failure_while_successful_retry_supports_diagnostics(
        monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    _, _, binary, scene_ref, _ = _scene_and_manifest(artifacts, tmp_path)
    campaign = runs / "retry-campaign"
    campaign.mkdir()
    first = campaign / "single" / "attempt-1"
    first.mkdir(parents=True)
    first_record = first / "attempt.json"
    write_json(first_record, {"schema_version": 1, "status": "failed",
                              "classification": "worker_exit", "exit_code": 1})
    latest = campaign / "single" / "attempt-2"
    latest_path, files = _attested_matrix(latest, scene_ref, binary)
    batch = campaign / "batch"
    batch.mkdir()
    slot_id = "synthetic:expert:idm:immediate"
    slot = {"slot_id": slot_id, "scene": "synthetic", "group": "german",
            "ego": "expert", "traffic": "idm", "startup": "immediate",
            "status": "not_run", "reason": None}
    write_json(campaign / "campaign.json", {"freeze": {
        "commit": "504218cb9ecd7fd64d2952630b9f10f56d80f923"},
        "inventory": {"schema_version": 1, "scenes": [{"name": "synthetic", "root": scene_ref,
                    "expected_binary_sha256": sha256(binary)}], "slots": [slot]}})
    write_json(campaign / "verification_matrix.json", {"schema_version": 1, "slots": [{
        **slot, "status": "FAIL", "integration_validity": "failed", "exact_parity": None,
        "single": {"status": "failed", "directory": str(latest), "files": files,
                   "failure": "worker_exit", "attempts": [
                       {"number": 1, "status": "failed", "record": str(first_record)},
                       {"number": 2, "status": "passed", "record": str(latest / "attempt.json")}]},
        "batch": {"status": "failed", "attempts": []},
    }]})
    index = reporting.evaluate_run(campaign=campaign,
                                   output=_evaluation_output(runs, "retry-campaign"))
    record = json.loads((_evaluation_output(runs, "retry-campaign") /
                         index["episodes"][0]["result_file"]).read_text())
    assert record["accounting"]["campaign_status"] == "FAIL"
    assert record["accounting"]["execution_status"] == "failed"
    assert [item["status"] for item in record["accounting"]["attempt_history"]] == ["failed", "passed"]
    assert record["evidence"]["level"] == "archived_attested"
    assert record["metric_validity"]["status"] == "computed"


def test_mismatched_trace_sidecar_remains_an_invalid_accounting_row(monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    _, _, binary, scene_ref, manifest = _scene_and_manifest(artifacts, tmp_path)
    run_dir = runs / "tampered-run"
    attempt_dir = run_dir / "attempt"
    attempt_dir.mkdir(parents=True)
    trace_path = attempt_dir / "trace.json"
    trace = _trace(scene_ref, sha256(binary))
    write_json(trace_path, trace)
    original_hash = sha256(trace_path)
    write_json(attempt_dir / "verification.json", {
        "schema_version": 2, "scene": scene_ref, "ego": "expert", "traffic": "idm",
        "startup": "immediate", "driving_outcome": "horizon",
        "trace_sha256": original_hash, "inputs": {"binary": {"sha256": sha256(binary)}},
    })
    write_json(attempt_dir / "attempt.json", {"schema_version": 1, "status": "failed",
                                               "classification": "invalid_evidence"})
    trace_path.write_bytes(trace_path.read_bytes() + b" ")
    _batch_run(run_dir, "synthetic", scene_ref, binary, status="failed",
               attempts=[{"number": 1, "status": "failed", "record": "attempt/attempt.json"}])
    index = reporting.evaluate_run(run=run_dir, manifest=manifest,
                                   output=_evaluation_output(runs, "tampered"))
    record = json.loads((_evaluation_output(runs, "tampered") / index["episodes"][0]["result_file"]).read_text())
    assert record["accounting"]["execution_status"] == "failed"
    assert record["evidence"]["status"] == "invalid"
    assert "trace hash mismatch" in record["evidence"]["reason"]
    assert record["metric_validity"]["status"] == "unavailable"


def test_ledger_protocol_is_checked_on_the_shared_reader_result_once(monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    _, _, binary, scene_ref, manifest = _scene_and_manifest(artifacts, tmp_path)
    run_dir = runs / "protocol-mismatch-run"
    attempt_dir = run_dir / "attempt"
    attempt_dir.mkdir(parents=True)
    trace_path = attempt_dir / "trace.json"
    trace = _trace(scene_ref, sha256(binary))
    trace["ego_controller"] = "smart"
    for frame in trace["frames"]:
        frame["actors"][0]["effective_owner"] = "ego:smart"
    write_json(trace_path, trace)
    write_json(attempt_dir / "attempt.json", {"schema_version": 1, "status": "failed",
                                               "classification": "worker_exit"})
    _batch_run(run_dir, "synthetic", scene_ref, binary, status="failed",
               attempts=[{"number": 1, "status": "failed", "record": "attempt/attempt.json"}])
    original_reader = reporting.load_saved_trace
    calls = []

    def counted_reader(*args, **kwargs):
        calls.append(args[0])
        return original_reader(*args, **kwargs)

    monkeypatch.setattr(reporting, "load_saved_trace", counted_reader)
    output = _evaluation_output(runs, "protocol-mismatch")
    index = reporting.evaluate_run(run=run_dir, manifest=manifest, output=output)
    record = json.loads((output / index["episodes"][0]["result_file"]).read_text())
    assert len(calls) == 1
    assert record["evidence"]["status"] == "invalid"
    assert "ego_controller differs" in record["evidence"]["reason"]


def test_event_order_and_nonexclusive_taxonomy_do_not_claim_cause(monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    _, _, binary, scene_ref, manifest = _scene_and_manifest(artifacts, tmp_path)
    run_dir = runs / "event-run"
    trace_folder = run_dir / "synthetic"
    trace_folder.mkdir(parents=True)
    trace_path = trace_folder / "trace.json"
    write_json(trace_path, _trace(scene_ref, sha256(binary), planner="expert",
                                  collision_step=11, goal_step=11))
    write_json(run_dir / "run.json", {"schema_version": 2, "results": [{
        "scene": scene_ref, "name": "synthetic", "output": str(trace_folder), "planner": "expert"
    }]})
    index = reporting.evaluate_run(run=run_dir, manifest=manifest,
                                   output=_evaluation_output(runs, "events"))
    result = json.loads((_evaluation_output(runs, "events") / index["episodes"][0]["result_file"]).read_text())
    event_data = json.loads((_evaluation_output(runs, "events") / result["events_file"]).read_text())
    assert [event["channel"] for event in event_data["events"]] == [
        "native_vehicle_collision", "goal_reached"]
    assert result["event_accounting"]["first_observed_event"]["event_id"] == event_data["events"][0]["event_id"]
    assert result["event_accounting"]["co_occurring_events_retained"] is True
    assert result["event_accounting"]["cause_established"] is False
    labels = {item["label"]: item for item in result["failure_taxonomy"]}
    assert "collision_or_unsafe_interaction" in labels
    assert labels["collision_or_unsafe_interaction"]["cause_established"] is False


def test_stale_manifest_duplicate_ids_and_output_overlap_are_rejected(monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    _, _, binary, scene_ref, manifest = _scene_and_manifest(artifacts, tmp_path)
    run_dir = runs / "stale"
    run_dir.mkdir()
    row = _batch_run(run_dir, "synthetic", scene_ref, binary, status="not_run")
    write_json(manifest, {"schema_version": 2, "scenes": [
        {"name": "synthetic", "root": {"root": "artifacts", "path": "other"},
         "binary_sha256": sha256(binary)}
    ]})
    with pytest.raises(ValueError, match="Stale manifest"):
        reporting.evaluate_run(run=run_dir, manifest=manifest, output=_evaluation_output(runs, "stale"))
    write_json(manifest, {"schema_version": 2, "scenes": [
        {"name": "synthetic", "root": scene_ref, "binary_sha256": sha256(binary)},
        {"name": "synthetic", "root": scene_ref, "binary_sha256": sha256(binary)},
    ]})
    with pytest.raises(ValueError, match="duplicate or ambiguous"):
        reporting.evaluate_run(run=run_dir, manifest=manifest, output=_evaluation_output(runs, "duplicate"))
    write_json(manifest, {"schema_version": 2, "scenes": [
        {"name": "synthetic", "root": scene_ref, "binary_sha256": sha256(binary)}
    ]})
    with pytest.raises(ValueError, match="saved run input directory"):
        reporting.evaluate_run(run=run_dir, manifest=manifest, output=run_dir / "nested-evaluation")


def test_report_rerenders_saved_results_without_metric_recomputation(monkeypatch, tmp_path):
    _, output = _saved_legacy_evaluation(monkeypatch, tmp_path, "rerender")
    before = ((output / "episodes.csv").read_bytes(), (output / "report.md").read_bytes())
    monkeypatch.setattr(reporting, "evaluate_episode", lambda *args, **kwargs: pytest.fail("metrics reran"))
    rendered = reporting.render_report(output)
    after = ((output / "episodes.csv").read_bytes(), (output / "report.md").read_bytes())
    assert before == after
    assert rendered["episodes"] == 1


def test_report_rejects_incomplete_index(monkeypatch, tmp_path):
    _, output = _saved_legacy_evaluation(monkeypatch, tmp_path, "incomplete")
    index_path = output / "index.json"
    index = json.loads(index_path.read_text())
    index["complete"] = False
    write_json(index_path, index)
    with pytest.raises(ValueError, match="incomplete"):
        reporting.render_report(output)


@pytest.mark.parametrize("snapshot_path", ["../escaped-snapshot.json", None])
def test_report_rejects_escaped_snapshot_paths(monkeypatch, tmp_path, snapshot_path):
    runs, output = _saved_legacy_evaluation(monkeypatch, tmp_path, "escaped-snapshot")
    index_path = output / "index.json"
    index = json.loads(index_path.read_text())
    snapshot = output / index["input_snapshot"]["file"]
    escaped = runs / "escaped-snapshot.json"
    escaped.write_bytes(snapshot.read_bytes())
    index["input_snapshot"]["file"] = str(escaped) if snapshot_path is None else snapshot_path
    index["input_snapshot"]["sha256"] = sha256(escaped)
    write_json(index_path, index)
    with pytest.raises(ValueError, match="relative|escapes"):
        reporting.render_report(output)


@pytest.mark.parametrize("target", ["index", "snapshot", "result", "events"])
def test_report_rejects_symlinked_input_paths_escaping_evaluation(
        monkeypatch, tmp_path, target):
    runs, output = _saved_legacy_evaluation(monkeypatch, tmp_path, f"symlink-{target}")
    index_path = output / "index.json"
    index = json.loads(index_path.read_text())
    if target == "index":
        original = index_path
    elif target == "snapshot":
        original = output / index["input_snapshot"]["file"]
    else:
        episode = index["episodes"][0]
        original = output / episode[f"{target}_file"]
    outside = runs / f"outside-{target}.json"
    outside.write_bytes(original.read_bytes())
    original.unlink()
    original.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes its evaluation directory"):
        reporting.render_report(output)


@pytest.mark.parametrize("filename", ["episodes.csv", "report.md"])
def test_report_refuses_output_symlink_to_external_file(monkeypatch, tmp_path, filename):
    runs, output = _saved_legacy_evaluation(monkeypatch, tmp_path, f"output-link-{filename}")
    outside = runs / f"protected-{filename}"
    outside.write_bytes(b"preserve this file")
    output_file = output / filename
    output_file.unlink()
    output_file.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes its evaluation directory"):
        reporting.render_report(output)
    assert outside.read_bytes() == b"preserve this file"
    assert output_file.is_symlink()


def test_campaign_duplicate_slot_is_rejected(monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    _, _, binary, scene_ref, _ = _scene_and_manifest(artifacts, tmp_path)
    campaign = runs / "duplicate-campaign"
    campaign.mkdir()
    slot = {"slot_id": "synthetic:expert:idm:immediate", "scene": "synthetic", "ego": "expert",
            "traffic": "idm", "startup": "immediate", "status": "not_run"}
    write_json(campaign / "campaign.json", {"freeze": {"commit": "b" * 40},
        "inventory": {"schema_version": 1, "scenes": [{"name": "synthetic", "root": scene_ref,
        "expected_binary_sha256": sha256(binary)}], "slots": [slot, slot]}})
    with pytest.raises(ValueError, match="duplicate or malformed slots"):
        reporting.evaluate_run(campaign=campaign, output=_evaluation_output(runs, "duplicate-campaign"))


def test_incomplete_campaign_report_keeps_unrecorded_slot_distinct(monkeypatch, tmp_path):
    artifacts, runs = _environment(monkeypatch, tmp_path)
    _, _, binary, scene_ref, _ = _scene_and_manifest(artifacts, tmp_path)
    campaign = runs / "partial-campaign"
    campaign.mkdir()
    slot = {"slot_id": "synthetic:expert:idm:immediate", "scene": "synthetic",
            "ego": "expert", "traffic": "idm", "startup": "immediate", "status": "not_run"}
    write_json(campaign / "campaign.json", {"freeze": {"commit": "b" * 40},
        "inventory": {"schema_version": 1, "scenes": [{"name": "synthetic", "root": scene_ref,
        "expected_binary_sha256": sha256(binary)}], "slots": [slot]}})
    write_json(campaign / "verification_matrix.json", {"schema_version": 1, "slots": []})
    index = reporting.evaluate_run(campaign=campaign,
                                   output=_evaluation_output(runs, "partial-campaign"))
    record = json.loads((_evaluation_output(runs, "partial-campaign") /
                         index["episodes"][0]["result_file"]).read_text())
    assert index["expected_episodes"] == 1
    assert record["accounting"]["execution_status"] == "not_recorded"
    assert record["accounting"]["campaign_status"] is None
    assert record["accounting"]["execution_failure"] == "campaign_report_missing_slot"
