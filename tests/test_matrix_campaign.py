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
