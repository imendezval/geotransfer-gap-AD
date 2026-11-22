"""Durable attempt ledger for existing fresh-process episode workers."""

from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import subprocess
import traceback

from geotransfer_gap.artifacts import read_json, write_json


def worker_environment():
    """Record exactly the environment passed to a matrix worker."""
    allowed = (
        "PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "PYTHONPATH",
        "LD_LIBRARY_PATH", "MPLCONFIGDIR",
        "GEOTRANSFER_CONFIG", "GEOTRANSFER_PROJECT", "GEOTRANSFER_SOURCE",
        "GEOTRANSFER_BENCH", "GEOTRANSFER_ARTIFACTS", "GEOTRANSFER_RUNS",
        "GEOTRANSFER_CACHE", "GEOTRANSFER_WEIGHTS", "GEOTRANSFER_REFERENCE_DATA",
    )
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               NUMEXPR_NUM_THREADS="1", PYTHONHASHSEED="0", CUDA_VISIBLE_DEVICES="")
    return env


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_json(path, record):
    write_json(path, record)
    with path.open("rb") as file:
        os.fsync(file.fileno())
    _sync_directory(path.parent)


def _persist(destination, ledger):
    ledger["passed"] = bool(ledger["results"]) and all(
        row["status"] == "passed" for row in ledger["results"]
    )
    durable_json(destination / "run.json", ledger)


def _complete(destination, row, attempt, status, classification, evidence=None):
    metadata = row["attempts"][-1]
    record_path = destination / metadata["record"]
    folder = record_path.parent
    artifacts = sorted(p.name for p in folder.iterdir()
                       if p.is_file() and p != record_path)
    for name in artifacts:
        with (folder / name).open("rb") as file:
            os.fsync(file.fileno())
    attempt.update(status=status, classification=classification,
                   finished_at=_timestamp(), artifacts=artifacts, evidence=evidence)
    if evidence is None:
        attempt["missing_provenance_reason"] = classification
    durable_json(record_path, attempt)
    row.update(status=status, output=str(folder))
    metadata["status"] = status


def _run_attempt(destination, ledger, row, command_for, verify, lock_fd):
    number = len(row["attempts"]) + 1
    scene_folder = destination / row["name"]
    folder = scene_folder if number == 1 else scene_folder / f"attempt-{number:04}"
    while folder.exists():
        orphan = {
            "schema_version": 1, "slot_id": row["slot_id"], "number": number,
            "status": "interrupted", "classification": "uncommitted_attempt_start",
            "missing_provenance_reason": "uncommitted_attempt_start",
            "scene_config": {key: row[key] for key in ledger["expected_fields"]},
            "exit_code": None, "signal": None, "finished_at": _timestamp(),
            "artifacts": sorted(p.name for p in folder.iterdir() if p.is_file()),
        }
        durable_json(folder / "recovery.json", orphan)
        row["attempts"].append({
            "number": number, "status": "interrupted",
            "record": str((folder / "recovery.json").relative_to(destination)),
        })
        number += 1
        folder = scene_folder / f"attempt-{number:04}"
    folder.mkdir(parents=True)
    _sync_directory(folder.parent)
    cmd = command_for(row, folder)
    record_path = folder / "attempt.json"
    attempt = {
        "schema_version": 1, "slot_id": row["slot_id"], "number": number,
        "scene_config": {key: row[key] for key in ledger["expected_fields"]},
        "status": "running", "command": cmd, "cwd": ledger["cwd"],
        "environment": ledger["environment"], "log": "execution.log",
        "started_at": _timestamp(), "exit_code": None, "signal": None,
    }
    durable_json(record_path, attempt)
    row["attempts"].append({
        "number": number, "status": "running",
        "record": str(record_path.relative_to(destination)),
    })
    row["status"] = "running"
    _persist(destination, ledger)
    status, classification, evidence = "failed", "worker_launch", None
    try:
        with (folder / "execution.log").open("w") as log:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False,
                                  env=ledger["environment"], cwd=ledger["cwd"], pass_fds=(lock_fd,))
        attempt["exit_code"] = proc.returncode if proc.returncode >= 0 else None
        attempt["signal"] = -proc.returncode if proc.returncode < 0 else None
        if proc.returncode:
            classification = "worker_signal" if proc.returncode < 0 else "worker_exit"
        else:
            classification = "invalid_evidence"
            evidence = verify(folder, row)
            status, classification = "passed", None
    except KeyboardInterrupt:
        _complete(destination, row, attempt, "interrupted", "batch_interrupt")
        _persist(destination, ledger)
        raise
    except Exception:
        attempt["exception"] = traceback.format_exc()
    _complete(destination, row, attempt, status, classification, evidence)
    _persist(destination, ledger)
    print(folder, flush=True)


def execute_batch(destination, protocol, rows, command_for, verify, *, resume=False):
    """Run pending slots in order. A retry always writes into a new attempt folder."""
    destination = Path(destination).resolve()
    names = [row["name"] for row in rows]
    if (not rows or len(set(names)) != len(names)
            or any(not name or Path(name).name != name or (name.startswith(".") or name == "run.json") for name in names)):
        raise ValueError("batch requires unique safe scene names")
    if len({row["slot_id"] for row in rows}) != len(rows):
        raise ValueError("batch slot IDs must be unique")
    expected_fields = sorted(set().union(*(row.keys() for row in rows)))
    if any(set(row) != set(expected_fields) for row in rows):
        raise ValueError("batch expectation fields must be consistent")
    environment = worker_environment()
    cwd = str(Path.cwd())
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "run.json"

    with (destination / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("batch is locked by a live process") from exc
        if resume:
            ledger = read_json(path)
            expected = [{key: row[key] for key in expected_fields} for row in ledger["results"]]
            if (ledger["schema_version"] != 4 or ledger["protocol"] != protocol
                    or expected != rows or ledger["environment"] != environment or ledger["cwd"] != cwd):
                raise ValueError("resume requires matching protocol, inputs and worker environment")
            for row in ledger["results"]:
                if row["status"] == "passed":
                    record_path = destination / row["attempts"][-1]["record"]
                    try:
                        attempt = read_json(record_path)
                        if (attempt["status"] != "passed"
                                or verify(record_path.parent, row) != attempt["evidence"]):
                            raise ValueError("validation record has changed")
                    except Exception as exc:
                        raise ValueError(f"passed evidence cannot be revalidated for {row['name']}: {exc}") from exc
                elif row["status"] == "running":
                    record_path = destination / row["attempts"][-1]["record"]
                    attempt = read_json(record_path)
                    if attempt["status"] != "running":
                        # The attempt record was written but the batch commit point was interrupted.
                        durable_json(record_path.with_name("uncommitted-result.json"), attempt)
                    _complete(destination, row, attempt, "interrupted", "abandoned_running_attempt")
        elif path.exists():
            raise ValueError("batch already exists; use resume")
        else:
            ledger = {
                "schema_version": 4, "selection": "matrix", "created_at": _timestamp(),
                "protocol": protocol, "cwd": cwd, "environment": environment,
                "expected_fields": expected_fields,
                **{key: value for key, value in protocol.items() if key != "steps"},
                "results": [
                    {**row, "status": "blocked" if row["blocked_reason"] else "not_run",
                     "attempts": []} for row in rows
                ],
            }
            _sync_directory(destination.parent)

        _persist(destination, ledger)
        for row in ledger["results"]:
            if row["status"] in {"not_run", "interrupted", "failed"}:
                _run_attempt(destination, ledger, row, command_for, verify, lock.fileno())
        return ledger
