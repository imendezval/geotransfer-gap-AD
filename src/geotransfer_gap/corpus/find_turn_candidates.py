"""Source-only shortlist of inD vehicle turns for scene admission screening."""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import json
import math
from pathlib import Path
import numpy as np
from geotransfer_gap.conversion.pipeline import SOURCE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--output", type=Path, default=project_path("pilot/audits/turn_candidates.json")
    )
    args = ap.parse_args()
    rows_out = []
    for recording in range(33):
        meta = {
            int(r["trackId"]): r
            for r in csv.DictReader(
                (SOURCE / f"data/{recording:02d}_tracksMeta.csv").open()
            )
            if r["class"] == "car"
            and int(r["finalFrame"]) - int(r["initialFrame"]) >= 225
        }
        if not meta:
            continue
        tracks = {i: [] for i in meta}
        with (SOURCE / f"data/{recording:02d}_tracks.csv").open() as f:
            for row in csv.DictReader(f):
                track_id = int(row["trackId"])
                if track_id in tracks:
                    tracks[track_id].append(
                        (
                            int(row["frame"]),
                            float(row["xCenter"]),
                            float(row["yCenter"]),
                            float(row["heading"]),
                        )
                    )
        for track_id, track in tracks.items():
            a = np.asarray(track)
            if len(a) < 226:
                continue
            first, last = (int(a[0, 0]), int(a[-1, 0]))
            starts = set(range(first, last - 224, 100)) | {last - 225}
            for start in sorted(starts):
                frames = start + np.arange(91) * 2.5
                x = np.interp(frames, a[:, 0], a[:, 1])
                y = np.interp(frames, a[:, 0], a[:, 2])
                h = np.interp(frames, a[:, 0], np.unwrap(np.deg2rad(a[:, 3])))
                turn = abs((h[-1] - h[0] + math.pi) % (2 * math.pi) - math.pi)
                path = float(np.hypot(np.diff(x), np.diff(y)).sum())
                displacement = math.hypot(x[-1] - x[0], y[-1] - y[0])
                if 0.75 <= turn <= 1.8 and 20 <= path <= 75 and (displacement >= 15):
                    rows_out.append(
                        {
                            "recording": recording,
                            "ego": track_id,
                            "first_frame": start,
                            "turn_rad": float(turn),
                            "path_m": path,
                            "displacement_m": displacement,
                        }
                    )
    rows_out.sort(
        key=lambda r: (-r["turn_rad"], -r["path_m"], r["recording"], r["ego"])
    )
    seen = set()
    unique = []
    for row in rows_out:
        key = (row["recording"], row["ego"])
        if key not in seen:
            unique.append(row)
            seen.add(key)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(unique, indent=2) + "\n")
    print(
        json.dumps(
            {"unique_turning_egos": len(unique), "first_20": unique[:20]}, indent=2
        )
    )


if __name__ == "__main__":
    main()
