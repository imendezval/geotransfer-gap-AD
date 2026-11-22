"""Self-contained, offline source/expert/planner playback. Never grants admission."""

import argparse
import base64
import csv
import html
import json
from pathlib import Path
import webbrowser
from geotransfer_gap.config import settings
from geotransfer_gap.artifacts import (
    scene_root,
    read_json,
    sha256,
    reference,
    read_manifest,
)


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
    life = {f["step"]: {a["source_id"]: a for a in f["actors"]} for f in evidence.get("lifecycle", [])}
    timeline = {f["step"]: f for f in (diagnostic or {}).get("timeline", [])}
    frames, previous = [], {}
    ego_id = None
    for record in report["frames"]:
        state = record["state"] if matrix else record
        tick = record["step"]
        assignments = {a["source_id"]: a for a in record["actors"]} if matrix else {}
        actors = []
        for raw in state["actors"]:
            sid = raw["id"]
            assignment = assignments.get(sid, {})
            actor = {**raw, **life.get(tick, {}).get(sid, {}), **assignment}
            actor.setdefault("lifetime_generation", None)
            actor.setdefault("action", None)
            if ego_index is not None and raw.get("binary_index") == ego_index:
                ego_id = sid
                if not matrix and "action" in timeline.get(tick, {}):
                    actor["action"] = timeline[tick]["action"]
            actor["owner_label"] = _owner_label(actor)
            actor["events"] = _actor_events(actor, previous.get(sid, {}), tick)
            actors.append(actor)
        previous = {actor["id"]: actor for actor in actors}
        frames.append({**state, "actors": actors, "transition_applied": record.get("transition_applied")})
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


def _check_playback_hashes(trace, verification, expected):
    attempt_path = trace.with_name("attempt.json")
    if attempt_path.is_file():
        attempt = read_json(attempt_path)
        recorded = (attempt.get("evidence") or {}).get("files")
        if attempt.get("status") == "passed" and not recorded:
            raise ValueError(f"Passed attempt has no playback hashes: {attempt_path}")
        if recorded is not None:
            if expected is not None and any(expected.get(kind) != recorded.get(kind)
                                            for kind in ("trace", "provenance")):
                raise ValueError(f"Campaign and attempt playback hashes disagree: {attempt_path}")
            expected = recorded
    if expected is not None:
        for kind, path in (("trace", trace), ("provenance", verification)):
            entry = expected.get(kind, {})
            if (entry.get("path") != path.name or not path.is_file()
                    or sha256(path) != entry.get("sha256")):
                raise ValueError(f"Playback hash or file differs from saved evidence: {path}")


def _load_playback(path, digest, expected):
    verification = path.with_name("verification.json")
    _check_playback_hashes(path, verification, expected)
    report = read_json(path)
    if report["binary_sha256"] != digest:
        raise ValueError("Trace binary differs from viewed scene")
    evidence = read_json(verification) if verification.is_file() else None
    if evidence is not None:
        fields = (("scene", "scene"), ("ego", "ego_controller"), ("traffic", "traffic_controller"),
                  ("startup", "traffic_startup"), ("driving_outcome", "terminal_reason"))
        if (report["planner"] != "controller_matrix"
                or evidence.get("inputs", {}).get("binary", {}).get("sha256") != digest
                or any(evidence.get(sidecar) != report.get(trace) for sidecar, trace in fields)
                or ("lifecycle" in evidence and [row["step"] for row in evidence["lifecycle"]]
                    != [frame["step"] for frame in report["frames"]])):
            raise ValueError(f"Verification sidecar differs from viewed trace: {verification}")
    diagnostic_path = path.with_name("diagnostic.json")
    diagnostic = read_json(diagnostic_path) if diagnostic_path.is_file() else None
    if diagnostic is not None:
        if diagnostic.get("binary_sha256") != digest:
            raise ValueError("Diagnostic binary differs from viewed scene")
        if ("traffic_protocol" in diagnostic and "traffic_protocol" in report
                and diagnostic["traffic_protocol"] != report["traffic_protocol"]):
            raise ValueError("Diagnostic traffic protocol differs from viewed trace")
    return normalize_trace(report, evidence, diagnostic)


def view_payload(root, traces=(), *, files_by_trace=None):
    t = root / "testing"
    digest = sha256(t / "map_000000.bin")
    files_by_trace = files_by_trace or {}
    runs = [_load_playback(path, digest, files_by_trace.get(path)) for path in traces]

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


def build(root, output, traces=(), *, files_by_trace=None):
    payload = view_payload(scene_root(str(root)), traces, files_by_trace=files_by_trace)
    encoded = json.dumps(payload, allow_nan=False).replace("</", "<\\/")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).with_name("viewer.html").read_text()
    output.write_text(template.replace("__DATA__", encoded))
    return output


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
    ap.add_argument("--output", type=Path)
    ap.add_argument(
        "--run",
        choices=["expert", "smart", "both"],
        help="Explicitly create fresh canonical traces before rendering",
    )
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args(argv)
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
        try:
            index = render_campaign(args.campaign, destination, scene=args.scene, ego=args.ego,
                                    traffic=args.traffic, startup=args.traffic_startup)
        except (OSError, ValueError) as exc:
            ap.error(str(exc))
        print(index, flush=True)
        if args.open:
            webbrowser.open(index.resolve().as_uri())
        return index
    if bool(args.manifest) == bool(args.scene):
        ap.error("Specify exactly one of --scene and --manifest, or use --campaign")
    if args.ego or args.traffic or args.traffic_startup:
        ap.error("Controller filters require --campaign")
    destination = args.output or settings().runs / "views"
    rows = (
        [{"name": scene_root(args.scene).name, "root": str(scene_root(args.scene))}]
        if args.scene
        else read_manifest(args.manifest)
    )
    links = []
    for row in rows:
        traces = list(args.trace)
        if args.run:
            from geotransfer_gap.execution import main as execute

            for planner in ["expert", "smart"] if args.run == "both" else [args.run]:
                run = execute(["--scene", row["root"], "--planner", planner])
                traces.append(run / row["name"] / "trace.json")
        output = (
            destination
            if args.scene and destination.suffix == ".html"
            else destination / (row["name"] + ".html")
        )
        build(row["root"], output, traces)
        links.append(output)
        print(output, flush=True)
    if args.manifest:
        destination.mkdir(parents=True, exist_ok=True)
        index = destination / "index.html"
        index.write_text(
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
    else:
        index = links[0]
    if args.open:
        webbrowser.open(index.resolve().as_uri())
