"""Publish candidate attempts by producer version, without pooling obsolete gates."""

from geotransfer_gap.artifacts import resolve_reference
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import collections
import hashlib
import json
from pathlib import Path

HERE = PROJECT_ROOT
A = project_path("pilot/audits")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    names = [
        "step2_oriented_candidate_ledger",
        "step2_source_task_gates",
        "step2_source_task_addition_gates",
        "footprint_task_gates",
        "body_task_gates",
        "body_task_remaining_gates",
        "fine_phase_gates",
        "source_variant_gates",
        "source_refined_phase_gates",
        "source_refined_phase_remaining_gates",
        "source_restart_gates",
        "source_restart_velocity_gates",
        "source_restart_turns_gates",
        "source_following_scope_retry_gates",
        "source_following_phase_gates",
        "source_moving_queue_gates",
        "step2_velocity_repaired_candidate_gates",
        "third_family_candidate_gates_v1",
        "third_family_event_gates_v1",
        "third_family_fine_straight_gates",
        "third_family_r02e40_phase_gates",
    ]
    ledgers = []
    identities = set()
    for name in names:
        p = A / (name + ".json")
        data = json.loads(p.read_text())
        rows = data["results"]
        groups = collections.defaultdict(list)
        for r in rows:
            identity = (r.get("recording"), r.get("ego"), r.get("first_frame"))
            identities.add(identity)
            f = r.get("screen_fingerprints", {})
            version = json.dumps(
                {
                    k: f.get(k)
                    for k in (
                        "pilot_ind.py",
                        "late_spawn_runtime.py",
                        "hybrid_traffic.py",
                    )
                },
                sort_keys=True,
            )
            groups[version].append(r)
        ledgers.append(
            {
                "path": str(p),
                "sha256": sha(p),
                "attempts": len(rows),
                "version_groups": [
                    {
                        "producer_hashes": json.loads(k),
                        "attempts": len(v),
                        "status_counts": dict(
                            collections.Counter(
                                (r.get("status", "unspecified") for r in v)
                            )
                        ),
                    }
                    for k, v in groups.items()
                ],
            }
        )
    selection = json.loads((A / "step2_expanded_current_selection.json").read_text())
    current = []
    for job in selection["jobs"]:
        root = resolve_reference(job["root"])
        p = root / "testing/admission_smart_hybrid_startup.json"
        gate = json.loads(p.read_text())
        current.append(
            {
                "root": str(root),
                "gate_sha256": sha(p),
                "research_admitted": gate["research_admitted"],
                "exclusion_reasons": gate["exclusion_reasons"],
            }
        )
    deferred = []
    for selection_name, ledger_name in [
        ("source_moving_queue_additions", "source_moving_queue_gates"),
        ("source_following_phase_selection", "source_following_phase_gates"),
    ]:
        s = json.loads((A / (selection_name + ".json")).read_text())
        jobs = s["jobs"]
        attempted = json.loads((A / (ledger_name + ".json")).read_text())["results"]
        keys = {(r["recording"], r["ego"], r["first_frame"]) for r in attempted}
        pending = [
            j for j in jobs if (j["recording"], j["ego"], j["first_frame"]) not in keys
        ]
        deferred.append(
            {
                "selection": selection_name,
                "source_selected": len(jobs),
                "attempted_windows": len(keys),
                "deferred_not_failed": len(pending),
                "reason": "Feasibility-stage queue stopped after finding the required supported task; remaining variants belong to later expansion.",
                "candidates": pending,
            }
        )
    manifest_path = A / "step2_expanded_current_manifest.json"
    metrics = []
    for row in json.loads(manifest_path.read_text()):
        t = resolve_reference(row["root"]) / "testing"
        probe = json.loads((t / "smart_map_transfer_all_actors_probe.json").read_text())
        replay = json.loads((t / "replay_validation.json").read_text())
        interaction = json.loads(
            (t / "interaction_fidelity_audit_hybrid_startup.json").read_text()
        )
        ids = set(row["interaction_actor_ids"])
        metrics.append(
            {
                "root": row["root"],
                "source_feature_audit": probe["source_feature_audit"],
                "max_expert_replay_position_error_m": replay[
                    "max_expert_replay_position_error_m"
                ],
                "max_expert_replay_heading_error_rad": replay[
                    "max_expert_replay_heading_error_rad"
                ],
                "primary_interactions": [
                    r
                    for r in interaction["actor_opportunities"]
                    if r["track_id"] in ids
                ],
                "report_sha256": {
                    n: sha(t / n)
                    for n in (
                        "smart_map_transfer_all_actors_probe.json",
                        "replay_validation.json",
                        "interaction_fidelity_audit_hybrid_startup.json",
                    )
                },
            }
        )
    (A / "step2_current_fidelity_metrics.json").write_text(
        json.dumps(
            {
                "producer_sha256": sha(Path(__file__)),
                "manifest_sha256": sha(manifest_path),
                "scope": "Source expert-state and primary encounter fidelity, not arbitrary interactive behavior equivalence.",
                "scenes": metrics,
            },
            indent=2,
        )
        + "\n"
    )
    result = {
        "tool_sha256": sha(Path(__file__)),
        "historical_ledgers": ledgers,
        "total_attempt_rows": sum((l["attempts"] for l in ledgers)),
        "distinct_source_windows_attempted": len(identities),
        "counting_policy": "Counts are retained ledger rows, not every historical actor-pair attempt: older runners consolidated same-window actor assessments. Source catalogs retain all pairs. Revisits/versions are not pooled as current rejection rates. Current gates/independence are separate; the repaired queue preserves actor-pair/version records and serializes shared-scene writes.",
        "current_gate_decisions": current,
        "current_manifest_sha256": sha(manifest_path),
        "current_selection_summary": json.loads(
            (A / "step2_expanded_current_summary.json").read_text()
        ),
        "original_pilot_current_exclusion": {
            "path": str(A / "step2_original_pilot_current_exclusion.json"),
            "sha256": sha(A / "step2_original_pilot_current_exclusion.json"),
        },
        "aerial_review_backlog": {
            "path": str(A / "step2_projection_review_backlog.json"),
            "sha256": sha(A / "step2_projection_review_backlog.json"),
        },
        "deferred_source_candidates": deferred,
    }
    result["third_family_source_catalogs"] = []
    for name in (
        "third_family_source_selection_v1",
        "third_family_event_selection_v1",
        "third_family_event_fine_selection_v1",
    ):
        path = A / (name + ".json")
        data = json.loads(path.read_text())
        jobs = data["jobs"]
        result["third_family_source_catalogs"].append(
            {
                "path": str(path),
                "sha256": sha(path),
                "positive_windows": len(jobs),
                "distinct_source_tasks": len(
                    {(r["recording"], r["ego"], r["actor"]) for r in jobs}
                ),
                "scope": "Source-only search catalogs overlap; do not sum them as independent scene counts.",
            }
        )
    (A / "step2_candidate_flow.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "attempt_rows": result["total_attempt_rows"],
                "distinct_source_windows": len(identities),
            }
        )
    )


if __name__ == "__main__":
    main()
