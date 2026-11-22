import pytest

from geotransfer_gap.matrix_campaign import acceptance_status, aggregate, job_plan


@pytest.mark.parametrize("eligible,single,batch,equal,status", [
    (False, "blocked", "blocked", None, "BLOCKED"),
    (True, "passed", "passed", True, "PASS"),
    (True, "passed", "passed", False, "FAIL"),
    (True, "failed", "passed", None, "FAIL"),
    (True, "interrupted", "passed", None, "NOT_RUN"),
    (True, "not_run", "not_run", None, "NOT_RUN"),
])
def test_acceptance_needs_independent_valid_execution_and_exact_parity(eligible, single, batch, equal, status):
    assert acceptance_status(eligible, single, batch, equal) == status


def test_generation_plan_has_separate_paths_and_no_substitute_for_block(tmp_path):
    corpus = {
        "slots": [
            dict(slot_id=f"{scene}:ppo:idm:source_hold", scene=scene, ego="ppo", traffic="idm",
                 startup="source_hold", status=status)
            for scene, status in (("r1", "not_run"), ("r2", "not_run"), ("us", "blocked"))
        ],
        "scenes": [{"name": name, "root": {"root": "artifacts", "path": name},
                    "inputs": {"binary": {"sha256": name}}} for name in ("r1", "r2", "us")],
    }
    single, batch = job_plan(tmp_path, corpus)
    assert len(single) == 2 and len(batch) == 1
    assert set(single[0]["slots"] + single[1]["slots"]) == set(batch[0]["slots"])
    assert {j["path"] for j in single + batch} == {
        "single/ppo_idm_source_hold/r1", "single/ppo_idm_source_hold/r2", "batch/ppo_idm_source_hold",
    }
    assert all("--scene" in j["selectors"] for j in single)
    assert "--manifest" in batch[0]["selectors"]
    assert [r["name"] for r in batch[0]["manifest"]["scenes"]] == ["r1", "r2"]


def test_aggregates_reconcile_all_slots_in_each_dimension():
    rows = [{"scene": "fixture", "group": "us", "ego": "ppo", "traffic": "idm",
             "startup": "source_hold", "status": result} for result in ("BLOCKED", "PASS")]
    report = aggregate(rows)
    assert report["total"] == {"BLOCKED": 1, "PASS": 1, "FAIL": 0, "NOT_RUN": 0}
    for field in ("scene", "group", "ego", "traffic", "startup"):
        assert next(iter(report[field].values())) == report["total"]


@pytest.mark.parametrize("terminal", ["passed", "failed"])
@pytest.mark.parametrize("resume_single_first", [True, False])
def test_terminal_ledger_recovers_interrupted_launcher_without_rerun(
    tmp_path, monkeypatch, terminal, resume_single_first,
):
    from geotransfer_gap import matrix_campaign
    from geotransfer_gap.artifacts import read_json, write_json

    job = {"path": "single/fixture", "slots": ["slot"]}
    folder = tmp_path / job["path"]
    ledger = folder / "runs/run/run.json"
    attempt = ledger.parent / "fixture/attempt.json"
    write_json(attempt, {"status": terminal, "exit_code": 0 if terminal == "passed" else 1})
    write_json(ledger, {"results": [{"slot_id": "slot", "status": terminal,
                                    "attempts": [{"record": "fixture/attempt.json"}]}]})
    original = {path: path.read_bytes() for path in (ledger, attempt)}
    launcher = folder / "launch-0001.json"
    write_json(launcher, {"status": "running", "log": "old.log", "command": ["old command"]})
    manifest = {"single": [job], "batch": [], "freeze": {"environment": {}}}
    monkeypatch.setattr(matrix_campaign, "_assert_frozen", lambda _: manifest)
    monkeypatch.setattr(matrix_campaign.subprocess, "run", lambda *a, **kw: pytest.fail("relaunched terminal job"))

    if resume_single_first:
        matrix_campaign.execute(tmp_path, "single", 1)
    matrix_campaign.execute(tmp_path, "batch", 1)
    recovered = read_json(launcher)
    assert recovered["status"] == "reconciled" and recovered["exit_code"] is None
    assert recovered["log"] == "old.log" and recovered["command"] == ["old command"]
    assert recovered["recovery"]["ledger"] == "runs/run/run.json"
    assert {path: path.read_bytes() for path in original} == original
    assert list(folder.glob("launch-*.json")) == [launcher]


def test_partial_ledger_still_blocks_batch(tmp_path, monkeypatch):
    from geotransfer_gap import matrix_campaign
    from geotransfer_gap.artifacts import write_json

    job = {"path": "single/fixture", "slots": ["slot"]}
    folder = tmp_path / job["path"]
    write_json(folder / "runs/run/run.json", {"results": [{"slot_id": "slot", "status": "running"}]})
    write_json(folder / "launch-0001.json", {"status": "running"})
    manifest = {"single": [job], "batch": [], "freeze": {"environment": {}}}
    monkeypatch.setattr(matrix_campaign, "_assert_frozen", lambda _: manifest)
    with pytest.raises(ValueError, match="finish the independent single pass"):
        matrix_campaign.execute(tmp_path, "batch", 1)
