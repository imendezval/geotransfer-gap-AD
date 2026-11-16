"""Supported command surface; backend imports are deferred until dispatch."""

import argparse
import json
import os
from pathlib import Path
import runpy
import sys

COMMANDS = {
    "convert": "pilot_ind",
    "validate": {
        "technical": "admit_scene",
        "smart": "admit_smart_scene",
        "replay": "validate_replay",
        "map": "audit_scene",
        "semantics": "audit_map_semantics",
        "rules": "audit_rule_applicability",
        "physical": "audit_physical_source",
        "interaction": "audit_interaction_fidelity",
        "counterfactual": "probe_counterfactual",
        "lifecycle": "trace_eval_lifecycle",
        "spawn": "validate_spawn",
        "parked": "validate_parked",
        "reset": "probe_repeat_reset",
        "registration": "register_background",
        "directed-rule": "audit_directed_rule_scope",
        "following": "audit_following_scope",
        "task-rule": "audit_task_rule_scope",
        "route": "audit_source_route_sequence",
        "smart-input": "probe_smart_map_transfer",
        "us": "probe_us_reference_parity",
        "us-traffic": "probe_hybrid_protocol_parity",
    },
    "corpus": {
        "catalog": "catalog_ind_windows",
        "cyclists": "catalog_cyclist_encounters",
        "tasks": "screen_source_tasks",
        "restarts": "screen_source_restarts",
        "interactions": "screen_source_interactions",
        "select": "select_oriented_candidates",
        "select-cyclists": "select_third_family",
        "phases": "expand_source_phase_queue",
        "preflight": "preflight_source_map",
        "screen": "run_oriented_candidate_queue",
        "build": "build_smart_pilot_manifest",
        "build-technical": "build_step2_corpus",
        "access": "audit_corpus_access",
        "targets": "audit_final_corpus_targets",
        "freeze": "freeze_smart_protocol",
        "report": "report_step2_flow",
    },
    "check": {
        "admission": "probe_smart_admission_regressions",
        "queue": "probe_queue_pair_identity",
        "orientation": "probe_lanelet_orientation",
        "lane-changes": "probe_source_lane_changes",
        "background": "probe_background_route_policy",
        "map": "probe_faithful_map",
        "route": "probe_source_route_sequence",
        "directed-rule": "probe_directed_rule_scope",
        "restart": "probe_source_restart_screen",
        "following": "probe_following_scope",
        "task-rule": "probe_task_rule_scope",
        "reentry": "probe_source_reentry",
        "startup": "probe_startup_departure",
    },
}


def invoke(tool, args):
    from .config import tool_path, ensure_bench

    ensure_bench()
    sys.argv = [tool + ".py", *args]
    runpy.run_path(str(tool_path(tool + ".py")), run_name="__main__")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description="Validated inD → BehaviorBench conversion, admission, execution and viewing."
    )
    parser.add_argument(
        "--config", type=Path, help="TOML configuration (before command)"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=[
            "doctor",
            "scenes",
            "convert",
            "validate",
            "corpus",
            "run",
            "view",
            "check",
        ],
    )
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    rest = args.arguments
    if args.config:
        os.environ["GEOTRANSFER_CONFIG"] = str(args.config.resolve())
    if not args.command:
        parser.print_help()
        return
    from .config import settings, registry

    if args.command == "doctor":
        cfg = settings()
        checks = {
            k: str(getattr(cfg, k))
            for k in (
                "project",
                "source",
                "bench",
                "artifacts",
                "weights",
                "cache",
                "runs",
            )
        }
        missing = [
            k for k in ("source", "bench", "weights") if not getattr(cfg, k).exists()
        ]
        print(
            json.dumps(
                {"paths": checks, "missing": missing, "python": sys.executable},
                indent=2,
            )
        )
        if missing:
            raise SystemExit(1)
        return
    if args.command == "scenes":
        from .artifacts import scenes, scene_root

        if not rest or rest[0] == "list":
            for r in scenes():
                print(r["name"], ",".join(r["interaction_type_families"]) or "control")
        elif rest[0] == "show" and len(rest) == 2:
            root = scene_root(rest[1])
            print(
                json.dumps(
                    {
                        "root": str(root),
                        "files": sorted((p.name for p in (root / "testing").iterdir())),
                    },
                    indent=2,
                )
            )
        else:
            parser.error("Use scenes list or scenes show SCENE")
        return
    if args.command == "run":
        from .execution import main as execute

        execute(rest)
        return
    if args.command == "view":
        from .visualization.viewer import main as view

        view(rest)
        return
    if args.command == "check" and rest and rest[0] == "all":
        from .validation.suite import main as suite

        suite(rest[1:])
        return
    if args.command == "check" and rest and (rest[0] == "migration"):
        from .migration import main as migrate

        migrate(rest[1:])
        return
    if args.command == "check" and rest and (rest[0] == "tool"):
        if len(rest) < 2 or rest[1] + ".py" not in registry():
            parser.error("Unknown retained tool")
        invoke(rest[1], rest[2:])
        return
    command = COMMANDS[args.command]
    if isinstance(command, dict):
        if not rest or rest[0] in ("-h", "--help"):
            print(args.command + ": " + ", ".join(command))
            return
        if rest[0] not in command:
            parser.error("Unknown action; choose " + ", ".join(command))
        command = command[rest.pop(0)]
    invoke(command, rest)
