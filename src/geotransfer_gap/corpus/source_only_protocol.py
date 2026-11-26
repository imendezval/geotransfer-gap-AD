"""Shared source-only identity and actor-scope helpers for German-200 v1."""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np


WINDOW_SOURCE_FRAMES = 225
SAMPLED_STEPS = 91
SAMPLE_SPACING_SOURCE_FRAMES = 2.5
MOVING_PATH_THRESHOLD_M = 1.0
SUPPORTED_CLASSES = {"car", "truck_bus", "pedestrian", "bicycle"}


def source_window_identity(row):
    """Return the canonical inclusive source-window identity.

    Accepts selector (`ego`) and catalog/manifest (`ego_track_id`) spellings.
    The repository's 91-sample window convention records `last_frame` as
    `first_frame + 225`, inclusive, although sample 90 is at that endpoint.
    """
    first = int(row["first_frame"])
    return {
        "recording": int(row["recording"]),
        "location": int(row["location"]),
        "ego_track_id": int(row.get("ego_track_id", row.get("ego"))),
        "first_frame": first,
        "last_frame": int(row.get("last_frame", first + WINDOW_SOURCE_FRAMES)),
    }


def source_window_identity_sha256(row):
    identity = source_window_identity(row)
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_task_identity(row):
    """Return a stable actor-task key, or `None` for random-window rows."""
    actor = row.get("actor", row.get("actor_track_id"))
    if actor is None:
        return None
    return (int(row["recording"]), int(row.get("ego_track_id", row.get("ego"))), int(actor))


def source_context_actors(row, tracks, track_meta):
    """Reconstruct converted source actors using `sources.ind.interpolate_actor`.

    `tracks` maps track ID to an Nx(3+) float array whose columns start with
    frame, xCenter, and yCenter. `track_meta` maps track ID to inD metadata.
    It applies the converter's inclusive row crop, supported-class check,
    2-raw-row and 2-valid-sample requirements, and >=1m raw source path rule.
    """
    ident = source_window_identity(row)
    start, end = ident["first_frame"], ident["last_frame"]
    sample_frames = start + np.arange(SAMPLED_STEPS, dtype=float) * SAMPLE_SPACING_SOURCE_FRAMES
    actors = []
    for raw_id, raw_track in tracks.items():
        track_id = int(raw_id)
        meta = track_meta.get(track_id)
        if not meta or meta.get("class") not in SUPPORTED_CLASSES:
            continue
        track = np.asarray(raw_track, dtype=float)
        if track.ndim != 2 or track.shape[1] < 3:
            continue
        # load_tracks crops source rows to [first_frame, ceil(sample_frames[-1])].
        rows = track[(track[:, 0] >= start) & (track[:, 0] <= math.ceil(end))]
        if len(rows) < 2:
            continue
        valid_count = int(((sample_frames >= rows[0, 0]) & (sample_frames <= rows[-1, 0])).sum())
        if valid_count < 2:
            continue
        path = float(np.hypot(np.diff(rows[:, 1]), np.diff(rows[:, 2])).sum())
        speeds = None
        if track.shape[1] >= 6:
            speeds = np.hypot(rows[:, 4], rows[:, 5])
        actors.append(
            {
                "track_id": track_id,
                "class": meta["class"],
                "raw_rows_in_window": int(len(rows)),
                "valid_samples": valid_count,
                "source_window_path_m": path,
                "moving": bool(path >= MOVING_PATH_THRESHOLD_M),
                "source_window_max_speed_mps": (
                    float(speeds.max()) if speeds is not None and len(speeds) else None
                ),
                "source_track_start_frame": int(rows[0, 0]),
                "source_track_end_frame": int(rows[-1, 0]),
            }
        )
    actors.sort(key=lambda actor: actor["track_id"])
    return actors


def independence_conflicts(candidate, retained):
    """Return conflicts under inclusive-window and all-moving-track rules."""
    candidate_identity = source_window_identity(candidate)
    candidate_recording = candidate_identity["recording"]
    candidate_tracks = set(map(int, candidate.get("moving_track_ids", ())))
    conflicts = []
    for prior in retained:
        prior_identity = source_window_identity(prior)
        if prior_identity["recording"] != candidate_recording:
            continue
        overlap = not (
            candidate_identity["first_frame"] > prior_identity["last_frame"]
            or candidate_identity["last_frame"] < prior_identity["first_frame"]
        )
        shared = sorted(candidate_tracks & set(map(int, prior.get("moving_track_ids", ()))))
        if overlap or shared:
            conflicts.append(
                {
                    "source_window_identity_sha256": source_window_identity_sha256(prior),
                    "inclusive_window_overlap": overlap,
                    "shared_moving_track_ids": shared,
                }
            )
    return conflicts


def split_label(location, recording):
    location, recording = int(location), int(recording)
    if location == 4:
        return "heldout_location_4"
    return "validation_recording" if recording % 5 == 0 else "adaptation_recording"
