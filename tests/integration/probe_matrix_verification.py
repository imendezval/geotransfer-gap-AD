"""Run representative fresh CLI single/batch comparisons and durable failure recovery."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from geotransfer_gap.artifacts import read_json, resolve_reference, sha256, write_json
from geotransfer_gap.config import settings
from geotransfer_gap.runtime.matrix_batch import execute_batch
from geotransfer_gap.runtime.run_trace import compare, load_bundle, validate_run
from geotransfer_gap.verification_matrix import build_matrix, slot_id


def capture(destination, label, argv, env, *, returncode=0):
    command = [sys.executable, "-m", "geotransfer_gap", "run", *argv]
    log, errors = destination / f"{label}.stdout", destination / f"{label}.stderr"
    with log.open("w") as out, errors.open("w") as err:
        proc = subprocess.run(command, env=env, stdout=out, stderr=err, check=False)
    info = {"command": command, "exit_code": proc.returncode, "stdout": str(log), "stderr": str(errors)}
    write_json(destination / f"{label}.command.json", info)
    if proc.returncode != returncode:
        raise RuntimeError(f"unexpected subprocess exit. Evidence in {log} and {errors}")
    folders = [Path(line) for line in log.read_text().splitlines()]
    return folders, info


def run_manifest(destination, matrix, scenes):
    path = destination / ("scenes_" + "_".join(row["name"] for row in scenes) + ".json")
    write_json(path, {"schema_version": 2, "matrix_manifest": matrix,
                      "scenes": [{"name": row["name"], "root": row["root"],
                                  "binary_sha256": row["inputs"]["binary"]["sha256"]}
                                 for row in scenes]})
    return path


def compare_group(destination, matrix, scenes, config, steps, env, *, matched):
    ego, traffic, startup = config
    options = ["--ego", ego, "--traffic", traffic, "--traffic-startup", startup, "--steps", str(steps)]
    ident = f"{ego}_{traffic}_{startup}_{scenes[0]['group']}_{steps}"
    manifest = run_manifest(destination, matrix["manifest"], scenes)
    batches, batch_command = capture(destination, f"{ident}_batch", ["--manifest", str(manifest), *options], env)
    assert len(batches) == len(scenes)
    batch = read_json(batches[0].parent / "run.json")
    assert batch["passed"] and all(row["status"] == "passed" for row in batch["results"])
    for scene, batched in zip(scenes, batches, strict=True):
        name = scene["name"]
        root = resolve_reference(scene["root"])
        (individual,), single_command = capture(destination, f"{ident}_{name}_single",
                                               ["--scene", str(root), *options], env)
        a, b = load_bundle(individual), load_bundle(batched)
        mismatch = compare(a, b)
        slot = slot_id(name, *config)
        outcome = a["trace"]
        single_result, = read_json(individual.parent / "run.json")["results"]
        batch_result, = [r for r in batch["results"] if r["slot_id"] == slot]
        raw = {}
        for label, folder, result in (("single", individual, single_result), ("batch", batched, batch_result)):
            attempt_path = folder / "attempt.json"
            attempt = read_json(attempt_path)
            assert (result["status"] == attempt["status"] == "passed" and attempt["exit_code"] == 0
                    and attempt["slot_id"] == slot)
            raw[label] = {"attempt": str(attempt_path), "files": attempt["evidence"]["files"]}
        result = {
            "slot_id": slot, "equal": mismatch is None, "first_mismatch": mismatch,
            "terminal_reason": outcome["terminal_reason"], "observation_frames": outcome["observation_frames"],
            "transitions": outcome["transitions"], "ego_binary_index": outcome["ego_binary_index"],
            "requested_frames": steps, "attempts": raw,
            "commands": {"single": single_command, "batch": batch_command},
        }
        write_json(destination / f"{ident}_{name}_parity.json", result)
        matched.append(result)
        assert mismatch is None, result


def intentional_worker_failure(destination, scene):
    root = resolve_reference(scene["root"])
    config = {
        "ego_controller": "expert", "traffic_controller": "expert", "traffic_startup": "immediate",
        "steps": 12, "diagnostic_only": True, "diagnostic_requested": False,
        "research_admission_status": "not_established",
    }
    row = {"name": scene["name"], "slot_id": slot_id(scene["name"], "expert", "expert", "immediate"),
           "scene": scene["root"], "inputs": {"binary": scene["inputs"]["binary"]},
           "blocked_reason": None, **config}

    def command(folder, path):
        return [sys.executable, "-m", "geotransfer_gap.runtime.episode_worker",
                "--root", str(path), "--ego", "expert", "--traffic", "expert",
                "--steps", "12", "--output", str(folder / "trace.json")]

    failed = execute_batch(destination, config, [row],
                           lambda _, folder: command(folder, destination / "nonexistent"), validate_run)
    first, = failed["results"][0]["attempts"]
    original = destination / first["record"]
    original_sha = sha256(original)
    assert first["status"] == "failed" and not failed["passed"]
    assert "FileNotFoundError" in (original.parent / "execution.log").read_text()
    resumed = execute_batch(destination, config, [row], lambda _, folder: command(folder, root),
                            validate_run, resume=True)
    assert resumed["passed"] and sha256(original) == original_sha
    assert [attempt["status"] for attempt in resumed["results"][0]["attempts"]] == ["failed", "passed"]
    return str(destination / "run.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.resolve()
    out.mkdir(parents=True)
    env = dict(os.environ, GEOTRANSFER_RUNS=str(out / "episodes"))
    matrix = build_matrix()
    german = ["r07_e200_f25439", "r12_e151_f12041"]
    scenes = {row["name"]: row for row in matrix["scenes"]}
    pair = [scenes[name] for name in german]
    us = [row for row in scenes.values() if row["group"] == "us"]
    results = []
    for config, steps in [
        (("ppo", "smart", "immediate"), 91), (("smart", "smart", "immediate"), 24),
        (("expert", "idm", "source_hold"), 24), (("ppo", "smart", "source_hold"), 24),
    ]:
        compare_group(out, matrix, pair, config, steps, env, matched=results)
    compare_group(out, matrix, us, ("expert", "smart", "immediate"), 20, env, matched=results)

    blocked = [row for row in us if row["source_hold_problem"]]
    if not blocked:
        raise RuntimeError("the pinned representative blocked check needs a reference missing an authoritative source")
    refs = run_manifest(out, matrix["manifest"], blocked)
    before = set((out / "episodes").iterdir())
    folders, blocked_command = capture(out, "blocked", ["--manifest", str(refs), "--ego", "expert",
                                        "--traffic", "idm", "--traffic-startup", "source_hold"], env, returncode=1)
    assert not folders
    blocked_run, = set((out / "episodes").iterdir()) - before
    ledger = read_json(blocked_run / "run.json")
    assert not ledger["passed"] and len(ledger["results"]) == len(blocked)
    assert all(r["status"] == "blocked" and not r["attempts"] and r["blocked_reason"] for r in ledger["results"])

    failed_run = intentional_worker_failure(out / "failure_then_retry", pair[0])
    assert any(r["terminal_reason"] != "horizon" for r in results)
    assert any(r["ego_binary_index"] > 0 for r in results)
    report = {"schema_version": 1, "comparisons": results, "blocked": str(blocked_run / "run.json"),
              "blocked_command": blocked_command, "failed_and_retried": failed_run}
    write_json(out / "representative_verification.json", report)
    print(json.dumps({"exact_comparisons": len(results), "blocked": len(blocked),
                      "report": str(out / "representative_verification.json")}))


if __name__ == "__main__":
    main()
