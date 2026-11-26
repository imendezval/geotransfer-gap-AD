"""Classify structured full-gate outcomes and run frozen structural fallbacks."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from geotransfer_gap.artifacts import sha256 as sha
from geotransfer_gap.config import PROJECT_ROOT, settings, tool_path
from geotransfer_gap.corpus.source_only_protocol import (
    independence_conflicts,
    source_window_identity_sha256,
)


STRUCTURAL_STATUSES = {"source_geometry_rejection", "source_physical_rejection"}
REVIEW_ONLY_TECHNICAL_BLOCKERS = {
    "exists:physical_overlap_review.json",
    "physical_overlap_review_current",
    "physical_overlap_review_complete",
    "source_box_overlaps_resolved",
}
RESEARCH_ONLY_CHECKS = {
    "semantic_screen",
    "rule_audit_current",
    "semantic_review_current",
    "semantic_review_complete",
    "source_supported_irrelevance_plausible",
    "interaction_audit_current",
    "interaction_claim_supported",
    "exists:rule_applicability_audit.json",
    "exists:semantic_review.json",
    "exists:interaction_fidelity_audit.json",
    "exists:semantic_review_hybrid_startup.json",
    "exists:interaction_fidelity_audit_hybrid_startup.json",
    "exists:lifecycle_trace_hybrid_startup.json",
    "exists:counterfactual_hybrid_probe.json",
    "hybrid_trace_current",
    "hybrid_lifecycle",
    "hybrid_counterfactual",
    "hybrid_us_mechanical_parity",
    "counterfactual_lifecycle",
    "exists:counterfactual_probe.json",
}
RESEARCH_ONLY_CHECKS.difference_update(
    {
        "exists:lifecycle_trace_hybrid_startup.json",
        "exists:counterfactual_hybrid_probe.json",
        "hybrid_trace_current",
        "hybrid_lifecycle",
        "hybrid_counterfactual",
    }
)


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temp, path)


def require_fingerprint_match(stored: dict | None, current: dict, label: str) -> None:
    if not isinstance(stored, dict) or stored != current:
        raise ValueError(f"Stale producer/input fingerprint: {label}")


def require_owner_match(stored: dict, expected: dict) -> None:
    if stored != expected:
        raise ValueError("Batch owner marker does not bind this frozen queue and output namespace")


def require_candidate_root(result: dict, output_root: Path, label: str) -> None:
    raw = result.get("root")
    if not raw:
        return
    candidate_root = (output_root / "candidate_runs").resolve()
    root = Path(raw).resolve()
    if root == candidate_root or not root.is_relative_to(candidate_root):
        raise ValueError(f"Candidate root escapes its owned namespace: {label}")


def gate_report(result: dict) -> tuple[dict | None, Path | None]:
    root = Path(result.get("root", "/missing"))
    path = root / "testing/admission_hybrid_startup.json"
    if not path.is_file():
        return None, None
    try:
        return json.loads(path.read_text()), path
    except (OSError, ValueError):
        return None, path


def structured_stage_failure(result: dict, gate: dict | None) -> list[dict]:
    """Recognize nonzero validation commands that wrote a deterministic fail report."""
    if gate is None:
        return []
    root = Path(result.get("root", "/missing"))
    refresh = gate.get("details", {}).get("refresh_commands", {})
    matches = []
    for stage, detail in refresh.items():
        report_names = {
            "validate_spawn.py": ("spawn_evaluation_validation.json",),
            "validate_replay.py": ("replay_validation.json",),
            "validate_parked.py": ("parked_evaluation_validation.json",),
            "probe_repeat_reset.py": ("reset_evaluation_probe.json",),
            "probe_eval_replay.py": ("evaluation_replay_probe.json",),
            "validate_spawn.py": ("spawn_evaluation_validation.json",),
        }.get(stage, ())
        for name in report_names:
            path = root / "testing" / name
            if not path.is_file():
                continue
            try:
                report = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            deterministic = report.get("passed") is False
            if name == "spawn_evaluation_validation.json":
                deterministic = deterministic or any(
                    mode.get("birth_passed") is False
                    for mode in report.get("modes", {}).values()
                )
            if name == "replay_validation.json":
                deterministic = deterministic or bool(report.get("failures"))
            if name == "parked_evaluation_validation.json":
                deterministic = deterministic or bool(report.get("exclusion_reasons"))
            if name == "reset_evaluation_probe.json":
                deterministic = deterministic or report.get("passed") is False
            if deterministic:
                matches.append({
                    "stage": stage,
                    "report": str(path.resolve()),
                    "report_sha256": sha(path),
                    "detail_excerpt": str(detail)[-1000:],
                })
                break
    return matches


def classify_primary(result: dict) -> None:
    gate, path = gate_report(result)
    if gate is None:
        return
    result.setdefault("technical_admission", {
        "technical_admitted": bool(gate.get("technical_admitted")),
        "research_admitted": bool(gate.get("research_admitted")),
        "exclusion_reasons": gate.get("exclusion_reasons", []),
        "gate_sha256": sha(path) if path and path.is_file() else None,
        "refresh_commands_passed": bool(gate.get("checks", {}).get("refresh_commands")),
        "gate_returncode": None,
    })
    if result.get("status") == "transient_error" and result.get("stage") == "technical_gate_refresh":
        structured = structured_stage_failure(result, gate)
        if structured:
            result["status"] = "technical_rejection"
            result["stage"] = "technical_gate_structured_failure"
            result["structured_failure_reports"] = structured
            result["technical_failure_note"] = "A prescribed gate command exited nonzero after writing a fresh, structured candidate-failure report; admission remains the exact unchanged gate result."
        else:
            result["unresolved_gate_command_errors"] = gate.get("details", {}).get("refresh_commands", {})

    if result.get("status") not in ("technical_rejection", "transient_error"):
        return
    failed = [
        name for name, passed in gate.get("checks", {}).items()
        if passed is False and name not in RESEARCH_ONLY_CHECKS
    ]
    if failed and set(failed).issubset(REVIEW_ONLY_TECHNICAL_BLOCKERS):
        root = Path(result.get("root", "/missing"))
        physical_path = root / "testing/physical_source_audit.json"
        physical = json.loads(physical_path.read_text()) if physical_path.is_file() else {}
        overlap_details = physical.get("source_box_actor_overlap_details", {})
        if overlap_details and all(x.get("reviewable_annotation_overlap") for x in overlap_details.values()):
            result["status"] = "review_blocked"
            result["review_blockers"] = failed
            result["technical_gate_nonpass_preserved"] = gate.get("technical_admitted") is False


def render_review_assets(result: dict, env: dict[str, str]) -> None:
    root = Path(result.get("root", "/missing"))
    rendered = {}
    for script, extra in (
        ("register_background.py", ()),
        ("render_rule_review.py", ("--steps", "10", "30", "50", "75")),
    ):
        proc = subprocess.run(
            [sys.executable, str(tool_path(script)), "--root", str(root), *extra],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        (root / f"{script}.log").write_text(proc.stdout + proc.stderr)
        rendered[script] = {
            "returncode": proc.returncode,
            "error": (proc.stderr or "")[-1000:] if proc.returncode else None,
        }
    result["review_assets"] = rendered
    result["manual_review_status"] = "pending"
    result["manual_review_created"] = False


def reusable_existing_result(result: dict, fingerprint: dict) -> bool:
    from geotransfer_gap.corpus.run_german_200_batch import reusable

    return reusable(result, fingerprint)


def fallback_candidates(primary: dict, retained: list[dict]) -> tuple[list[dict], list[dict]]:
    selected = []
    skipped = []
    primary_families = primary.get("source_task_families", [])
    primary_kinds = primary.get("source_interaction_kinds", [])
    for wrapper in sorted(primary.get("alternate_source_windows", []), key=lambda x: int(x.get("replacement_order", 0))):
        candidate = wrapper.get("candidate", {})
        order = int(wrapper.get("replacement_order", 0))
        if (
            candidate.get("arm") != primary.get("arm")
            or candidate.get("source_task_families", []) != primary_families
            or candidate.get("source_interaction_kinds", []) != primary_kinds
        ):
            skipped.append({"replacement_order": order, "reason": "arm_or_task_family_changed"})
            continue
        if candidate.get("planner_outcomes_present") is True:
            skipped.append({"replacement_order": order, "reason": "planner_outcome_present"})
            continue
        from geotransfer_gap.corpus.run_german_200_batch import verify_source_identity

        source_errors = verify_source_identity(candidate)
        if source_errors:
            skipped.append({"replacement_order": order, "reason": "source_integrity_failed", "details": source_errors})
            continue
        conflicts = independence_conflicts(candidate, retained)
        if conflicts:
            skipped.append({"replacement_order": order, "reason": "independence_conflict", "details": conflicts})
            continue
        selected.append({"replacement_order": order, "replacement_rule": wrapper.get("replacement_rule"), "candidate": candidate})
        break
    return selected, skipped


COHORT_QUEUE_SHA256 = "33069002fe04000c0b6e35213f90a219554a1accba6c9bce8230bb990d779cba"
FIRST_BATCH_SHA256 = "5af1c9ef57cb57adffbbf54a59cf74ab5181b2347c68ca4282121b9ed5a2c6a0"
SECOND_BATCH_SHA256 = "a7d39afc578cbb2e7c95e54b79ba1463e23ce0b74fc78022facc015fcb2fb11f"
FIRST_BATCH_LEDGER_SHA256 = "4076644465ae3d7a9483499bad9ab28b37a2e5effadc32a43bbba98a36dcdf4a"
BATCH1_OWNER_SHA256 = "035e8377b2e79308a104ec78237c4b7f67a6d496818301489d54f7e25707db8a"
BATCH1_REPORT_SHA256 = "f19558c5be16e0d2f14cf2f9d7e1709db9dee409db07150badb36d6fecc701d0"
BATCH1_REVIEW_SHA256 = "be0134a7c4ee48af943709353e8d55ee8bf39fd5f92c1e1d132d90d4bf1e4f3b"
BATCH2_LEDGER_SHA256 = "a6d36cd0e13375d4236b0a19cf393990e9fc0da1aaa6eb9df8f67e270329ac78"
BATCH2_OWNER_SHA256 = "741b0608c0ada55ffe2eb33b2349d31fc856b92351a86c3324edf37dbbbaebec"
BATCH2_REPORT_SHA256 = "66104de328e525ce8619888d6a3071805820d8ec9200a3ff20d731f4721af0dd"
BATCH2_REVIEW_SHA256 = "66a4841a3b511ec784ccb76f4ea465118927eb779792f6337dc63e315678c304"
RETENTION_PROTOCOL = "german_200_source_only_retention_v1"
RETENTION_ROOT = PROJECT_ROOT / "artifacts/german_200_v1_runs/retention_v1"
RETENTION_HISTORY_PATH = RETENTION_ROOT / "retention_history.jsonl"
RETENTION_TIP_PATH = RETENTION_ROOT / "retention_tip.json"
RETENTION_LOCK_PATH = RETENTION_ROOT / "retention_history.lock"


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def retention_record_sha256(record: dict) -> str:
    payload = {key: value for key, value in record.items() if key != "record_sha256"}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def seal_retention_record(record: dict) -> dict:
    sealed = dict(record)
    sealed["record_sha256"] = retention_record_sha256(sealed)
    return sealed


@contextmanager
def retention_history_lock():
    """Serialize finalizer publication and rechecks for this one frozen corpus."""
    RETENTION_ROOT.mkdir(parents=True, exist_ok=True)
    with RETENTION_LOCK_PATH.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def retained_fallback_rows_from_ledger(ledger: dict) -> list[dict]:
    retained = []
    for primary in sorted(ledger.get("results", []), key=lambda row: int(row.get("queue_index", -1))):
        choice = primary.get("phase_fallback")
        if not isinstance(choice, dict) or not isinstance(choice.get("candidate"), dict):
            continue
        result = choice.get("result")
        preflight = result.get("source_preflight", {}) if isinstance(result, dict) else {}
        if (
            preflight.get("status") == "source_screened"
            and not preflight.get("structural_reasons")
            and not preflight.get("physical_reasons")
        ):
            retained.append(choice["candidate"])
    return retained


BATCH1_CHAIN_SHA256 = "ab65e52b09c597c6c663bafe046cb79434ce4f87595c1527fea09e5c80b902fc"
BATCH2_CHAIN_SHA256 = "40bafed89a5f1ca33b33856b693a1f92d5aedbd7cd91efe3f39ebecda7650432"


def load_retention_cohort() -> tuple[list[dict], list[dict], Path]:
    queue_path = PROJECT_ROOT / "artifacts/german_200_v1/queues.json"
    first_batch_path = PROJECT_ROOT / "artifacts/german_200_v1/first_batch.json"
    if sha(queue_path) != COHORT_QUEUE_SHA256 or sha(first_batch_path) != FIRST_BATCH_SHA256:
        raise ValueError("Frozen German-200 cohort evidence hash changed")
    cohort = json.loads(queue_path.read_text())
    anchors, primaries = cohort.get("frozen_16_identity_rows"), cohort.get("candidates")
    if not isinstance(anchors, list) or len(anchors) != 16 or not isinstance(primaries, list) or len(primaries) != 200:
        raise ValueError("Missing cohort evidence: expected all 16 anchors and 200 frozen primaries")
    return anchors, primaries, first_batch_path


def _row_without_queue_order(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in {"first_batch_order", "queue_order", "next_queue_order"}}


def deterministic_next_rows(source_rows: list[dict], prior_ids: set[str]) -> tuple[list[dict], dict[str, list[int]]]:
    selected, ranks = [], {}
    for arm in ("Interactive100", "Random100"):
        ranked = [row for row in source_rows if row.get("arm") == arm]
        arm_rows = [row for row in ranked if row.get("source_window_identity_sha256") not in prior_ids][:12]
        if len(arm_rows) != 12:
            raise ValueError(f"Frozen rank queue has fewer than 12 remaining {arm} rows")
        ranks[arm] = [next(i + 1 for i, row in enumerate(ranked) if row["source_window_identity_sha256"] == chosen["source_window_identity_sha256"]) for chosen in arm_rows]
        selected.extend(arm_rows)
    return selected, ranks


def read_retention_history() -> tuple[list[dict], bytes]:
    if not RETENTION_HISTORY_PATH.is_file():
        raise ValueError("Canonical retention history is missing")
    raw = RETENTION_HISTORY_PATH.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("Canonical retention history has an incomplete tail")
    records = []
    previous = None
    for index, line in enumerate(raw.splitlines()):
        record = json.loads(line)
        if canonical_json_bytes(record) + b"\n" != line + b"\n" or record.get("record_sha256") != retention_record_sha256(record):
            raise ValueError(f"Retention record {index + 1} is noncanonical or has a stale digest")
        if record.get("batch_number") != index + 1 or record.get("previous_record_sha256") != previous:
            raise ValueError("Retention chain has an omitted, reordered, or duplicate prior")
        if record.get("protocol") != RETENTION_PROTOCOL or record.get("schema_version") != 1:
            raise ValueError("Unsupported retention history version")
        records.append(record)
        previous = record["record_sha256"]
    if len(records) < 2 or records[0].get("record_sha256") != BATCH1_CHAIN_SHA256 or records[1].get("record_sha256") != BATCH2_CHAIN_SHA256:
        raise ValueError("Retention chain does not start at the pinned B1/B2 roots")
    return records, raw


def verify_retention_roots(records: list[dict], runner) -> None:
    source_path = PROJECT_ROOT / "artifacts/german_200_v1/queues.json"
    roots = (
        (records[0], PROJECT_ROOT / "artifacts/german_200_v1/first_batch.json", FIRST_BATCH_SHA256,
         PROJECT_ROOT / "artifacts/german_200_v1_workstream_b", FIRST_BATCH_LEDGER_SHA256,
         BATCH1_OWNER_SHA256, BATCH1_REPORT_SHA256, BATCH1_REVIEW_SHA256),
        (records[1], PROJECT_ROOT / "artifacts/german_200_v1_workstream_d/next_validation_queue.json", SECOND_BATCH_SHA256,
         PROJECT_ROOT / "artifacts/german_200_v1_runs/workstream_c_batch_001", BATCH2_LEDGER_SHA256,
         BATCH2_OWNER_SHA256, BATCH2_REPORT_SHA256, BATCH2_REVIEW_SHA256),
    )
    if sha(source_path) != COHORT_QUEUE_SHA256:
        raise ValueError("Pinned German-200 source queue changed")
    for index, (record, queue_path, queue_sha, output_root, ledger_sha, owner_sha, report_sha, review_sha) in enumerate(roots, 1):
        if sha(queue_path) != queue_sha or record.get("queue_sha256") != queue_sha:
            raise ValueError(f"Pinned B{index} queue changed")
        if record.get("source_queue_sha256") != COHORT_QUEUE_SHA256:
            raise ValueError(f"Pinned B{index} source queue root changed")
        if record.get("queue_path") != str(queue_path.resolve().relative_to(PROJECT_ROOT)) or record.get("output_root") != str(output_root.resolve()):
            raise ValueError(f"Pinned B{index} output or queue root moved")
        for name, expected in (("batch_owner.json", owner_sha), ("batch_ledger.json", ledger_sha),
                               ("batch_run_report.json", report_sha), ("human_review_manifest.json", review_sha)):
            path = output_root / name
            if not path.is_file() or sha(path) != expected or record.get({
                "batch_owner.json": "owner_sha256", "batch_ledger.json": "ledger_sha256",
                "batch_run_report.json": "run_report_sha256", "human_review_manifest.json": "review_manifest_sha256",
            }[name]) != expected:
                raise ValueError(f"Pinned B{index} {name} changed")
        queue = json.loads(queue_path.read_text())
        ids = [row.get("source_window_identity_sha256") for row in runner.get_rows(queue)]
        if ids != record.get("ordered_primary_identity_sha256") or len(ids) != 24 or len(set(ids)) != 24:
            raise ValueError(f"Pinned B{index} membership/order differs from its history root")


def check_history_tip(records: list[dict], *, allow_one_behind: bool = False) -> bool:
    if not RETENTION_TIP_PATH.is_file():
        raise ValueError("Canonical retention tip is missing")
    tip = json.loads(RETENTION_TIP_PATH.read_text())
    latest = {"schema_version": 1, "batch_number": records[-1]["batch_number"], "record_sha256": records[-1]["record_sha256"]}
    if tip == latest:
        return False
    previous = {"schema_version": 1, "batch_number": records[-2]["batch_number"], "record_sha256": records[-2]["record_sha256"]} if len(records) > 2 else None
    if allow_one_behind and previous is not None and tip == previous:
        return True
    raise ValueError("Canonical retention tip does not match its append-only history")


def publish_retention_record(prefix: bytes, records: list[dict], record: dict) -> list[dict]:
    current, current_bytes = read_retention_history()
    if current != records or current_bytes != prefix or check_history_tip(current):
        raise ValueError("Canonical retention history changed before publication")
    updated = [*records, record]
    payload = prefix + canonical_json_bytes(record) + b"\n"
    temp = RETENTION_HISTORY_PATH.with_name(f"retention_history.tmp-{os.getpid()}")
    with temp.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, RETENTION_HISTORY_PATH)
    dir_fd = os.open(RETENTION_ROOT, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    atomic_json(RETENTION_TIP_PATH, {"schema_version": 1, "batch_number": record["batch_number"], "record_sha256": record["record_sha256"]})
    verified, _ = read_retention_history()
    if verified != updated:
        raise ValueError("Published retention history failed its post-write verification")
    return updated


def validate_source_only_next(queue_path: Path, queue: dict, rows: list[dict], output_root: Path,
                              records: list[dict], runner, *, check_current_source: bool) -> tuple[Path, Path, dict]:
    source_path = PROJECT_ROOT / "artifacts/german_200_v1/queues.json"
    if sha(source_path) != COHORT_QUEUE_SHA256 or queue.get("source_queue_sha256") != COHORT_QUEUE_SHA256:
        raise ValueError("Source-only queue is not bound to the pinned cohort")
    batch_number = queue.get("batch_number")
    if not isinstance(batch_number, int) or batch_number != len(records) + 1 or batch_number < 3:
        raise ValueError("Source-only queue is not the canonical next batch index")
    prior_ids = {identity for record in records for identity in record["ordered_primary_identity_sha256"]}
    source_rows = json.loads(source_path.read_text()).get("candidates", [])
    selected, ranks = deterministic_next_rows(source_rows, prior_ids)
    if len(rows) != 24 or [row.get("arm") for row in rows] != ["Interactive100"] * 12 + ["Random100"] * 12:
        raise ValueError("Next source-only queue must be 12 Interactive100 followed by 12 Random100")
    for actual, expected in zip(rows, selected):
        if _row_without_queue_order(actual) != expected:
            raise ValueError("Next queue omits, duplicates, or reorders the frozen source ranks")
    queue_sha = sha(queue_path)
    plan_path = queue_path.parent / "retention_plan.json"
    receipt_path = queue_path.parent / "source_queue_verification.json"
    if not plan_path.is_file() or not receipt_path.is_file():
        raise ValueError("Next source-only queue needs its durable plan and verification receipt")
    plan = json.loads(plan_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    prior_tip = records[-1]["record_sha256"]
    ids = [row["source_window_identity_sha256"] for row in rows]
    prior_ids_by_arm = {
        arm: [
            row["source_window_identity_sha256"]
            for prior in records
            for row in runner.get_rows(json.loads((PROJECT_ROOT / prior["queue_path"]).read_text()))
            if row.get("arm") == arm
        ]
        for arm in ("Interactive100", "Random100")
    }
    if (plan.get("batch_number") != batch_number or plan.get("queue_sha256") != queue_sha
            or plan.get("source_queue_sha256") != COHORT_QUEUE_SHA256
            or plan.get("prior_canonical_tip_sha256") != prior_tip
            or plan.get("primary_ordered_identity_sha256") != ids
            or plan.get("output_root") != str(output_root.resolve())
            or plan.get("outcome_conditioned_selection") is not False):
        raise ValueError("Frozen retention plan does not bind this queue, output root, and prior tip")
    if (receipt.get("queue_sha256") != queue_sha or receipt.get("source_queue_sha256") != COHORT_QUEUE_SHA256
            or receipt.get("ordered_primary_identity_sha256") != ids
            or receipt.get("prior_canonical_tip_sha256") != prior_tip
            or receipt.get("prior_primary_identity_sha256_by_arm") != prior_ids_by_arm
            or receipt.get("per_arm_frozen_source_rank_order") != ranks
            or receipt.get("outcome_conditioned_selection") is not False
            or any(receipt.get("source_identity_check_problems", {}).values())):
        raise ValueError("Source-only queue receipt is stale or has invalid identities")
    if check_current_source:
        failures = {row["source_window_identity_sha256"]: runner.verify_source_identity(row) for row in rows}
        failures = {identity: problems for identity, problems in failures.items() if problems}
        if failures:
            raise ValueError(f"Current source identity changed: {json.dumps(failures, sort_keys=True)}")
    return plan_path, receipt_path, receipt


def verify_later_record(record: dict, prior_records: list[dict], anchors: list[dict], primaries: list[dict], runner,
                        retained: list[dict], *, verify_primary_trees: bool = False) -> list[dict]:
    queue_path = (PROJECT_ROOT / record["queue_path"]).resolve()
    output_root = Path(record["output_root"]).resolve()
    queue = json.loads(queue_path.read_text()) if queue_path.is_file() else {}
    if (not queue_path.is_file() or sha(queue_path) != record.get("queue_sha256")
            or record.get("source_queue_sha256") != COHORT_QUEUE_SHA256
            or queue.get("batch_number") != record.get("batch_number")):
        raise ValueError("Earlier retention queue is missing or stale")
    for name, field in (("batch_owner.json", "owner_sha256"), ("batch_ledger.json", "ledger_sha256"),
                         ("batch_run_report.json", "run_report_sha256"), ("batch_summary.json", "summary_sha256"),
                         ("human_review_manifest.json", "review_manifest_sha256")):
        path = output_root / name
        if not path.is_file() or sha(path) != record.get(field):
            raise ValueError(f"Earlier retention {name} is missing or stale")
    require_owner_match(json.loads((output_root / "batch_owner.json").read_text()), runner.batch_owner(queue_path, record["queue_sha256"], output_root))
    rows = runner.get_rows(queue)
    ids = [row.get("source_window_identity_sha256") for row in rows]
    if ids != record.get("ordered_primary_identity_sha256") or len(rows) != 24 or len(set(ids)) != 24:
        raise ValueError("Earlier retention queue membership/order changed")
    source_rows = json.loads((PROJECT_ROOT / "artifacts/german_200_v1/queues.json").read_text())["candidates"]
    first = json.loads((PROJECT_ROOT / "artifacts/german_200_v1/first_batch.json").read_text())
    prior_ids = {identity for item in prior_records for identity in item["ordered_primary_identity_sha256"]}
    expected, _ = deterministic_next_rows(source_rows, prior_ids)
    if record["batch_number"] >= 3 and [_row_without_queue_order(row) for row in rows] != expected:
        raise ValueError("Earlier retention queue is not the deterministic frozen-rank successor")
    ledger = json.loads((output_root / "batch_ledger.json").read_text())
    by_index = {int(result.get("queue_index", -1)): result for result in ledger.get("results", [])}
    if ledger.get("queue_sha256") != record["queue_sha256"] or ledger.get("queue_row_count") != 24 or set(by_index) != set(range(24)) or len(by_index) != len(ledger.get("results", [])):
        raise ValueError("Earlier retention ledger is incomplete or bound to another queue")
    for index, row in enumerate(rows):
        result = by_index[index]
        if result.get("frozen_row") != row:
            raise ValueError("Earlier retention ledger differs from its frozen queue")
        _verify_result_tree(result, output_root, runner, f"batch {record['batch_number']} row {index}") if verify_primary_trees else require_candidate_root(result, output_root, f"batch {record['batch_number']} row {index}")
    plan_path = (PROJECT_ROOT / record["retention_plan_path"]).resolve()
    receipt_path = (PROJECT_ROOT / record["queue_receipt_path"]).resolve()
    if not plan_path.is_file() or sha(plan_path) != record.get("retention_plan_sha256") or not receipt_path.is_file() or sha(receipt_path) != record.get("queue_receipt_sha256"):
        raise ValueError("Earlier retention plan or source-only receipt changed")
    plan = json.loads(plan_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    if (plan.get("prior_canonical_tip_sha256") != prior_records[-1]["record_sha256"]
            or plan.get("queue_sha256") != record["queue_sha256"]
            or plan.get("output_root") != str(output_root)
            or receipt.get("ordered_primary_identity_sha256") != ids
            or any(receipt.get("source_identity_check_problems", {}).values())):
        raise ValueError("Earlier retention plan/receipt is stale")
    retained_rows = retained_fallback_rows_from_ledger(ledger)
    if len(retained_rows) != len(record.get("retained_fallbacks", [])):
        raise ValueError("Earlier retention fallback history omitted or duplicated a retained fallback")
    for candidate, entry in zip(retained_rows, record["retained_fallbacks"]):
        primary_id = entry.get("primary_identity_sha256")
        primary_matches = [row for row in rows if row["source_window_identity_sha256"] == primary_id]
        if (entry.get("candidate") != candidate or len(primary_matches) != 1
                or runner.verify_source_identity(candidate)):
            raise ValueError("Earlier retained fallback has invalid source or primary identity")
        result = by_index[rows.index(primary_matches[0])].get("phase_fallback", {}).get("result", {})
        _verify_result_tree(result, output_root, runner, "earlier retained fallback")
        conflicts = independence_conflicts(candidate, retained_for_replacement(anchors, primaries, retained, primary_matches[0]))
        if conflicts:
            raise ValueError("Earlier retained fallback conflicts with anchors, primaries, or a prior retained fallback")
        retained.append(candidate)
    return rows


def retention_fallback_entries(ledger: dict, rows: list[dict], anchors: list[dict], primaries: list[dict],
                               earlier: list[dict], runner, output_root: Path) -> list[dict]:
    entries = []
    results = {int(result["queue_index"]): result for result in ledger.get("results", [])}
    for index, row in enumerate(rows):
        result = results[index]
        choice = result.get("phase_fallback")
        if not isinstance(choice, dict) or not isinstance(choice.get("candidate"), dict):
            continue
        candidate = choice["candidate"]
        fallback = choice.get("result", {})
        preflight = fallback.get("source_preflight", {})
        if preflight.get("status") != "source_screened" or preflight.get("structural_reasons") or preflight.get("physical_reasons"):
            continue
        if runner.verify_source_identity(candidate):
            raise ValueError("Retained fallback source identity is invalid")
        conflicts = independence_conflicts(candidate, retained_for_replacement(anchors, primaries, earlier + [entry["candidate"] for entry in entries], row))
        if conflicts:
            raise ValueError("Retained fallback conflicts with anchors, primaries, or an earlier fallback")
        _verify_result_tree(fallback, output_root, runner, f"fallback for row {index}")
        entries.append({"primary_identity_sha256": row["source_window_identity_sha256"], "candidate": candidate})
    return entries


def completed_record(queue_path: Path, rows: list[dict], output_root: Path, previous: dict, plan_path: Path,
                    receipt_path: Path, ledger: dict, retained_entries: list[dict]) -> dict:
    return seal_retention_record({
        "schema_version": 1, "protocol": RETENTION_PROTOCOL, "record_kind": "finalized_batch",
        "batch_number": int(json.loads(queue_path.read_text())["batch_number"]),
        "batch_label": f"B{int(json.loads(queue_path.read_text())['batch_number'])}",
        "previous_record_sha256": previous["record_sha256"],
        "queue_path": str(queue_path.resolve().relative_to(PROJECT_ROOT)), "queue_sha256": sha(queue_path),
        "source_queue_path": "artifacts/german_200_v1/queues.json", "source_queue_sha256": COHORT_QUEUE_SHA256,
        "ordered_primary_identity_sha256": [row["source_window_identity_sha256"] for row in rows],
        "output_root": str(output_root.resolve()), "owner_sha256": sha(output_root / "batch_owner.json"),
        "ledger_sha256": sha(output_root / "batch_ledger.json"), "run_report_sha256": sha(output_root / "batch_run_report.json"),
        "summary_sha256": sha(output_root / "batch_summary.json"), "review_manifest_sha256": sha(output_root / "human_review_manifest.json"),
        "retention_plan_path": str(plan_path.resolve().relative_to(PROJECT_ROOT)), "retention_plan_sha256": sha(plan_path),
        "queue_receipt_path": str(receipt_path.resolve().relative_to(PROJECT_ROOT)), "queue_receipt_sha256": sha(receipt_path),
        "retained_fallbacks": retained_entries,
    })


def publish_pending(queue_path: Path, rows: list[dict], output_root: Path, previous: dict, records: list[dict],
                    prefix: bytes, runner, anchors: list[dict], primaries: list[dict], earlier: list[dict],
                    plan_path: Path, receipt_path: Path) -> None:
    pending_path = output_root / "retention_pending.json"
    ledger = json.loads((output_root / "batch_ledger.json").read_text())
    retained = retention_fallback_entries(ledger, rows, anchors, primaries, earlier, runner, output_root)
    record = completed_record(queue_path, rows, output_root, previous, plan_path, receipt_path, ledger, retained)
    pending = {"schema_version": 1, "protocol": RETENTION_PROTOCOL, "expected_record": record}
    atomic_json(pending_path, pending)
    verify_later_record(record, records, anchors, primaries, runner, earlier, verify_primary_trees=True)
    publish_retention_record(prefix, records, record)


def recover_or_read_retention(queue_path: Path, rows: list[dict], output_root: Path, queue: dict, runner,
                              records: list[dict], prefix: bytes, tip_behind: bool) -> bool:
    batch_number = queue.get("batch_number")
    if batch_number <= len(records):
        record = records[batch_number - 1]
        if record.get("queue_sha256") != sha(queue_path) or record.get("queue_path") != str(queue_path.resolve().relative_to(PROJECT_ROOT)) or record.get("output_root") != str(output_root.resolve()):
            raise ValueError("This retention index already belongs to another queue or moved output root")
        plan_path, receipt_path, _ = validate_source_only_next(queue_path, queue, rows, output_root, records[:batch_number - 1], runner, check_current_source=False)
        anchors, primaries, _ = load_retention_cohort()
        earlier = []
        for index, item in enumerate(records[:batch_number - 1]):
            if index == 0:
                first, audit = load_prior_screened_fallbacks(PROJECT_ROOT / "artifacts/german_200_v1/first_batch.json", anchors, primaries, runner)
                earlier.extend(first)
            elif index >= 2:
                verify_later_record(item, records[:index], anchors, primaries, runner, earlier, verify_primary_trees=False)
        verify_later_record(record, records[:batch_number - 1], anchors, primaries, runner, earlier, verify_primary_trees=True)
        if tip_behind:
            atomic_json(RETENTION_TIP_PATH, {"schema_version": 1, "batch_number": records[-1]["batch_number"], "record_sha256": records[-1]["record_sha256"]})
        print(json.dumps(json.loads((output_root / "batch_run_report.json").read_text()), indent=2))
        return True
    if batch_number != len(records) + 1:
        raise ValueError("Retention queue is not the canonical next batch index")
    pending_path = output_root / "retention_pending.json"
    if not pending_path.is_file():
        return False
    prior = records[-1]
    plan_path, receipt_path, _ = validate_source_only_next(queue_path, queue, rows, output_root, records, runner, check_current_source=False)
    pending = json.loads(pending_path.read_text())
    expected = pending.get("expected_record")
    if (pending.get("protocol") != RETENTION_PROTOCOL or not isinstance(expected, dict)
            or expected.get("queue_sha256") != sha(queue_path)
            or expected.get("previous_record_sha256") != prior["record_sha256"]):
        raise ValueError("Pending completion marker is not bound to this queue and canonical prior")
    anchors, primaries, _ = load_retention_cohort()
    earlier = []
    for index, item in enumerate(records):
        if index == 0:
            first, _ = load_prior_screened_fallbacks(PROJECT_ROOT / "artifacts/german_200_v1/first_batch.json", anchors, primaries, runner)
            earlier.extend(first)
        elif index >= 2:
            verify_later_record(item, records[:index], anchors, primaries, runner, earlier)
    ledger = json.loads((output_root / "batch_ledger.json").read_text())
    retained = retention_fallback_entries(ledger, rows, anchors, primaries, earlier, runner, output_root)
    rebuilt = completed_record(queue_path, rows, output_root, prior, plan_path, receipt_path, ledger, retained)
    if rebuilt != expected:
        raise ValueError("Pending completion marker does not match finalized output bytes")
    record = seal_retention_record(expected)
    verify_later_record(record, records, anchors, primaries, runner, earlier, verify_primary_trees=True)
    publish_retention_record(prefix, records, record)
    print(json.dumps(json.loads((output_root / "batch_run_report.json").read_text()), indent=2))
    return True


def load_frozen_cohort(queue_path: Path, rows: list[dict]) -> tuple[list[dict], list[dict], Path, bool]:
    """Load the one pinned German-200 cohort and accept only frozen Batch 1/2 queues."""
    cohort_path = PROJECT_ROOT / "artifacts/german_200_v1/queues.json"
    first_batch_path = cohort_path.parent / "first_batch.json"
    batch2_path = PROJECT_ROOT / "artifacts/german_200_v1_workstream_d/next_validation_queue.json"
    if not cohort_path.is_file() or not first_batch_path.is_file():
        raise ValueError("Missing frozen German-200 cohort or first-batch evidence")
    if sha(cohort_path) != COHORT_QUEUE_SHA256 or sha(first_batch_path) != FIRST_BATCH_SHA256:
        raise ValueError("Frozen German-200 cohort evidence hash changed")
    is_first_batch = sha(queue_path) == FIRST_BATCH_SHA256
    if not is_first_batch and (not batch2_path.is_file() or sha(queue_path) != SECOND_BATCH_SHA256):
        raise ValueError("Unsupported batch queue: prior retention evidence is only complete for frozen Batch 1/2")
    if not is_first_batch and sha(batch2_path) != SECOND_BATCH_SHA256:
        raise ValueError("Frozen Batch 2 queue evidence hash changed")

    cohort = json.loads(cohort_path.read_text())
    anchors, primaries = cohort.get("frozen_16_identity_rows"), cohort.get("candidates")
    if not isinstance(anchors, list) or len(anchors) != 16 or not isinstance(primaries, list) or len(primaries) != 200:
        raise ValueError("Missing cohort evidence: expected all 16 anchors and 200 frozen primaries")
    first_batch = json.loads(first_batch_path.read_text())
    expected_rows = first_batch["candidates"] if is_first_batch else json.loads(batch2_path.read_text())["candidates"]
    primary_by_id = {row["source_window_identity_sha256"]: row for row in primaries}
    for row, frozen in zip(rows, expected_rows):
        current = {k: v for k, v in row.items() if k not in {"first_batch_order", "queue_order", "next_queue_order"}}
        frozen_data = {k: v for k, v in frozen.items() if k not in {"first_batch_order", "queue_order", "next_queue_order"}}
        if current != frozen_data:
            raise ValueError("Missing cohort evidence: batch row differs from its frozen queue")
        if primary_by_id.get(row["source_window_identity_sha256"]) != frozen_data:
            raise ValueError("Missing cohort evidence: batch row is outside the frozen 200-primary cohort")
    if len(rows) != len(expected_rows):
        raise ValueError("Missing cohort evidence: batch row count differs from its frozen queue")
    return anchors, primaries, first_batch_path, is_first_batch


def retained_for_replacement(
    anchors: list[dict],
    primaries: list[dict],
    earlier_fallbacks: list[dict],
    replaced_primary: dict,
) -> list[dict]:
    """Keep every frozen row except the one primary whose phase is being replaced."""
    replaced_identity = source_window_identity_sha256(replaced_primary)
    matches = [row for row in primaries if source_window_identity_sha256(row) == replaced_identity]
    if len(matches) != 1:
        raise ValueError("Missing cohort evidence: replacement primary is not unique in the frozen 200-row cohort")
    return [
        *anchors,
        *(row for row in primaries if source_window_identity_sha256(row) != replaced_identity),
        *earlier_fallbacks,
    ]


def load_prior_screened_fallbacks(
    first_batch_path: Path,
    anchors: list[dict],
    primaries: list[dict],
    runner,
) -> tuple[list[dict], list[dict]]:
    """Validate prior batch choices and return only structurally retained alternates."""
    first_batch_path = first_batch_path.resolve()
    if sha(first_batch_path) != FIRST_BATCH_SHA256:
        raise ValueError("Frozen first-batch evidence hash changed")
    first_batch = json.loads(first_batch_path.read_text())
    ledger_path = first_batch_path.parent.parent / "german_200_v1_workstream_b/batch_ledger.json"
    if not ledger_path.is_file() or sha(ledger_path) != FIRST_BATCH_LEDGER_SHA256:
        raise ValueError("Missing or changed frozen Batch 1 retention ledger")
    ledger = json.loads(ledger_path.read_text())
    first_batch_rows = first_batch.get("candidates")
    if not isinstance(first_batch_rows, list):
        raise ValueError("Missing cohort evidence: prior first-batch candidates are unavailable")
    result_by_index = {int(result.get("queue_index", -1)): result for result in ledger.get("results", [])}
    if len(result_by_index) != len(first_batch_rows):
        raise ValueError("Missing cohort evidence: prior first-batch result ledger is incomplete")

    retained, audit = [], []
    for index, primary in enumerate(first_batch_rows):
        result = result_by_index.get(index)
        if result is None or result.get("frozen_row") != primary:
            raise ValueError(f"Missing Batch 1 frozen row evidence at {index}")
        if result.get("status") not in STRUCTURAL_STATUSES:
            continue
        choice = result.get("phase_fallback")
        if not isinstance(choice, dict):
            raise ValueError(f"Missing Batch 1 fallback disposition at row {index}")
        if choice.get("status") == "unavailable":
            continue
        candidate = choice.get("candidate")
        fallback_result = choice.get("result")
        order = choice.get("replacement_order")
        if not isinstance(candidate, dict) or not isinstance(fallback_result, dict) or fallback_result.get("frozen_row") != candidate:
            raise ValueError(f"Missing cohort evidence: Batch 1 fallback choice/result mismatch at row {index}")
        if not any(
            int(item.get("replacement_order", -1)) == order
            and item.get("candidate") == candidate
            and item.get("replacement_rule") == choice.get("replacement_rule")
            for item in primary.get("alternate_source_windows", [])
        ):
            raise ValueError(f"Missing cohort evidence: Batch 1 fallback is not a frozen alternate at row {index}")
        if runner.verify_source_identity(candidate):
            raise ValueError(f"Missing cohort evidence: Batch 1 fallback source changed at row {index}")
        preflight = fallback_result.get("source_preflight")
        if not isinstance(preflight, dict) or preflight.get("status") != "source_screened":
            continue
        conflicts = independence_conflicts(candidate, retained_for_replacement(anchors, primaries, retained, primary))
        audit.append({"queue_index": index, "source_window_identity_sha256": source_window_identity_sha256(candidate), "conflicts": conflicts})
        structurally_retained = not preflight.get("structural_reasons") and not preflight.get("physical_reasons")
        if conflicts and structurally_retained:
            raise ValueError(
                f"Batch 1 screened fallback conflicts with frozen cohort at row {index}: {json.dumps(conflicts, sort_keys=True)}"
            )
        if structurally_retained:
            retained.append(candidate)
    return retained, audit



def finish_batch_results(queue_path, queue, rows, output_root, queue_sha, result_by_index, anchors, frozen_primaries,
                         ledger, ledger_path, retention_batch, prior_fallbacks, prior_fallback_audit, env, support,
                         global_fingerprint, runner, retention_state=None):
    if retention_batch:
        current_records, current_prefix = read_retention_history()
        verify_retention_roots(current_records, runner)
        current_tip_behind = check_history_tip(current_records, allow_one_behind=True)
        if recover_or_read_retention(queue_path, rows, output_root, queue, runner, current_records, current_prefix, current_tip_behind):
            return True
        if current_records != retention_state[0] or current_prefix != retention_state[1] or current_tip_behind:
            raise ValueError("Canonical retention tip changed while this batch was being finalized")
    for result in result_by_index.values():
        classify_primary(result)
        if result.get("status") == "review_blocked" and "review_assets" not in result:
            render_review_assets(result, env)
        if result.get("root"):
            result["output_tree_sha256"] = runner.output_tree_fingerprint(Path(result["root"]))

    structural = {i for i, result in result_by_index.items() if result.get("status") in STRUCTURAL_STATUSES}
    earlier_fallbacks = list(prior_fallbacks)
    fallback_outcomes = []
    for index in sorted(structural):
        primary_result = result_by_index[index]
        prior_fallback = primary_result.get("phase_fallback")
        retained = retained_for_replacement(anchors, frozen_primaries, earlier_fallbacks, rows[index])
        selected, skipped = fallback_candidates(rows[index], retained)
        if not selected:
            primary_result["phase_fallback"] = {
                "status": "unavailable",
                "reason": "no prespecified alternate satisfied same-arm/task, current source hash, and recomputed independence constraints",
                "skipped_alternates": skipped,
            }
            fallback_outcomes.append(primary_result["phase_fallback"])
            continue
        wrapper = selected[0]
        alternate = wrapper["candidate"]
        alt_hash = alternate["source_window_identity_sha256"]
        fingerprint = runner.candidate_fingerprint(alternate, queue_sha, support, global_fingerprint)
        if (
            isinstance(prior_fallback, dict)
            and prior_fallback.get("candidate", {}).get("source_window_identity_sha256") == alt_hash
            and reusable_existing_result(prior_fallback.get("result", {}), fingerprint)
        ):
            fallback_result = prior_fallback["result"]
        else:
            safe = hashlib.sha256(f"{index}:{wrapper['replacement_order']}:{alt_hash}".encode()).hexdigest()[:12]
            root = output_root / "candidate_runs" / f"fallback_{index:03d}_{wrapper['replacement_order']:02d}_{safe}"
            if root.exists():
                n = 1
                while root.with_name(root.name + f"_attempt{n:02d}").exists():
                    n += 1
                root = root.with_name(root.name + f"_attempt{n:02d}")
            fallback_result = runner.process_row(index, alternate, [], root, env, fingerprint)
            fallback_result["output_tree_sha256"] = runner.output_tree_fingerprint(Path(fallback_result["root"])) if fallback_result.get("root") else {}
        fallback_result["fallback_for_queue_index"] = index
        fallback_result["fallback_replacement_order"] = wrapper["replacement_order"]
        fallback_result["replacement_rule"] = wrapper.get("replacement_rule")
        classify_primary(fallback_result)
        if fallback_result.get("status") == "review_blocked" and "review_assets" not in fallback_result:
            render_review_assets(fallback_result, env)
        if fallback_result.get("root"):
            fallback_result["output_tree_sha256"] = runner.output_tree_fingerprint(Path(fallback_result["root"]))
        primary_result["phase_fallback"] = {
            "status": fallback_result.get("status"),
            "candidate": alternate,
            "replacement_order": wrapper["replacement_order"],
            "replacement_rule": wrapper.get("replacement_rule"),
            "skipped_alternates": skipped,
            "result": fallback_result,
            "independence_recomputed_against_primary_rows": True,
        }
        fallback_outcomes.append(primary_result["phase_fallback"])
        # A structurally screened fallback now occupies the vacated phase slot,
        # regardless of its later technical outcome.
        if fallback_result.get("source_preflight", {}).get("status") == "source_screened" and not (
            fallback_result.get("source_preflight", {}).get("structural_reasons")
            or fallback_result.get("source_preflight", {}).get("physical_reasons")
        ):
            earlier_fallbacks.append(alternate)
        ledger["results"] = [result_by_index[i] for i in sorted(result_by_index)]
        ledger["fallback_updated_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(ledger_path, ledger)

    results = [result_by_index[i] for i in sorted(result_by_index)]
    ledger["results"] = results
    ledger["fallback_updated_utc"] = datetime.now(timezone.utc).isoformat()
    ledger["prior_fallback_cohort_audit"] = prior_fallback_audit
    atomic_json(ledger_path, ledger)
    write_reports(output_root, rows, results, fallback_outcomes, queue_sha, prior_fallback_audit, retention_history=retention_batch)
    if retention_batch:
        records, prefix, prior_fallbacks, _ = retention_state
        publish_pending(queue_path, rows, output_root, records[-1], records, prefix, runner,
                        anchors, frozen_primaries, prior_fallbacks,
                        queue_path.parent / "retention_plan.json",
                        queue_path.parent / "source_queue_verification.json")
    print(json.dumps(json.loads((output_root / "batch_run_report.json").read_text()), indent=2))
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    queue_path = args.queue.resolve()
    queue = json.loads(queue_path.read_text())
    from geotransfer_gap.corpus import run_german_200_batch as runner

    rows = runner.get_rows(queue)
    retention_batch = isinstance(queue.get("batch_number"), int) and queue["batch_number"] >= 3
    if retention_batch:
        anchors, frozen_primaries, first_batch_path = load_retention_cohort()
        is_first_batch = False
    else:
        anchors, frozen_primaries, first_batch_path, is_first_batch = load_frozen_cohort(queue_path, rows)
    queue_sha = sha(queue_path)
    cfg = settings()
    output_root = runner.output_namespace(cfg, queue_path, args.output_root)
    retention_state = None
    if retention_batch:
        with retention_history_lock():
            records, prefix = read_retention_history()
            verify_retention_roots(records, runner)
            tip_behind = check_history_tip(records, allow_one_behind=True)
            if recover_or_read_retention(queue_path, rows, output_root, queue, runner, records, prefix, tip_behind):
                return
            validate_source_only_next(queue_path, queue, rows, output_root, records, runner, check_current_source=True)
            prior_fallbacks, prior_fallback_audit = load_prior_screened_fallbacks(first_batch_path, anchors, frozen_primaries, runner)
            if [row["source_window_identity_sha256"] for row in prior_fallbacks] != records[0].get("retained_fallback_identity_sha256"):
                raise ValueError("Pinned Batch 1 retained fallback list differs from its history root")
            for index, record in enumerate(records[2:], start=2):
                verify_later_record(record, records[:index], anchors, frozen_primaries, runner, prior_fallbacks)
            retention_state = (records, prefix, prior_fallbacks, prior_fallback_audit)
    owner_path = output_root / "batch_owner.json"
    if not owner_path.is_file():
        raise ValueError("Batch owner marker is missing; refusing finalization")
    owner = json.loads(owner_path.read_text())
    require_owner_match(owner, runner.batch_owner(queue_path, queue_sha, output_root))
    ledger_path = output_root / "batch_ledger.json"
    ledger = json.loads(ledger_path.read_text())
    if ledger.get("queue_sha256") != queue_sha or ledger.get("queue_row_count") != len(rows):
        raise ValueError("Ledger queue provenance does not match frozen queue")
    result_by_index = {int(r["queue_index"]): r for r in ledger.get("results", [])}
    if set(result_by_index) != set(range(len(rows))):
        raise ValueError("Primary batch is incomplete; finish all frozen rows before fallback")

    os.environ["GEOTRANSFER_ARTIFACTS"] = str(output_root)
    env = dict(os.environ, GEOTRANSFER_ARTIFACTS=str(output_root), OMP_NUM_THREADS="2", MPLCONFIGDIR=os.environ.get("MPLCONFIGDIR", "/tmp/geotransfer_mpl"))

    support = json.loads((output_root / "source_support_provenance.json").read_text())
    from geotransfer_gap.runtime import late_spawn_runtime

    runtime_sha = late_spawn_runtime.load()["runtime_source_sha256"]
    runner.validate_copied_support(output_root, support, runtime_sha)
    global_fingerprint = runner.build_global_fingerprint(cfg, output_root, support, runtime_sha)
    # Validate all original and fallback producer/input stamps before changing
    # status labels, rendering assets, running another candidate, or writing a report.
    for index, result in result_by_index.items():
        require_candidate_root(result, output_root, f"primary row {index}")
        if result.get("frozen_row") != rows[index]:
            raise ValueError(f"Frozen row mismatch at primary row {index}")
        if result.get("root") and result.get("output_tree_sha256") != runner.output_tree_fingerprint(Path(result["root"])):
            raise ValueError(f"Candidate output evidence changed at primary row {index}")
        stored_fingerprint = result.get("input_fingerprint")
        if not isinstance(stored_fingerprint, dict):
            raise ValueError(f"Missing producer/input fingerprint at primary row {index}")
        require_fingerprint_match(stored_fingerprint.get("global"), global_fingerprint, f"primary row {index}")
        expected = runner.candidate_fingerprint(rows[index], queue_sha, support, global_fingerprint)
        require_fingerprint_match(stored_fingerprint, expected, f"primary row {index}")
        fallback = result.get("phase_fallback", {}).get("result")
        if fallback:
            require_candidate_root(fallback, output_root, f"fallback for row {index}")
            if fallback.get("root") and fallback.get("output_tree_sha256") != runner.output_tree_fingerprint(Path(fallback["root"])):
                raise ValueError(f"Candidate output evidence changed at fallback for row {index}")
            fallback_row = fallback.get("frozen_row")
            if fallback_row != result.get("phase_fallback", {}).get("candidate"):
                raise ValueError(f"Frozen fallback row mismatch for primary row {index}")
            fallback_fp = fallback.get("input_fingerprint")
            if not isinstance(fallback_row, dict) or not isinstance(fallback_fp, dict):
                raise ValueError(f"Missing producer/input fingerprint at fallback for row {index}")
            require_fingerprint_match(fallback_fp.get("global"), global_fingerprint, f"fallback for row {index}")
            expected_fallback = runner.candidate_fingerprint(fallback_row, queue_sha, support, global_fingerprint)
            require_fingerprint_match(fallback_fp, expected_fallback, f"fallback for row {index}")

    prior_fallbacks = []
    prior_fallback_audit = []
    if retention_batch:
        assert retention_state is not None
        prior_fallbacks, prior_fallback_audit = retention_state[2], retention_state[3]
    elif not is_first_batch:
        prior_fallbacks, prior_fallback_audit = load_prior_screened_fallbacks(
            first_batch_path, anchors, frozen_primaries, runner
        )

    if retention_batch:
        with retention_history_lock():
            completed = finish_batch_results(
                queue_path, queue, rows, output_root, queue_sha, result_by_index, anchors, frozen_primaries,
                ledger, ledger_path, retention_batch, prior_fallbacks, prior_fallback_audit, env, support,
                global_fingerprint, runner, retention_state,
            )
    else:
        completed = finish_batch_results(
            queue_path, queue, rows, output_root, queue_sha, result_by_index, anchors, frozen_primaries,
            ledger, ledger_path, retention_batch, prior_fallbacks, prior_fallback_audit, env, support,
            global_fingerprint, runner,
        )
    if completed:
        return


def write_reports(
    output_root: Path,
    frozen_rows: list[dict],
    results: list[dict],
    fallbacks: list[dict],
    queue_sha: str,
    prior_fallback_audit: list[dict] | None = None,
    *,
    retention_history: bool = False,
) -> None:
    statuses = Counter(r.get("status", "pending") for r in results)
    primary_eligible = sum(r.get("status") in {"awaiting_human_review", "technical_rejection", "review_blocked"} for r in results)
    primary_pass = sum(r.get("technical_admission", {}).get("technical_admitted") is True for r in results)
    fallback_results = [f.get("result") for f in fallbacks if f.get("result")]
    fallback_eligible = sum(r.get("status") in {"awaiting_human_review", "technical_rejection", "review_blocked"} for r in fallback_results)
    fallback_pass = sum(r.get("technical_admission", {}).get("technical_admitted") is True for r in fallback_results)
    arm_counts = {}
    for index, row in enumerate(frozen_rows):
        arm = row.get("arm", "unknown")
        summary = arm_counts.setdefault(arm, {"frozen_primary": 0, "technical_pass": 0, "review_blocked": 0, "technical_rejection": 0, "source_geometry_rejection": 0, "source_physical_rejection": 0, "transient_error": 0, "fallback_attempted": 0})
        summary["frozen_primary"] += 1
        result = results[index]
        if result.get("technical_admission", {}).get("technical_admitted") is True:
            summary["technical_pass"] += 1
        status = result.get("status")
        if status in summary:
            summary[status] += 1
        if isinstance(result.get("phase_fallback", {}).get("result"), dict):
            summary["fallback_attempted"] += 1
    review_rows = []
    for primary in results:
        for item in (primary, primary.get("phase_fallback", {}).get("result")):
            if not isinstance(item, dict) or item.get("status") not in ("awaiting_human_review", "review_blocked"):
                continue
            candidate = item.get("frozen_row", {})
            scene_root = Path(item["root"])
            testing = scene_root / "testing"
            physical_path = testing / "physical_source_audit.json"
            physical = json.loads(physical_path.read_text()) if physical_path.is_file() else {}
            review_rows.append({
                "candidate_id": item.get("candidate_id"),
                "arm": candidate.get("arm"),
                "queue_index": item.get("queue_index"),
                "phase_fallback": item.get("fallback_for_queue_index") is not None,
                "technical_status": item.get("status"),
                "technical_admitted": item.get("technical_admission", {}).get("technical_admitted"),
                "technical_gate_sha256": item.get("technical_admission", {}).get("gate_sha256"),
                "source_window_identity_sha256": candidate.get("source_window_identity_sha256"),
                "recording": candidate.get("recording"),
                "location": candidate.get("location"),
                "ego_track_id": candidate.get("ego_track_id"),
                "actor": candidate.get("actor"),
                "first_frame": candidate.get("first_frame"),
                "scene_root": str(scene_root.resolve()),
                "source_image_registration": str((testing / "source_image_registration.json").resolve()),
                "rule_review_montage": str((testing / "rule_review_montage.png").resolve()),
                "semantic_applicability_status": (item.get("semantic_applicability") or {}).get("status"),
                "semantic_applicability_flags": (item.get("semantic_applicability") or {}).get("applicability_flags", []),
                "physical_overlap_pair_count": len(physical.get("source_box_actor_overlap_details", {})),
                "physical_overlap_review_required": item.get("status") == "review_blocked",
                "review_blockers": item.get("review_blockers", []),
                "manual_review_created": False,
            })
    review_manifest_path = output_root / "human_review_manifest.json"
    atomic_json(review_manifest_path, {
        "schema_version": 1,
        "queue_sha256": queue_sha,
        "manual_reviews_created": False,
        "review_candidates": review_rows,
    })
    owner = json.loads((output_root / "batch_owner.json").read_text())
    provenance_path = Path(owner["queue_path"]).parent / "provenance.json"
    report = {
        "schema_version": 1,
        "protocol": "german_200_frozen_mixed_arm_v1",
        "queue_sha256": queue_sha,
        "primary_frozen_count": len(frozen_rows),
        "primary_status_counts": dict(statuses),
        "primary_eligible_technical_denominator": primary_eligible,
        "primary_technical_pass_count": primary_pass,
        "primary_pass_fraction_of_eligible": primary_pass / primary_eligible if primary_eligible else None,
        "raw_primary_pass_fraction_of_all_frozen": primary_pass / len(frozen_rows) if frozen_rows else None,
        "fallback_prespecified_count": sum(len(row.get("alternate_source_windows", [])) for row in frozen_rows),
        "fallback_attempt_count": len(fallback_results),
        "fallback_status_counts": dict(Counter(r.get("status", "pending") for r in fallback_results)),
        "fallback_eligible_technical_denominator": fallback_eligible,
        "fallback_technical_pass_count": fallback_pass,
        "fallback_adjusted_pass_fraction_of_eligible": (primary_pass + fallback_pass) / (primary_eligible + fallback_eligible) if primary_eligible + fallback_eligible else None,
        "arm_counts": arm_counts,
        "review_blocked_count": statuses.get("review_blocked", 0),
        "technical_gate_nonpass_preserved_count": sum(r.get("technical_gate_nonpass_preserved") is True for r in results),
        "human_review_manifest_count": len(review_rows),
        "human_review_manifest_sha256": sha(review_manifest_path),
        "source_support_provenance_sha256": sha(output_root / "source_support_provenance.json"),
        "frozen_queue_provenance_sha256": sha(provenance_path) if provenance_path.is_file() else None,
        "source_context_independence_passed": json.loads((output_root / "batch_independence_audit.json").read_text()).get("passed") is True,
        "semantic_flags_are_annotation_only": True,
        "manual_reviews_created": False,
        "fallback_policy": (
            "At most one prespecified same-arm/task alternate is attempted for each structural rejection; each is checked against all 16 anchors, all other frozen German-200 primaries, and earlier retained screened fallbacks from the authenticated append-only history."
            if retention_history else
            "At most one prespecified same-arm/task alternate is attempted for each structural rejection; each is checked against all 16 anchors, all other frozen German-200 primaries, and previously retained screened fallbacks. Batch 1/2 evidence only; unknown later batches fail closed."
        ),
        "prior_fallback_cohort_audit": prior_fallback_audit or [],
        "scope": "This frozen mixed-arm batch only. The raw primary fraction is kept separate from the technical-eligible and fallback-adjusted fractions; no historic ledger pooling.",
    }
    atomic_json(output_root / "batch_run_report.json", report)
    atomic_json(output_root / "batch_summary.json", report)


if __name__ == "__main__":
    main()
