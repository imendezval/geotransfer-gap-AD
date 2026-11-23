"""Lazy command handlers for offline saved-evidence evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from geotransfer_gap.artifacts import reference, resolve_reference, scene_root, sha256, write_json
from geotransfer_gap.config import settings
from geotransfer_gap.evaluation.episode import evaluate_episode
from geotransfer_gap.evaluation.profile import load_profile


def _overlaps(left, right):
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _output_path(output, trace, profile_path, selected_scene):
    cfg = settings()
    runs = cfg.runs.resolve()
    destination = Path(output).expanduser().resolve()
    if destination == runs or not destination.is_relative_to(runs):
        raise ValueError(f"Evaluation output must be beneath configured runs: {runs}")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite evaluation output: {destination}")
    protected = (cfg.source.resolve(), cfg.artifacts.resolve(), cfg.bench.resolve(),
                 cfg.reference_data.resolve())
    for root in protected:
        if _overlaps(destination, root):
            raise ValueError(f"Evaluation output overlaps protected input root: {root}")
    input_paths = [Path(trace).expanduser().resolve(), Path(profile_path).expanduser().resolve()]
    for suffix in ("verification.json", "diagnostic.json", "attempt.json"):
        sidecar = input_paths[0].with_name(suffix)
        if sidecar.is_file():
            input_paths.append(sidecar.resolve())
    if selected_scene is not None:
        input_paths.append(selected_scene.resolve())
    for source in input_paths:
        if _overlaps(destination, source):
            raise ValueError(f"Evaluation output overlaps supplied input: {source}")
        if (source.is_file() and source.parent.is_relative_to(runs)
                and source.parent != runs and destination.is_relative_to(source.parent)):
            raise ValueError(f"Evaluation output must not be inside a saved run input directory: {source.parent}")
    # A fresh child of a saved run/campaign directory still overlaps that
    # archived evidence context even if the trace was selected elsewhere.
    ancestor = destination.parent
    while ancestor.is_relative_to(runs):
        if ancestor != runs and any((ancestor / marker).is_file() for marker in
                                    ("trace.json", "attempt.json", "verification.json",
                                     "campaign.json", "campaign_report.json", "report.json",
                                     "run.json", "manifest.json", "matrix.json", "inventory.json",
                                     "ledger.json")):
            raise ValueError(f"Evaluation output is nested in an existing run/evidence directory: {ancestor}")
        if ancestor == runs:
            break
        ancestor = ancestor.parent
    return destination


def _scene_context(selection, report):
    if selection is None:
        return None, None
    selected_root = scene_root(selection).resolve()
    recorded = report.get("scene")
    if not isinstance(recorded, dict):
        raise ValueError("Selected scene cannot be checked because this trace has no scene identity")
    recorded_root = resolve_reference(recorded).resolve()
    if selected_root != recorded_root:
        raise ValueError("Selected scene root differs from the saved trace identity")
    binary = selected_root / "testing" / "map_000000.bin"
    if not binary.is_file():
        raise ValueError(f"Selected scene has no evaluation binary: {binary}")
    digest = sha256(binary)
    if digest != report.get("binary_sha256"):
        raise ValueError("Selected scene binary differs from the saved trace identity")
    try:
        portable = reference(selected_root)
    except ValueError:
        portable = None
    return selected_root, {"selection": str(selection), "root": portable,
                           "binary_sha256": digest, "status": "scene_and_binary_identity_checked"}


def _episode(args):
    trace = Path(args.trace).expanduser().resolve()
    if not trace.is_file():
        raise FileNotFoundError(f"Saved trace does not exist: {trace}")
    from geotransfer_gap.runtime.trace_io import load_saved_trace

    saved = load_saved_trace(trace)
    selected_root, scene_info = _scene_context(args.scene, saved.playback.report)
    profile_path = args.profile or settings().project / "configs/evaluation/default.toml"
    destination = _output_path(args.output, trace, profile_path, selected_root)
    profile = load_profile(profile_path)
    result, events = evaluate_episode(saved, profile, scene=scene_info)
    result["input"]["trace_filename"] = trace.name
    destination.mkdir(parents=True, exist_ok=False)
    if events:
        event_path = destination / "events.json"
        write_json(event_path, {"schema_version": 1, "events": events})
        result["observed_events"]["sha256"] = sha256(event_path)
    else:
        result["observed_events"]["sha256"] = None
    write_json(destination / "episode.json", result)
    print(json.dumps({"episode": str(destination / "episode.json"),
                      "events": str(destination / "events.json") if events else None,
                      "trace_sha256": result["input"]["trace_sha256"],
                      "evidence_level": result["input"]["evidence_level"]}, indent=2))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser("geotransfer evaluate")
    sub = parser.add_subparsers(dest="action", required=True)
    episode = sub.add_parser("episode", help="measure one existing saved trace")
    episode.add_argument("--trace", required=True, type=Path)
    episode.add_argument("--output", required=True, type=Path)
    episode.add_argument("--profile", type=Path)
    episode.add_argument("--scene", help="scene ID or scene root for identity checking")
    args = parser.parse_args(argv)
    if args.action == "episode":
        return _episode(args)
    parser.error("unsupported evaluation action")
