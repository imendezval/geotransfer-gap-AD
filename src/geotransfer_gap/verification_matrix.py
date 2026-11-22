"""Inventory the fixed 504-slot controller verification matrix without running it."""

import argparse
from itertools import product
from pathlib import Path

from .artifacts import read_json, reference, resolve_reference, sha256, write_json
from .config import settings
from .execution import CONTROLLERS, STARTUP_POLICIES
from .runtime.matrix_inputs import fingerprint, load_binary, preflight_inputs, slot_id

MANIFEST_SHA256 = "316438458c537adfd6b3347a8387844c95ac806d2067365fdc0d72abe2b3992c"
US_REFERENCES = {
    "us_hybrid_1002fdc9826fc6d1": "105a45498ea7edf1d92e2664814b1b94b93f772209cf36ff233c950895ed0828",
    "us_smart_negative_world_739e0513c6f7cfe8": "a4aa356dbd348f50154dd38272518f0819084eeb1112f23b4e48be4f6e071859",
}


def enumerate_slots(scenes):
    slots = []
    seen = set()
    for scene in sorted(scenes, key=lambda scene: scene["name"]):
        name = scene["name"]
        if name in seen:
            raise ValueError(f"duplicate scene identity: {name}")
        seen.add(name)
        for ego, traffic, startup in product(CONTROLLERS, CONTROLLERS, STARTUP_POLICIES):
            if traffic == "expert" and startup == "source_hold":
                continue
            problem = scene.get("binary_problem")
            if startup == "source_hold":
                problem = problem or scene["source_hold_problem"]
            slots.append({
                "slot_id": slot_id(name, ego, traffic, startup),
                "scene": name, "group": scene["group"],
                "ego": ego, "traffic": traffic, "startup": startup,
                "status": "blocked" if problem else "not_run", "reason": problem,
            })
    return slots


def _verify_fingerprint(entry):
    path = resolve_reference(entry["reference"])
    if sha256(path) != entry["sha256"]:
        raise ValueError(f"input hash mismatch: {entry['reference']}")


def _german_scene(row):
    root = resolve_reference(row["root"])
    gate = root / "testing/admission_smart_hybrid_startup.json"
    admission = fingerprint(gate)
    if admission["sha256"] != row["admission_sha256"]:
        raise ValueError(f"admission hash mismatch: {root}")
    record = read_json(gate)
    contract = record["contract"]
    if (row["name"] != root.name or not record["research_admitted"]
            or contract["scene_reference"] != row["root"]
            or any(row[k] != contract[k] for k in ("ego_track_id", "ego_binary_index", "recording"))):
        raise ValueError(f"unexpected German scene identity: {root}")
    inputs = {k: v for k, v in contract["files"].items()
              if k.startswith(("source_", "scene_"))}
    for key, entry in inputs.items():
        inputs[key] = {"reference": entry["reference"], "sha256": entry["sha256"]}
        _verify_fingerprint(entry)
    for field, key in (
        ("binary_sha256", "scene_binary"), ("source_tracks_sha256", "source_tracks_csv"),
        ("source_map_sha256", "source_lanelet2_map"), ("source_background_sha256", "source_background_image"),
    ):
        if row[field] != inputs[key]["sha256"]:
            raise ValueError(f"manifest disagreement for {root}: {field}")
    scene = _scene(row["name"], root, row["binary_sha256"], "german")
    if scene.get("binary_problem"):
        raise ValueError(scene["binary_problem"])
    return {**scene, "protected_inputs": inputs, "original_source_admission": admission}


def _scene(name, root, expected, group):
    scene = {"name": name, "root": reference(root), "group": group,
             "expected_binary_sha256": expected}
    try:
        inputs, problem = preflight_inputs(root, name, expected, 91, check_source_hold=True)
        binary = load_binary(root)
    except (ValueError, OSError) as exc:
        return {**scene, "binary_problem": str(exc), "source_hold_problem": None}
    ego = int(binary["sdc_track_index"])
    return {**scene, "inputs": inputs, "source_hold_problem": problem,
            "ego_binary_index": ego, "ego_source_id": int(binary["objects"][ego]["id"])}


def build_matrix():
    s = settings()
    manifest = s.project / "configs/current_manifest.json"
    pinned = fingerprint(manifest)
    if pinned["sha256"] != MANIFEST_SHA256:
        raise ValueError(f"unexpected portable manifest hash: {manifest}")
    payload = read_json(manifest)
    rows = payload["scenes"]
    if payload["schema_version"] != 2 or len(rows) != 16 or len({r["name"] for r in rows}) != 16:
        raise ValueError("expected 16 unique German scenes in the portable manifest")
    scenes = [_german_scene(row) for row in rows]
    scenes.extend(_scene(name, s.artifacts / "probes" / name, digest, "us")
                  for name, digest in US_REFERENCES.items())
    return {"schema_version": 1, "manifest": pinned, "scenes": scenes,
            "slots": enumerate_slots(scenes)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    write_json(args.output, build_matrix())


if __name__ == "__main__":
    main()
