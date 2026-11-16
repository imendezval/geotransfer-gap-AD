"""Verify source-startup hybrid traffic mode transitions on a US WOMD scene."""

from geotransfer_gap.conversion import binary as binary_io
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from geotransfer_gap.runtime import hybrid_traffic


def main(us_json, output_root, steps):
    source = json.loads(us_json.read_text())
    testing = output_root / "testing"
    testing.mkdir(parents=True, exist_ok=True)
    binary = testing / "map_000000.bin"
    binary_io.load_source_writer()(source, str(binary), 0, trajectory_length=91)
    schedule = hybrid_traffic.release_schedule(source)
    if not schedule:
        raise ValueError(
            "US parity probe needs at least one initially stopped vehicle that restarts"
        )
    alias = Path("/tmp") / ("geo_us_hybrid_" + sha(us_json)[:12])
    if not alias.exists():
        alias.symlink_to(output_root.resolve(), target_is_directory=True)
    sys.path.insert(0, str(settings().bench))
    from geotransfer_gap.runtime import late_spawn_runtime

    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding

    ini = settings().bench / "pufferlib/config/evaluation.ini"
    env = Drive(
        data_root=str(alias),
        split="testing",
        num_maps=1,
        num_agents=128,
        episode_length=91,
        map_id=0,
        action_type="continuous",
        control_mode="control_evaluation",
        goal_behavior=3,
        ini_file=str(ini),
        resample_frequency=0,
    )
    ego_index = source["metadata"]["sdc_track_index"]
    observed = {str(source["objects"][i]["id"]): [] for i in schedule}
    try:
        env.reset()
        for step in range(steps):
            state = env.get_state()[0]
            slots = {
                index: slot for slot, index in enumerate(state["active_agent_indices"])
            }
            if ego_index in slots:
                binding.vec_set_movement_mode(env.c_envs, [slots[ego_index]], 2)
            hybrid_traffic.apply(env, source, schedule, step, binding)
            state = env.get_state()[0]
            for index, release in schedule.items():
                if step not in (0, release - 1, release) or index not in slots:
                    continue
                entity = state["entities"][index]
                if entity["x"] != -10000.0:
                    observed[str(source["objects"][index]["id"])].append(
                        {
                            "step": step,
                            "release_step": release,
                            "movement_mode": entity["movement_mode"],
                            "expected_mode": 2 if step < release else 1,
                        }
                    )
            env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
    finally:
        env.close()
    checked = [row for rows in observed.values() for row in rows]
    report = {
        "schema_version": 1,
        "us_source_json": str(us_json.resolve()),
        "us_source_sha256": sha(us_json),
        "us_binary_sha256": sha(binary),
        "us_binary_path": str(binary.resolve()),
        "evaluator_ini_sha256": sha(ini),
        "runtime_source_sha256": runtime["runtime_source_sha256"],
        "hybrid_protocol_sha256": sha(Path(hybrid_traffic.__file__)),
        "us_scenario_id": source["scenario_id"],
        "us_sdc_index": ego_index,
        "observed_steps": steps,
        "held_vehicle_release_steps": {
            str(source["objects"][i]["id"]): t for i, t in schedule.items()
        },
        "observed_mode_transitions": observed,
        "mechanical_parity_pass": bool(checked)
        and any((row["step"] == row["release_step"] for row in checked))
        and all((row["movement_mode"] == row["expected_mode"] for row in checked)),
        "scope": "Same hybrid_traffic.py release rule and mode assignment on a local US WOMD JSON binary; this verifies mechanics, not US planner scores or training parity.",
    }
    output = project_path("pilot/audits/hybrid_protocol_us_parity.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "mechanical_parity_pass": report["mechanical_parity_pass"],
                "held_vehicles": len(schedule),
                "checked_modes": len(checked),
                "report": str(output),
            },
            indent=2,
        )
    )
    if not report["mechanical_parity_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--us-json", type=Path, required=True)
    ap.add_argument(
        "--output-root",
        type=Path,
        default=project_path("pilot/probes/us_hybrid_parity"),
    )
    ap.add_argument("--steps", type=int, default=45)
    args = ap.parse_args()
    main(args.us_json, args.output_root, args.steps)
