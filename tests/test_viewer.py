import pytest

from geotransfer_gap.visualization import viewer


def legacy(planner):
    return {
        "planner": planner, "ego_binary_index": 4, "binary_sha256": "binary",
        "frames": [{"step": 0, "actors": [{"id": 41, "binary_index": 4, "present": True,
                                          "movement_mode": 2, "x": 1, "y": 2}]}],
    }


@pytest.mark.parametrize("planner", ["expert", "smart"])
def test_historical_trace_retains_state_and_marks_unrecorded_metadata(planner):
    run = viewer.normalize_trace(legacy(planner))
    assert run["ego_id"] == 41
    assert run["frames"][0]["actors"][0]["movement_mode"] == 2
    assert run["frames"][0]["actors"][0]["lifetime_generation"] is None
    assert run["terminal_reason"] is None
    assert run["name"].startswith(planner)


@pytest.mark.parametrize("ego,traffic,startup", [
    ("ppo", "smart", "immediate"), ("smart", "smart", "immediate"),
    ("expert", "ppo", "source_hold"),
])
def test_matrix_role_mode_release_and_reentry(ego, traffic, startup):
    report = dict(legacy("controller_matrix"), ego_controller=ego, traffic_controller=traffic,
                  traffic_startup=startup, terminal_reason="ego_removed")
    frames, lifecycle = [], []
    for tick, present, generation in ((10, True, 0), (11, True, 0), (12, False, 0), (13, True, 1)):
        sid = 99
        held = startup == "source_hold" and tick == 10
        owner = "source_hold_replay" if held else f"traffic:{traffic}" if present else "not_present"
        action = [0, 0] if held else [0.1, -0.25] if present and tick != 13 else None
        row = {"source_id": sid, "binary_index": 2, "lifetime_generation": generation,
               "declared_controller": traffic if present else None, "effective_owner": owner,
               "applied_movement_mode": (2 if held else 0) if action else None, "action": action}
        if startup == "source_hold":
            row.update(scheduled_release_step=11, actual_release_step=11 if tick in (11,12) else None)
        frames.append({"step": tick, "transition_applied": tick != 13, "actors": [row],
                       "state": {"step": tick, "time_s": tick / 10, "actors": [
                           {"id": 41, "binary_index": 4, "present": tick != 13, "removed": tick == 13},
                           {"id": sid, "binary_index": 2, "present": present, "movement_mode": 2},
                       ]}})
        lifecycle.append({"step": tick, "actors": [{"source_id": sid, "source_valid": present,
                                                     "native_present": present}]})
    report["frames"] = frames
    run = viewer.normalize_trace(report, {"lifecycle": lifecycle})
    assert run["ego_id"] == 41 and run["terminal_reason"] == "ego_removed"
    assert run["frames"][1]["actors"][1]["action"] == [0.1, -0.25]
    assert "source gap" in run["frames"][2]["actors"][1]["events"]
    assert "re-entry" in run["frames"][3]["actors"][1]["events"]
    if startup == "source_hold":
        assert run["frames"][0]["actors"][1]["owner_label"] == "PPO target / expert replay (source hold)"
        assert "released at step 11" in run["frames"][1]["actors"][1]["events"]


def test_trace_only_viewer_has_explicit_missing_source_assets(tmp_path, monkeypatch):
    from geotransfer_gap.artifacts import sha256, write_json

    artifacts = tmp_path / "artifacts"
    monkeypatch.setenv("GEOTRANSFER_ARTIFACTS", str(artifacts))
    root = artifacts / "us"
    (root / "testing").mkdir(parents=True)
    binary = root / "testing/map_000000.bin"
    binary.write_bytes(b"fixture")
    trace_file = root / "trace.json"
    write_json(trace_file, dict(legacy("expert"), binary_sha256=sha256(binary)))
    monkeypatch.setattr(viewer, "binary_roads", lambda _: [])
    payload = viewer.view_payload(root, [trace_file])
    assert payload["ego_id"] == 41
    assert payload["source"] == payload["converted"] == []
    assert all("unavailable" in line for line in payload["limitations"])
    assert "unavailable" in viewer.build(root, tmp_path / "index.html", [trace_file]).read_text()
    with pytest.raises(ValueError, match="protected input"):
        viewer.build(root, root / "index.html", [trace_file])


@pytest.fixture
def matrix_bundle(tmp_path, monkeypatch):
    from geotransfer_gap.artifacts import reference, sha256, write_json

    artifacts = tmp_path / "artifacts"
    monkeypatch.setenv("GEOTRANSFER_ARTIFACTS", str(artifacts))
    root = artifacts / "scene"
    binary = root / "testing/map_000000.bin"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"scene")
    monkeypatch.setattr(viewer, "binary_roads", lambda _: [])
    folder = tmp_path / "episode"
    report = dict(legacy("controller_matrix"), scene=reference(root),
                  ego_controller="expert", traffic_controller="idm", traffic_startup="source_hold",
                  binary_sha256=sha256(binary), terminal_reason="horizon")
    report["frames"] = [{"step": 0, "state": report["frames"][0], "actors": []}]
    evidence = {
        "inputs": {"binary": {"sha256": sha256(binary)}},
        "scene": report["scene"], "ego": "expert", "traffic": "idm", "startup": "source_hold",
        "driving_outcome": "horizon", "lifecycle": [{"step": 0, "actors": []}],
    }
    write_json(folder / "trace.json", report)
    write_json(folder / "verification.json", evidence)
    return root, folder, report, evidence


def _write_evaluation_bundle(tmp_path, root, folder, report, *, status="valid", profile_hash=None,
                             event=None, limitation="fixture limitation"):
    from geotransfer_gap.artifacts import sha256, write_json

    digest = sha256(folder / "trace.json")
    binary_digest = sha256(root / "testing/map_000000.bin")
    profile_hash = profile_hash or "a" * 64
    profile = {"raw_sha256": "b" * 64, "effective_sha256": profile_hash,
               "definition_version": "1.0.0"}
    event = event or {
        "event_id": "terminal:ego_removed:0", "channel": "trace_terminal",
        "observation": "terminal_recorded", "attribution": "terminal_status_only",
        "step": 0, "time_s": 0.0, "actor": {"source_id": 41, "lifetime_generation": 0},
        "pose_present": False, "terminal_reason": "ego_removed",
        "evidence": "trace_terminal_reason", "cause_established": False,
    }
    output = tmp_path / ("evaluation-" + profile_hash[:6])
    output.mkdir()
    write_json(output / "input_snapshot.json", {"synthetic": True})
    write_json(output / "episodes/test/events.json", {"schema_version": 1, "events": [event]})
    events_hash = sha256(output / "episodes/test/events.json")
    protocol = {"ego": "expert", "traffic": "idm", "startup": "source_hold"}
    trace_protocol = {
        "ego_controller": protocol["ego"], "traffic_controller": protocol["traffic"],
        "traffic_startup": protocol["startup"],
    }
    metrics = [{
        "metric_id": "safety.native_vehicle_collision_onsets", "definition_version": "1.0.0",
        "status": status, "reason": limitation, "value": 0 if status == "valid" else None,
        "units": "onsets", "criterion_outcome": "not_assessed", "limitations": [limitation],
    }]
    episode_metrics = {
        "input": {"trace_sha256": digest, "binary_sha256": binary_digest,
                  "scene": report.get("scene"), "protocol": trace_protocol},
        "evaluator": {"effective_profile_sha256": profile_hash,
                      "definition_version": profile["definition_version"]},
        "metrics": metrics,
        "exposure": {"transition_count": 0, "transition_count_status": "valid",
                     "recorded_duration_s": 0.0, "controlled_transition_count": 0,
                     "controlled_duration_s": 0.0, "unknown_transition_count": 0},
        "limitations": [limitation], "context_limitations": [],
    }
    result = {
        "result_schema_version": 1, "episode_id": "scene:expert:idm:source_hold",
        "scene_id": root.name, "protocol": protocol,
        "accounting": {"execution_status": "passed", "campaign_status": "PASS"},
        "evidence": {"status": "valid", "level": "archived_attested", "trace_sha256": digest},
        "metric_validity": {"status": "computed"},
        "task_result": {"outcome": "failed"}, "encounter_result": {"status": "unavailable"},
        "driving_outcome": {"status": "assessed", "outcome": "failed"},
        "event_accounting": {"status": "valid", "limitations": []},
        "episode_metrics": episode_metrics, "input_profile": profile,
        "events_sha256": events_hash,
    }
    write_json(output / "episodes/test/result.json", result)
    snapshot_hash = sha256(output / "input_snapshot.json")
    entry = {"episode_id": result["episode_id"], "trace_sha256": digest,
             "trace_path": str(folder / "trace.json"), "result_file": "episodes/test/result.json",
             "result_sha256": sha256(output / "episodes/test/result.json"),
             "events_file": "episodes/test/events.json", "events_sha256": events_hash}
    write_json(output / "index.json", {
        "schema_version": 1, "complete": True, "expected_episodes": 1,
        "profile": profile, "input_snapshot": {"file": "input_snapshot.json", "sha256": snapshot_hash},
        "episodes": [entry],
    })
    return output


@pytest.mark.parametrize("changes", [
    {"ego": "smart"},
    {"traffic": "ppo"},
    {"startup": "immediate"},
    {"driving_outcome": "ego_removed"},
    {"lifecycle": [{"step": 1, "actors": []}]},
])
def test_rejects_same_scene_sidecar_from_a_different_playback(matrix_bundle, changes):
    from geotransfer_gap.artifacts import write_json

    root, folder, _, evidence = matrix_bundle
    assert len(viewer.view_payload(root, [folder / "trace.json"])["runs"]) == 1
    write_json(folder / "verification.json", dict(evidence, **changes))
    with pytest.raises(ValueError, match="Verification sidecar"):
        viewer.view_payload(root, [folder / "trace.json"])


@pytest.mark.parametrize("changed", ["trace.json", "verification.json"])
def test_checks_attempt_hashes_even_for_same_protocol(matrix_bundle, changed):
    from geotransfer_gap.artifacts import read_json, sha256, write_json

    root, folder, _, _ = matrix_bundle
    files = {kind: {"path": name, "sha256": sha256(folder / name)}
             for kind, name in (("trace", "trace.json"), ("provenance", "verification.json"))}
    write_json(folder / "attempt.json", {"status": "passed", "evidence": {"files": files}})
    assert len(viewer.view_payload(root, [folder / "trace.json"])["runs"]) == 1
    path = folder / changed
    write_json(path, dict(read_json(path), swapped=True))
    with pytest.raises(ValueError, match="hash.*" + changed):
        viewer.view_payload(root, [folder / "trace.json"])


def test_legacy_smart_diagnostic_rejects_wrong_traffic_protocol(matrix_bundle):
    from geotransfer_gap.artifacts import write_json

    root, folder, report, _ = matrix_bundle
    (folder / "verification.json").unlink()
    report = dict(legacy("smart"), traffic_protocol="hybrid_startup", binary_sha256=report["binary_sha256"])
    write_json(folder / "trace.json", report)
    diagnostic = {"binary_sha256": report["binary_sha256"], "timeline": [{"step": 0, "action": [0, 1]}]}
    write_json(folder / "diagnostic.json", diagnostic)
    assert viewer.view_payload(root, [folder / "trace.json"])["runs"][0]["frames"][0]["actors"][0]["action"] == [0, 1]
    write_json(folder / "diagnostic.json", dict(diagnostic, traffic_protocol="expert"))
    with pytest.raises(ValueError, match="Diagnostic traffic protocol"):
        viewer.view_payload(root, [folder / "trace.json"])


@pytest.fixture
def saved_campaign(tmp_path, matrix_bundle):
    from geotransfer_gap.artifacts import sha256, write_json

    root, folder, report, _ = matrix_bundle
    campaign = tmp_path / "campaign"
    files = {kind: {"path": name, "sha256": sha256(folder / name)}
             for kind, name in (("trace", "trace.json"), ("provenance", "verification.json"))}
    write_json(campaign / "campaign.json", {"inventory": {"scenes": [
        {"name": root.name, "root": report["scene"]},
    ]}})
    write_json(campaign / "verification_matrix.json", {"slots": [
        {"scene": root.name, "ego": "expert", "traffic": "idm", "startup": "source_hold",
         "status": "PASS", "single": {"directory": str(folder), "files": files}},
        {"scene": root.name, "ego": "smart", "traffic": "idm", "startup": "source_hold",
         "status": "BLOCKED", "reason": "missing authoritative example"},
    ]})
    return campaign, folder


def test_campaign_gallery_and_specific_configuration_use_saved_traces(tmp_path, saved_campaign):
    from geotransfer_gap.cli import main

    campaign, _ = saved_campaign
    gallery = tmp_path / "gallery"
    main(["view", "--campaign", str(campaign), "--output", str(gallery)])
    index = (gallery / "index.html").read_text()
    assert "scene.html#pair=expert%20%2F%20idm%20%2F%20source_hold" in index
    assert 'title="missing authoritative example"' in index
    assert "verification_matrix.json" in index
    assert '"name": "expert / idm / source_hold"' in (gallery / "scene.html").read_text()

    episode = tmp_path / "selected.html"
    main(["view", "--campaign", str(campaign), "--scene", "scene",
          "--ego", "expert", "--traffic", "idm", "--traffic-startup", "source_hold",
          "--output", str(episode)])
    assert '"name": "expert / idm / source_hold"' in episode.read_text()


def test_campaign_export_does_not_write_inside_evidence(tmp_path, saved_campaign, capsys):
    campaign, _ = saved_campaign
    with pytest.raises(SystemExit):
        viewer.main(["--campaign", str(campaign), "--output", str(campaign / "gallery")])
    assert "outside the saved campaign" in capsys.readouterr().err
    assert not (campaign / "gallery").exists()


def test_campaign_export_checks_saved_hashes_without_attempt_record(tmp_path, saved_campaign, capsys):
    from geotransfer_gap.artifacts import read_json, write_json

    campaign, folder = saved_campaign
    sidecar = folder / "verification.json"
    write_json(sidecar, dict(read_json(sidecar), swapped=True))
    with pytest.raises(SystemExit):
        viewer.main(["--campaign", str(campaign), "--output", str(tmp_path / "gallery")])
    assert "Playback hash" in capsys.readouterr().err


def test_blocked_campaign_configuration_explains_missing_evidence(tmp_path, saved_campaign, capsys):
    campaign, _ = saved_campaign
    with pytest.raises(SystemExit):
        viewer.main(["--campaign", str(campaign), "--scene", "scene", "--ego", "smart",
                     "--output", str(tmp_path / "blocked.html")])
    assert "missing authoritative example" in capsys.readouterr().err
    assert not (tmp_path / "blocked.html").exists()


def test_default_campaign_selection_keeps_full_gallery_intact(tmp_path, monkeypatch, saved_campaign):
    campaign, _ = saved_campaign
    monkeypatch.setenv("GEOTRANSFER_RUNS", str(tmp_path / "runs"))
    full = viewer.main(["--campaign", str(campaign)])
    scene = viewer.main(["--campaign", str(campaign), "--scene", "scene", "--ego", "expert"])
    assert full.parent / "scene.html" != scene
    assert full.is_file() and scene.is_file()


def test_campaign_gallery_cannot_follow_page_symlink_into_evidence(tmp_path, saved_campaign, capsys):
    campaign, _ = saved_campaign
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    report = campaign / "verification_matrix.json"
    before = report.read_bytes()
    (gallery / "scene.html").symlink_to(report)
    with pytest.raises(SystemExit):
        viewer.main(["--campaign", str(campaign), "--output", str(gallery)])
    assert "outside the saved campaign" in capsys.readouterr().err
    assert report.read_bytes() == before


def test_matching_saved_evaluation_attaches_and_seeks_terminal_without_pose(
        tmp_path, matrix_bundle):
    from geotransfer_gap.artifacts import read_json, write_json

    root, folder, report, _ = matrix_bundle
    # A stable actor can be retained in the observation table while the terminal
    # event explicitly records that no pose was available at its time.
    trace_path = folder / "trace.json"
    trace = read_json(trace_path)
    state = trace["frames"][0]["state"]
    state["actors"][0].update(present=False, x=None, y=None)
    write_json(trace_path, trace)
    evaluation = _write_evaluation_bundle(tmp_path, root, folder, trace)
    payload = viewer.view_payload(root, [trace_path], evaluations=[evaluation])
    attached = payload["runs"][0]["evaluation"]
    assert attached["status"] == "attached"
    assert attached["campaign"]["status"] == "PASS"
    assert attached["driving_outcome"]["outcome"] == "failed"
    assert attached["events"][0]["step"] == 0 and attached["events"][0]["pose_present"] is False
    page = viewer.build(root, tmp_path / "view.html", [trace_path], evaluations=[evaluation]).read_text()
    assert '"status": "PASS"' in page and "integration/parity only" in page
    assert "Recorded trace terminal status." in page
    assert '"pose_present": false' in page


def test_old_trace_without_metrics_remains_viewable(tmp_path, matrix_bundle):
    root, folder, _, _ = matrix_bundle
    payload = viewer.view_payload(root, [folder / "trace.json"])
    assert payload["runs"][0]["evaluation"]["status"] == "unavailable"
    page = viewer.build(root, tmp_path / "old.html", [folder / "trace.json"]).read_text()
    assert "No evaluation attachment" in page
    assert '"name": "expert / idm / source_hold"' in page


def test_explicit_fresh_run_comparison_uses_existing_execution_entrypoint(
        tmp_path, matrix_bundle, monkeypatch):
    from geotransfer_gap import execution
    from geotransfer_gap.artifacts import write_json

    scene, _, report, _ = matrix_bundle
    calls = []

    def fake_saved_run(args):
        calls.append(args)
        planner = args[-1]
        run = tmp_path / "runs" / planner
        write_json(run / scene.name / "trace.json", {
            **legacy(planner), "scene": report["scene"], "binary_sha256": report["binary_sha256"],
        })
        return run

    monkeypatch.setattr(execution, "main", fake_saved_run)
    page = tmp_path / "fresh.html"
    viewer.main(["--scene", str(scene), "--run", "both", "--output", str(page)])
    assert [args[-1] for args in calls] == ["expert", "smart"]
    html = page.read_text()
    assert '"name": "expert evaluator rollout"' in html and '"name": "smart evaluator rollout"' in html


def test_stale_trace_hash_is_not_attached(tmp_path, matrix_bundle):
    from geotransfer_gap.artifacts import read_json, write_json

    root, folder, report, _ = matrix_bundle
    evaluation = _write_evaluation_bundle(tmp_path, root, folder, report)
    trace_path = folder / "trace.json"
    write_json(trace_path, dict(read_json(trace_path), harmless_later_metadata=True))
    attachment = viewer.view_payload(root, [trace_path], evaluations=[evaluation])["runs"][0]["evaluation"]
    assert attachment["status"] == "stale"
    assert "different trace hash" in attachment["reason"]


def test_same_trace_with_conflicting_protocol_is_rejected(tmp_path, matrix_bundle):
    from geotransfer_gap.artifacts import read_json, sha256, write_json

    root, folder, report, _ = matrix_bundle
    evaluation = _write_evaluation_bundle(tmp_path, root, folder, report)
    result_path = evaluation / "episodes/test/result.json"
    result = read_json(result_path)
    result["protocol"]["traffic"] = "ppo"
    write_json(result_path, result)
    index_path = evaluation / "index.json"
    index = read_json(index_path)
    index["episodes"][0]["result_sha256"] = sha256(result_path)
    write_json(index_path, index)
    with pytest.raises(ValueError, match="scene/protocol identity"):
        viewer.view_payload(root, [folder / "trace.json"], evaluations=[evaluation])


@pytest.mark.parametrize("file,expected", [
    ("episodes/test/result.json", "result is missing or has changed"),
    ("episodes/test/events.json", "events are missing or have changed"),
])
def test_tampered_saved_evaluation_files_are_rejected(tmp_path, matrix_bundle, file, expected):
    from geotransfer_gap.artifacts import read_json, write_json

    root, folder, report, _ = matrix_bundle
    evaluation = _write_evaluation_bundle(tmp_path, root, folder, report)
    path = evaluation / file
    write_json(path, dict(read_json(path), tampered=True))
    with pytest.raises(ValueError, match=expected):
        viewer.view_payload(root, [folder / "trace.json"], evaluations=[evaluation])


def test_unavailable_metric_stays_null_and_conflicting_profiles_are_suppressed(
        tmp_path, matrix_bundle):
    root, folder, report, _ = matrix_bundle
    first = _write_evaluation_bundle(tmp_path, root, folder, report, status="unavailable")
    unavailable = viewer.view_payload(root, [folder / "trace.json"], evaluations=[first])["runs"][0]["evaluation"]
    assert unavailable["metrics"][0]["value"] is None
    page = viewer.build(root, tmp_path / "unavailable.html", [folder / "trace.json"],
                        evaluations=[first]).read_text()
    assert '"status": "unavailable"' in page and "not available" in page

    second = _write_evaluation_bundle(tmp_path, root, folder, report,
                                      profile_hash="c" * 64)
    conflict = viewer.view_payload(root, [folder / "trace.json"],
                                   evaluations=[first, second])["runs"][0]["evaluation"]
    assert conflict["status"] == "conflict"
    assert "conflicting metric profiles" in conflict["reason"]
    assert "metrics suppressed" in conflict["reason"]


def test_evaluation_text_is_not_interpreted_as_html(tmp_path, matrix_bundle):
    root, folder, report, _ = matrix_bundle
    hostile = "</script><img src=x onerror=alert(1)>"
    event = {"event_id": "hostile", "channel": "native_vehicle_collision", "step": 0,
             "time_s": 0.0, "actor": {"source_id": 41}, "pose_present": True,
             "evidence": hostile, "cause_established": False}
    evaluation = _write_evaluation_bundle(tmp_path, root, folder, report, event=event,
                                          limitation=hostile)
    html = viewer.build(root, tmp_path / "escaped.html", [folder / "trace.json"],
                        evaluations=[evaluation]).read_text()
    assert "</script><img" not in html
    assert "<\\/script><img" in html


def test_campaign_evaluation_attachment_respects_filtered_output_isolation(
        tmp_path, saved_campaign):
    from geotransfer_gap.artifacts import read_json, resolve_reference, sha256
    from geotransfer_gap.visualization.campaign_gallery import render_campaign

    campaign, folder = saved_campaign
    # Use the existing fixture trace as the exact evaluation input.
    trace = folder / "trace.json"
    report = read_json(trace)
    root = resolve_reference(report["scene"])
    evaluation = _write_evaluation_bundle(tmp_path, root, folder, report)
    evidence_before = {p: sha256(p) for p in (campaign / "campaign.json",
                                               campaign / "verification_matrix.json",
                                               evaluation / "index.json",
                                               evaluation / "episodes/test/result.json",
                                               evaluation / "episodes/test/events.json")}
    output = tmp_path / "selected"
    page = render_campaign(campaign, output, scene="scene", ego="expert",
                           traffic="idm", startup="source_hold", evaluations=[evaluation])
    assert page.is_file()
    assert '"status": "PASS"' in page.read_text() and "integration/parity only" in page.read_text()
    assert all(sha256(path) == digest for path, digest in evidence_before.items())


def test_viewer_output_cannot_be_written_inside_evaluation_evidence(tmp_path, matrix_bundle):
    root, folder, report, _ = matrix_bundle
    evaluation = _write_evaluation_bundle(tmp_path, root, folder, report)
    with pytest.raises(ValueError, match="outside attached evaluation"):
        viewer.build(root, evaluation / "viewer.html", [folder / "trace.json"],
                     evaluations=[evaluation])
    assert not (evaluation / "viewer.html").exists()
