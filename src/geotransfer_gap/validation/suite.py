"""Run independent regression producers in isolated processes, retaining failures."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from geotransfer_gap.config import settings
from geotransfer_gap.artifacts import write_json


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--skip-admission", action="store_true")
    args = ap.parse_args(argv)
    cfg = settings()
    destination = cfg.runs / "checks"
    destination.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        MPLCONFIGDIR=os.environ.get("MPLCONFIGDIR", "/tmp/geotransfer_mpl"),
        OMP_NUM_THREADS="2",
    )
    with TemporaryDirectory(prefix="check-artifacts-", dir=destination) as scratch:
        artifacts = Path(scratch)
        # Dereference input aliases. Hard links would let a regression rewrite
        # live evidence through a scratch path.
        subprocess.run(["cp", "-RL", "--reflink=auto", str(cfg.artifacts) + "/.",
                        str(artifacts)], check=True)
        # Keep the configured logical root. Historical evidence contains
        # absolute references, which must resolve to the same scratch mount.
        env["GEOTRANSFER_ARTIFACTS"] = str(cfg.artifacts)
        cfg.cache.mkdir(parents=True, exist_ok=True)
        env["GEOTRANSFER_CHECK_SANDBOX"] = json.dumps(_sandbox(cfg.artifacts, artifacts, cfg.cache))
        _run_checks(args, destination, env, cfg.project, artifacts)


def _sandbox(live, scratch, cache):
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise SystemExit("check all requires bubblewrap to protect live evidence")
    return [bwrap, "--die-with-parent", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
            "--proc", "/proc", "--bind", "/tmp", "/tmp", "--bind", str(cache), str(cache),
            "--bind", str(scratch), str(scratch), "--bind", str(scratch), str(live)]


def _run_checks(args, destination, env, project, artifacts):
    checks = [
        "orientation",
        "lane-changes",
        "background",
        "map",
        "route",
        "directed-rule",
        "restart",
        "following",
        "task-rule",
        "queue",
    ]
    if not args.skip_admission:
        checks += ["admission"]
    sandbox = json.loads(env.pop("GEOTRANSFER_CHECK_SANDBOX"))
    artifacts = Path(env["GEOTRANSFER_ARTIFACTS"])
    results = []
    for check in checks:
        with (destination / (check + ".log")).open("w") as log:
            proc = subprocess.run(
                [*sandbox, sys.executable, "-m", "geotransfer_gap", "check", check],
                cwd=project,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        results.append(
            dict(check=check, passed=proc.returncode == 0, returncode=proc.returncode)
        )
        print(json.dumps(results[-1]), flush=True)
    # Re-entry requires an explicit fixture; startup has its own isolated diagnostic root.
    for check, extra in [
        (
            "reentry",
            ["--root", str(artifacts / "probes/us_hybrid_1002fdc9826fc6d1")],
        ),
        (
            "startup",
            [
                "--root",
                str(artifacts / "oriented_v3/r32_e391_f21356"),
                "--output-root",
                str(artifacts / "probes/startup_regression"),
            ],
        ),
    ]:
        with (destination / (check + ".log")).open("w") as log:
            proc = subprocess.run(
                [*sandbox, sys.executable, "-m", "geotransfer_gap", "check", check, *extra],
                cwd=project,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        results.append(
            dict(check=check, passed=proc.returncode == 0, returncode=proc.returncode)
        )
        print(json.dumps(results[-1]), flush=True)
    write_json(
        destination / "summary.json",
        dict(passed=all(r["passed"] for r in results), checks=results),
    )
    if not all(r["passed"] for r in results):
        raise SystemExit(1)
