"""Sequential, admission-enforcing SMART diagnostics with isolated scene state."""

from geotransfer_gap.artifacts import resolve_reference
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as digest
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = PROJECT_ROOT


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    rows = json.loads(args.manifest.read_text())
    results = []
    env = dict(
        os.environ,
        MPLCONFIGDIR=os.environ.get("MPLCONFIGDIR", "/tmp/geotransfer_mpl"),
        OMP_NUM_THREADS=os.environ.get("OMP_NUM_THREADS", "2"),
    )
    for row in rows:
        root = resolve_reference(row["root"]).resolve()
        traffic = row["traffic_protocol"]
        if traffic not in ("hybrid_startup", "idm"):
            raise ValueError("Unsupported traffic protocol")
        gate = root / "testing" / f"admission_smart_{traffic}.json"
        binary = root / "testing/map_000000.bin"
        if (
            digest(gate) != row["admission_sha256"]
            or digest(binary) != row["binary_sha256"]
        ):
            raise ValueError(f"Stale manifest: {root}")
        path = root / "testing" / f"smart_all_actors_closed_loop_{traffic}.json"
        before = json.loads(path.read_text()) if path.is_file() else None
        proc = subprocess.run(
            [
                sys.executable,
                str(project_path("probe_faithful_smart_closed_loop.py")),
                "--root",
                str(root),
                "--traffic",
                traffic,
                "--require-admission",
            ],
            cwd=HERE,
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode:
            raise RuntimeError(f"{root}: {proc.stderr[-1500:]}")
        report = json.loads(path.read_text())
        bad = [
            r["step"]
            for r in report["timeline"]
            if r.get("prediction_refreshed") and (not r["identity_match"])
        ]
        if bad:
            raise ValueError(f"Prediction identity mismatch: {root}: {bad}")
        same_protocol = (
            before is not None
            and before.get("protocol_sha256") == report["protocol_sha256"]
            and (before.get("runtime") == report["runtime"])
            and (before.get("binary_sha256") == report["binary_sha256"])
        )
        parity = before["timeline"] == report["timeline"] if same_protocol else None
        if parity is False:
            raise ValueError(f"Single-scene/batch timeline mismatch: {root}")
        results.append(
            {
                "root": str(root),
                "admission_sha256": digest(gate),
                "diagnostic_sha256": digest(path),
                "steps": len(report["timeline"]),
                "identity_errors_at_refresh": bad,
                "matches_prior_single_scene_timeline": parity,
            }
        )
        output = {
            "diagnostic_only": True,
            "manifest_sha256": digest(args.manifest),
            "runner_sha256": digest(Path(__file__)),
            "isolation": "Fresh canonical runner subprocess per scene; seed0; no shared planner/history state.",
            "results": results,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2) + "\n")
        print(json.dumps(results[-1]), flush=True)


if __name__ == "__main__":
    main()
