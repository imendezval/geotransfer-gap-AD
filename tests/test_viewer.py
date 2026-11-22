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

    monkeypatch.setenv("GEOTRANSFER_ARTIFACTS", str(tmp_path))
    root = tmp_path / "us"
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
    assert "unavailable" in viewer.build(root, root / "index.html", [trace_file]).read_text()


@pytest.fixture
def matrix_bundle(tmp_path, monkeypatch):
    from geotransfer_gap.artifacts import reference, sha256, write_json

    monkeypatch.setenv("GEOTRANSFER_ARTIFACTS", str(tmp_path))
    root = tmp_path / "scene"
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
    from shutil import copytree

    folder = copytree(folder, campaign / "single/expert_idm_source_hold" / root.name / "runs/old" / root.name)
    files = {kind: {"path": name, "sha256": sha256(folder / name)}
             for kind, name in (("trace", "trace.json"), ("provenance", "verification.json"))}
    write_json(campaign / "campaign.json", {
        "batch": [{"selectors": ["--manifest", str(campaign / "manifests/source_hold.json")]}],
        "inventory": {"scenes": [
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


def test_relocated_campaign_uses_only_archive_evidence(tmp_path, saved_campaign):
    from shutil import copytree

    from geotransfer_gap.artifacts import read_json, write_json
    from geotransfer_gap.visualization.campaign_gallery import render_campaign

    campaign, folder = saved_campaign
    original = render_campaign(campaign, tmp_path / "original")
    moved = copytree(campaign, tmp_path / "relocated")
    (folder / "trace.json").unlink()
    relocated = render_campaign(moved, tmp_path / "new-gallery")
    marker = '#pair=expert%20%2F%20idm%20%2F%20source_hold'
    assert marker in original.read_text() and marker in relocated.read_text()
    matrix = moved / "verification_matrix.json"
    report = read_json(matrix)
    report["slots"][0]["single"]["directory"] = str(tmp_path / "escape" / folder.name)
    write_json(matrix, report)
    with pytest.raises(ValueError, match="outside|escapes"):
        render_campaign(moved, tmp_path / "unsafe-gallery")
