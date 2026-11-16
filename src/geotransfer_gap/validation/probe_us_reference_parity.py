"""Reproduce or validate both US interface references and publish their aggregate.

Mechanical diagnostics only: no matched cohort or US research admission claim.
"""

from geotransfer_gap.planners.protocol import input_paths, execution_hashes
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = PROJECT_ROOT
BENCH = settings().bench
sys.path.insert(0, str(BENCH))


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument(
        "--roots",
        type=Path,
        nargs="+",
        default=[
            project_path("pilot/probes/us_hybrid_1002fdc9826fc6d1"),
            project_path("pilot/probes/us_smart_negative_world_739e0513c6f7cfe8"),
        ],
    )
    ap.add_argument(
        "--reuse-current",
        action="store_true",
        help="Validate current producer/runtime/model hashes before aggregating existing diagnostics.",
    )
    args = ap.parse_args()
    from geotransfer_gap.runtime import late_spawn_runtime
    from geotransfer_gap.runtime import hybrid_traffic
    from geotransfer_gap.planners import faithful_map

    runtime = late_spawn_runtime.load()
    roots = [r.resolve() for r in args.roots]
    logs = project_path("pilot/probes/us_reference_checks")
    logs.mkdir(parents=True, exist_ok=True)
    protocol = execution_hashes()
    inputs = input_paths()
    expected = {k: sha(v) for k, v in inputs.items()}
    results = []
    for root in roots:
        if not args.reuse_current:
            for tool, extra in [
                (
                    "probe_smart_map_transfer.py",
                    [
                        "--us-binary",
                        str(roots[0] / "testing/map_000000.bin"),
                        "--all-actors",
                        "--inference",
                        "--steps",
                        "81",
                    ],
                ),
                ("probe_faithful_smart_closed_loop.py", ["--steps", "50"]),
            ]:
                with (logs / (root.name + "_" + tool + ".log")).open("w") as stream:
                    p = subprocess.run(
                        [
                            sys.executable,
                            str(project_path(tool)),
                            "--root",
                            str(root),
                            *extra,
                        ],
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                    )
                if p.returncode:
                    raise RuntimeError(
                        "US reference producer failed: " + root.name + "/" + tool
                    )
        t = root / "testing"
        input_path = t / "smart_map_transfer_all_actors_probe.json"
        probe = json.loads(input_path.read_text())
        features = probe["source_feature_audit"]
        assert probe["runtime_source_sha256"] == runtime["runtime_source_sha256"]
        assert probe["protocol_file_sha256"] == expected
        assert probe["checkpoint_sha256"] == sha(settings().weights)
        assert probe["maps"]["german"]["binary_sha256"] == sha(t / "map_000000.bin")
        assert probe["map_encoding_protocol"] == faithful_map.PROTOCOL_VERSION
        assert probe["inference_finite"] and probe["future_mutation_invariant_at_reset"]
        assert features["presence_mismatches"] == features["class_mismatches"] == 0
        assert all(
            (
                features[k] < 0.01
                for k in (
                    "max_position_error_m",
                    "max_local_position_error_m",
                    "max_heading_error_rad",
                    "max_dimension_error_m",
                    "max_evaluator_velocity_error_mps",
                )
            )
        )
        assert (
            probe["map_frame_position_error_m"] < 0.01
            and probe["perturbed_ego_input_error_m"] < 0.01
        )
        path = t / "smart_all_actors_closed_loop_hybrid_startup.json"
        report = json.loads(path.read_text())
        assert (
            report["runtime"]["runtime_source_sha256"]
            == runtime["runtime_source_sha256"]
        )
        assert report["protocol_sha256"] == protocol and report["binary_sha256"] == sha(
            t / "map_000000.bin"
        )
        bad = [
            r["step"]
            for r in report["timeline"]
            if r.get("prediction_refreshed") and (not r["identity_match"])
        ]
        assert not bad and any(
            (r.get("prediction_refreshed") for r in report["timeline"])
        )
        results.append(
            {
                "root": str(root),
                "report_sha256": sha(path),
                "input_probe_sha256": sha(input_path),
                "identity_errors": bad,
                "runtime": report["runtime"],
                "steps": len(report["timeline"]),
            }
        )
    output = {
        "producer_sha256": sha(Path(__file__)),
        "traffic_version": hybrid_traffic.PROTOCOL_VERSION,
        "map_encoding_protocol": faithful_map.PROTOCOL_VERSION,
        "diagnostic_only": True,
        "results": results,
        "passed": True,
        "scope": "Same source-state/map/traffic/canonical execution checks on two US references; not matched research data or upstream training equivalence.",
    }
    project_path("pilot/audits/step2_velocity_us_closed_loop_parity.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(json.dumps({"references": len(results), "passed": True}))


if __name__ == "__main__":
    main()
