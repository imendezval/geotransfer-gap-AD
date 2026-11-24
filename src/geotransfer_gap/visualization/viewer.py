"""Self-contained, offline source/expert/planner playback. Never grants admission."""

import argparse
import base64
import csv
import html
import json
import math
from pathlib import Path
import webbrowser
from geotransfer_gap.config import settings
from geotransfer_gap.artifacts import (
    atomic_write_text,
    protected_input_paths,
    saved_evidence_ancestor,
    scene_root,
    read_json,
    sha256,
    reference,
    read_manifest,
)
from geotransfer_gap.runtime.trace_io import iter_frames, read_playback


def source_frames(root):
    """Independent CSV sampling for visual comparison, without simulator/model imports."""
    import numpy as np

    t = root / "testing"
    scene_file = next(t.glob("ind_*.json"), None)
    if scene_file is None:
        raise FileNotFoundError("Authoritative source scene JSON unavailable")
    scene = read_json(scene_file)
    validation = read_json(t / "validation.json")
    tracks = {int(o["id"]): [] for o in scene["objects"]}
    path = settings().source / f"data/{validation['recording']:02d}_tracks.csv"
    with path.open() as stream:
        for row in csv.DictReader(stream):
            if int(row["trackId"]) in tracks:
                tracks[int(row["trackId"])].append(row)
    frames = []
    for step in range(91):
        sample = validation["first_frame"] + 2.5 * step
        actors = []
        for i, obj in enumerate(scene["objects"]):
            rows = tracks[int(obj["id"])]
            f = np.array([float(r["frame"]) for r in rows])
            idx = np.searchsorted(f, sample)
            valid = bool(len(f) and f[0] <= sample <= f[-1])
            if (
                valid
                and 0 < idx < len(f)
                and (f[idx] != sample)
                and (f[idx] - f[idx - 1] > 1)
            ):
                valid = False

            def value(key):
                return (
                    float(np.interp(sample, f, [float(r[key]) for r in rows]))
                    if valid
                    else None
                )

            heading = (
                float(
                    np.interp(
                        sample,
                        f,
                        np.unwrap(np.deg2rad([float(r["heading"]) for r in rows])),
                    )
                )
                if valid
                else 0
            )
            actors.append(
                dict(
                    id=obj["id"],
                    binary_index=i,
                    type=obj["type"],
                    present=valid,
                    x=value("xCenter"),
                    y=value("yCenter"),
                    heading=heading,
                    length=obj["length"],
                    width=obj["width"],
                    dimension_imputed=obj.get("dimension_imputed", False),
                    collision_state=0,
                    removed=False,
                )
            )
        frames.append(dict(step=step, time_s=step * 0.1, actors=actors))
    return (scene, frames, sha256(path))


def _owner_label(actor):
    declared = actor.get("declared_controller")
    owner = actor.get("effective_owner")
    target = f"{declared.upper()} target / " if declared else ""
    labels = {
        "source_hold_replay": "expert replay (source hold)",
        "warmup_replay": "expert replay (warmup)",
        "context_replay": "expert replay (context)",
        "inactive_replay_mode": "replay mode (inactive slot)",
        "not_present": "not present",
    }
    if owner in labels:
        return target + labels[owner]
    if owner and ":" in owner:
        role, controller = owner.split(":", 1)
        return f"{controller.upper()} ({role})"
    return "not recorded"


def _actor_events(actor, previous, tick):
    events = []
    if actor.get("source_valid") is False and previous.get("source_valid") is True:
        events.append("source gap")
    if actor.get("present") and not previous.get("present"):
        generation = actor.get("lifetime_generation")
        if generation is not None and generation > 0:
            events.append("re-entry")
        elif tick > 0:
            events.append("birth / became present")
    if previous.get("present") and not actor.get("present"):
        events.append("exit / became absent")
    if actor.get("actual_release_step") == tick:
        events.append(f"released at step {tick}")
    if actor.get("removed") and not previous.get("removed"):
        events.append("native removal")
    collision = actor.get("collision_state")
    if collision and collision != previous.get("collision_state"):
        events.append({1: "collision", 2: "off-road"}.get(collision, f"collision state {collision}"))
    if actor.get("reached_goal") and not previous.get("reached_goal"):
        events.append("goal")
    return events


def normalize_trace(report, verification=None, diagnostic=None):
    """Project legacy and matrix traces into the same display-only frame layout."""
    evidence = verification or {}
    ego_index = report.get("ego_binary_index")
    planner = report.get("planner", "not recorded")
    matrix = planner == "controller_matrix"
    ego = report.get("ego_controller", planner if planner in {"expert", "smart"} else None)
    traffic = report.get("traffic_controller", "expert" if planner == "expert" else None)
    startup = report.get("traffic_startup", report.get("traffic_protocol"))
    name = f"{ego} / {traffic} / {startup}" if matrix else f"{planner} evaluator rollout"
    timeline = {f["step"]: f for f in (diagnostic or {}).get("timeline", [])}
    frames, previous = [], {}
    ego_id = None
    for frame in iter_frames(report, evidence):
        tick = frame["step"]
        for actor in frame["actors"]:
            sid = actor["id"]
            if ego_index is not None and actor.get("binary_index") == ego_index:
                ego_id = sid
                if not matrix and "action" in timeline.get(tick, {}):
                    actor["action"] = timeline[tick]["action"]
            actor["owner_label"] = _owner_label(actor)
            actor["events"] = _actor_events(actor, previous.get(sid, {}), tick)
        previous = {actor["id"]: actor for actor in frame["actors"]}
        frames.append(frame)
    return {
        "name": name, "ego_id": ego_id, "ego_binary_index": ego_index, "frames": frames,
        "config": {"ego": ego, "traffic": traffic, "startup": startup},
        "terminal_reason": report.get("terminal_reason"),
        "diagnostic_only": evidence.get("diagnostic_only", report.get("diagnostic_only",
                              (diagnostic or {}).get("diagnostic_only"))),
        "research_admission": evidence.get("controller_pair_research_admission",
                                           "not_established" if matrix else None),
        "original_source_admission": evidence.get("original_source_admission"),
        "provenance": {k: v for k, v in report.items() if k != "frames"},
    }


def binary_roads(root):
    """Use recorded binary coordinates, which are also the trace world frame."""
    from geotransfer_gap.runtime.matrix_inputs import load_binary

    return [
        {"type": road["type"], "geometry": [{"x": float(x), "y": float(y)}
                                           for x, y in zip(road["polyline_x"], road["polyline_y"], strict=True)]}
        for road in load_binary(root)["roads"]
    ]


def _load_playback(path, digest, expected):
    return _normalize_playback(read_playback(path, digest, expected))


def _normalize_playback(saved):
    run = normalize_trace(saved.report, saved.verification, saved.diagnostic)
    run["trace_sha256"] = saved.hashes["trace"]
    return run


def _evaluation_records(paths):
    """Read PE09 indexed records through its saved-result/hash boundary."""
    if not paths:
        return []
    from geotransfer_gap.evaluation.reporting import read_indexed_evaluation

    loaded, seen = [], set()
    for value in paths:
        root = Path(value).expanduser().resolve()
        if root in seen:
            continue
        seen.add(root)
        _, index, indexed = read_indexed_evaluation(root)
        loaded.extend(_indexed_attachments(root, index, indexed))
    return loaded


def _indexed_attachments(root, index, indexed):
    profile = index.get("profile")
    if (not isinstance(profile, dict)
            or not all(isinstance(profile.get(key), str) and profile[key]
                       for key in ("raw_sha256", "effective_sha256", "definition_version"))):
        raise ValueError(f"Saved evaluation profile identity is malformed: {root}")
    if any(len(profile[key]) != 64 or any(char not in "0123456789abcdef" for char in profile[key])
           for key in ("raw_sha256", "effective_sha256")):
        raise ValueError(f"Saved evaluation profile hashes are malformed: {root}")
    for entry in index["episodes"]:
        result, events = indexed[entry["episode_id"]]
        if not isinstance(result.get("protocol"), dict):
            raise ValueError("Saved evaluation protocol identity is malformed")
        evidence = result.get("evidence", {})
        if entry.get("trace_sha256") != evidence.get("trace_sha256"):
            raise ValueError("Saved evaluation trace binding disagrees with its index")
        input_profile = result.get("input_profile", {})
        if (input_profile.get("raw_sha256") != profile["raw_sha256"]
                or input_profile.get("effective_sha256") != profile["effective_sha256"]):
            raise ValueError("Saved evaluation profile disagrees with its indexed profile")
        episode_metrics = result.get("episode_metrics")
        if episode_metrics is not None:
            if (not isinstance(episode_metrics.get("input"), dict)
                    or not isinstance(episode_metrics["input"].get("evidence_sha256", {}), dict)
                    or not isinstance(episode_metrics.get("evaluator"), dict)
                    or not isinstance(episode_metrics.get("metrics", []), list)
                    or any(not isinstance(metric, dict)
                           for metric in episode_metrics.get("metrics", []))):
                raise ValueError("Saved episode metrics contain malformed profile or metric records")
            evaluator = episode_metrics.get("evaluator", {})
            if (evaluator.get("effective_profile_sha256") != profile["effective_sha256"]
                    or evaluator.get("definition_version") != profile["definition_version"]):
                raise ValueError("Saved metric profile/version disagrees with its indexed profile")
        yield {
            "directory": str(root), "profile": profile, "entry": entry,
            "result": result, "events": events,
        }


def _trace_protocol(run):
    report = run["provenance"]
    planner = report.get("planner")
    return {
        "ego": report.get("ego_controller") or (planner if planner in {"expert", "smart"} else None),
        "traffic": report.get("traffic_controller"),
        "startup": report.get("traffic_startup", report.get("traffic_protocol")),
    }


def _evaluated_run(item, root, digest, detached_bindings):
    """Resolve a playback from the exact trace and sidecars used by a saved result."""
    result, entry = item["result"], item["entry"]
    evidence = result["evidence"]
    trace_path = evidence.get("trace_path")
    if trace_path != entry.get("trace_path"):
        raise ValueError("Saved evaluation trace path disagrees with its index")
    if not trace_path:
        raise FileNotFoundError("No saved trace was recorded")
    trace = Path(trace_path)
    if not trace.is_absolute():
        raise ValueError("Saved evaluation trace path must be absolute")
    if not trace.is_file():
        raise FileNotFoundError(f"Saved trace is missing: {trace}")
    inputs = (result.get("episode_metrics") or {}).get("input") or {}
    hashes = inputs.get("evidence_sha256", {})
    expected = None
    if evidence.get("level") == "archived_attested" and "attempt" not in hashes:
        expected = detached_bindings.get(trace.parent)
        if expected is None or not {"trace", "provenance"} <= expected.keys():
            raise ValueError("Archived trace is missing its saved evidence binding")
    saved = read_playback(trace, digest, expected, verify_all_files=True)
    if saved.hashes.get("trace") != evidence.get("trace_sha256"):
        raise ValueError("Saved trace hash differs from the evaluated trace")
    if saved.hashes != {**hashes, "trace": evidence["trace_sha256"]}:
        raise ValueError("Saved trace sidecars differ from the evaluated evidence")
    run = _normalize_playback(saved)
    run["evaluation"] = _bind_evaluation(run, root.name, digest, [item])
    return run, saved.files.values()


def _bind_evaluation(run, scene_name, binary_digest, records, campaign_status=None):
    matches, stale = [], False
    protocol = _trace_protocol(run)
    for item in records:
        result = item["result"]
        recorded_protocol = result.get("protocol") or {}
        protocol_agrees = all(value is None or value == protocol[key]
                              for key, value in recorded_protocol.items()
                              if key in protocol)
        same_scene_protocol = result.get("scene_id") == scene_name and protocol_agrees
        if item["entry"].get("trace_sha256") != run.get("trace_sha256"):
            stale = stale or same_scene_protocol
            continue
        if not same_scene_protocol:
            raise ValueError("Saved evaluation scene/protocol identity differs from the exact trace")
        episode = result.get("episode_metrics")
        if episode is not None:
            identity = episode.get("input", {})
            metric_protocol = identity.get("protocol", {})
            report = run["provenance"]
            recorded_fields = (
                ("ego_controller", "ego"), ("traffic_controller", "traffic"),
                ("traffic_startup", "startup"),
            )
            protocol_fields_agree = all(
                metric_protocol.get(field) is None or metric_protocol.get(field) == protocol[key]
                for field, key in recorded_fields
            )
            legacy_startup = identity.get("traffic_protocol")
            if legacy_startup is None and isinstance(identity.get("startup_policy"), str):
                legacy_startup = identity["startup_policy"]
            legacy_agrees = legacy_startup is None or legacy_startup == protocol["startup"]
            if (identity.get("trace_sha256") != run.get("trace_sha256")
                    or identity.get("binary_sha256") != binary_digest
                    or identity.get("scene") != report.get("scene")
                    or not protocol_fields_agree or not legacy_agrees):
                raise ValueError("Saved metric trace/scene/protocol identity differs from playback")
        matches.append(item)

    campaign = {
        "status": campaign_status,
        "meaning": "integration/parity only; independent of driving outcome"
        if campaign_status == "PASS" else "integration/parity status",
    }
    if not matches:
        return {
            "status": "stale" if stale else "unavailable",
            "reason": ("Saved evaluation for this scene/protocol has a different trace hash; ignored."
                       if stale else "No saved evaluation is attached to this trace."),
            "campaign": campaign,
        }

    profiles = {(row["profile"]["effective_sha256"], row["profile"]["definition_version"])
                for row in matches}
    result_hashes = {row["entry"]["result_sha256"] for row in matches}
    event_hashes = {row["entry"]["events_sha256"] for row in matches}
    if len(profiles) != 1:
        return {"status": "conflict", "reason": "Matching results use conflicting metric profiles/versions; metrics suppressed.",
                "profiles": sorted({f"{effective} / {version}" for effective, version in profiles}),
                "campaign": campaign}
    if len(result_hashes) != 1 or len(event_hashes) != 1:
        return {"status": "conflict", "reason": "Different saved result/event records match this trace; metrics suppressed.",
                "campaign": campaign}

    row = matches[0]
    result = row["result"]
    metrics = []
    episode = result.get("episode_metrics") or {}
    for metric in episode.get("metrics", []):
        value = metric.get("value")
        # Samples remain in the indexed result; playback shows only stored summaries.
        if isinstance(value, dict):
            value = {key: item for key, item in value.items()
                     if not (isinstance(item, list) and key in {
                         "samples", "series", "records", "pair_samples", "overlap_samples", "onsets",
                     })}
        metrics.append({key: metric.get(key) for key in (
            "metric_id", "definition_version", "status", "reason", "criterion_outcome",
            "units", "eligible_samples", "eligible_duration_s", "window", "limitations",
        )} | {"value": value})
    events = []
    observed_steps = {frame["step"] for frame in run["frames"]}
    for event in row["events"]:
        event_time = event.get("time_s") if isinstance(event, dict) else None
        if (not isinstance(event, dict) or type(event.get("step")) is not int
                or event["step"] not in observed_steps
                or event_time is not None and
                (type(event_time) not in (int, float) or not math.isfinite(event_time))):
            raise ValueError("Saved evaluation contains a malformed event record")
        actor = event.get("actor")
        refs = []
        if isinstance(actor, dict) and type(actor.get("source_id")) is int:
            refs.append({"source_id": actor["source_id"],
                         "lifetime_generation": actor.get("lifetime_generation")})
        collision = event.get("collision_details")
        if isinstance(collision, dict) and type(collision.get("partner_source_id")) is int:
            refs.append({"source_id": collision["partner_source_id"],
                         "lifetime_generation": collision.get("partner_lifetime_generation")})
        events.append({key: event.get(key) for key in (
            "event_id", "channel", "observation", "attribution", "step", "time_s",
            "pose_present", "terminal_reason", "evidence", "cause_established",
        )} | {"actor_refs": refs})
    account = result.get("accounting", {})
    exposure = episode.get("exposure", {})
    if isinstance(exposure.get("windows"), dict):
        exposure = exposure["windows"].get("full") or {}
    return {
        "status": "attached", "episode_id": result.get("episode_id"),
        "scene_id": result.get("scene_id"), "protocol": result.get("protocol"),
        "profile": {key: row["profile"].get(key) for key in
                    ("raw_sha256", "effective_sha256", "definition_version")},
        "source": {
            "index": str(Path(row["directory"]) / "index.json"),
            "result_file": row["entry"]["result_file"],
            "result_sha256": row["entry"]["result_sha256"],
            "events_file": row["entry"]["events_file"],
            "events_sha256": row["entry"]["events_sha256"],
        },
        "evidence": result.get("evidence"),
        "execution_status": account.get("execution_status"),
        "campaign": {**campaign, "status": account.get("campaign_status") or campaign_status},
        "metric_validity": result.get("metric_validity"),
        "task_result": result.get("task_result"),
        "encounter_result": result.get("encounter_result"),
        "driving_outcome": result.get("driving_outcome"),
        "exposure": exposure,
        "limitations": list(episode.get("limitations", []))
        + list(episode.get("context_limitations", []))
        + list(result.get("event_accounting", {}).get("limitations", [])),
        "event_status": result.get("event_accounting", {}).get("status", "unavailable"),
        "events": events, "metrics": metrics,
    }


def _check_output(output, *, evaluations=(), campaign=None, inputs=(),
                  directory=None):
    output = Path(output).expanduser()
    target = output.resolve()
    if campaign is not None and target.is_relative_to(campaign):
        raise ValueError("Choose a viewer output outside the saved campaign")
    for evaluation in evaluations:
        if target.is_relative_to(Path(evaluation).expanduser().resolve()):
            raise ValueError("Choose a viewer output outside attached evaluation evidence")
    cfg = settings()
    for root in (*protected_input_paths(cfg), *inputs):
        if target.is_relative_to(Path(root).resolve()):
            raise ValueError(f"Viewer output overlaps protected input: {root}")
    if (ancestor := saved_evidence_ancestor(target, cfg.runs)) is not None:
        raise ValueError(f"Viewer output is nested in an existing run/evidence directory: {ancestor}")
    if output.is_symlink() or (directory is not None and target.parent != directory.resolve()):
        raise ValueError(f"Viewer page escapes its output directory: {output}")
    return target


def _page_path(directory, name):
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValueError(f"Invalid viewer page name: {name!r}")
    return directory / f"{name}.html"


def view_payload(root, traces=(), *, files_by_trace=None, evaluations=(),
                 campaign_status_by_trace=None):
    t = root / "testing"
    digest = sha256(t / "map_000000.bin")
    files_by_trace = files_by_trace or {}
    runs = [_load_playback(path, digest, files_by_trace.get(path)) for path in traces]
    evaluation_records = _evaluation_records(evaluations)
    campaign_status_by_trace = campaign_status_by_trace or {}
    for path, run in zip(traces, runs, strict=True):
        run["evaluation"] = _bind_evaluation(
            run, root.name, digest, evaluation_records,
            campaign_status_by_trace.get(path),
        )

    return _scene_payload(root, digest, runs)


def _scene_payload(root, digest, runs):
    t = root / "testing"
    source_hash = registration = image = goal = None
    limitations = []
    source = converted = []
    ego_id = next((run["ego_id"] for run in runs if run["ego_id"] is not None), None)
    try:
        scene, source, source_hash = source_frames(root)
    except FileNotFoundError:
        limitations.append("Source trajectory comparison unavailable")
        roads = binary_roads(root)
    else:
        roads = scene["roads"]
        ego_index = int(scene["metadata"]["sdc_track_index"])
        ego = scene["objects"][ego_index]
        ego_id, goal = ego["id"], ego["goalPosition"]
        converted = [
            dict(
                step=i, time_s=i * 0.1,
                actors=[
                    dict(id=o["id"], binary_index=index, type=o["type"], present=bool(o["valid"][i]),
                         x=o["position"][i]["x"], y=o["position"][i]["y"], heading=o["heading"][i],
                         length=o["length"], width=o["width"])
                    for index, o in enumerate(scene["objects"])
                ],
            )
            for i in range(len(ego["valid"]))
        ]
        registration_path = t / "source_image_registration.json"
        if registration_path.is_file():
            v = read_json(t / "validation.json")
            image_path = settings().source / f"data/{v['recording']:02d}_background.png"
            if image_path.is_file():
                registration = read_json(registration_path)
                image = "data:image/png;base64," + base64.b64encode(image_path.read_bytes()).decode()
    if image is None:
        limitations.append("Registered source imagery unavailable")
    if not roads:
        limitations.append("Map geometry unavailable")
    return dict(
        scene=root.name, ego_id=ego_id, goal=goal, roads=roads, source=source,
        converted=converted, runs=runs, registration=registration, image=image, limitations=limitations,
        provenance=dict(
            schema_version=2, scene=reference(root), binary_sha256=digest, source_tracks_sha256=source_hash,
            notice="Diagnostic playback. Viewer output does not establish research admission or encounter preservation.",
        ),
    )


def build(root, output, traces=(), *, files_by_trace=None, evaluations=(),
          campaign_status_by_trace=None):
    root = scene_root(str(root))
    traces = tuple(traces)
    target = _check_output(output, evaluations=evaluations, inputs=(root, *traces))
    payload = view_payload(root, traces, files_by_trace=files_by_trace,
                           evaluations=evaluations, campaign_status_by_trace=campaign_status_by_trace)
    _write_playback(target, payload)
    return Path(output)


def _write_playback(output, payload):
    encoded = json.dumps(payload, allow_nan=False).replace("</", "<\\/")
    output.parent.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).with_name("viewer.html").read_text()
    atomic_write_text(output, template.replace("__DATA__", encoded))


def main(argv=None):
    from geotransfer_gap.execution import CONTROLLERS, STARTUP_POLICIES

    ap = argparse.ArgumentParser(__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--manifest", type=Path)
    g.add_argument("--campaign", type=Path, help="Render a saved matrix campaign under runs")
    ap.add_argument("--scene", help="Scene ID or root (scene ID when filtering a campaign)")
    ap.add_argument("--ego", choices=CONTROLLERS, help="Filter saved campaign traces")
    ap.add_argument("--traffic", choices=CONTROLLERS, help="Filter saved campaign traces")
    ap.add_argument("--traffic-startup", choices=STARTUP_POLICIES, help="Filter saved campaign traces")
    ap.add_argument("--trace", type=Path, action="append", default=[])
    ap.add_argument("--evaluation", type=Path, action="append", default=[],
                    help="Select one saved indexed evaluation, or attach evaluations to an explicit view")
    ap.add_argument("--output", type=Path)
    ap.add_argument(
        "--run",
        choices=["expert", "smart", "both"],
        help="Explicitly create fresh canonical traces before rendering",
    )
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args(argv)
    evaluation_only = bool(args.evaluation and not (args.campaign or args.scene or args.manifest))
    if args.campaign:
        if args.trace or args.run:
            ap.error("--campaign uses its saved traces and cannot be combined with --trace or --run")
        from geotransfer_gap.visualization.campaign_gallery import render_campaign

        destination = args.output
        if destination is None:
            destination = settings().runs / "views" / args.campaign.resolve().name
            filters = args.ego, args.traffic, args.traffic_startup
            if args.scene or any(filters):
                selection = "__".join(value or "all" for value in filters)
                destination = destination / "selections" / selection
    elif evaluation_only:
        if args.trace or args.run or args.ego or args.traffic or args.traffic_startup:
            ap.error("Use --scene or --manifest for explicit traces or a fresh run, or --campaign for filters")
        if len(args.evaluation) != 1:
            ap.error("Evaluation-only viewing requires exactly one --evaluation directory")
    if args.campaign or evaluation_only:
        try:
            if args.campaign:
                index = render_campaign(args.campaign, destination, scene=args.scene, ego=args.ego,
                                        traffic=args.traffic, startup=args.traffic_startup,
                                        evaluations=args.evaluation)
            else:
                from geotransfer_gap.visualization.campaign_gallery import render_evaluation

                index = render_evaluation(args.evaluation[0], args.output)
        except (OSError, ValueError) as exc:
            ap.error(str(exc))
        print(index, flush=True)
        if args.open:
            webbrowser.open(index.resolve().as_uri())
        return index
    if bool(args.manifest) == bool(args.scene):
        ap.error("Specify --scene, --manifest, --campaign, or --evaluation")
    if args.ego or args.traffic or args.traffic_startup:
        ap.error("Controller filters require --campaign")
    destination = (args.output or settings().runs / "views").expanduser()
    selected_scene = scene_root(args.scene) if args.scene else None
    rows = (
        [{"name": selected_scene.name, "root": str(selected_scene)}]
        if selected_scene is not None
        else read_manifest(args.manifest)
    )
    checks = {"evaluations": args.evaluation,
              "inputs": [row["root"] for row in rows] + args.trace}
    if args.manifest:
        checks["inputs"].append(args.manifest)
    try:
        _check_output(destination, **checks)
        links = [
            _check_output(destination, **checks)
            if args.scene and destination.suffix == ".html" else
            _check_output(_page_path(destination, row["name"]), directory=destination, **checks)
            for row in rows
        ]
        index = (_check_output(destination / "index.html", directory=destination, **checks)
                 if args.manifest else links[0])
        if len(set(links)) != len(links) or args.manifest and index in links:
            raise ValueError("Scene gallery pages resolve to the same output path")
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    for row, output in zip(rows, links, strict=True):
        traces = list(args.trace)
        if args.run:
            from geotransfer_gap.execution import main as execute

            for planner in ["expert", "smart"] if args.run == "both" else [args.run]:
                run = execute(["--scene", row["root"], "--planner", planner])
                traces.append(run / row["name"] / "trace.json")
        build(row["root"], output, traces, evaluations=args.evaluation)
        print(output, flush=True)
    if args.manifest:
        destination.mkdir(parents=True, exist_ok=True)
        atomic_write_text(index,
            '<!doctype html><meta charset="utf-8"><title>GeoTransfer scenes</title><h1>Admitted scene gallery</h1><ul>'
            + "".join(
                (
                    '<li><a href="'
                    + html.escape(p.name)
                    + '">'
                    + html.escape(p.stem)
                    + "</a></li>"
                    for p in links
                )
            )
            + "</ul>"
        )
    if args.open:
        webbrowser.open(index.resolve().as_uri())
