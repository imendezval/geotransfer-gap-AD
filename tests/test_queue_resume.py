from geotransfer_gap.corpus import run_oriented_candidate_queue as queue


def test_transient_attempt_is_retried_but_verified_rejection_is_reusable(tmp_path):
    test = tmp_path / "testing"
    test.mkdir()
    evidence = test / "map_audit.json"
    evidence.write_text("initial")
    row = {"recording": 1, "ego": 2, "first_frame": 3, "actor": 4, "root": str(tmp_path),
           "screen_fingerprints": {"tool": "one"}, "source_fingerprints": {"source": "one"},
           "status": "conversion_failure"}
    failed = dict(row)
    assert not queue.reusable_result(failed, row["screen_fingerprints"], row["source_fingerprints"])
    row.update(status="source_geometry_rejection",
               artifact_fingerprints={"map_audit.json": queue.sha(evidence)})
    queue.retain_previous(row, [failed])
    assert row["attempt_history"] == [failed]
    assert queue.reusable_result(row, row["screen_fingerprints"], row["source_fingerprints"])
    assert not queue.reusable_result(row, row["screen_fingerprints"], {"source": "changed"})
    evidence.write_text("changed")
    assert not queue.reusable_result(row, row["screen_fingerprints"], row["source_fingerprints"])


def test_queue_resume_retries_failed_conversion_and_retains_attempt(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from geotransfer_gap.artifacts import read_json, write_json

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEOTRANSFER_ARTIFACTS", str(tmp_path))
    monkeypatch.setattr(queue, "source_fingerprints", lambda _: {"tracks": "fixed"})
    job = {"recording": 0, "ego": 321, "first_frame": 21017, "actor": 9,
           "role": "interaction", "location": 1}
    selection, ledger = tmp_path / "selection.json", tmp_path / "ledger.json"
    write_json(selection, {"jobs": [job]})
    monkeypatch.setattr(sys, "argv", ["queue", "--selection", str(selection), "--ledger", str(ledger),
                                     "--one-faithful-window-per-task"])
    conversions = []

    def tool(cmd, **_):
        if cmd[1:4] == ["-m", "geotransfer_gap", "convert"]:
            conversions.append(cmd)
            if len(conversions) == 1:
                return SimpleNamespace(returncode=1, stdout="", stderr="injected transient failure")
            testing = tmp_path / "oriented_v3/r00_e321_f21017/testing"
            write_json(testing / "map_audit.json", {"ego_samples_outside_lanelet_polygons": [1],
                       "occupied_start_to_occupied_goal_reachable": False})
            write_json(testing / "rule_applicability_audit.json", {})
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(queue.subprocess, "run", tool)
    queue.main()
    assert read_json(ledger)["results"][0]["status"] == "conversion_failure"
    queue.main()
    row, = read_json(ledger)["results"]
    assert row["status"] == "source_geometry_rejection"
    assert [prior["status"] for prior in row["attempt_history"]] == ["conversion_failure"]
    queue.main()
    assert len(conversions) == 2
