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
