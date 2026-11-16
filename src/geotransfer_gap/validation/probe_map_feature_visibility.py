"""Add supported binary sign/crosswalk types and compare unchanged C observations."""

from geotransfer_gap.conversion import binary as binary_io
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()
    root = args.root.resolve()
    source = root / "testing"
    scene = json.loads(next(source.glob("ind_*.json")).read_text())
    ego = scene["objects"][0]["position"][0]
    x, y = (ego["x"], ego["y"])
    features = [
        {
            "id": 90000001,
            "type": "traffic_sign",
            "map_element_id": 17,
            "geometry": [{"x": x + 2, "y": y, "z": 0}, {"x": x + 2.1, "y": y, "z": 0}],
        },
        {
            "id": 90000002,
            "type": "crosswalk",
            "map_element_id": 18,
            "geometry": [
                {"x": x + 4, "y": y - 2, "z": 0},
                {"x": x + 4, "y": y + 2, "z": 0},
            ],
        },
    ]
    variant = json.loads(json.dumps(scene))
    variant["roads"].extend(features)
    base_dir = Path("/tmp/geo_feature_base")
    variant_dir = Path("/tmp/geo_feature_variant")
    for out, data in ((base_dir, scene), (variant_dir, variant)):
        testing = out / "testing"
        testing.mkdir(parents=True, exist_ok=True)
        binary_io.load_source_writer()(
            data, str(testing / "map_000000.bin"), 0, trajectory_length=91
        )
    sys.path.insert(0, str(settings().bench))
    from geotransfer_gap.runtime import late_spawn_runtime

    late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive

    def observe(directory):
        env = Drive(
            data_root=str(directory),
            split="testing",
            num_maps=1,
            num_agents=128,
            episode_length=91,
            map_id=0,
            action_type="continuous",
            control_mode="control_evaluation",
            goal_behavior=3,
            ini_file=str(settings().bench / "pufferlib/config/evaluation.ini"),
            resample_frequency=0,
        )
        try:
            env.reset()
            state = env.get_state()[0]
            slot = state["active_agent_indices"].index(0)
            return (np.array(env.observations[slot], copy=True), state)
        finally:
            env.close()

    base_obs, base_state = observe(base_dir)
    variant_obs, variant_state = observe(variant_dir)
    delta = np.abs(base_obs - variant_obs)
    report = {
        "source_binary_sha256": hashlib.sha256(
            (source / "map_000000.bin").read_bytes()
        ).hexdigest(),
        "base_binary_sha256": hashlib.sha256(
            (base_dir / "testing/map_000000.bin").read_bytes()
        ).hexdigest(),
        "variant_binary_sha256": hashlib.sha256(
            (variant_dir / "testing/map_000000.bin").read_bytes()
        ).hexdigest(),
        "added_binary_types": [e["type"] for e in variant_state["entities"][-2:]],
        "observation_shape": list(base_obs.shape),
        "max_abs_observation_delta": float(delta.max()),
        "nonzero_over_1e_5": int(np.count_nonzero(delta > 1e-05)),
        "observation_unchanged_to_1e_5": bool(delta.max() <= 1e-05),
    }
    (source / "map_feature_visibility_probe.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
