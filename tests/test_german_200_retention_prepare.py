import importlib.util
import json
from pathlib import Path

import pytest

from geotransfer_gap.artifacts import sha256
from geotransfer_gap.corpus import finalize_german_200_batch as finalize
from geotransfer_gap.corpus import run_german_200_batch as runner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/prepare_german_200_retention_batch.py"
SPEC = importlib.util.spec_from_file_location("prepare_german_200_retention_batch", SCRIPT_PATH)
prepare_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_script)


def _source_rows(per_arm):
    rows = []
    for arm, prefix in (("Interactive100", "i"), ("Random100", "r")):
        for rank in range(1, per_arm + 1):
            rows.append({
                "arm": arm,
                "rank": rank,
                "recording": 1,
                "source_hashes": {"recording": "frozen"},
                "source_window_identity_sha256": f"{prefix}{rank:03d}",
            })
    return rows


def _history(project, source_rows, batch_sizes):
    records = []
    next_rank = {"Interactive100": 1, "Random100": 1}
    identity_prefix = {"Interactive100": "i", "Random100": "r"}
    for batch_number, per_arm_count in enumerate(batch_sizes, start=1):
        rows = []
        for arm in ("Interactive100", "Random100"):
            for rank in range(next_rank[arm], next_rank[arm] + per_arm_count):
                rows.append({
                    "arm": arm,
                    "rank": rank,
                    "recording": 1,
                    "source_hashes": {"recording": "frozen"},
                    "source_window_identity_sha256": f"{identity_prefix[arm]}{rank:03d}",
                })
            next_rank[arm] += per_arm_count

        queue_path = project / f"artifacts/prior/B{batch_number}.json"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue = {
            "batch_number": batch_number,
            "batch_label": f"B{batch_number}",
            "metadata_marker": "preserve-prior-queue-metadata",
            "candidates": [
                dict(row, queue_order=index + 1, next_queue_order=index % per_arm_count + 1)
                for index, row in enumerate(rows)
            ],
        }
        queue_path.write_text(json.dumps(queue))
        identities = [row["source_window_identity_sha256"] for row in rows]
        records.append({
            "batch_number": batch_number,
            "batch_label": f"B{batch_number}",
            "record_sha256": f"tip-{batch_number}",
            "queue_path": str(queue_path.relative_to(project)),
            "queue_sha256": sha256(queue_path),
            "ordered_primary_identity_sha256": identities,
            "retained_fallback_identity_sha256": [],
            "ledger_sha256": f"ledger-{batch_number}",
            "review_manifest_sha256": f"review-{batch_number}",
        })
    return records


def _prepare_fixture(monkeypatch, tmp_path, *, per_arm_source_count, batch_sizes):
    project = tmp_path / "project"
    producer_root = project / "src/geotransfer_gap/corpus"
    producer_root.mkdir(parents=True)
    for name in ("census_german_200_v1.py", "freeze_random_interactive_v1.py", "source_only_protocol.py"):
        (producer_root / name).write_text(f"# synthetic {name}\n")
    source_path = project / "artifacts/german_200_v1/queues.json"
    source_path.parent.mkdir(parents=True)
    source_rows = _source_rows(per_arm_source_count)
    source_path.write_text(json.dumps({"candidates": source_rows}))
    records = _history(project, source_rows, batch_sizes)

    monkeypatch.setattr(finalize, "PROJECT_ROOT", project)
    monkeypatch.setattr(finalize, "COHORT_QUEUE_SHA256", sha256(source_path))
    monkeypatch.setattr(finalize, "read_retention_history", lambda: (records, b"synthetic-history"))
    monkeypatch.setattr(finalize, "verify_retention_roots", lambda *_args: None)
    monkeypatch.setattr(finalize, "check_history_tip", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(finalize, "load_retention_cohort", lambda: ([], source_rows, source_path))
    monkeypatch.setattr(finalize, "load_prior_screened_fallbacks", lambda *_args: ([], []))
    monkeypatch.setattr(finalize, "verify_later_record", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(runner, "verify_source_identity", lambda _row: [])
    return project, source_rows, records


def _run_prepare(project, batch_number):
    plan_dir = project / f"artifacts/german_200_v1_workstream_{batch_number}"
    output_root = project / f"artifacts/german_200_v1_runs/b{batch_number}"
    result = prepare_script.prepare(plan_dir, output_root)
    queue = json.loads((plan_dir / "next_validation_queue.json").read_text())
    plan = json.loads((plan_dir / "retention_plan.json").read_text())
    receipt = json.loads((plan_dir / "source_queue_verification.json").read_text())
    return result, plan_dir, output_root, queue, plan, receipt


def test_prepare_full_batch_keeps_existing_arm_order_indices_and_language(monkeypatch, tmp_path):
    project, _source_rows_for_test, _records = _prepare_fixture(
        monkeypatch, tmp_path, per_arm_source_count=36, batch_sizes=[12, 12]
    )

    _result, _plan_dir, _output_root, queue, plan, receipt = _run_prepare(project, 3)

    rows = queue["candidates"]
    assert len(rows) == 24
    assert [row["arm"] for row in rows] == ["Interactive100"] * 12 + ["Random100"] * 12
    assert [row["source_window_identity_sha256"] for row in rows] == (
        [f"i{rank:03d}" for rank in range(25, 37)]
        + [f"r{rank:03d}" for rank in range(25, 37)]
    )
    assert [row["queue_order"] for row in rows] == list(range(1, 25))
    assert [row["next_queue_order"] for row in rows] == list(range(1, 13)) * 2
    assert queue["total_candidate_count"] == 24
    assert queue["metadata_marker"] == "preserve-prior-queue-metadata"
    assert queue["selection_scope"] == (
        "Candidates are ordered Interactive100 first, then Random100, preserving each arm's frozen rank order. "
        "Exclude only immutable primary identities from prior batches B1-B2; "
        "no outcome-conditioned selection or fallback exclusion."
    )
    assert queue["envelopes"]["Interactive100"]["candidate_count"] == 12
    assert queue["envelopes"]["Interactive100"]["selection"] == (
        "Next 12 frozen primary rows in original deterministic Interactive100 rank order "
        "after excluding only B1-B2 primary identities."
    )
    assert plan["selection_rule"] == (
        "For each arm, preserve frozen candidate rank order, exclude only prior primary identities B1-B2, "
        "then take the next 12; output Interactive100 then Random100."
    )
    assert receipt["prior_primary_identity_sha256_by_arm"] == {
        "Interactive100": [f"i{rank:03d}" for rank in range(1, 25)],
        "Random100": [f"r{rank:03d}" for rank in range(1, 25)],
    }


def test_prepare_balanced_b9_tail_has_per_arm_indices_and_counted_metadata(monkeypatch, tmp_path):
    project, _source_rows_for_test, _records = _prepare_fixture(
        monkeypatch, tmp_path, per_arm_source_count=100, batch_sizes=[12] * 8
    )

    _result, _plan_dir, _output_root, queue, plan, receipt = _run_prepare(project, 9)

    rows = queue["candidates"]
    assert queue["batch_number"] == 9
    assert queue["batch_label"] == "B9"
    assert len(rows) == 8
    assert [row["arm"] for row in rows] == ["Interactive100"] * 4 + ["Random100"] * 4
    assert [row["queue_order"] for row in rows] == list(range(1, 9))
    assert [row["next_queue_order"] for row in rows] == [1, 2, 3, 4, 1, 2, 3, 4]
    assert queue["total_candidate_count"] == 8
    for arm, prefix in (("Interactive100", "i"), ("Random100", "r")):
        envelope = queue["envelopes"][arm]
        assert envelope["candidate_count"] == 4
        assert envelope["frozen_source_rank_order"] == [97, 98, 99, 100]
        assert envelope["ordered_source_window_identity_sha256"] == [f"{prefix}{rank:03d}" for rank in range(97, 101)]
        assert envelope["selection"] == (
            f"Next 4 frozen primary rows in original deterministic {arm} rank order "
            "after excluding only B1-B8 primary identities."
        )
    assert plan["batch_label"] == "B9"
    assert plan["selection_rule"] == (
        "For each arm, preserve frozen candidate rank order, exclude only prior primary identities B1-B8, "
        "then take the next 4; output Interactive100 then Random100."
    )
    assert {arm: len(ids) for arm, ids in receipt["prior_primary_identity_sha256_by_arm"].items()} == {
        "Interactive100": 96,
        "Random100": 96,
    }


def test_prepare_exhaustion_leaves_plan_and_output_uncreated(monkeypatch, tmp_path):
    project, _source_rows_for_test, _records = _prepare_fixture(
        monkeypatch, tmp_path, per_arm_source_count=100, batch_sizes=[12] * 8 + [4]
    )
    plan_dir = project / "artifacts/german_200_v1_workstream_10"
    output_root = project / "artifacts/german_200_v1_runs/b10"

    with pytest.raises(ValueError, match="exhausted for both arms"):
        prepare_script.prepare(plan_dir, output_root)

    assert not plan_dir.exists()
    assert not output_root.exists()
    assert not plan_dir.with_name(plan_dir.name + ".lock").exists()


def test_prepare_refuses_to_overwrite_existing_plan_or_output(monkeypatch, tmp_path):
    project, _source_rows_for_test, _records = _prepare_fixture(
        monkeypatch, tmp_path, per_arm_source_count=36, batch_sizes=[12, 12]
    )
    plan_dir = project / "artifacts/german_200_v1_workstream_3"
    output_root = project / "artifacts/german_200_v1_runs/b3"
    plan_dir.mkdir(parents=True)
    output_root.mkdir(parents=True)
    plan_marker = plan_dir / "existing-plan.txt"
    output_marker = output_root / "existing-output.txt"
    plan_marker.write_text("frozen plan")
    output_marker.write_text("frozen output")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        prepare_script.prepare(plan_dir, output_root)

    assert plan_marker.read_text() == "frozen plan"
    assert output_marker.read_text() == "frozen output"


def test_prior_arm_metadata_rejects_incomplete_historical_queue(monkeypatch, tmp_path):
    project, _source_rows_for_test, records = _prepare_fixture(
        monkeypatch, tmp_path, per_arm_source_count=36, batch_sizes=[12, 12]
    )
    path = project / records[1]["queue_path"]
    queue = json.loads(path.read_text())
    queue["candidates"].pop()
    path.write_text(json.dumps(queue))
    records[1]["queue_sha256"] = sha256(path)
    records[1]["ordered_primary_identity_sha256"] = [
        row["source_window_identity_sha256"] for row in queue["candidates"]
    ]

    with pytest.raises(ValueError, match="Prior queue order or membership changed"):
        prepare_script.prior_ids_by_arm(records)
