"""Reject ranked windows whose sampled ego path approaches a source traffic sign."""

from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
from collections import defaultdict
import csv
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input", type=Path, default=project_path("pilot/audits/vru_candidates.json")
    )
    ap.add_argument(
        "--output", type=Path, default=project_path("pilot/audits/vru_sign_clear.json")
    )
    ap.add_argument("--radius", type=float, default=20.0)
    args = ap.parse_args()
    raw = json.loads(args.input.read_text())
    by_recording = defaultdict(list)
    for candidate in raw:
        by_recording[candidate["recording"]].append(candidate)
    clear = set()
    minimums = {}
    for recording, candidates in by_recording.items():
        with (
            settings().source / f"data/{recording:02d}_recordingMeta.csv"
        ).open() as f:
            meta = next(csv.DictReader(f))
        osm_path, _ = map_geometry.map_paths(meta, recording)
        osm = ET.parse(osm_path).getroot()
        nodes = map_geometry.project_nodes(
            osm, float(meta["xUtmOrigin"]), float(meta["yUtmOrigin"])
        )
        signs = []
        for way in osm.findall("way"):
            if any(
                (
                    t.get("k") == "type" and t.get("v") == "traffic_sign"
                    for t in way.findall("tag")
                )
            ):
                coords = [nodes[int(n.get("ref"))] for n in way.findall("nd")]
                if coords:
                    signs.append(coords)
        egos = {x["ego"] for x in candidates}
        tracks = defaultdict(list)
        with (settings().source / f"data/{recording:02d}_tracks.csv").open() as f:
            for row in csv.DictReader(f):
                tid = int(row["trackId"])
                if tid in egos:
                    tracks[tid].append(
                        (
                            int(row["frame"]),
                            float(row["xCenter"]),
                            float(row["yCenter"]),
                        )
                    )
        arrays = {k: np.asarray(v) for k, v in tracks.items()}
        for candidate in candidates:
            arr = arrays[candidate["ego"]]
            frames = candidate["first_frame"] + np.arange(91) * 2.5
            points = list(
                zip(
                    np.interp(frames, arr[:, 0], arr[:, 1]),
                    np.interp(frames, arr[:, 0], arr[:, 2]),
                )
            )
            distance = (
                min(
                    (
                        (
                            map_geometry.point_polyline_distance(pt, coords)
                            if len(coords) > 1
                            else math.dist(pt, coords[0])
                        )
                        for coords in signs
                        for pt in points
                    )
                )
                if signs
                else float("inf")
            )
            key = (candidate["recording"], candidate["ego"], candidate["first_frame"])
            minimums[key] = distance
            if distance >= args.radius:
                clear.add(key)
    result = [
        dict(
            x,
            source_sign_min_distance_m=minimums[
                x["recording"], x["ego"], x["first_frame"]
            ],
        )
        for x in raw
        if (x["recording"], x["ego"], x["first_frame"]) in clear
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "pairs": len(raw),
                "sign_clear_pairs": len(result),
                "unique_sign_clear_windows": len(clear),
                "radius_m": args.radius,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
