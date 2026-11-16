"""Fingerprint a converted scene and the exact BehaviorBench evaluation contract."""

from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha, reference
import argparse
import configparser
import csv
import hashlib
import json
import subprocess
from pathlib import Path


def build(root, traffic_mode):
    root = root.resolve()
    testing = root / "testing"
    validation = json.loads((testing / "validation.json").read_text())
    recording = int(validation["recording"])
    source = settings().source / "data"
    recording_meta = source / f"{recording:02d}_recordingMeta.csv"
    with recording_meta.open() as f:
        meta = next(csv.DictReader(f))
    osm, xodr = map_geometry.map_paths(meta, recording)
    scene_files = list(testing.glob("ind_*.json"))
    if len(scene_files) != 1:
        raise ValueError(f"Expected one scene JSON, found {len(scene_files)}")
    scene = json.loads(scene_files[0].read_text())
    manifest = list(csv.DictReader((testing / "manifest.csv").open()))
    if len(manifest) != 1 or int(manifest[0]["ego_agent_idx"]) != 0:
        raise ValueError("Expected a one-map manifest with ego index 0")
    ini = settings().bench / "pufferlib/config/evaluation.ini"
    config = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    config.read(ini)
    commit = subprocess.check_output(
        ["git", "-C", str(settings().bench), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "-C", str(settings().bench), "status", "--porcelain"], text=True
        ).strip()
    )
    from geotransfer_gap.runtime import late_spawn_runtime

    runtime = late_spawn_runtime.load()
    paths = {
        "source_tracks_csv": source / f"{recording:02d}_tracks.csv",
        "source_tracks_meta_csv": source / f"{recording:02d}_tracksMeta.csv",
        "source_recording_meta_csv": recording_meta,
        "source_background_image": source / f"{recording:02d}_background.png",
        "source_lanelet2_map": osm,
        "source_opendrive_map": xodr,
        "scene_json": scene_files[0],
        "scene_binary": testing / "map_000000.bin",
        "scene_manifest": testing / "manifest.csv",
        "evaluation_ini": ini,
    }
    for name in (
        "pilot_ind.py",
        "late_spawn_runtime.py",
        "admit_scene.py",
        "scene_contract.py",
        "run_pilot_eval.py",
        "audit_rule_applicability.py",
        "register_background.py",
        "render_rule_review.py",
        "audit_scene.py",
        "audit_map_semantics.py",
        "audit_physical_source.py",
        "validate_replay.py",
        "probe_eval_replay.py",
        "validate_spawn.py",
        "validate_parked.py",
        "trace_eval_lifecycle.py",
        "probe_counterfactual.py",
        "probe_repeat_reset.py",
        "audit_interaction_fidelity.py",
        "render_overlap_reference.py",
        "hybrid_traffic.py",
        "probe_hybrid_protocol_parity.py",
        "background_route_intent.py",
        "source_lane_changes.py",
        "config.py",
        "artifacts.py",
        "lanelet.py",
        "binary.py",
        "ind.py",
        "session.py",
    ):
        paths["tool_" + name] = tool_path(name)
    return {
        "schema_version": 2,
        "scene_reference": reference(root),
        "scene_root": str(root),
        "recording": recording,
        "ego_track_id": scene["objects"][0]["id"],
        "ego_binary_index": 0,
        "traffic_mode": traffic_mode,
        "episode_steps": len(scene["objects"][0]["valid"]),
        "goal_sample": validation["ego_goal_sample"],
        "goal_position": scene["objects"][0]["goalPosition"],
        "evaluator_env": {
            key: config["env"].get(key)
            for key in (
                "dt",
                "goal_behavior",
                "termination_mode",
                "collision_behavior",
                "offroad_behavior",
                "collision_shrink",
                "episode_length",
            )
        },
        "behavior_bench_commit": commit,
        "behavior_bench_dirty": dirty,
        "runtime_source_sha256": runtime["runtime_source_sha256"],
        "files": {
            name: {"path": str(path), "reference": reference(path), "sha256": sha(path)}
            for name, path in paths.items()
        },
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument(
        "--traffic-mode", choices=("expert", "idm", "dynamics"), required=True
    )
    args = ap.parse_args()
    report = build(args.root, args.traffic_mode)
    path = (
        args.root.resolve()
        / "testing"
        / f"evaluation_contract_{args.traffic_mode}.json"
    )
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "path": str(path),
                "ego_track_id": report["ego_track_id"],
                "runtime_source_sha256": report["runtime_source_sha256"],
            },
            indent=2,
        )
    )


def identity(contract):
    """Logical locations and content define identity; absolute paths are metadata."""
    if not isinstance(contract, dict):
        return contract
    value = dict(contract)
    if "scene_reference" in value:
        value.pop("scene_root", None)
    value["files"] = {
        name: {
            k: v for k, v in entry.items() if k != "path" or "reference" not in entry
        }
        for name, entry in value.get("files", {}).items()
    }
    return value


def contracts_equal(left, right):
    return identity(left) == identity(right)
