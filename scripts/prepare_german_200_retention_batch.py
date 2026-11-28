#!/usr/bin/env python3
"""Prepare the exact next German-200 retention queue from canonical history."""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from pathlib import Path

from geotransfer_gap.artifacts import sha256
from geotransfer_gap.corpus import finalize_german_200_batch as finalizer
from geotransfer_gap.corpus import run_german_200_batch as runner


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def prior_ids_by_arm(records: list[dict]) -> dict[str, list[str]]:
    result = {arm: [] for arm in ("Interactive100", "Random100")}
    for record in records:
        queue_path = finalizer.PROJECT_ROOT / record["queue_path"]
        if not queue_path.is_file():
            raise ValueError(f"Prior queue is missing: {queue_path}")
        prior_queue = json.loads(queue_path.read_text())
        if sha256(queue_path) != record["queue_sha256"]:
            raise ValueError(f"Prior queue hash changed: {queue_path}")
        rows = runner.get_rows(prior_queue)
        identities = [row.get("source_window_identity_sha256") for row in rows]
        if identities != record.get("ordered_primary_identity_sha256") or len(identities) != 24 or len(set(identities)) != 24:
            raise ValueError(f"Prior queue order or membership changed: {queue_path}")
        for row in rows:
            arm = row.get("arm")
            if arm not in result:
                raise ValueError(f"Unsupported prior arm: {arm}")
            result[arm].append(row["source_window_identity_sha256"])
    return result


def prepare(plan_dir: Path, output_root: Path) -> dict:
    plan_dir = plan_dir.resolve()
    output_root = output_root.resolve()
    project = finalizer.PROJECT_ROOT.resolve()
    if not plan_dir.is_relative_to(project) or not output_root.is_relative_to(project):
        raise ValueError("Plan and output paths must stay inside the repository")
    plan_dir.parent.mkdir(parents=True, exist_ok=True)
    lock_path = plan_dir.with_name(plan_dir.name + ".lock")
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"A plan writer already owns {lock_path}") from exc

    stage_dir: Path | None = None
    try:
        if plan_dir.exists() or output_root.exists():
            raise FileExistsError("Refusing to overwrite an existing plan or output namespace")
        records, _ = finalizer.read_retention_history()
        finalizer.verify_retention_roots(records, runner)
        finalizer.check_history_tip(records)
        anchors, frozen_primaries, first_batch_path = finalizer.load_retention_cohort()
        earlier_fallbacks, _ = finalizer.load_prior_screened_fallbacks(
            first_batch_path, anchors, frozen_primaries, runner
        )
        if [row["source_window_identity_sha256"] for row in earlier_fallbacks] != records[0].get("retained_fallback_identity_sha256"):
            raise ValueError("Pinned Batch 1 retained fallbacks differ from canonical history")
        verified_history = []
        for index, record in enumerate(records[2:], start=2):
            finalizer.verify_later_record(
                record, records[:index], anchors, frozen_primaries, runner,
                earlier_fallbacks, verify_primary_trees=True,
            )
            verified_history.append({
                "batch_number": record["batch_number"],
                "record_sha256": record["record_sha256"],
                "queue_sha256": record["queue_sha256"],
                "ledger_sha256": record["ledger_sha256"],
                "review_manifest_sha256": record["review_manifest_sha256"],
            })
        batch_number = len(records) + 1
        source_path = project / "artifacts/german_200_v1/queues.json"
        source_queue = json.loads(source_path.read_text())
        if sha256(source_path) != finalizer.COHORT_QUEUE_SHA256:
            raise ValueError("Pinned German-200 source queue changed")
        prior_ids = {identity for record in records for identity in record["ordered_primary_identity_sha256"]}
        selected, ranks = finalizer.deterministic_next_rows(source_queue.get("candidates", []), prior_ids)
        per_arm_count = sum(row.get("arm") == "Interactive100" for row in selected)
        expected_arms = ["Interactive100"] * per_arm_count + ["Random100"] * per_arm_count
        if (not 1 <= per_arm_count <= 12 or len(selected) != 2 * per_arm_count
                or [row.get("arm") for row in selected] != expected_arms):
            raise ValueError("Frozen rank source did not produce 1-12 ordered rows for each arm")
        rows = [dict(row) for row in selected]
        next_order_by_arm = {"Interactive100": 0, "Random100": 0}
        for index, row in enumerate(rows):
            row["queue_order"] = index + 1
            next_order_by_arm[row["arm"]] += 1
            row["next_queue_order"] = next_order_by_arm[row["arm"]]

        queue_path_relative = str((plan_dir / "next_validation_queue.json").relative_to(project))
        previous_queue = json.loads((project / records[-1]["queue_path"]).read_text())
        queue = copy.deepcopy(previous_queue)
        queue.update({
            "batch_label": f"B{batch_number}",
            "batch_number": batch_number,
            "candidates": rows,
            "source_queue_path": "artifacts/german_200_v1/queues.json",
            "source_queue_sha256": finalizer.COHORT_QUEUE_SHA256,
            "total_candidate_count": len(rows),
            "selection_scope": (
                f"Candidates are ordered Interactive100 first, then Random100, preserving each arm's frozen rank order. "
                f"Exclude only immutable primary identities from prior batches B1-B{batch_number - 1}; "
                "no outcome-conditioned selection or fallback exclusion."
            ),
        })
        queue["envelopes"] = {}
        for arm in ("Interactive100", "Random100"):
            arm_rows = [row for row in rows if row.get("arm") == arm]
            queue["envelopes"][arm] = {
                "candidate_count": len(arm_rows),
                "frozen_source_rank_order": ranks[arm],
                "ordered_source_window_identity_sha256": [row["source_window_identity_sha256"] for row in arm_rows],
                "outcome_conditioned_selection": False,
                "protocol_version": "german_random100_interactive100_source_only_v1",
                "selection": (
                    f"Next {per_arm_count} frozen primary rows in original deterministic {arm} rank order "
                    f"after excluding only B1-B{batch_number - 1} primary identities."
                ),
            }

        prior_by_arm = prior_ids_by_arm(records)
        identities = [row["source_window_identity_sha256"] for row in rows]
        selection_producers = {
            "census_german_200_v1": project / "src/geotransfer_gap/corpus/census_german_200_v1.py",
            "freeze_random_interactive_v1": project / "src/geotransfer_gap/corpus/freeze_random_interactive_v1.py",
            "source_only_protocol": project / "src/geotransfer_gap/corpus/source_only_protocol.py",
        }
        selection_producer_sha256 = {
            name: sha256(path) for name, path in selection_producers.items()
        }
        source_hashes_by_recording: dict[str, dict] = {}
        for row in rows:
            recording = str(row["recording"])
            hashes = row.get("source_hashes")
            if not isinstance(hashes, dict):
                raise ValueError(f"Missing frozen source hashes for recording {recording}")
            prior_hashes = source_hashes_by_recording.setdefault(recording, hashes)
            if prior_hashes != hashes:
                raise ValueError(f"Conflicting frozen source hashes for recording {recording}")
        source_problems = {identity: runner.verify_source_identity(row) for identity, row in zip(identities, rows)}
        source_problems = {identity: problems for identity, problems in source_problems.items() if problems}
        if source_problems:
            raise ValueError(f"Current source identities changed: {json.dumps(source_problems, sort_keys=True)}")

        stage_dir = Path(tempfile.mkdtemp(prefix=f".{plan_dir.name}.stage-", dir=plan_dir.parent))
        staged_queue = stage_dir / "next_validation_queue.json"
        write_json(staged_queue, queue)
        queue_sha = sha256(staged_queue)
        prior_tip = records[-1]["record_sha256"]
        plan = {
            "schema_version": 1,
            "protocol": "german_200_source_only_retention_plan_v1",
            "batch_number": batch_number,
            "batch_label": f"B{batch_number}",
            "status": "frozen_source_only_plan",
            "native_execution_started": False,
            "outcome_conditioned_selection": False,
            "selection_rule": (
                f"For each arm, preserve frozen candidate rank order, exclude only prior primary identities B1-B{batch_number - 1}, "
                f"then take the next {per_arm_count}; output Interactive100 then Random100."
            ),
            "queue_path": queue_path_relative,
            "queue_sha256": queue_sha,
            "source_queue_path": "artifacts/german_200_v1/queues.json",
            "source_queue_sha256": finalizer.COHORT_QUEUE_SHA256,
            "prior_canonical_tip_sha256": prior_tip,
            "prior_primary_identity_sha256_by_arm": prior_by_arm,
            "per_arm_frozen_source_rank_order": ranks,
            "primary_ordered_identity_sha256": identities,
            "output_root": str(output_root),
        }
        receipt = {
            "schema_version": 1,
            "protocol": "german_200_source_only_batch_queue_receipt_v1",
            "batch_number": batch_number,
            "queue_path": queue_path_relative,
            "queue_sha256": queue_sha,
            "source_queue_path": "artifacts/german_200_v1/queues.json",
            "source_queue_sha256": finalizer.COHORT_QUEUE_SHA256,
            "prior_canonical_tip_sha256": prior_tip,
            "legacy_retention_genesis": [
                {"batch_label": record.get("batch_label"), "batch_number": record["batch_number"],
                 "record_sha256": record["record_sha256"]}
                for record in records[:2]
            ],
            "prior_primary_identity_sha256_by_arm": prior_by_arm,
            "ordered_primary_identity_sha256": identities,
            "per_arm_frozen_source_rank_order": ranks,
            "source_hashes_by_recording": source_hashes_by_recording,
            "source_identity_check_problems": {identity: [] for identity in identities},
            "selection_producer_sha256": selection_producer_sha256,
            "plan_preparation_script_sha256": sha256(Path(__file__).resolve()),
            "verified_prior_finalized_records": verified_history,
            "outcome_conditioned_selection": False,
        }
        write_json(stage_dir / "retention_plan.json", plan)
        write_json(stage_dir / "source_queue_verification.json", receipt)
        finalizer.validate_source_only_next(
            staged_queue, queue, runner.get_rows(queue), output_root, records, runner, check_current_source=True
        )
        if plan_dir.exists() or output_root.exists():
            raise FileExistsError("Plan or output namespace appeared during preparation; refusing overwrite")
        os.rename(stage_dir, plan_dir)
        stage_dir = None
        return {
            "batch_number": batch_number,
            "queue_path": str(plan_dir / "next_validation_queue.json"),
            "queue_sha256": queue_sha,
            "plan_path": str(plan_dir / "retention_plan.json"),
            "plan_sha256": sha256(plan_dir / "retention_plan.json"),
            "receipt_path": str(plan_dir / "source_queue_verification.json"),
            "receipt_sha256": sha256(plan_dir / "source_queue_verification.json"),
            "prior_canonical_tip_sha256": prior_tip,
            "output_root": str(output_root),
            "current_source_identity_checks": len(identities),
            "native_execution_started": False,
        }
    finally:
        if stage_dir is not None and stage_dir.exists():
            for child in stage_dir.iterdir():
                child.unlink()
            stage_dir.rmdir()
        os.close(lock_fd)
        lock_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.plan_dir, args.output_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
