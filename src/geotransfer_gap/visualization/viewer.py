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
    scene_root,
    read_json,
    write_json,
    sha256,
    reference,
    scenes,
    read_manifest,
)


def source_frames(root):
    """Independent CSV sampling for visual comparison, without simulator/model imports."""
    import numpy as np

    t = root / "testing"
    scene = read_json(next(t.glob("ind_*.json")))
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


def build(root, output, traces=()):
    root = scene_root(str(root))
    scene, source, source_hash = source_frames(root)
    t = root / "testing"
    registration = read_json(t / "source_image_registration.json")
    v = read_json(t / "validation.json")
    image = settings().source / f"data/{v['recording']:02d}_background.png"
    converted = [
        dict(
            step=i,
            time_s=i * 0.1,
            actors=[
                dict(
                    id=o["id"],
                    type=o["type"],
                    present=bool(o["valid"][i]),
                    x=o["position"][i]["x"],
                    y=o["position"][i]["y"],
                    heading=o["heading"][i],
                    length=o["length"],
                    width=o["width"],
                    collision_state=0,
                    removed=False,
                )
                for o in scene["objects"]
            ],
        )
        for i in range(91)
    ]
    runs = []
    for path in traces:
        report = read_json(path)
        if report["binary_sha256"] != sha256(t / "map_000000.bin"):
            raise ValueError("Trace binary differs from viewed scene")
        runs.append(
            dict(
                name=report["planner"],
                frames=report["frames"],
                provenance={k: v for k, v in report.items() if k != "frames"},
            )
        )
    ego_index = int(scene["metadata"]["sdc_track_index"])
    ego = scene["objects"][ego_index]
    payload = dict(
        scene=root.name,
        ego_id=ego["id"],
        goal=ego["goalPosition"],
        roads=scene["roads"],
        source=source,
        converted=converted,
        runs=runs,
        registration=registration,
        image="data:image/png;base64," + base64.b64encode(image.read_bytes()).decode(),
        provenance=dict(
            schema_version=2,
            scene=reference(root),
            binary_sha256=sha256(t / "map_000000.bin"),
            source_tracks_sha256=source_hash,
            notice="Source and expert traffic are recorded/replayed. SMART is closed loop. Views do not grant admission; estimated dimensions and route-intent limits remain.",
        ),
    )
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
