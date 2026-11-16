"""Freeze a verified manifest and its effective SMART/runtime protocol.

Fails on stale admission, unequal scene protocols, stale batch output or missing
single/batch parity. It records existing evidence; it never grants admission.
"""

from geotransfer_gap.artifacts import evidence_current
from geotransfer_gap.validation.scene_contract import contracts_equal
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import argparse
import hashlib
import json
from pathlib import Path
from geotransfer_gap.validation import scene_contract
from geotransfer_gap.runtime import hybrid_traffic

HERE = PROJECT_ROOT


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--batch-report", type=Path, required=True)
    ap.add_argument(
        "--output",
        type=Path,
        default=project_path("pilot/audits/step2_frozen_protocol_baseline.json"),
    )
    args = ap.parse_args()
    rows = json.loads(args.manifest.read_text())
    if not rows:
        raise ValueError("No admitted baseline")
    baseline = []
    protocols = []
    for row in rows:
        root = Path(row["root"])
        t = root / "testing"
        gate_path = t / f"admission_smart_{row['traffic_protocol']}.json"
        gate = json.loads(gate_path.read_text())
        if (
            sha(gate_path) != row["admission_sha256"]
            or not gate.get("research_admitted")
            or gate.get("gate_sha256") != sha(project_path("admit_smart_scene.py"))
            or (
                not contracts_equal(
                    gate.get("contract"), scene_contract.build(root, "expert")
                )
            )
            or (not evidence_current(gate))
        ):
            raise ValueError("Stale admission: " + str(root))
        probe = json.loads((t / "smart_map_transfer_all_actors_probe.json").read_text())
        closed = t / f"smart_all_actors_closed_loop_{row['traffic_protocol']}.json"
        rollout = json.loads(closed.read_text())
        protocol = {
            "planner_protocol": gate["planner_protocol"],
            "traffic_protocol": gate["traffic_protocol"],
            "traffic_controller_version": hybrid_traffic.PROTOCOL_VERSION,
            "map_encoding_protocol": gate["map_encoding_protocol"],
            "runtime_source_sha256": gate["contract"]["runtime_source_sha256"],
            "warmup_steps": gate["warmup_steps"],
            "evaluator_goal": gate["evaluator_goal"],
            "planner_config": gate["planner_config"],
            "seed": rollout["seed"],
            "checkpoint_sha256": probe["checkpoint_sha256"],
            "input_protocol_file_sha256": probe["protocol_file_sha256"],
            "closed_loop_protocol_sha256": rollout["protocol_sha256"],
        }
        if (
            rollout["runtime"]["runtime_source_sha256"]
            != protocol["runtime_source_sha256"]
        ):
            raise ValueError("Stale rollout runtime: " + str(root))
        protocols.append(json.dumps(protocol, sort_keys=True))
        baseline.append(
            {
                "root": str(root),
                "admission_sha256": sha(gate_path),
                "closed_loop_sha256": sha(closed),
                "source_feature_audit": probe["source_feature_audit"],
            }
        )
    if len(set(protocols)) != 1:
        raise ValueError("Mixed effective protocols")
    batch = json.loads(args.batch_report.read_text())
    if (
        batch.get("manifest_sha256") != sha(args.manifest)
        or batch.get("runner_sha256") != sha(project_path("run_smart_manifest.py"))
        or {r["root"] for r in batch["results"]} != {r["root"] for r in rows}
        or (
            not all(
                (
                    r.get("matches_prior_single_scene_timeline") is True
                    and (not r["identity_errors_at_refresh"])
                    and (
                        r["diagnostic_sha256"]
                        == next(
                            (
                                b["closed_loop_sha256"]
                                for b in baseline
                                if b["root"] == r["root"]
                            )
                        )
                    )
                    and (
                        r["admission_sha256"]
                        == next(
                            (
                                b["admission_sha256"]
                                for b in baseline
                                if b["root"] == r["root"]
                            )
                        )
                    )
                    for r in batch["results"]
                )
            )
        )
    ):
        raise ValueError(
            "Batch evidence is stale or has not reproduced single-scene timelines"
        )
    proofs = {}
    for name in [
        "step2_native_lanelet_orientation.json",
        "step2_smart_gate_regressions.json",
        "step2_stop_scope_regressions.json",
        "runtime_source_reentry_regression.json",
        "hybrid_protocol_us_parity.json",
        "source_restart_screen_regressions.json",
        "source_following_scope_regressions.json",
        "directed_rule_scope_regressions.json",
        "source_lane_change_native_oracle.json",
        "background_route_policy_regressions.json",
        "source_route_sequence_regressions.json",
        "faithful_map_regressions.json",
        "queue_pair_identity_regression.json",
    ]:
        path = project_path("pilot/audits") / name
        data = json.loads(path.read_text())
        if not (data.get("passed") or data.get("mechanical_parity_pass")):
            raise ValueError("Failed proof: " + name)
        proofs[name] = {"path": str(path), "sha256": sha(path)}
        if (
            "runtime_source_sha256" in data
            and data["runtime_source_sha256"] != protocol["runtime_source_sha256"]
        ):
            raise ValueError("Stale runtime proof: " + name)
        for field, tool in [
            ("converter_sha256", "pilot_ind.py"),
            ("gate_sha256", "admit_smart_scene.py"),
            ("scope_tool_sha256", "audit_task_rule_scope.py"),
            ("hybrid_protocol_sha256", "hybrid_traffic.py"),
            ("screen_sha256", "screen_source_restarts.py"),
            ("audit_sha256", "audit_following_scope.py"),
            ("directed_scope_sha256", "audit_directed_rule_scope.py"),
            ("lane_change_tool_sha256", "source_lane_changes.py"),
            ("route_policy_sha256", "background_route_intent.py"),
            ("route_sequence_sha256", "audit_source_route_sequence.py"),
            ("map_preprocessor_sha256", "faithful_map.py"),
            ("queue_sha256", "run_oriented_candidate_queue.py"),
        ]:
            if field in data and data[field] != sha(project_path(tool)):
                raise ValueError("Stale tool proof: " + name)
    result = {
        "schema_version": 2,
        "status": "verified_runtime_scoped_baseline",
        "freeze_tool_sha256": sha(Path(__file__)),
        "effective_protocol": protocol,
        "manifest_sha256": sha(args.manifest),
        "manifest_path": str(args.manifest.resolve()),
        "batch_report_sha256": sha(args.batch_report),
        "batch_report_path": str(args.batch_report.resolve()),
        "baselines": baseline,
        "regressions": proofs,
        "scope": "Per-scene technical/manual/SMART admission, source expert pose/velocity fidelity, and deterministic isolated batch execution. Not universal source-traffic imitation, upstream training equivalence, or a matched US/German study.",
    }
    access_path = project_path("pilot/audits/step2_corpus_access.json")
    access = json.loads(access_path.read_text())
    if (
        not access["passed"]
        or access["manifest_sha256"] != sha(args.manifest)
        or access["tool_sha256"] != sha(project_path("audit_corpus_access.py"))
    ):
        raise ValueError("Missing or stale ordinary-road access proof")
    if {r["root"] for r in access["scenes"]} != {r["root"] for r in rows}:
        raise ValueError("Incomplete ordinary-road access proof")
    for row in access["scenes"]:
        root = Path(row["root"])
        contract = scene_contract.build(root, "expert")
        if (
            not row["passed"]
            or row["map_audit_sha256"] != sha(root / "testing/map_audit.json")
            or row["source_map_sha256"]
            != contract["files"]["source_lanelet2_map"]["sha256"]
        ):
            raise ValueError("Stale access source evidence: " + str(root))
    result["regressions"]["step2_corpus_access.json"] = {
        "path": str(access_path),
        "sha256": sha(access_path),
    }
    us_path = project_path("pilot/audits/step2_velocity_us_closed_loop_parity.json")
    us = json.loads(us_path.read_text())
    if (
        not us["passed"]
        or us["traffic_version"] != hybrid_traffic.PROTOCOL_VERSION
        or us.get("map_encoding_protocol") != protocol["map_encoding_protocol"]
        or (
            us.get("producer_sha256")
            != sha(project_path("probe_us_reference_parity.py"))
        )
    ):
        raise ValueError("Stale US closed-loop references")
    for row in us["results"]:
        report_path = (
            Path(row["root"])
            / "testing/smart_all_actors_closed_loop_hybrid_startup.json"
        )
        report = json.loads(report_path.read_text())
        input_path = (
            Path(row["root"]) / "testing/smart_map_transfer_all_actors_probe.json"
        )
        if (
            row["report_sha256"] != sha(report_path)
            or row.get("input_probe_sha256") != sha(input_path)
            or row["identity_errors"]
            or (report["protocol_sha256"] != protocol["closed_loop_protocol_sha256"])
            or (
                report["runtime"]["runtime_source_sha256"]
                != protocol["runtime_source_sha256"]
            )
        ):
            raise ValueError("Stale US closed-loop report: " + row["root"])
    result["regressions"]["step2_velocity_us_closed_loop_parity.json"] = {
        "path": str(us_path),
        "sha256": sha(us_path),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {"frozen_scenes": len(rows), "runtime": protocol["runtime_source_sha256"]}
        )
    )


if __name__ == "__main__":
    main()
