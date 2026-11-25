"""Prespecified 5-source-frame refinement of supported, unadmitted source tasks.

Refines source timing/fidelity, never policy performance. Keeps the same 9s,
10Hz evaluator, source goal85/first-entry75, physical source bodies and gates.
"""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from geotransfer_gap.corpus.screen_source_tasks import sample, screen
from geotransfer_gap.corpus.screen_source_restarts import restart
from geotransfer_gap.corpus.run_oriented_candidate_queue import candidate_key as phase_key


PHASE_OFFSETS = (-20, -15, -10, -5, 5, 10, 15, 20)


def phase_variants(seeds, offsets=PHASE_OFFSETS):
    """Create deterministic actor/window candidates while retaining pair identity."""
    todo = {}
    for row in seeds:
        for offset in offsets:
            first = row["first_frame"] + offset
            variant = dict(row, first_frame=first)
            key = phase_key(variant)
            if first >= 0 and key not in todo:
                todo[key] = variant
    return todo


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--ledgers", type=Path, nargs="+", required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text())
    occupied = {
        (r["recording"], tid) for r in manifest for tid in r["moving_track_ids"]
    }
    seeds, inputs = ({}, [])
    for path in args.ledgers:
        inputs.append(
            {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
        for row in json.loads(path.read_text())["results"]:
            if "actor" not in row:
                continue
            key = phase_key(row)
            flags = row.get("source_unsupported_rule_flags", [])
            if flags and (
                not (
                    row.get("stop_scope_requires_explicit_manual_review")
                    or (
                        row.get("same_route_following_requires_manual_review")
                        and row.get("unresolved_rule_flags_after_source_proofs") == []
                    )
                )
            ):
                continue
            if row["location"] not in (1, 3, 4):
                continue
            if any(((row["recording"], row[k]) in occupied for k in ("ego", "actor"))):
                continue
            seeds[key] = row
    ordered_seeds = sorted(
        seeds.values(),
        key=lambda row: (
            row["location"],
            row["recording"],
            row["ego"],
            row["first_frame"],
            row["actor"],
        ),
    )
    todo = phase_variants(ordered_seeds)
    jobs = []
    for rec in sorted({k[0] for k in todo}):
        rows = [r for k, r in todo.items() if k[0] == rec]
        ids = {r[k] for r in rows for k in ("ego", "actor")}
        df = pd.read_csv(
            settings().source / f"data/{rec:02d}_tracks.csv",
            usecols=[
                "frame",
                "trackId",
                "xCenter",
                "yCenter",
                "heading",
                "xVelocity",
                "yVelocity",
            ],
        )
        tracks = {
            int(i): g[
                ["frame", "xCenter", "yCenter", "heading", "xVelocity", "yVelocity"]
            ].to_numpy(float)
            for i, g in df[df.trackId.isin(ids)].groupby("trackId", sort=False)
        }
        with (settings().source / f"data/{rec:02d}_tracksMeta.csv").open() as stream:
            meta = {int(r["trackId"]): r for r in csv.DictReader(stream)}

        def dims(tid):
            m = meta[tid]
            default = (
                (0.6, 0.6)
                if m["class"] == "pedestrian"
                else (1.8, 0.6) if m["class"] == "bicycle" else (4.5, 1.8)
            )
            return tuple(
                (
                    float(m[k]) if float(m[k]) > 0 else d
                    for k, d in zip(("length", "width"), default)
                )
            )

        for row in rows:
            frames = row["first_frame"] + np.arange(91) * 2.5
            ego, actor = (
                sample(tracks[row["ego"]], frames),
                sample(tracks[row["actor"]], frames),
            )
            xy, velocity, heading, valid = ego
            if not valid.all():
                continue
            path = float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum())
            if path < 5 or np.linalg.norm(xy[-1] - xy[0]) < 4:
                continue
            end = int(np.flatnonzero(np.linalg.norm(xy - xy[85], axis=1) <= 2)[0])
            if end < 75:
                continue
            evidence = screen(
                ego, actor, row["actor_class"], dims(row["ego"]), dims(row["actor"])
            )
            if evidence is None and row["actor_class"] in ("car", "truck_bus"):
                evidence = restart(
                    ego,
                    actor,
                    dims(row["ego"])[0],
                    dims(row["actor"])[0],
                    dims(row["ego"])[1],
                    dims(row["actor"])[1],
                )
            if evidence is None:
                continue
            distances = np.linalg.norm(xy - actor[0], axis=1)
            distances[~actor[3]] = np.inf
            nearest = int(distances.argmin())
            if not 15 <= nearest <= 70:
                continue
            keep = {
                k: row[k]
                for k in (
                    "recording",
                    "location",
                    "ego",
                    "first_frame",
                    "actor",
                    "actor_class",
                    "role",
                )
            }
            jobs.append(
                dict(
                    keep,
                    task_evidence=evidence,
                    ego_path_m=path,
                    goal_first_entry_step=end,
                    source_nearest_step=nearest,
                    source_center_gap_m=float(distances[nearest]),
                )
            )
        print("recording", rec, "source-positive refined phases", len(jobs), flush=True)
    jobs.sort(
        key=lambda r: (
            r["location"],
            r["recording"],
            r["ego"],
            abs(r["task_evidence"].get("ego_path_crossing_step", 45) - 45),
            r["first_frame"],
            r["actor"],
        )
    )
    result = {
        "schema_version": 1,
        "selection": "Fixed offsets±5/10/15/20 source frames around supported unadmitted tasks; source-only resampling/task recheck; min5m path/4m displacement; unchanged goal first-entry75, source goal85, full fidelity/manual/model admission. Skip source ego/claimed actor IDs already in the independent manifest. No planner outcomes.",
        "selector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "task_screen_sha256": hashlib.sha256(
            tool_path("screen_source_tasks.py").read_bytes()
        ).hexdigest(),
        "restart_screen_sha256": hashlib.sha256(
            tool_path("screen_source_restarts.py").read_bytes()
        ).hexdigest(),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "inputs": inputs,
        "seed_windows": len(seeds),
        "proposed_variants": len(todo),
        "jobs": jobs,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("new refined source jobs", len(jobs))


if __name__ == "__main__":
    main()
