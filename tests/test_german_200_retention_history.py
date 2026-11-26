import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from geotransfer_gap.artifacts import sha256
from geotransfer_gap.corpus import finalize_german_200_batch as finalize
from geotransfer_gap.corpus import run_german_200_batch as runner
from geotransfer_gap.corpus.source_only_protocol import source_window_identity_sha256


def synthetic_chain(tmp_path, monkeypatch):
    root = tmp_path / "retention"
    root.mkdir()
    records = []
    previous = None
    for index in (1, 2):
        record = finalize.seal_retention_record({
            "schema_version": 1,
            "protocol": finalize.RETENTION_PROTOCOL,
            "record_kind": "pinned_legacy_batch",
            "batch_number": index,
            "previous_record_sha256": previous,
        })
        records.append(record)
        previous = record["record_sha256"]
    history = root / "retention_history.jsonl"
    history.write_bytes(b"".join(finalize.canonical_json_bytes(row) + b"\n" for row in records))
    tip = root / "retention_tip.json"
    finalize.atomic_json(tip, {"schema_version": 1, "batch_number": 2, "record_sha256": records[-1]["record_sha256"]})
    monkeypatch.setattr(finalize, "RETENTION_ROOT", root)
    monkeypatch.setattr(finalize, "RETENTION_HISTORY_PATH", history)
    monkeypatch.setattr(finalize, "RETENTION_TIP_PATH", tip)
    monkeypatch.setattr(finalize, "RETENTION_LOCK_PATH", root / "retention_history.lock")
    monkeypatch.setattr(finalize, "BATCH1_CHAIN_SHA256", records[0]["record_sha256"])
    monkeypatch.setattr(finalize, "BATCH2_CHAIN_SHA256", records[1]["record_sha256"])
    return records, history, tip


def test_reader_rejects_omitted_duplicate_and_stale_chain_records(tmp_path, monkeypatch):
    records, history, _ = synthetic_chain(tmp_path, monkeypatch)
    parsed, _, = finalize.read_retention_history()
    assert parsed == records

    history.write_bytes(history.read_bytes() + finalize.canonical_json_bytes(records[0]) + b"\n")
    with pytest.raises(ValueError, match="omitted, reordered, or duplicate"):
        finalize.read_retention_history()

    history.write_bytes(finalize.canonical_json_bytes({**records[0], "batch_label": "changed"}) + b"\n")
    with pytest.raises(ValueError, match="stale digest"):
        finalize.read_retention_history()


def test_tip_and_atomic_publication_preserve_the_validated_prefix(tmp_path, monkeypatch):
    records, history, tip = synthetic_chain(tmp_path, monkeypatch)
    parsed, prefix = finalize.read_retention_history()
    assert parsed == records
    assert finalize.check_history_tip(parsed) is False

    tip.write_text('{"schema_version":1,"batch_number":1,"record_sha256":"stale"}\n')
    with pytest.raises(ValueError, match="tip does not match"):
        finalize.check_history_tip(parsed)
    finalize.atomic_json(tip, {"schema_version": 1, "batch_number": 2, "record_sha256": records[-1]["record_sha256"]})

    record = finalize.seal_retention_record({
        "schema_version": 1,
        "protocol": finalize.RETENTION_PROTOCOL,
        "record_kind": "finalized_batch",
        "batch_number": 3,
        "previous_record_sha256": records[-1]["record_sha256"],
    })
    updated = finalize.publish_retention_record(prefix, records, record)
    assert history.read_bytes().startswith(prefix)
    assert updated[-1] == record
    assert json.loads(tip.read_text())["record_sha256"] == record["record_sha256"]
    with pytest.raises(ValueError, match="changed before publication"):
        finalize.publish_retention_record(prefix, records, record)


def test_deterministic_source_only_successor_excludes_only_prior_primaries():
    source = []
    prior = set()
    for arm, prefix in (("Interactive100", "i"), ("Random100", "r")):
        for rank in range(36):
            identity = f"{prefix}{rank:02d}"
            source.append({"arm": arm, "source_window_identity_sha256": identity, "rank": rank + 1})
            if rank < 24:
                prior.add(identity)
    selected, ranks = finalize.deterministic_next_rows(source, prior)
    assert [row["arm"] for row in selected] == ["Interactive100"] * 12 + ["Random100"] * 12
    assert ranks["Interactive100"] == list(range(25, 37))
    assert ranks["Random100"] == list(range(25, 37))
    assert [row["source_window_identity_sha256"] for row in selected[:12]] == [f"i{i:02d}" for i in range(24, 36)]


def source_row(recording, first, last, moving):
    row = {"recording": recording, "location": 1, "ego_track_id": 100 + first,
           "first_frame": first, "last_frame": last, "moving_track_ids": moving}
    row["source_window_identity_sha256"] = source_window_identity_sha256(row)
    return row


def test_retention_fails_closed_on_invalid_source_identity_and_earlier_fallback_conflict(tmp_path):
    replaced = source_row(1, 0, 225, [10])
    earlier = source_row(2, 1000, 1225, [22])
    candidate = source_row(2, 2000, 2225, [22, 23])
    fallback_root = tmp_path / "candidate_runs/fallback"
    fallback_root.mkdir(parents=True)
    ledger = {"results": [{"queue_index": 0, "phase_fallback": {
        "candidate": candidate,
        "result": {"root": str(fallback_root), "output_tree_sha256": {},
                   "source_preflight": {"status": "source_screened", "structural_reasons": [], "physical_reasons": []}},
    }}]}
    runner = SimpleNamespace(verify_source_identity=lambda _row: [], output_tree_fingerprint=lambda _root: {})
    with pytest.raises(ValueError, match="conflicts with anchors, primaries"):
        finalize.retention_fallback_entries(ledger, [replaced], [], [replaced], [earlier], runner, tmp_path)

    runner.verify_source_identity = lambda _row: ["source changed"]
    with pytest.raises(ValueError, match="source identity is invalid"):
        finalize.retention_fallback_entries(ledger, [replaced], [], [replaced], [], runner, tmp_path)


def test_prior_batch_rejects_stale_ledger_bytes(tmp_path, monkeypatch):
    project = tmp_path / "project"
    monkeypatch.setattr(finalize, "PROJECT_ROOT", project)
    source_path = project / "artifacts/german_200_v1/queues.json"
    first_path = project / "artifacts/german_200_v1/first_batch.json"
    source_path.parent.mkdir(parents=True)
    first_path.write_text(json.dumps({"candidates": []}))
    source_rows, prior_records = [], []
    for arm, prefix in (("Interactive100", "i"), ("Random100", "r")):
        arm_rows = [{"arm": arm, "rank": rank, "source_window_identity_sha256": f"{prefix}{rank:02d}"} for rank in range(36)]
        source_rows.extend(arm_rows)
        prior_records.append(arm_rows[:12])
        if arm == "Interactive100":
            interactive = arm_rows
        else:
            random = arm_rows
    source_path.write_text(json.dumps({"candidates": source_rows}))
    prior = [
        {"record_sha256": "b1-tip", "ordered_primary_identity_sha256": [row["source_window_identity_sha256"] for row in interactive[:12] + random[:12]]},
        {"record_sha256": "b2-tip", "ordered_primary_identity_sha256": [row["source_window_identity_sha256"] for row in interactive[12:24] + random[12:24]]},
    ]
    selected, _ = finalize.deterministic_next_rows(source_rows, {
        identity for item in prior for identity in item["ordered_primary_identity_sha256"]
    })
    queue_rows = [dict(row, queue_order=index + 1 if index < 12 else index + 1,
                       next_queue_order=index + 1 if index < 12 else index - 11)
                  for index, row in enumerate(selected)]
    queue = {"batch_number": 3, "candidates": queue_rows}
    queue_path = project / "artifacts/queue.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps(queue))
    output_root = project / "artifacts/german_200_v1_runs/b3"
    output_root.mkdir(parents=True)
    runner = SimpleNamespace(
        get_rows=lambda value: value["candidates"],
        batch_owner=lambda path, qsha, root: {"queue_sha256": qsha, "output_root": str(root.resolve())},
        output_tree_fingerprint=lambda _root: {},
        verify_source_identity=lambda _row: [],
    )
    queue_sha = sha256(queue_path)
    owner = runner.batch_owner(queue_path, queue_sha, output_root)
    (output_root / "batch_owner.json").write_text(json.dumps(owner))
    ledger = {"queue_sha256": queue_sha, "queue_row_count": 24,
              "results": [{"queue_index": index, "frozen_row": row} for index, row in enumerate(queue_rows)]}
    ledger_path = output_root / "batch_ledger.json"
    ledger_path.write_text(json.dumps(ledger))
    paths = {}
    for name in ("batch_run_report.json", "batch_summary.json", "human_review_manifest.json"):
        path = output_root / name
        path.write_text(name)
        paths[name] = sha256(path)
    plan_path, receipt_path = project / "artifacts/plan.json", project / "artifacts/receipt.json"
    plan_path.write_text(json.dumps({"prior_canonical_tip_sha256": "b2-tip", "queue_sha256": queue_sha,
                                     "output_root": str(output_root.resolve())}))
    receipt_path.write_text(json.dumps({"ordered_primary_identity_sha256": [row["source_window_identity_sha256"] for row in queue_rows],
                                        "source_identity_check_problems": {}}))
    record = {
        "batch_number": 3,
        "queue_path": str(queue_path.relative_to(project)),
        "queue_sha256": queue_sha,
        "source_queue_sha256": finalize.COHORT_QUEUE_SHA256,
        "ordered_primary_identity_sha256": [row["source_window_identity_sha256"] for row in queue_rows],
        "output_root": str(output_root.resolve()),
        "owner_sha256": sha256(output_root / "batch_owner.json"),
        "ledger_sha256": sha256(ledger_path),
        "run_report_sha256": paths["batch_run_report.json"],
        "summary_sha256": paths["batch_summary.json"],
        "review_manifest_sha256": paths["human_review_manifest.json"],
        "retention_plan_path": str(plan_path.relative_to(project)),
        "retention_plan_sha256": sha256(plan_path),
        "queue_receipt_path": str(receipt_path.relative_to(project)),
        "queue_receipt_sha256": sha256(receipt_path),
        "retained_fallbacks": [],
    }
    finalize.verify_later_record(record, prior, [], source_rows, runner, [])
    ledger_path.write_text('{"queue_sha256":"changed"}')
    with pytest.raises(ValueError, match="batch_ledger.json is missing or stale"):
        finalize.verify_later_record(record, prior, [], source_rows, runner, [])


def test_completed_history_resume_reads_report_without_mutation(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    queue_path = project / "artifacts/queue.json"
    output_root = project / "artifacts/output"
    queue_path.parent.mkdir(parents=True)
    output_root.mkdir(parents=True)
    queue_path.write_text("frozen queue")
    report = output_root / "batch_run_report.json"
    report.write_text('{"queue_sha256":"frozen"}\n')
    before = report.read_bytes()
    monkeypatch.setattr(finalize, "PROJECT_ROOT", project)
    monkeypatch.setattr(finalize, "validate_source_only_next", lambda *args, **kwargs: (Path("plan"), Path("receipt"), {}))
    monkeypatch.setattr(finalize, "load_retention_cohort", lambda: ([], [], Path("first")))
    monkeypatch.setattr(finalize, "load_prior_screened_fallbacks", lambda *args: ([], []))
    verified = []
    monkeypatch.setattr(finalize, "verify_later_record", lambda *args, **kwargs: verified.append(True))
    record = {"batch_number": 3, "queue_path": str(queue_path.resolve().relative_to(project)),
              "queue_sha256": sha256(queue_path), "output_root": str(output_root.resolve())}
    records = [{"batch_number": 1}, {"batch_number": 2}, record]

    assert finalize.recover_or_read_retention(queue_path, [{"source_window_identity_sha256": "a" * 64}], output_root,
                                               {"batch_number": 3}, SimpleNamespace(), records, b"history-prefix", False)
    assert verified == [True]
    assert report.read_bytes() == before
    assert "frozen" in capsys.readouterr().out


def test_pending_completion_recovers_append_after_output_finalization(tmp_path, monkeypatch, capsys):
    records, history, tip = synthetic_chain(tmp_path, monkeypatch)
    project = tmp_path / "project"
    monkeypatch.setattr(finalize, "PROJECT_ROOT", project)
    queue_path = project / "artifacts/queue.json"
    output_root = project / "artifacts/output"
    queue_path.parent.mkdir(parents=True)
    output_root.mkdir(parents=True)
    queue_path.write_text("frozen queue")
    (output_root / "batch_run_report.json").write_text('{"status":"complete"}\n')
    (output_root / "batch_ledger.json").write_text('{"results":[]}\n')
    plan_path, receipt_path = queue_path.parent / "retention_plan.json", queue_path.parent / "source_queue_verification.json"
    plan_path.write_text("plan")
    receipt_path.write_text("receipt")
    expected = finalize.seal_retention_record({
        "schema_version": 1, "protocol": finalize.RETENTION_PROTOCOL, "record_kind": "finalized_batch",
        "batch_number": 3, "previous_record_sha256": records[-1]["record_sha256"],
        "queue_sha256": sha256(queue_path),
    })
    finalize.atomic_json(output_root / "retention_pending.json", {"protocol": finalize.RETENTION_PROTOCOL, "expected_record": expected})
    monkeypatch.setattr(finalize, "validate_source_only_next", lambda *args, **kwargs: (plan_path, receipt_path, {}))
    monkeypatch.setattr(finalize, "load_retention_cohort", lambda: ([], [], Path("first")))
    monkeypatch.setattr(finalize, "load_prior_screened_fallbacks", lambda *args: ([], []))
    monkeypatch.setattr(finalize, "retention_fallback_entries", lambda *args: [])
    monkeypatch.setattr(finalize, "completed_record", lambda *args: expected)
    monkeypatch.setattr(finalize, "verify_later_record", lambda *args, **kwargs: [])

    assert finalize.recover_or_read_retention(queue_path, [], output_root, {"batch_number": 3}, SimpleNamespace(),
                                               records, history.read_bytes(), False)
    updated, _ = finalize.read_retention_history()
    assert [row["batch_number"] for row in updated] == [1, 2, 3]
    assert json.loads(tip.read_text())["record_sha256"] == updated[-1]["record_sha256"]
    assert "complete" in capsys.readouterr().out


def test_native_runner_refuses_to_persist_after_retention_receipt(tmp_path, monkeypatch):
    queue_path = tmp_path / "queue.json"
    output_root = tmp_path / "output"
    output_root.mkdir()
    queue_path.write_text(json.dumps({"batch_number": 3, "candidates": []}))
    (output_root / "retention_pending.json").write_text("{}")
    monkeypatch.setattr(runner, "settings", lambda: SimpleNamespace())
    monkeypatch.setattr(runner, "output_namespace", lambda _cfg, _queue, _root: output_root)
    monkeypatch.setattr("sys.argv", ["runner", "--queue", str(queue_path), "--output-root", str(output_root),
                                     "--lane-oracle", str(tmp_path / "oracle.json")])

    with pytest.raises(ValueError, match="use the finalizer's read-only resume path"):
        runner.main()


def test_finalizer_publication_writes_fallback_and_reports(tmp_path, monkeypatch):
    output_root = tmp_path / "output"
    output_root.mkdir()
    queue_path = tmp_path / "plan" / "queue.json"
    queue_path.parent.mkdir()
    queue_path.write_text("{}\n")
    (output_root / "batch_owner.json").write_text(json.dumps({"queue_path": str(queue_path)}))
    (output_root / "source_support_provenance.json").write_text("{}\n")
    (output_root / "batch_independence_audit.json").write_text('{"passed":true}\n')

    primary = {"queue_index": 0, "candidate_id": "primary", "status": "source_physical_rejection",
               "frozen_row": {"arm": "Interactive100", "source_window_identity_sha256": "primary"}}
    alternate = {"arm": "Interactive100", "source_window_identity_sha256": "alternate"}
    ledger = {"results": [primary]}
    ledger_path = output_root / "batch_ledger.json"
    ledger_path.write_text(json.dumps(ledger))
    monkeypatch.setattr(finalize, "fallback_candidates", lambda _row, _retained: ([
        {"candidate": alternate, "replacement_order": 1, "replacement_rule": "same-arm"}
    ], []))
    monkeypatch.setattr(finalize, "retained_for_replacement", lambda *_args: [])
    fake_runner = SimpleNamespace(
        candidate_fingerprint=lambda *_args: {},
        output_tree_fingerprint=lambda _root: {},
        process_row=lambda *_args: {"status": "technical_rejection", "source_preflight": {
            "status": "source_screened", "structural_reasons": [], "physical_reasons": []
        }},
    )

    finalize.finish_batch_results(
        queue_path, {}, [primary["frozen_row"]], output_root, "queue-sha", {0: primary}, [], [],
        ledger, ledger_path, False, [], [], {}, {}, {}, fake_runner,
    )

    saved_ledger = json.loads(ledger_path.read_text())
    fallback = saved_ledger["results"][0]["phase_fallback"]
    assert fallback["candidate"] == alternate
    assert fallback["result"]["status"] == "technical_rejection"
    report = json.loads((output_root / "batch_run_report.json").read_text())
    summary = json.loads((output_root / "batch_summary.json").read_text())
    assert report["fallback_attempt_count"] == 1
    assert summary == report
