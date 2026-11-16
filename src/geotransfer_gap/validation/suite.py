"""Run independent regression producers in isolated processes, retaining failures."""

import json
import os
from pathlib import Path
import subprocess
import sys
from geotransfer_gap.config import settings
from geotransfer_gap.artifacts import write_json


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--skip-admission", action="store_true")
    args = ap.parse_args(argv)
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
    destination = settings().runs / "checks"
    destination.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        MPLCONFIGDIR=os.environ.get("MPLCONFIGDIR", "/tmp/geotransfer_mpl"),
        OMP_NUM_THREADS="2",
    )
    results = []
    for check in checks:
        with (destination / (check + ".log")).open("w") as log:
            proc = subprocess.run(
                [sys.executable, "-m", "geotransfer_gap", "check", check],
                cwd=settings().project,
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
            ["--root", str(settings().artifacts / "probes/us_hybrid_1002fdc9826fc6d1")],
        ),
        (
            "startup",
            [
                "--root",
                str(settings().artifacts / "oriented_v3/r32_e391_f21356"),
                "--output-root",
                str(settings().artifacts / "probes/startup_regression"),
            ],
        ),
    ]:
        with (destination / (check + ".log")).open("w") as log:
            proc = subprocess.run(
                [sys.executable, "-m", "geotransfer_gap", "check", check, *extra],
                cwd=settings().project,
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
