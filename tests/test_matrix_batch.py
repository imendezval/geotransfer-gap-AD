import signal
import subprocess
import sys
import hashlib

import pytest

from geotransfer_gap.artifacts import read_json
from geotransfer_gap.runtime.matrix_batch import execute_batch


def row(name, problem=None):
    return {"slot_id": name, "name": name, "blocked_reason": problem}


def verify(folder, _):
    evidence = folder / "trace.json"
    if evidence.read_text() != "{}":
        raise ValueError("bad trace")
    return {"trace": "trace.json"}


def execute(root, rows, code, *, resume=False, verifier=verify):
    return execute_batch(root, {"steps": 12}, rows,
                         lambda _row, folder: [sys.executable, "-c", code, str(folder)],
                         verifier, resume=resume)


PASS = "import pathlib,sys; (pathlib.Path(sys.argv[1])/'trace.json').write_text('{}')"


def test_failure_kept_and_retry_does_not_overwrite_passed(tmp_path):
    rows = [row("bad"), row("good"), row("held", "missing authoritative JSON")]
    code = (
        "import json,pathlib,sys; folder=pathlib.Path(sys.argv[1]); "
        "expected=json.loads((folder.parent/'run.json').read_text()); "
        "assert [r['name'] for r in expected['results']]==['bad','good','held']; "
        "assert len(expected['results'])==3; "
        "(folder/'trace.json').write_text('{}'); "
        "exec('if folder.name == \"bad\": raise ValueError(\"intentional\")')"
    )
    record = execute(tmp_path, rows, code)
    assert not record["passed"]
    bad, good, held = record["results"]
    assert [r["status"] for r in (bad, good, held)] == ["failed", "passed", "blocked"]
    assert held["attempts"] == []
    reason = read_json(tmp_path / bad["attempts"][0]["record"])
    assert reason["exit_code"] == 1 and reason["classification"] == "worker_exit"
    assert "ValueError: intentional" in (tmp_path / "bad/execution.log").read_text()
    assert "trace.json" in reason["artifacts"]
    with pytest.raises(ValueError, match="resume"):
        execute(tmp_path, rows, PASS)
    updated = execute(tmp_path, rows, PASS, resume=True)
    assert [r["status"] for r in updated["results"]] == ["passed", "passed", "blocked"]
    assert updated["results"][1] == good
    assert len(updated["results"][0]["attempts"]) == 2
    assert read_json(tmp_path / bad["attempts"][0]["record"]) == reason
    assert (tmp_path / "bad/attempt-0002/trace.json").is_file()
    assert not updated["passed"]


def test_exit_zero_without_validated_trace_fails(tmp_path):
    record = execute(tmp_path, [row("empty")], "pass")
    result, = record["results"]
    attempt = read_json(tmp_path / result["attempts"][0]["record"])
    assert attempt["exit_code"] == 0
    assert attempt["classification"] == "invalid_evidence"
    assert result["status"] == "failed"


def test_signal_and_keyboard_interrupt_are_distinct(tmp_path):
    code = f"import os; os.kill(os.getpid(), {signal.SIGTERM})"
    record = execute(tmp_path, [row("signal")], code)
    attempt = read_json(tmp_path / record["results"][0]["attempts"][0]["record"])
    assert attempt["exit_code"] is None
    assert attempt["signal"] == signal.SIGTERM
    with pytest.raises(KeyboardInterrupt):
        execute(tmp_path / "interrupted", [row("first"), row("second")], PASS,
                verifier=lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    saved = read_json(tmp_path / "interrupted/run.json")
    assert [r["status"] for r in saved["results"]] == ["interrupted", "not_run"]
    continued = execute(tmp_path / "interrupted", [row("first"), row("second")], PASS,
                        resume=True)
    assert continued["passed"]


def test_hard_kill_leaves_running_then_resumes_as_interrupted(tmp_path):
    child = """
import os, pathlib, signal, sys, time
pathlib.Path(sys.argv[1], 'trace.json').write_text('{}')
os.kill(os.getppid(), signal.SIGKILL)
time.sleep(.2)
"""
    parent = """
import sys
from pathlib import Path
from geotransfer_gap.runtime.matrix_batch import execute_batch
execute_batch(Path(sys.argv[1]), {"steps": 12},
              [{"slot_id": "killed", "name": "killed", "blocked_reason": None}],
              lambda _, out: [sys.executable, "-c", sys.argv[2], str(out)], lambda *_: {})
"""
    original = subprocess.run([sys.executable, "-c", parent, str(tmp_path), child],
                              check=False, timeout=10)
    assert original.returncode == -signal.SIGKILL
    saved = read_json(tmp_path / "run.json")
    assert saved["results"][0]["status"] == "running"
    # Wait for the orphaned stdout holder and inherited batch lock to close.
    with (tmp_path / ".lock").open("r") as lock:
        import fcntl

        fcntl.flock(lock, fcntl.LOCK_EX)
    continued = execute(tmp_path, [row("killed")], PASS, resume=True)
    assert [a["status"] for a in continued["results"][0]["attempts"]] == ["interrupted", "passed"]


def test_resume_checks_existing_passed_evidence_without_rerunning(tmp_path):
    execute(tmp_path, [row("done")], PASS)
    (tmp_path / "done/trace.json").write_text("tampered")
    with pytest.raises((ValueError, OSError), match="passed evidence"):
        execute(tmp_path, [row("done")], PASS, resume=True)
    assert not (tmp_path / "done/attempt-0002").exists()


def test_requested_capture_failure_is_retained_and_passed_capture_is_resume_bound(tmp_path):
    requested = {**row("captured"), "capture_evaluation": True}

    def verify_capture(folder, expectation):
        names = ["trace.json"]
        if expectation["capture_evaluation"]:
            names.append("evaluation_capture.json")
        files = {}
        for name in names:
            path = folder / name
            if not path.is_file():
                raise ValueError(f"missing required evidence: {name}")
            files[name.removesuffix(".json")] = {
                "path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        return {"integration_validity": "validated_fixture", "files": files}

    missing_capture = (
        "import pathlib,sys; pathlib.Path(sys.argv[1], 'trace.json').write_text('{}')"
    )
    result = execute(tmp_path, [requested], missing_capture, verifier=verify_capture)
    failed = result["results"][0]
    attempt = read_json(tmp_path / failed["attempts"][0]["record"])
    assert failed["status"] == "failed"
    assert attempt["classification"] == "invalid_evidence"
    assert "trace.json" in attempt["artifacts"]
    assert (tmp_path / "captured/execution.log").is_file()

    with_capture = (
        "import pathlib,sys; out=pathlib.Path(sys.argv[1]); "
        "(out/'trace.json').write_text('{}'); (out/'evaluation_capture.json').write_text('{\"trace_sha256\":\"bound\"}')"
    )
    resumed = execute(tmp_path, [requested], with_capture, resume=True, verifier=verify_capture)
    row_result = resumed["results"][0]
    assert row_result["status"] == "passed"
    attempt = read_json(tmp_path / row_result["attempts"][-1]["record"])
    assert "evaluation_capture" in attempt["evidence"]["files"]

    (tmp_path / "captured/attempt-0002/evaluation_capture.json").write_text("tampered")
    with pytest.raises(ValueError, match="passed evidence"):
        execute(tmp_path, [requested], with_capture, resume=True, verifier=verify_capture)
