"""Profile source screens and technical admission in a fresh ``/tmp`` tree."""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from geotransfer_gap.config import PROJECT_ROOT, settings, tool_path
from geotransfer_gap.corpus import run_oriented_candidate_queue as queue
from geotransfer_gap.validation import admit_scene, scene_contract


QUEUE_SCREENS = (
    "audit_scene.py",
    "audit_map_semantics.py",
    "audit_rule_applicability.py",
    "audit_physical_source.py",
)
DECISION_FIELDS = (
    "checks",
    "details",
    "traffic_protocol",
    "technical_admitted",
    "research_admitted",
    "eligible_interaction_types",
    "diagnostic_traffic_modes",
    "diagnostic_findings",
    "exclusion_reasons",
)


def parse_candidate(value: str) -> tuple[str, Path]:
    label, separator, path = value.partition("=")
    if not separator or not label or Path(label).name != label or not path:
        raise argparse.ArgumentTypeError("candidate must use LABEL=PATH")
    return label, Path(path).expanduser().resolve()


def decision(report: dict[str, Any]) -> dict[str, Any]:
    return {key: report.get(key) for key in DECISION_FIELDS}


def dependency_digest(root: Path) -> tuple[int, str]:
    files = scene_contract.build(root, "expert")["files"]
    tools = {
        name: row["sha256"]
        for name, row in files.items()
        if name.startswith("tool_")
    }
    payload = json.dumps(tools, sort_keys=True, separators=(",", ":")).encode()
    return len(tools), hashlib.sha256(payload).hexdigest()


def copy_scratch_support(source_artifacts: Path, scratch_artifacts: Path) -> None:
    for name in (
        "source_lane_change_native_oracle.json",
        "hybrid_protocol_us_parity.json",
    ):
        source = source_artifacts / "audits" / name
        if source.is_file():
            target = scratch_artifacts / "audits" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def queue_screens(root: Path, env: dict[str, str]) -> dict[str, Any]:
    stages = []
    for name in QUEUE_SCREENS:
        started = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, str(tool_path(name)), "--root", str(root)],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        elapsed = time.perf_counter() - started
        (root / f"{name}.log").write_text(proc.stdout + proc.stderr)
        stages.append({"stage": name, "seconds": elapsed, "returncode": proc.returncode})
        if proc.returncode:
            return {"stages": stages, "source_screen_slice_passed": False, "blocker": name}

    testing = root / "testing"
    geometry = json.loads((testing / "map_audit.json").read_text())
    rules = json.loads((testing / "rule_applicability_audit.json").read_text())
    physical = json.loads((testing / "physical_source_audit.json").read_text())
    ego_id = str(rules.get("ego_track_id"))
    overlaps = physical.get("source_box_actor_overlap_details", {})
    blocker = None
    if geometry.get("ego_samples_outside_lanelet_polygons") or not geometry.get(
        "occupied_start_to_occupied_goal_reachable"
    ):
        blocker = "source_geometry_rejection"
    elif queue.unsupported_rules(rules):
        blocker = "raw_rule_flags_require_optional_scope_proof_or_exclusion"
    elif ego_id in physical.get("source_box_boundary_contacts", {}):
        blocker = "source_ego_boundary_rejection"
    elif any(not row.get("reviewable_annotation_overlap") for row in overlaps.values()):
        blocker = "unreviewable_source_overlap"
    return {
        "stages": stages,
        "source_screen_slice_passed": blocker is None,
        "blocker": blocker,
        "raw_rule_flags": queue.unsupported_rules(rules),
        "overlap_count": len(overlaps),
        "note": "Optional queue scope proofs are not run by this source-screen slice.",
    }


def profile_admission(root: Path, protocol: str) -> dict[str, Any]:
    calls: list[tuple[str, float]] = []
    original_subprocess = admit_scene.subprocess

    class ScopedSubprocess:
        def __getattr__(self, name: str) -> Any:
            return getattr(original_subprocess, name)

        def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
            command = args[0] if args else kwargs.get("args")
            started = time.perf_counter()
            try:
                return original_subprocess.run(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - started
                parts = (
                    [str(part) for part in command]
                    if isinstance(command, (list, tuple))
                    else []
                )
                stage = (
                    Path(parts[1]).name
                    if len(parts) > 1 and parts[1].endswith(".py")
                    else "other"
                )
                calls.append((stage, elapsed))

    old_argv = sys.argv
    started = time.perf_counter()
    returncode = 0
    stdout = io.StringIO()
    stderr = io.StringIO()
    failure = None
    try:
        admit_scene.subprocess = ScopedSubprocess()
        sys.argv = [
            str(tool_path("admit_scene.py")),
            "--root",
            str(root),
            "--traffic-protocol",
            protocol,
        ]
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                admit_scene.main()
            except SystemExit as error:
                returncode = int(error.code or 0)
            except Exception as error:
                failure = f"{type(error).__name__}: {error}"
    finally:
        sys.argv = old_argv
        admit_scene.subprocess = original_subprocess

    grouped: dict[str, list[float]] = defaultdict(list)
    for name, elapsed in calls:
        grouped[name].append(elapsed)
    stages = {
        name: {"count": len(values), "seconds": sum(values)}
        for name, values in sorted(grouped.items())
    }
    subprocess_seconds = sum(elapsed for _, elapsed in calls)
    outer_seconds = time.perf_counter() - started
    return {
        "returncode": returncode,
        "outer_seconds": outer_seconds,
        "subprocess_seconds": subprocess_seconds,
        "unattributed_seconds": outer_seconds - subprocess_seconds,
        "stages": stages,
        "failure": failure,
        "stderr": stderr.getvalue(),
        "stdout": stdout.getvalue(),
    }


def profile_candidate(
    label: str,
    source_root: Path,
    protocol: str,
    scratch_artifacts: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    if not (source_root / "testing/validation.json").is_file():
        raise ValueError(f"candidate is missing testing/validation.json: {source_root}")
    root = scratch_artifacts / label
    shutil.copytree(source_root, root)
    screen = queue_screens(root, env)
    count_before, digest_before = dependency_digest(root)
    admission_name = "admission.json" if protocol == "idm" else "admission_hybrid_startup.json"
    admission_path = root / "testing" / admission_name
    command = [
        sys.executable,
        str(tool_path("admit_scene.py")),
        "--root",
        str(root),
        "--traffic-protocol",
        protocol,
    ]
    admission_path.unlink(missing_ok=True)
    started = time.perf_counter()
    ordinary = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    ordinary_seconds = time.perf_counter() - started
    if not admission_path.is_file():
        raise RuntimeError(
            "ordinary admission did not create a fresh report. "
            f"returncode={ordinary.returncode}\n"
            f"stderr:\n{ordinary.stderr}\nstdout:\n{ordinary.stdout}"
        )
    ordinary_report = json.loads(admission_path.read_text())

    admission_path.unlink()
    profiled = profile_admission(root, protocol)
    if not admission_path.is_file():
        raise RuntimeError(
            "profiled admission did not create a fresh report. "
            f"failure={profiled['failure']}\n"
            f"stderr:\n{profiled['stderr']}\nstdout:\n{profiled['stdout']}"
        )
    profiled_report = json.loads(admission_path.read_text())
    count_after, digest_after = dependency_digest(root)
    differences = [
        name
        for name in DECISION_FIELDS
        if decision(ordinary_report)[name] != decision(profiled_report)[name]
    ]
    full_stages = profiled["stages"]
    queue_stage_times = {row["stage"]: row["seconds"] for row in screen["stages"]}
    duplicate_stages = {
        name: {
            "queue_seconds": queue_stage_times.get(name),
            "full_gate_seconds": full_stages.get(name, {}).get("seconds", 0.0),
            "repeated_by_full_gate": name in queue_stage_times and name in full_stages,
        }
        for name in QUEUE_SCREENS
    }
    return {
        "source_root": str(source_root),
        "scratch_root": str(root),
        "queue_screens": screen,
        "ordinary_admission_seconds": ordinary_seconds,
        "ordinary_returncode": ordinary.returncode,
        "profiled_admission": profiled,
        "decision_parity": not differences,
        "decision_fields_different": differences,
        "technical_admitted": profiled_report.get("technical_admitted"),
        "research_admitted": profiled_report.get("research_admitted"),
        "exclusion_reasons": profiled_report.get("exclusion_reasons"),
        "queue_full_gate_duplicate_stages": duplicate_stages,
        "validation_dependency_count": count_before,
        "validation_dependencies_unchanged": count_before == count_after
        and digest_before == digest_after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", type=parse_candidate)
    parser.add_argument("--traffic-protocol", choices=("idm", "hybrid_startup"), default="hybrid_startup")
    parser.add_argument(
        "--support-artifacts",
        type=Path,
        help="read-only artifacts tree supplying current pinned audit evidence",
    )
    args = parser.parse_args()
    source_artifacts = settings().artifacts
    support_artifacts = args.support_artifacts.resolve() if args.support_artifacts else source_artifacts
    candidates = args.candidate or [
        ("technical_pass", source_artifacts / "oriented_v3/r15_e332_f25626"),
        ("technical_reject", source_artifacts / "oriented_v3/r00_e321_f21052"),
    ]
    if len({label for label, _ in candidates}) != len(candidates):
        parser.error("candidate labels must be unique")
    run_dir = Path(tempfile.mkdtemp(prefix="geotransfer-admission-profile-", dir="/tmp"))
    scratch_artifacts = run_dir / "artifacts"
    scratch_artifacts.mkdir()
    copy_scratch_support(support_artifacts, scratch_artifacts)
    env = dict(
        os.environ,
        GEOTRANSFER_ARTIFACTS=str(scratch_artifacts),
        MPLCONFIGDIR=os.environ.get("MPLCONFIGDIR", "/tmp/geotransfer_mpl"),
        OMP_NUM_THREADS="2",
    )
    old_artifacts = os.environ.get("GEOTRANSFER_ARTIFACTS")
    os.environ["GEOTRANSFER_ARTIFACTS"] = str(scratch_artifacts)
    try:
        result = {
            "schema_version": 1,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_dir": str(run_dir),
            "protocol": args.traffic_protocol,
            "support_artifacts": str(support_artifacts),
            "software": {
                "repo_revision": subprocess.check_output(
                    ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"], text=True
                ).strip(),
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "behavior_bench_revision": subprocess.check_output(
                    ["git", "-C", str(settings().bench), "rev-parse", "HEAD"], text=True
                ).strip(),
                "lanelet2_version": importlib.metadata.version("lanelet2"),
            },
            "candidates": {},
        }
        for label, source_root in candidates:
            result["candidates"][label] = profile_candidate(
                label, source_root, args.traffic_protocol, scratch_artifacts, env
            )
        output = run_dir / "profile.json"
        output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"run_dir": str(run_dir), "profile_json": str(output)}, indent=2))
    finally:
        if old_artifacts is None:
            os.environ.pop("GEOTRANSFER_ARTIFACTS", None)
        else:
            os.environ["GEOTRANSFER_ARTIFACTS"] = old_artifacts
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
