"""Progressive source screens and full technical gates for a frozen candidate queue.

Never grants research admission. Manual source review and SMART model-input
proof are separate. Resume skips only records bound to unchanged sources/tools.
"""

from geotransfer_gap.artifacts import resolve_reference
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
from geotransfer_gap.maps import lanelet as map_geometry
import argparse
import concurrent.futures
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import fcntl

HERE = PROJECT_ROOT


def scene_key(row):
    return (row["recording"], row["ego"], row["first_frame"])


def candidate_key(row):
    return (*scene_key(row), row["actor"])


def same_pair_version(left, right):
    return (
        all(key in left for key in ("recording", "ego", "first_frame", "actor"))
        and candidate_key(left) == candidate_key(right)
        and left.get("screen_fingerprints") == right.get("screen_fingerprints")
    )


def scope_audit_failed(proc, output_path):
    return proc.returncode != 0 or not Path(output_path).is_file()


def candidate_result(scene_result, row, opportunities=()):
    opportunities = scene_result.get("_actor_opportunities", opportunities)
    result = dict(row, **scene_result)
    result.pop("_actor_opportunities", None)
    result["candidate_actor_fidelity"] = next(
        (x for x in opportunities if x.get("track_id") == row["actor"]), None
    )
    return result


# These are the tools and BehaviorBench inputs bound by scene_contract.build,
# plus the source-only audits and proofs executed by this queue.
SCREEN_TOOLS = (
    "pilot_ind.py",
    "admit_scene.py",
    "audit_scene.py",
    "audit_rule_applicability.py",
    "audit_map_semantics.py",
    "audit_physical_source.py",
    "late_spawn_runtime.py",
    "hybrid_traffic.py",
    "background_route_intent.py",
    "run_pilot_eval.py",
    "register_background.py",
    "render_rule_review.py",
    "validate_replay.py",
    "probe_eval_replay.py",
    "validate_spawn.py",
    "validate_parked.py",
    "trace_eval_lifecycle.py",
    "audit_interaction_fidelity.py",
    "probe_counterfactual.py",
    "probe_repeat_reset.py",
    "probe_hybrid_protocol_parity.py",
    "render_overlap_reference.py",
    "audit_task_rule_scope.py",
    "audit_following_scope.py",
    "audit_directed_rule_scope.py",
    "audit_source_route_sequence.py",
    "source_lane_changes.py",
    "config.py",
    "artifacts.py",
    "scene_contract.py",
    "ind.py",
    "lanelet.py",
    "binary.py",
    "session.py",
    "provenance.py",
    "run_oriented_candidate_queue.py",
)

REUSABLE_OUTPUTS = {
    "source_geometry_rejection": (
        "testing/map_audit.json",
        "testing/rule_applicability_audit.json",
    ),
    "unresolved_semantics_screen": (
        "testing/map_audit.json",
        "testing/rule_applicability_audit.json",
    ),
    "source_ego_boundary_rejection": ("testing/physical_source_audit.json",),
    "unreviewable_source_overlap": ("testing/physical_source_audit.json",),
    "technical_rejection": (
        "testing/admission_hybrid_startup.json",
        "testing/interaction_fidelity_audit_hybrid_startup.json",
    ),
    "awaiting_manual_review": (
        "testing/admission_hybrid_startup.json",
        "testing/interaction_fidelity_audit_hybrid_startup.json",
    ),
}

TECHNICAL_EVIDENCE = (
    "admission_hybrid_startup.json",
    "interaction_fidelity_audit_hybrid_startup.json",
    "evaluation_contract_expert.json",
    "evaluation_contract_idm.json",
    "evaluation_contract_hybrid_startup.json",
    "map_audit.json",
    "map_semantics_audit.json",
    "rule_applicability_audit.json",
    "physical_source_audit.json",
    "replay_validation.json",
    "evaluation_replay_probe.json",
    "spawn_evaluation_validation.json",
    "parked_evaluation_validation.json",
    "reset_evaluation_probe.json",
    "lifecycle_trace_expert.json",
    "lifecycle_trace_idm.json",
    "lifecycle_trace_hybrid_startup.json",
    "counterfactual_probe.json",
    "counterfactual_hybrid_probe.json",
    "physical_overlap_review.json",
)


def source_input_paths(row, source_root):
    """Return the actual source files used for this recording and its map."""
    rec = row["recording"]
    data = source_root / "data"
    paths = {
        "tracks": data / f"{rec:02d}_tracks.csv",
        "tracks_meta": data / f"{rec:02d}_tracksMeta.csv",
        "recording_meta": data / f"{rec:02d}_recordingMeta.csv",
        "background": data / f"{rec:02d}_background.png",
    }
    recording_meta = paths["recording_meta"]
    if recording_meta.is_file():
        try:
            with recording_meta.open() as stream:
                meta = next(csv.DictReader(stream))
            osm, xodr = map_geometry.map_paths(meta, rec)
            try:
                paths["lanelet_map"] = source_root / osm.relative_to(map_geometry.SOURCE)
                paths["opendrive_map"] = source_root / xodr.relative_to(map_geometry.SOURCE)
            except ValueError:
                paths["lanelet_map"] = osm
                paths["opendrive_map"] = xodr
        except (OSError, StopIteration, KeyError, ValueError):
            paths["lanelet_map"] = source_root / "maps/missing_lanelet_map.osm"
            paths["opendrive_map"] = source_root / "maps/missing_opendrive_map.xodr"
    else:
        paths["lanelet_map"] = source_root / "maps/missing_lanelet_map.osm"
        paths["opendrive_map"] = source_root / "maps/missing_opendrive_map.xodr"
    return paths


def file_fingerprints(paths):
    """Hash existing inputs and represent absent inputs so later additions invalidate reuse."""
    return {
        name: sha(path) if Path(path).is_file() else None
        for name, path in sorted(paths.items())
    }


def runtime_fingerprint():
    packages = {}
    for name in ("numpy", "pandas", "lanelet2", "shapely"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    executable = Path(sys.executable).resolve()
    return {
        "python": sys.version,
        "implementation": sys.implementation.name,
        "platform": platform.platform(),
        "executable": str(executable),
        "executable_sha256": sha(executable) if executable.is_file() else None,
        "packages": packages,
        "environment": {
            name: os.environ.get(name)
            for name in ("PATH", "LD_LIBRARY_PATH", "PYTHONPATH", "GDAL_DATA")
        },
    }


def configuration_fingerprint():
    cfg = settings()
    names = (
        "project",
        "source",
        "bench",
        "artifacts",
        "runs",
        "cache",
        "weights",
        "reference_data",
    )
    config_path = Path(
        os.environ.get("GEOTRANSFER_CONFIG", cfg.project / "configs/local.toml")
    ).expanduser()
    return {
        "settings": {name: str(getattr(cfg, name)) for name in names},
        "config_path": str(config_path.resolve()),
        "config_sha256": sha(config_path) if config_path.is_file() else None,
    }


def benchmark_input_fingerprints(bench_root):
    paths = {
        "evaluation_ini": bench_root / "pufferlib/config/evaluation.ini",
        "drive_writer": bench_root / "pufferlib/ocean/drive/drive.py",
        "binary_reader": bench_root / "pufferlib/prediction/binary_reader.py",
        "drive_header": bench_root / "pufferlib/ocean/drive/drive.h",
        "binding": bench_root / "pufferlib/ocean/drive/binding.c",
        "env_binding": bench_root / "pufferlib/ocean/env_binding.h",
        "env_config": bench_root / "pufferlib/ocean/env_config.h",
        "ini_source": bench_root / "inih-r62/ini.c",
    }
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(bench_root), "rev-parse", "HEAD"], text=True
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "-C", str(bench_root), "status", "--porcelain"],
                text=True,
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return {
        "files": file_fingerprints(paths),
        "git_commit": commit,
        "git_dirty": dirty,
    }


def external_evidence_fingerprints():
    paths = {
        "lane_change_oracle": project_path(
            "pilot/audits/source_lane_change_native_oracle.json"
        ),
        "hybrid_protocol_parity": project_path(
            "pilot/audits/hybrid_protocol_us_parity.json"
        ),
    }
    result = file_fingerprints(paths)
    parity = paths["hybrid_protocol_parity"]
    if parity.is_file():
        try:
            report = json.loads(parity.read_text())
        except (OSError, ValueError):
            report = {}
        for field in ("us_source_json", "us_binary_path"):
            value = report.get(field)
            path = Path(value) if value else Path("/missing")
            result[field] = sha(path) if path.is_file() else None
    return result


def output_fingerprints(root, status):
    root = Path(root)
    base = [
        "testing/validation.json",
        "testing/manifest.csv",
        "testing/map_000000.bin",
    ]
    scenes = sorted((root / "testing").glob("ind_*.json"))
    paths = [root / name for name in base] + scenes
    paths.extend(root / name for name in REUSABLE_OUTPUTS[status])
    if status in ("technical_rejection", "awaiting_manual_review"):
        paths.extend(root / "testing" / name for name in TECHNICAL_EVIDENCE)
    if status == "unresolved_semantics_screen":
        paths.extend(
            root / "testing" / name
            for name in (
                "source_task_rule_scope.json",
                "source_following_scope.json",
            )
        )
    return {
        path.relative_to(root).as_posix(): sha(path)
        for path in sorted(set(paths))
        if path.is_file()
    }


def reusable_result(row, fingerprints):
    """Reuse only a conclusive row whose source, producers, and output tree still match."""
    required = REUSABLE_OUTPUTS.get(row.get("status"))
    if not required or row.get("screen_fingerprints") != fingerprints:
        return False
    root = row.get("root")
    bound = row.get("output_fingerprints")
    if not root or not isinstance(bound, dict) or not bound:
        return False
    root = Path(root)
    try:
        expected = output_fingerprints(root, row["status"])
        core = (
            "testing/validation.json",
            "testing/manifest.csv",
            "testing/map_000000.bin",
        )
        return (
            all(name in expected for name in (*core, *required))
            and any(name.startswith("testing/ind_") for name in expected)
            and expected == bound
        )
    except OSError:
        return False


def candidate_output_base(row, artifacts_root, fingerprint):
    rec, ego, first = scene_key(row)
    token = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True).encode()
    ).hexdigest()[:12]
    return Path(artifacts_root) / "oriented_v3" / (
        f"r{rec:02d}_e{ego}_f{first}_q{token}"
    )


def next_candidate_output_root(base):
    base = Path(base)
    root = base
    attempt = 1
    while root.exists():
        root = base.with_name(f"{base.name}_attempt{attempt:03d}")
        attempt += 1
    root.mkdir(parents=True, exist_ok=False)
    return root


def unsupported_rules(a):
    flags = []
    for rule in a.get("governing_regulatory_elements", []):
        if not any((m["role"] == "yield" for m in rule["ego_members"])):
            continue
        if any((s.get("subtype") == "de206" for s in rule.get("signs", []))):
            flags.append("ego_stop_sign_requires_stop_even_without_conflicting_traffic")
        for actor in a.get("priority_lane_traffic", []):
            if (
                actor.get("actor_source_path_m", 0) > 1
                and actor.get("minimum_spatial_box_gap_m", float("inf")) <= 2
                and any(
                    (
                        actor.get("priority_lanelet_steps", {}).get(str(lid))
                        for lid in rule["priority_lanelets"]
                    )
                )
            ):
                flags.append(
                    f"rule_{rule['id']}_priority_{actor['type']}_{actor['track_id']}_spatial_conflict"
                )
    for key, prefix in [
        ("oncoming_turn_conflicts", "implicit_oncoming_turn_priority"),
        ("slow_ego_fast_crosspath_conflicts", "slow_ego_fast_crosspath"),
        ("yield_lane_fast_crosspath_conflicts", "yield_lane_fast_crosspath"),
    ]:
        flags.extend((f"{prefix}_{x['type']}_{x['track_id']}" for x in a.get(key, [])))
    return sorted(set(flags))


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument(
        "--selection",
        type=Path,
        default=project_path("pilot/audits/step2_oriented_source_selection.json"),
    )
    ap.add_argument(
        "--ledger",
        type=Path,
        default=project_path("pilot/audits/step2_oriented_candidate_ledger.json"),
    )
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument(
        "--one-faithful-window-per-task",
        action="store_true",
        help="Defer alternate windows after a technically admitted, primary-actor-preserved window; manual/research review remains mandatory.",
    )
    args = ap.parse_args()
    args.selection = args.selection.resolve()
    args.ledger = args.ledger.resolve()
    os.chdir(HERE)
    selection = json.loads(args.selection.read_text())
    jobs = selection["jobs"]
    groups = {}
    for r in jobs:
        groups.setdefault((r["location"], r["role"]), []).append(r)
    jobs = [
        groups[k][i]
        for i in range(max(map(len, groups.values()), default=0))
        for k in sorted(groups)
        if i < len(groups[k])
    ]

    def task_key(r):
        return (r["recording"], r["ego"], r["actor"])

    if args.one_faithful_window_per_task:
        tasks = {}
        for r in jobs:
            tasks.setdefault(task_key(r), []).append(r)
        jobs = [
            tasks[k][i]
            for i in range(max(map(len, tasks.values()), default=0))
            for k in tasks
            if i < len(tasks[k])
        ]
    base_fingerprints = {n: sha(tool_path(n)) for n in SCREEN_TOOLS}
    base_fingerprints["benchmark_inputs"] = benchmark_input_fingerprints(
        settings().bench
    )
    base_fingerprints["external_evidence"] = external_evidence_fingerprints()
    base_fingerprints["runtime"] = runtime_fingerprint()
    base_fingerprints["config"] = configuration_fingerprint()
    base_fingerprints["selection"] = sha(args.selection)
    base_fingerprints["variant_selection_mode"] = (
        "one_faithful_per_task" if args.one_faithful_window_per_task else "all_windows"
    )
    source_fingerprints = {}

    def fingerprints_for(row):
        source_key = (row["recording"], row["location"])
        if source_key not in source_fingerprints:
            source_fingerprints[source_key] = file_fingerprints(
                source_input_paths(row, settings().source)
            )
        return dict(
            base_fingerprints,
            source_inputs=source_fingerprints[source_key],
        )

    job_fingerprints = {candidate_key(r): fingerprints_for(r) for r in jobs}
    previous = (
        json.loads(args.ledger.read_text()) if args.ledger.exists() else {"results": []}
    )
    rows = previous["results"]
    reusable_rows = [
        r
        for r in rows
        if all(k in r for k in ("recording", "location", "ego", "first_frame", "actor"))
        and reusable_result(r, fingerprints_for(r))
    ]
    done = {candidate_key(r) for r in reusable_rows}
    remaining = [r for r in jobs if candidate_key(r) not in done]
    print("remaining chunk", len(remaining), "total selection", len(jobs), flush=True)
    env = dict(
        os.environ,
        MPLCONFIGDIR=os.environ.get("MPLCONFIGDIR", "/tmp/geotransfer_mpl"),
        OMP_NUM_THREADS="2",
    )
    scene_locks = {scene_key(row): threading.Lock() for row in jobs}
    scene_results = {}

    def run(row):
        nonlocal scene_runs, scene_reuses
        key = scene_key(row)
        fingerprints = job_fingerprints[candidate_key(row)]
        with scene_locks[key]:
            cached = scene_results.get(key)
            if cached and cached[0] == fingerprints:
                with stats_lock:
                    scene_reuses += 1
                return candidate_result(cached[1], row)
            lock_identity = hashlib.sha256(
                json.dumps(
                    {"artifacts": str(settings().artifacts), "scene": key},
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            lock_dir = Path(tempfile.gettempdir()) / "geotransfer_candidate_queue_locks"
            lock_dir.mkdir(parents=True, exist_ok=True)
            with (lock_dir / f"{lock_identity}.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    root = next_candidate_output_root(
                        candidate_output_base(row, settings().artifacts, fingerprints)
                    )
                    result = run_scene(row, root, fingerprints)
                    result["output_fingerprints"] = (
                        output_fingerprints(root, result["status"])
                        if result.get("status") in REUSABLE_OUTPUTS
                        else {}
                    )
                    if result.get("status") in REUSABLE_OUTPUTS and result.get(
                        "output_fingerprints"
                    ):
                        scene_results[key] = (fingerprints, result)
                    with stats_lock:
                        scene_runs += 1
                    return candidate_result(result, row)
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def run_scene(row, root, fingerprints):
        rec, ego, first = scene_key(row)
        row = {"recording": rec, "ego": ego, "first_frame": first}
        t = root / "testing"
        row.update(root=str(root), screen_fingerprints=fingerprints)

        def command(script, extra=()):
            proc = subprocess.run(
                [
                    sys.executable,
                    str(tool_path(script)),
                    "--root",
                    str(root),
                    *extra,
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            (root / (script + ".log")).write_text(proc.stdout + proc.stderr)
            return proc

        proc = subprocess.run(
            [
                sys.executable,
                str(tool_path("pilot_ind.py")),
                "--recording",
                str(rec),
                "--ego",
                str(ego),
                "--first-frame",
                str(first),
                "--goal-sample",
                "85",
                "--late-mode",
                "runtime_spawn",
                "--static-crop-radius",
                "1000000",
                "--parked-as-static-expert",
                "--emit-crosswalks",
                "--output-root",
                str(root),
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        (root / "conversion.log").write_text(proc.stdout + proc.stderr)
        if proc.returncode:
            row.update(status="conversion_failure", error=proc.stderr[-1000:])
            return row
        for script in [
            "audit_scene.py",
            "audit_map_semantics.py",
            "audit_rule_applicability.py",
        ]:
            proc = command(script)
            if proc.returncode:
                row.update(status="source_audit_error", error=proc.stderr[-1000:])
                return row
        m = json.loads((t / "map_audit.json").read_text())
        a = json.loads((t / "rule_applicability_audit.json").read_text())
        row["source_unsupported_rule_flags"] = unsupported_rules(a)
        if (
            m["ego_samples_outside_lanelet_polygons"]
            or not m["occupied_start_to_occupied_goal_reachable"]
        ):
            row.update(
                status="source_geometry_rejection",
                outside_steps=m["ego_samples_outside_lanelet_polygons"],
                directed_route=m["occupied_start_to_occupied_goal_reachable"],
            )
            return row
        if row["source_unsupported_rule_flags"]:
            pending = set(row["source_unsupported_rule_flags"])
            if (
                "ego_stop_sign_requires_stop_even_without_conflicting_traffic"
                in pending
            ):
                proc = command("audit_task_rule_scope.py")
                scope_path = t / "source_task_rule_scope.json"
                if scope_audit_failed(proc, scope_path):
                    row.update(
                        status="source_audit_error",
                        error=(proc.stderr or proc.stdout)[-1000:],
                    )
                    return row
                scope = json.loads(scope_path.read_text())
                scoped = bool(scope["rules"]) and all(
                    (x["stop_obligation_outside_task"] for x in scope["rules"])
                )
                row["stop_scope_requires_explicit_manual_review"] = scoped
                if scoped:
                    pending.remove(
                        "ego_stop_sign_requires_stop_even_without_conflicting_traffic"
                    )
            from geotransfer_gap.maps.audit_following_scope import heuristic_flags

            flag_actors = heuristic_flags(a)
            ids = sorted({flag_actors[x] for x in pending if x in flag_actors})
            if ids:
                proc = command("audit_following_scope.py", ["--actors", *map(str, ids)])
                proof_path = t / "source_following_scope.json"
                if scope_audit_failed(proc, proof_path):
                    row.update(
                        status="source_audit_error",
                        error=(proc.stderr or proc.stdout)[-1000:],
                    )
                    return row
                proof = json.loads(proof_path.read_text())
                certified = {
                    x["actor_id"]
                    for x in proof["actors"]
                    if x["same_route_following"]
                }
                row["same_route_following_requires_manual_review"] = sorted(
                    certified
                )
                pending = {
                    x
                    for x in pending
                    if not (x in flag_actors and flag_actors[x] in certified)
                }
            row["unresolved_rule_flags_after_source_proofs"] = sorted(pending)
            if pending:
                row.update(
                    status="unresolved_semantics_screen",
                    note="Current SMART hard-rule exclusion; no model run. Source interpretation may be revisited, never silently admitted.",
                )
                return row
        proc = command("audit_physical_source.py")
        if proc.returncode:
            row.update(status="physical_audit_error", error=proc.stderr[-1000:])
            return row
        physical = json.loads((t / "physical_source_audit.json").read_text())
        if str(ego) in physical.get("source_box_boundary_contacts", {}):
            row.update(status="source_ego_boundary_rejection")
            return row
        details = physical.get("source_box_actor_overlap_details", {})
        if any((not d.get("reviewable_annotation_overlap") for d in details.values())):
            row.update(status="unreviewable_source_overlap", overlaps=list(details))
            return row
        proc = command("admit_scene.py", ["--traffic-protocol", "hybrid_startup"])
        gate = t / "admission_hybrid_startup.json"
        if not gate.exists():
            row.update(status="technical_gate_error", error=proc.stderr[-1000:])
            return row
        d = json.loads(gate.read_text())
        if not d.get("checks", {}).get("refresh_commands", False):
            row.update(
                status="technical_gate_error",
                error="Technical gate refresh commands did not complete",
            )
            return row
        interaction_path = t / "interaction_fidelity_audit_hybrid_startup.json"
        if not interaction_path.is_file():
            row.update(
                status="technical_gate_error",
                error="Missing hybrid interaction fidelity output",
            )
            return row
        interaction = json.loads(interaction_path.read_text())
        row.update(
            status=(
                "awaiting_manual_review"
                if d["technical_admitted"]
                else "technical_rejection"
            ),
            technical_admitted=d["technical_admitted"],
            technical_gate_reasons=d["exclusion_reasons"],
            preserved_actor_ids=[
                x["track_id"]
                for x in interaction["actor_opportunities"]
                if x["preserved_for_claimed_interaction"]
            ],
            _actor_opportunities=interaction["actor_opportunities"],
        )
        return row

    faithful = {
        task_key(result)
        for result in reusable_rows
        if result.get("technical_admitted")
        and (result.get("candidate_actor_fidelity") or {}).get(
            "preserved_for_claimed_interaction"
        )
    }
    attempted = 0
    scene_runs = 0
    scene_reuses = 0
    stats_lock = threading.Lock()

    def record(row):
        nonlocal rows, attempted
        ledger_lock_name = hashlib.sha256(str(args.ledger).encode()).hexdigest()
        lock_dir = Path(tempfile.gettempdir()) / "geotransfer_candidate_queue_locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        with (lock_dir / f"ledger_{ledger_lock_name}.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = (
                json.loads(args.ledger.read_text())
                if args.ledger.exists()
                else {"results": []}
            )
            rows = [
                r
                for r in current["results"]
                if not same_pair_version(r, row)
            ] + [row]
            report = {
                "schema_version": 2,
                "selection_sha256": sha(args.selection),
                "record_identity": "recording/ego/frame/actor/producer-fingerprints; scene writes serialized",
                "variant_selection_mode": row["screen_fingerprints"][
                    "variant_selection_mode"
                ],
                "results": rows,
            }
            args.ledger.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.ledger.with_name(
                f"{args.ledger.name}.tmp-{os.getpid()}-{threading.get_ident()}"
            )
            temporary.write_text(json.dumps(report, indent=2) + "\n")
            temporary.replace(args.ledger)
            fcntl.flock(lock, fcntl.LOCK_UN)
        if row.get("technical_admitted") and (
            row.get("candidate_actor_fidelity") or {}
        ).get("preserved_for_claimed_interaction"):
            faithful.add(task_key(row))
        if row.get("status") in REUSABLE_OUTPUTS and row.get(
            "output_fingerprints"
        ):
            done.add(candidate_key(row))
        attempted += 1
        print(
            resolve_reference(row["root"]).name,
            row["status"],
            row.get("preserved_actor_ids", []),
            flush=True,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        if not args.one_faithful_window_per_task:
            for row in pool.map(run, remaining[: args.limit]):
                record(row)
        else:
            while remaining and attempted < args.limit:
                batch = []
                later = []
                batch_tasks = set()
                batch_scenes = set()
                for r in remaining:
                    key = task_key(r)
                    if key in faithful:
                        continue
                    if (
                        len(batch) < min(args.workers, args.limit - attempted)
                        and key not in batch_tasks
                        and (scene_key(r) not in batch_scenes)
                    ):
                        batch.append(r)
                        batch_tasks.add(key)
                        batch_scenes.add(scene_key(r))
                    else:
                        later.append(r)
                remaining = later
                if not batch:
                    break
                for row in pool.map(run, batch):
                    record(row)
    print(
        "attempted",
        attempted,
        "scene runs",
        scene_runs,
        "scene evidence reuses",
        scene_reuses,
        "faithful tasks",
        len(faithful),
        "unprocessed viable variants",
        sum(
            (
                task_key(r) not in faithful
                and candidate_key(r) not in done
                for r in remaining
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
