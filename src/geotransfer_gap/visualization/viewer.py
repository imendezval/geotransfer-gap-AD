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
    write_json,
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


def view_payload(root, traces=()):
    t = root / "testing"
    digest = sha256(t / "map_000000.bin")
    runs = []
    for path in traces:
        report = read_json(path)
        if report["binary_sha256"] != digest:
            raise ValueError("Trace binary differs from viewed scene")
        verification_path = path.with_name("verification.json")
        evidence = read_json(verification_path) if verification_path.is_file() else None
        if evidence and (evidence.get("inputs", {}).get("binary", {}).get("sha256") != digest
                         or evidence.get("scene") != report.get("scene")):
            raise ValueError("Verification sidecar differs from viewed trace")
        diagnostic_path = path.with_name("diagnostic.json")
        diagnostic = read_json(diagnostic_path) if diagnostic_path.is_file() else None
        if diagnostic and diagnostic.get("binary_sha256") != digest:
            raise ValueError("Diagnostic binary differs from viewed scene")
        runs.append(normalize_trace(report, evidence, diagnostic))

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


def build(root, output, traces=()):
    payload = view_payload(scene_root(str(root)), traces)
    encoded = json.dumps(payload, allow_nan=False).replace("</", "<\\/")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).with_name("viewer.html").read_text()
    output.write_text(template.replace("__DATA__", encoded))
    return output


def main(argv=None):
    ap = argparse.ArgumentParser(__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--scene")
    g.add_argument("--manifest", type=Path)
    ap.add_argument("--trace", type=Path, action="append", default=[])
    ap.add_argument("--output", type=Path)
    ap.add_argument(
        "--run",
        choices=["expert", "smart", "both"],
        help="Explicitly create fresh canonical traces before rendering",
    )
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args(argv)
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
