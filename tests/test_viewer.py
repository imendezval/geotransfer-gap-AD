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
