"""Freeze, launch and report an acceptance campaign using the existing matrix CLI."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
from hashlib import sha256 as hash_bytes
from importlib.metadata import distribution
import math
from pathlib import Path
import subprocess
import sys

from .artifacts import read_json, resolve_reference, sha256
from .config import settings
from .planners.protocol import input_paths
from .runtime import late_spawn_runtime
from .runtime.matrix_batch import durable_json, worker_environment
from .runtime.matrix_inputs import fingerprint
from .runtime.run_trace import (
    BB_COMMIT, EVAL_INI_SHA256, PPO_SHA256, RUNTIME_DIGEST, SMART_CODEBOOK_SHA256, SMART_SHA256,
    VERIFICATION_SCHEMA_VERSION, code_fingerprints, compare, load_bundle, validate_run,
)
from .verification_matrix import build_matrix

STATES = ("PASS", "FAIL", "BLOCKED", "NOT_RUN")
TERMINAL = {"passed", "failed", "blocked"}


def acceptance_status(eligible, single, batch, equal):
    if not eligible:
        return "BLOCKED"
    if "failed" in (single, batch) or equal is False:
        return "FAIL"
    if single == batch == "passed" and equal is True:
        return "PASS"
    return "NOT_RUN"


def aggregate(rows):
    def counts(values):
        counter = Counter(values)
        return {state: counter[state] for state in STATES}

    totals = {"total": counts(row["status"] for row in rows)}
    for key in ("scene", "group", "ego", "traffic", "startup"):
        groups = defaultdict(list)
        for row in rows:
            groups[row[key]].append(row["status"])
        totals[key] = {name: counts(group) for name, group in sorted(groups.items())}
    return totals


def job_plan(root, inventory):
    scenes = {scene["name"]: scene for scene in inventory["scenes"]}
    singles, groups = [], {}
    for slot in inventory["slots"]:
        if slot["status"] == "blocked":
            continue
        scene = scenes[slot["scene"]]
        config = "_".join(slot[key] for key in ("ego", "traffic", "startup"))
        options = ["--ego", slot["ego"], "--traffic", slot["traffic"],
                   "--traffic-startup", slot["startup"], "--steps", "91"]
        singles.append({
            "path": f"single/{config}/{scene['name']}", "slots": [slot["slot_id"]],
            "selectors": ["--scene", str(resolve_reference(scene["root"])), *options],
        })
        group = groups.setdefault(config, {
            "path": f"batch/{config}", "slots": [], "manifest": {"schema_version": 2, "scenes": []},
            "selectors": ["--manifest", str(root / "manifests" / f"{config}.json"), *options],
        })
        group["slots"].append(slot["slot_id"])
        group["manifest"]["scenes"].append({
            "name": scene["name"], "root": scene["root"],
            "binary_sha256": scene["inputs"]["binary"]["sha256"],
        })
    return singles, list(groups.values())


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def fingerprint_environment():
    cfg = settings()
    if _git(cfg.project, "diff", "HEAD", "--name-only", "--", "src", "tests", "configs", "pyproject.toml"):
        raise ValueError("tracked campaign source, tests or configuration have changes")
    if _git(cfg.project, "ls-files", "--others", "--exclude-standard", "--", "src", "tests", "configs"):
        raise ValueError("untracked files in campaign source, tests or configuration")
    bench = _git(cfg.bench, "rev-parse", "HEAD")
    if bench != BB_COMMIT or _git(cfg.bench, "status", "--porcelain"):
        raise ValueError("BehaviorBench is not clean at the pinned revision")
    models = {"ppo": fingerprint(cfg.bench / "weights/simple_ppo.pt"),
              "smart": fingerprint(cfg.weights)}
    smart = {key: fingerprint(path) for key, path in input_paths().items()}
    ini = smart["evaluation_ini"]
    if (models["ppo"]["sha256"] != PPO_SHA256 or models["smart"]["sha256"] != SMART_SHA256
            or ini["sha256"] != EVAL_INI_SHA256
            or any(smart[key]["sha256"] != digest for key, digest in SMART_CODEBOOK_SHA256.items())):
        raise ValueError("checkpoint, codebook or INI does not match the pinned input")
    runtime = late_spawn_runtime.load()
    if runtime["runtime_source_sha256"] != RUNTIME_DIGEST:
        raise ValueError("unexpected corrected native runtime digest")
    packages = {}
    for name, filenames in {
        "numpy": ("_multiarray_umath",),
        "torch": ("_C.cpython", "libtorch_cpu.so", "libtorch_python.so"),
    }.items():
        package = distribution(name)
        record = package.read_text("RECORD")
        if record is None:
            raise ValueError(f"{name} distribution has no RECORD")
        critical = {
            str(file): sha256(package.locate_file(file))
            for file in package.files if str(file).endswith(".so")
            and file.name.startswith(filenames) and str(file).startswith(name + "/")
        }
        if len(critical) != len(filenames):
            raise ValueError(f"{name} distribution lacks expected native library fingerprints")
        packages[name] = {"version": package.version,
                          "record_sha256": hash_bytes(record.encode()).hexdigest(), "libraries": critical}
    return {
        "commit": _git(cfg.project, "rev-parse", "HEAD"),
        "tree": _git(cfg.project, "rev-parse", "HEAD^{tree}"),
        "code_sha256": code_fingerprints(),
        "behaviorbench_commit": bench, "verification_schema": VERIFICATION_SCHEMA_VERSION,
        "models": models, "smart_inputs": smart, "evaluation_ini": ini,
        "runtime": {**runtime, "binary_sha256": sha256(runtime["runtime_binary"])},
        "packages": packages, "python": sys.version, "python_executable": sys.executable,
        "environment": worker_environment(), "cwd": str(Path.cwd()),
        "seeds": {"native_reset": 0, "numpy": 0, "torch": 0},
        "protocol": {"device": "cpu", "ppo": "argmax", "smart": "greedy",
                     "warmup_observations": 10, "requested_observations": 91},
    }


def freeze(root, gates):
    snapshot = fingerprint_environment()
    gate = read_json(gates)
    if (gate.get("revision") != snapshot["commit"]
            or set(gate.get("gates", {})) != {"V", "F"}
            or any(value["status"] != "PASS" for value in gate["gates"].values())):
        raise ValueError("viewer and pre-campaign gates must pass at this revision")
    inventory = build_matrix()
    if len(inventory["slots"]) != 504:
        raise ValueError("campaign inventory does not have 504 slots")
    root.mkdir(parents=True, exist_ok=False)
    singles, batches = job_plan(root, inventory)
    for job in batches:
        path = Path(job["selectors"][1])
        durable_json(path, job.pop("manifest"))
        job["manifest_sha256"] = sha256(path)
    snapshot["preflight"] = {"path": str(gates), "sha256": sha256(gates), **gate["gates"]}
    durable_json(root / "campaign.json", {"manifest_version": 1, "freeze": snapshot,
                                         "inventory": inventory, "single": singles, "batch": batches})


def _assert_frozen(root):
    manifest = read_json(root / "campaign.json")
    recorded = {k: v for k, v in manifest["freeze"].items() if k != "preflight"}
    if fingerprint_environment() != recorded:
        raise ValueError("campaign revision or runtime environment no longer matches the freeze")
    if build_matrix() != manifest["inventory"]:
        raise ValueError("current input inventory no longer matches the campaign freeze")
    for job in manifest["batch"]:
        if sha256(job["selectors"][1]) != job["manifest_sha256"]:
            raise ValueError(f"frozen batch manifest changed: {job['path']}")
    return manifest


def _ledger(folder):
    paths = sorted((folder / "runs").glob("*/run.json"))
    if len(paths) > 1:
        raise ValueError(f"multiple ledgers for one campaign job: {folder}")
    return paths[0] if paths else None


def _run_job(root, job, env):
    folder = root / job["path"]
    folder.mkdir(parents=True, exist_ok=True)
    ledger = _ledger(folder)
    launcher_records = sorted(folder.glob("launch-*.json"))
    if ledger:
        statuses = {r["status"] for r in read_json(ledger)["results"]}
        if statuses <= TERMINAL:
            return
    elif launcher_records and read_json(launcher_records[-1])["status"] == "finished":
        return  # retain a process failure before matrix ledger creation

    index = len(launcher_records) + 1
    stem = f"launch-{index:04}"
    command = [sys.executable, "-m", "geotransfer_gap", "run", *job["selectors"]]
    if ledger:
        command.extend(("--resume", str(ledger.parent)))
    child_env = dict(env, GEOTRANSFER_RUNS=str(folder / "runs"))
    record = {"status": "running", "command": command, "environment": child_env, "log": stem + ".log"}
    durable_json(folder / (stem + ".json"), record)
    with (folder / record["log"]).open("w") as log:
        result = subprocess.run(command, env=child_env, stdout=log, stderr=subprocess.STDOUT, check=False)
    durable_json(folder / (stem + ".json"), dict(record, status="finished", exit_code=result.returncode))


def execute(root, phase, jobs):
    with (root / ".campaign.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = _assert_frozen(root)
        if phase == "batch":
            for job in manifest["single"]:
                folder = root / job["path"]
                launches = sorted(folder.glob("launch-*.json"))
                ledger = _ledger(folder)
                if (not launches or read_json(launches[-1])["status"] != "finished"
                        or (ledger and any(r["status"] not in TERMINAL for r in read_json(ledger)["results"]))):
                    raise ValueError("finish the independent single pass before launching the batch repeat")
        env = manifest["freeze"]["environment"]
        pending = manifest[phase]
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(_run_job, root, job, env) for job in pending]
            for i, task in enumerate(as_completed(futures), 1):
                task.result()
                if i == len(pending) or i % 16 == 0:
                    print(f"{phase}: {i}/{len(pending)} CLI jobs complete", flush=True)


def _job_results(root, inventory, jobs):
    scenes = {s["name"]: s for s in inventory["scenes"]}
    slots = {s["slot_id"]: s for s in inventory["slots"]}
    results = {}
    for job in jobs:
        folder = root / job["path"]
        launcher_paths = sorted(folder.glob("launch-*.json"))
        ledger_path = _ledger(folder)
        rows = {}
        if ledger_path is not None:
            rows = {r["slot_id"]: r for r in read_json(ledger_path)["results"]}
            if set(rows) != set(job["slots"]):
                raise ValueError(f"ledger slots differ from frozen job: {ledger_path}")
        for slot in job["slots"]:
            record = {"status": "not_run", "launches": [str(p) for p in launcher_paths], "attempts": []}
            results[slot] = record
            if slot not in rows:
                if launcher_paths:
                    launcher = read_json(launcher_paths[-1])
                    if launcher["status"] == "finished":
                        record.update(status="failed", failure="CLI exited without expected ledger")
                    else:
                        record["status"] = "interrupted"
                continue

            row = rows[slot]
            record.update(status=row["status"], ledger=str(ledger_path))
            for item in row["attempts"]:
                path = ledger_path.parent / item["record"]
                attempt = read_json(path)
                record["attempts"].append({"record": str(path), "status": item["status"],
                                           "class": attempt.get("classification"),
                                           "log": str(path.parent / attempt["log"]) if attempt.get("log") else None})
                if item["status"] == "failed":
                    record.update(status="failed", failure=attempt.get("classification"))
            if record["status"] == "passed":
                try:
                    expected = slots[slot]
                    scene = scenes[expected["scene"]]
                    inputs = dict(scene["inputs"])
                    if expected["startup"] == "immediate":
                        inputs.pop("source_hold", None)
                    if (row["scene"] != scene["root"] or row["inputs"] != inputs or row["steps"] != 91
                            or (row["ego_controller"], row["traffic_controller"], row["traffic_startup"])
                               != (expected["ego"], expected["traffic"], expected["startup"])):
                        raise ValueError("attempt scene, inputs or protocol differs from the campaign freeze")
                    latest = Path(record["attempts"][-1]["record"])
                    data = read_json(latest)
                    if data["status"] != "passed" or data["exit_code"] != 0 or data["slot_id"] != slot:
                        raise ValueError("inconsistent passed attempt")
                    validated = validate_run(latest.parent, row)
                    if validated != data["evidence"]:
                        raise ValueError("attempt evidence no longer matches artifacts")
                    record.update(directory=str(latest.parent), files=validated["files"])
                except (ValueError, KeyError, OSError, IndexError, TypeError) as exc:
                    record.update(status="failed", failure=str(exc))
            elif record["status"] == "running":
                record["status"] = "interrupted"
            elif record["status"] == "blocked":
                record.update(status="failed", failure=f"eligible input was blocked: {row['blocked_reason']}")
    return results


def _driving_outcome(trace):
    ego = trace["ego_binary_index"]
    states = [next(a for a in frame["state"]["actors"] if a["binary_index"] == ego)
              for frame in trace["frames"]]
    present = [a for a in states if a["present"]]
    displacement = None
    if present:
        a, b = present[0], present[-1]
        displacement = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
    return {
        "terminal_reason": trace["terminal_reason"], "steps": trace["observation_frames"],
        "transitions": trace["transitions"],
        "early": trace["observation_frames"] < trace["requested_observation_frames"],
        "collision_observed": any(a["collision_state"] == 1 for a in states),
        "offroad_observed": any(a["collision_state"] == 2 for a in states),
        "removed": any(a["removed"] for a in states), "reached_goal": any(a["reached_goal"] for a in states),
        "ego_displacement_m": displacement,
    }


def _report_rows(root, inventory, single, batch):
    scenes = {s["name"]: s for s in inventory["scenes"]}
    for slot in inventory["slots"]:
        eligible = slot["status"] != "blocked"
        sid = slot["slot_id"]
        a, b = (single[sid], batch[sid]) if eligible else (
            {"status": "blocked", "attempts": []}, {"status": "blocked", "attempts": []})
        bundles = [load_bundle(Path(attempt["directory"])) if attempt["status"] == "passed" else None
                   for attempt in (a, b)]
        parity = mismatch = None
        if all(bundles):
            diff = compare(*bundles)
            parity = diff is None
            if not parity:
                mismatch = "mismatches/" + sid.replace(":", "__") + ".json"
                durable_json(root / mismatch, diff)
        status = acceptance_status(eligible, a["status"], b["status"], parity)
        original = scenes[slot["scene"]].get("original_source_admission")
        yield {
            **slot, "eligible": eligible, "status": status, "single": a, "batch": b,
            "exact_parity": parity, "mismatch": mismatch,
            "integration_validity": {"PASS": "validated_exact", "FAIL": "failed",
                                     "BLOCKED": "blocked", "NOT_RUN": "incomplete"}[status],
            "original_source_admission": {"status": "recorded", "protocol": "SMART/hybrid_startup",
                                          "evidence": original} if original else {"status": "not_recorded"},
            "diagnostic_only": True, "controller_pair_research_admission": "not_established",
            "task_preservation": "not_assessed", "campaign_manifest": "campaign.json",
            "verification_schema": VERIFICATION_SCHEMA_VERSION,
            "driving_outcomes": {
                view: _driving_outcome(bundle["trace"]) if bundle else None
                for view, bundle in zip(("single", "batch"), bundles, strict=True)
            },
        }


def report(root):
    manifest = _assert_frozen(root)
    single, batch = (_job_results(root, manifest["inventory"], manifest[key]) for key in ("single", "batch"))
    rows = list(_report_rows(root, manifest["inventory"], single, batch))
    counts = aggregate(rows)
    totals = counts["total"]
    assert sum(totals.values()) == len(rows) == 504
    failures = [{"slot_id": row["slot_id"], "single": row["single"], "batch": row["batch"],
                 "mismatch": row["mismatch"]} for row in rows if row["status"] == "FAIL"]
    gates = {
        **manifest["freeze"]["preflight"],
        "E": {"status": "PASS" if all(
            row[view]["status"] in TERMINAL for row in rows for view in ("single", "batch")
        ) else "BLOCKED", "evidence": "verification_matrix.json"},
        "D": {"status": "FAIL" if totals["FAIL"] else "BLOCKED" if totals["NOT_RUN"] else "PASS",
              "evidence": "verification_matrix.json"},
    }
    durable_json(root / "verification_matrix.json", {"schema_version": 1, "campaign": "campaign.json",
                 "slots": rows, "aggregate": counts, "failures": failures, "gates": gates})
    _summary(root, manifest, rows, totals, gates)


def _summary(root, manifest, rows, totals, gates):
    lines = ["# Controller matrix acceptance", "",
             f"Frozen revision `{manifest['freeze']['commit']}`.",
             "Expected slots: 504. " + ", ".join(f"{status} {count}" for status, count in totals.items()) + ".", "",
             "## Gates", "", "| Gate | Status | Evidence |", "| --- | --- | --- |"]
    for name, gate in gates.items():
        evidence = gate["evidence"]
        lines.append(f"| {name} | {gate['status']} | [{Path(evidence).name}]({evidence}) |")
    lines += ["", "## Integration validity", "",
              "PASS requires two independently verified attempts with exact canonical equality. "
              "A failed attempt, crash or divergence is retained. Missing source inputs are BLOCKED. "
              "See [verification matrix](verification_matrix.json) for the per-scene, controller, startup and group totals.",
              "", "## Original source admission", "",
              "Recorded German SMART/hybrid admission applies to the original protocol. "
              "Controller-pair research admission remains `not_established`. All campaign runs are diagnostic.",
              "", "## Encounter preservation", "",
              "Encounter preservation remains `not_assessed`. No ego-outcome-independent encounter gate was evaluated.",
              "", "## Driving outcomes", ""]
    outcomes = [row["driving_outcomes"]["single"] for row in rows if row["driving_outcomes"]["single"]]
    lines += [f"{len(outcomes)} validated single episodes supplied driving outcomes.",
              "", "| Observed outcome | Episodes |", "| --- | --- |"]
    for label, count in sorted(Counter(outcome["terminal_reason"] for outcome in outcomes).items()):
        lines.append(f"| Terminal {label} | {count} |")
    for field in ("early", "collision_observed", "offroad_observed", "removed", "reached_goal"):
        lines.append(f"| {field.replace('_', ' ')} | {sum(outcome[field] for outcome in outcomes)} |")
    lines += ["", "Collisions and goal misses can be valid simulation outcomes. Observed ego displacement is "
              "available per attempt. Wrong-way or task-specific progress was not classified.",
              "", "## Information access", "",
              "- SMART uses the static map and causal observed joint histories.",
              "- PPO uses native actor-centric observations and simulator navigation goals, including source-derived destinations.",
              "- IDM background routing can use the recorded source-informed route prior.",
              "- Source-hold release times use recorded future motion separately from learned-model inputs.",
              "", "These results establish execution reproducibility for passing slots. "
              "They do not establish human-likeness, geographic generalization or encounter suitability.", ""]
    if totals["FAIL"]:
        lines += ["## First failures", ""]
        for row in [r for r in rows if r["status"] == "FAIL"][:12]:
            sides = [row[phase] for phase in ("single", "batch")]
            paths = [item["record"] for side in sides for item in side["attempts"] if item["status"] == "failed"]
            paths = paths or ([row["mismatch"]] if row["mismatch"] else [p for side in sides for p in side["launches"]])
            links = " ".join(f"[{Path(path).name}]({path})" for path in paths)
            lines.append(f"- `{row['slot_id']}` {links}")
    (root / "summary.md").write_text("\n".join(lines) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "single", "batch", "report"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gates", type=Path)
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args(argv)
    root = args.output.resolve()
    if args.action == "freeze":
        if not args.gates:
            parser.error("freeze requires --gates")
        freeze(root, args.gates.resolve())
    elif args.action == "report":
        report(root)
    else:
        if args.jobs < 1:
            parser.error("--jobs must be positive")
        execute(root, args.action, args.jobs)


if __name__ == "__main__":
    main()
