"""Build a current, source-independent manifest for a fixed SMART pilot batch."""

from geotransfer_gap.artifacts import resolve_reference
from geotransfer_gap.artifacts import evidence_current
from geotransfer_gap.validation.scene_contract import contracts_equal
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import argparse
import csv
import hashlib
import json
from pathlib import Path
from geotransfer_gap.validation import scene_contract

HERE = PROJECT_ROOT


def type_family(label):
    if label.startswith("pedestrian_crossing"):
        return "pedestrian_crossing"
    if label.startswith("cyclist_crossing"):
        return "cyclist_crossing"
    if label.startswith("lead_vehicle_"):
        return "longitudinal_following"
    return label


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument(
        "--selection",
        type=Path,
        default=project_path("pilot/audits/step2_smart_pilot_selection.json"),
    )
    ap.add_argument(
        "--output-prefix",
        type=Path,
        default=project_path("pilot/audits/step2_smart_pilot"),
    )
    ap.add_argument(
        "--retain-independence-exclusions",
        action="store_true",
        help="Keep conflicts in the ledger instead of aborting; selection order decides which source window is retained.",
    )
    ap.add_argument(
        "--source-order",
        action="store_true",
        help="Order interactions before controls, then recording/frame/ego; uses source metadata and review labels only.",
    )
    ap.add_argument(
        "--publish-current",
        action="store_true",
        help="Publish the admitted selection as the portable current corpus",
    )
    args = ap.parse_args()
    accepted, ledger = ([], [])
    jobs = json.loads(args.selection.read_text())["jobs"]
    if args.source_order:

        def source_order(job):
            testing = resolve_reference(job["root"]) / "testing"
            validation = json.loads((testing / "validation.json").read_text())
            review_path = testing / "semantic_review_smart_hybrid_startup.json"
            review = (
                json.loads(review_path.read_text()) if review_path.is_file() else {}
            )
            return (
                not review.get("interaction_opportunity", False),
                validation["recording"],
                validation["first_frame"],
                validation["ego_track"],
                str(testing),
            )

        jobs = sorted(jobs, key=source_order)
    for job in jobs:
        root = resolve_reference(job["root"]).resolve()
        t = root / "testing"
        gate_path = t / "admission_smart_hybrid_startup.json"
        if not gate_path.is_file():
            ledger.append(
                {
                    "root": str(root),
                    "role": job["role"],
                    "admission_current": False,
                    "research_admitted": False,
                    "corpus_selected": False,
                    "exclusion_reasons": ["missing_smart_admission"],
                }
            )
            continue
        gate = json.loads(gate_path.read_text())
        current = scene_contract.build(root, "expert")
        fresh = (
            contracts_equal(gate.get("contract"), current)
            and gate.get("gate_sha256") == sha(project_path("admit_smart_scene.py"))
            and evidence_current(gate)
        )
        row = {
            "root": str(root),
            "role": job["role"],
            "admission_current": fresh,
            "research_admitted": bool(fresh and gate["research_admitted"]),
            "corpus_selected": False,
            "exclusion_reasons": (
                gate["exclusion_reasons"] if fresh else ["stale_smart_admission"]
            ),
        }
        ledger.append(row)
        if not row["research_admitted"]:
            continue
        source = json.loads(next(t.glob("ind_*.json")).read_text())
        v = json.loads((t / "validation.json").read_text())
        review = json.loads(
            (t / "semantic_review_smart_hybrid_startup.json").read_text()
        )
        moving = {
            o["id"]
            for o in source["objects"]
            if o.get("source_window_path_length_m", 0) >= 1.0
        }
        conflicts = []
        for prior in accepted:
            if prior["recording"] == v["recording"]:
                overlap = not (
                    v["first_frame"] > prior["last_frame"]
                    or v["first_frame"] + 225 < prior["first_frame"]
                )
                shared = sorted(moving & set(prior["moving_track_ids"]))
                if overlap or shared:
                    conflicts.append(
                        {
                            "retained_root": prior["root"],
                            "overlapping_window": overlap,
                            "shared_moving_track_ids": shared,
                        }
                    )
        if conflicts:
            if not args.retain_independence_exclusions:
                raise ValueError("Overlapping source windows or shared moving tracks")
            row["exclusion_reasons"] = ["source_independence_conflict"]
            row["independence_conflicts"] = conflicts
            continue
        row["corpus_selected"] = True
        accepted.append(
            {
                "name": root.name,
                "root": str(root),
                "recording": v["recording"],
                "location": v["location"],
                "ego_track_id": v["ego_track"],
                "ego_binary_index": current["ego_binary_index"],
                "first_frame": v["first_frame"],
                "last_frame": v["first_frame"] + 225,
                "planner_protocol": gate["planner_protocol"],
                "traffic_protocol": gate["traffic_protocol"],
                "interaction_opportunity": review["interaction_opportunity"],
                "interaction_types": review["eligible_interaction_types"],
                "interaction_actor_ids": review["interaction_actor_ids"],
                "moving_track_ids": sorted(moving),
                "interaction_type_families": (
                    sorted(
                        {type_family(x) for x in review["eligible_interaction_types"]}
                    )
                    if review["interaction_opportunity"]
                    else []
                ),
                "split": (
                    "heldout_location_4"
                    if v["location"] == 4
                    else (
                        "validation_recording"
                        if v["recording"] % 5 == 0
                        else "adaptation_recording"
                    )
                ),
                "admission_sha256": sha(gate_path),
                "binary_sha256": current["files"]["scene_binary"]["sha256"],
                "source_tracks_sha256": current["files"]["source_tracks_csv"]["sha256"],
                "source_map_sha256": current["files"]["source_lanelet2_map"]["sha256"],
                "source_background_sha256": current["files"]["source_background_image"][
                    "sha256"
                ],
            }
        )
    if args.publish_current:
        from geotransfer_gap.artifacts import write_json, portable_manifest

        write_json(
            settings().artifacts / "corpus/current.json", portable_manifest(accepted)
        )
    summary = {
        "schema_version": 1,
        "selection_sha256": sha(args.selection),
        "manifest_builder_sha256": sha(Path(__file__)),
        "selected": len(ledger),
        "current": sum((x["admission_current"] for x in ledger)),
        "admitted": len(accepted),
        "raw_research_admissions": sum((x["research_admitted"] for x in ledger)),
        "independence_exclusions": sum(
            (bool(x.get("independence_conflicts")) for x in ledger)
        ),
        "independence_policy": (
            "Interactions first, then recording/frame/ego source order. "
            if args.source_order
            else "Prespecified selection-file order. "
        )
        + "Retain the first admissible source window; exclude later overlapping windows or shared moving tracks within the same recording. No planner outcomes used.",
        "interaction_scenes": sum((x["interaction_opportunity"] for x in accepted)),
        "interaction_type_families": sorted(
            {k for x in accepted for k in x["interaction_type_families"]}
        ),
        "accepted_locations": sorted({x["location"] for x in accepted}),
        "recording_clusters": sorted({x["recording"] for x in accepted}),
        "split_policy": "Whole recordings; location4 held out; other records divisible by5 reserved for validation. Stationary parked tracks may recur. Recording remains the inference cluster.",
        "candidate_ledger": ledger,
    }
    prefix = args.output_prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_name(prefix.name + "_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    prefix.with_name(prefix.name + "_manifest.json").write_text(
        json.dumps(accepted, indent=2) + "\n"
    )
    if accepted:
        with prefix.with_name(prefix.name + "_manifest.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(accepted[0]))
            w.writeheader()
            for row in accepted:
                w.writerow(
                    {
                        k: json.dumps(v) if isinstance(v, list) else v
                        for k, v in row.items()
                    }
                )
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "selected",
                    "current",
                    "admitted",
                    "interaction_scenes",
                    "accepted_locations",
                    "recording_clusters",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
