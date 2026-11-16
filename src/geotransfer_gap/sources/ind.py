"""inD CSV loading and trajectory interpolation for conversion."""

from geotransfer_gap.config import settings
import csv
import math
import numpy as np

SOURCE = settings().source


def load_tracks(config, frames):
    tracks = {}
    with (SOURCE / f"data/{config.recording:02d}_tracks.csv").open() as f:
        for row in csv.DictReader(f):
            frame = int(row["frame"])
            if config.first_frame <= frame <= math.ceil(frames[-1]):
                tracks.setdefault(int(row["trackId"]), []).append(row)
    with (SOURCE / f"data/{config.recording:02d}_tracksMeta.csv").open() as f:
        meta = {int(r["trackId"]): r for r in csv.DictReader(f)}
    with (SOURCE / f"data/{config.recording:02d}_recordingMeta.csv").open() as f:
        recording_meta = next(csv.DictReader(f))
    return (tracks, meta, recording_meta)


def interpolate_actor(config, frames, track_id, rows, meta):
    src_frames = np.array([int(r["frame"]) for r in rows])
    if len(src_frames) < 2:
        return None
    valid = (frames >= src_frames[0]) & (frames <= src_frames[-1])
    if valid.sum() < 2:
        return None

    def series(key):
        return np.interp(frames, src_frames, [float(r[key]) for r in rows])

    x, y, vx, vy = (series(k) for k in ("xCenter", "yCenter", "xVelocity", "yVelocity"))
    angles = np.unwrap(np.deg2rad([float(r["heading"]) for r in rows]))
    heading = np.interp(frames, src_frames, angles)
    cls = meta["class"]
    kind = {
        "car": "vehicle",
        "truck_bus": "vehicle",
        "pedestrian": "pedestrian",
        "bicycle": "cyclist",
    }.get(cls)
    if kind is None:
        return None
    source_length, source_width = (float(meta["length"]), float(meta["width"]))
    source_xy = [(float(r["xCenter"]), float(r["yCenter"])) for r in rows]
    source_path_length = sum(
        (math.dist(a, b) for a, b in zip(source_xy, source_xy[1:]))
    )
    source_max_speed = max(
        (math.hypot(float(r["xVelocity"]), float(r["yVelocity"])) for r in rows)
    )
    defaults = {"pedestrian": (0.6, 0.6), "cyclist": (1.8, 0.6), "vehicle": (4.5, 1.8)}
    length = source_length if source_length > 0 else defaults[kind][0]
    width = source_width if source_width > 0 else defaults[kind][1]
    positions = [{"x": float(a), "y": float(b), "z": 0.0} for a, b in zip(x, y)]
    velocities = [{"x": float(a), "y": float(b), "z": 0.0} for a, b in zip(vx, vy)]
    last = int(np.flatnonzero(valid)[-1])
    return {
        "id": track_id,
        "type": kind,
        "length": length,
        "width": width,
        "height": 1.6 if kind == "vehicle" else 1.7,
        "dimension_imputed": source_length <= 0 or source_width <= 0,
        "source_window_path_length_m": source_path_length,
        "source_window_max_speed_mps": source_max_speed,
        "position": positions,
        "velocity": velocities,
        "heading": heading.tolist(),
        "valid": valid.astype(int).tolist(),
        "goalPosition": positions[last],
        "mark_as_expert": 0,
    }
