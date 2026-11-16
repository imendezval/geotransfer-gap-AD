"""Deterministic first-pass conversion screen from the source-only window ledger."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PYTHON = "/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python"


def choose(windows, per_category):
    selected = []
    for recording in range(33):
        pool = [x for x in windows if x["recording"] == recording
                and x["source_rejection"] is None and x["nearby_moving_actor_count"] >= 1]
        for category, predicate in (("turn", lambda x: x["turn_rad"] >= 0.75),
                                    ("straight", lambda x: x["turn_rad"] <= 0.3),
                                    ("moderate", lambda x: 0.3 < x["turn_rad"] < 0.75)):
            choices = [x for x in pool if predicate(x)]
            if not choices:
                continue
            # Favor a modest number of moving participants and a visible VRU,
            # while using source data only.  Ties are stable and reproducible.
            choices.sort(key=lambda x: (abs(x["nearby_moving_actor_count"] - 3)
                                        + abs(x["nearby_vru_count"] - 1),
                                        abs(x["nearby_actor_count"] - 5),
                                        -x["ego_path_m"], x["ego_track_id"], x["first_frame"]))
            selected.extend((category, row) for row in choices[:per_category])
    return selected


def run(command, root):
    proc = subprocess.run([PYTHON, str(HERE / command[0]), "--root", str(root), *command[1:]],
                          capture_output=True, text=True)
    return proc.returncode == 0, (proc.stderr or proc.stdout)[-1000:]


def main(args):
    ledger = json.loads(args.catalog.read_text())
    windows = ledger["windows"]
    if args.locations:
        windows = [x for x in windows if x["location"] in args.locations]
    if args.map_passing_only:
        preflight = json.loads(args.map_preflight.read_text())
        passing = {(x["recording"], x["ego_track_id"], x["first_frame"])
                   for x in preflight["windows"] if x["outside_sample_count"] == 0
                   and x["directed_route"]}
        windows = [x for x in windows if (x["recording"], x["ego_track_id"], x["first_frame"]) in passing]
    selected = choose(windows, args.per_category)
    results = json.loads(args.output.read_text())["results"] if args.output.is_file() else []
    screened_names = {x["name"] for x in results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for category, row in selected[:args.limit]:
        r, e, f = row["recording"], row["ego_track_id"], row["first_frame"]
        name = f"r{r:02d}_e{e}_f{f}_{category}"
        if name in screened_names:
            continue
        root = (HERE / args.candidate_dir / name).resolve()
        command = [PYTHON, str(HERE / "pilot_ind.py"), "--recording", str(r),
                   "--ego", str(e), "--first-frame", str(f), "--goal-sample", "85",
                   "--late-mode", "runtime_spawn", "--static-crop-radius", "1000000",
                   "--parked-as-static-expert", "--output-root", str(root)]
        proc = subprocess.run(command, capture_output=True, text=True)
        outcome = {"name": name, "root": str(root), "category": category, "recording": r,
                   "location": row["location"], "ego_track_id": e, "first_frame": f,
                   "source_nearby_moving_actors": row["nearby_moving_actor_count"],
                   "source_nearby_vrus": row["nearby_vru_count"],
                   "conversion_pass": proc.returncode == 0,
                   "exclusion_reasons": [], "error_tail": None}
        if proc.returncode:
            outcome["exclusion_reasons"].append("conversion")
            outcome["error_tail"] = (proc.stderr or proc.stdout)[-1000:]
        else:
            for command, label in ((["audit_scene.py"], "route_or_topology"),
                                   (["audit_physical_source.py"], "physical_audit"),
                                   (["audit_map_semantics.py"], "semantic_inventory"),
                                   (["audit_rule_applicability.py"], "rule_inventory")):
                ok, error = run(command, root)
                if not ok:
                    outcome["exclusion_reasons"].append(label + "_execution")
                    outcome["error_tail"] = error
                    break
            if not outcome["exclusion_reasons"]:
                g = json.loads((root / "testing/map_audit.json").read_text())
                p = json.loads((root / "testing/physical_source_audit.json").read_text())
                checks = {"route": bool(g["occupied_start_to_occupied_goal_reachable"]),
                          "ego_inside_lanelets": not g["ego_samples_outside_lanelet_polygons"],
                          "no_reversed_successors": not g["successors_direction_reversed"],
                          "no_unsupported_successor": g["successors_with_no_boundary_ids_shared"] == 0,
                          "ego_boundary_clear": str(e) not in p["source_box_boundary_contacts"],
                          "source_boxes_nonoverlapping": not p["source_box_actor_overlaps"],
                          "all_moving_vehicles_boundary_clear": all(
                              str(obj["id"]) not in p["source_box_boundary_contacts"]
                              for obj in json.loads(next((root / "testing").glob("ind_*.json")).read_text())["objects"]
                              if obj["type"] == "vehicle" and obj["source_window_path_length_m"] >= 0.5)}
                outcome["prefilter_checks"] = checks
                outcome["exclusion_reasons"] = [key for key, ok in checks.items() if not ok]
        results.append(outcome)
        args.output.write_text(json.dumps({"schema_version": 1, "catalog": str(args.catalog),
                                           "selection": ("up to " + str(args.per_category) + " per turn/straight/moderate category "
                                                         "per recording; source-only deterministic rank"),
                                           "results": results}, indent=2) + "\n")
        print(f"{len(results)}/{min(len(selected), args.limit)} {name}: "
              f"{'prefilter pass' if not outcome['exclusion_reasons'] else ','.join(outcome['exclusion_reasons'])}",
              flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, default=Path("pilot/audits/all_moving_windows.json"))
    ap.add_argument("--output", type=Path, default=Path("pilot/audits/step2_first_screen.json"))
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--per-category", type=int, default=1)
    ap.add_argument("--locations", type=int, nargs="*")
    ap.add_argument("--map-passing-only", action="store_true")
    ap.add_argument("--map-preflight", type=Path, default=Path("pilot/audits/source_map_preflight.json"))
    ap.add_argument("--candidate-dir", type=Path, default=Path("pilot/corpus/candidates"))
    main(ap.parse_args())
