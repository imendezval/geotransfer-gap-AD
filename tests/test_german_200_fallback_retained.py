from __future__ import annotations

import pytest

from geotransfer_gap.corpus import finalize_german_200_batch as finalize
from geotransfer_gap.corpus.source_only_protocol import (
    independence_conflicts,
    source_window_identity_sha256,
)


def row(recording: int, first: int, last: int, moving: list[int], **extra) -> dict:
    candidate = {
        "recording": recording,
        "location": 1,
        "ego_track_id": 100 + first,
        "first_frame": first,
        "last_frame": last,
        "moving_track_ids": moving,
    }
    candidate["source_window_identity_sha256"] = source_window_identity_sha256(candidate)
    candidate.update(extra)
    return candidate


def alternate(candidate: dict, order: int = 1) -> dict:
    candidate = {
        **candidate,
        "arm": "Interactive100",
        "source_task_families": ["crossing"],
        "source_interaction_kinds": ["vehicle_crossing"],
        "planner_outcomes_present": False,
    }
    return {
        "replacement_order": order,
        "replacement_rule": "same_arm_same_task",
        "candidate": candidate,
    }


def primary(candidate: dict, alternates: list[dict]) -> dict:
    return {
        **candidate,
        "arm": "Interactive100",
        "source_task_families": ["crossing"],
        "source_interaction_kinds": ["vehicle_crossing"],
        "alternate_source_windows": alternates,
    }


def test_retained_set_keeps_anchor_and_every_other_frozen_primary(monkeypatch):
    anchor = row(1, 0, 225, [1])
    replaced = primary(row(2, 0, 225, [2]), [])
    unprocessed = row(3, 10, 235, [3])
    remaining = row(4, 20, 245, [4])
    replacement = row(5, 1000, 1225, [5])
    monkeypatch.setattr("geotransfer_gap.corpus.run_german_200_batch.verify_source_identity", lambda _: [])

    retained = finalize.retained_for_replacement(
        [anchor], [replaced, unprocessed, remaining], [], replaced
    )
    selected, skipped = finalize.fallback_candidates(
        primary(replaced, [alternate(replacement)]), retained
    )

    assert len(selected) == 1
    assert skipped == []
    assert selected[0]["candidate"]["source_window_identity_sha256"] == replacement["source_window_identity_sha256"]
    assert anchor in retained and unprocessed in retained and remaining in retained
    assert replaced not in retained


def test_fallback_conflicting_with_frozen_anchor_is_skipped(monkeypatch):
    anchor = row(7, 100, 325, [71])
    replacement = row(7, 325, 550, [72])
    replaced = primary(row(8, 1000, 1225, [80]), [])
    retained = finalize.retained_for_replacement([anchor], [replaced], [], replaced)
    candidate = primary(replaced, [alternate(replacement)])
    monkeypatch.setattr("geotransfer_gap.corpus.run_german_200_batch.verify_source_identity", lambda _: [])

    selected, skipped = finalize.fallback_candidates(candidate, retained)

    assert selected == []
    assert skipped[0]["reason"] == "independence_conflict"
    assert skipped[0]["details"][0]["inclusive_window_overlap"] is True
    assert skipped[0]["details"][0]["shared_moving_track_ids"] == []


def test_fallback_conflicting_with_primary_outside_current_batch_is_skipped(monkeypatch):
    replaced = primary(row(1, 0, 225, [10]), [])
    outside_current_batch = row(9, 500, 725, [92])
    replacement = row(9, 700, 925, [93])
    candidate = primary(replaced, [alternate(replacement)])
    retained = finalize.retained_for_replacement([], [replaced, outside_current_batch], [], replaced)
    monkeypatch.setattr("geotransfer_gap.corpus.run_german_200_batch.verify_source_identity", lambda _: [])

    selected, skipped = finalize.fallback_candidates(candidate, retained)

    assert selected == []
    assert skipped[0]["reason"] == "independence_conflict"
    assert skipped[0]["details"][0]["inclusive_window_overlap"] is True


def test_fallback_conflicting_with_earlier_selected_fallback_is_skipped(monkeypatch):
    replaced = primary(row(1, 0, 225, [10]), [])
    earlier_fallback = row(2, 100, 325, [22])
    replacement = row(2, 325, 550, [23])
    retained = finalize.retained_for_replacement([], [replaced], [earlier_fallback], replaced)
    candidate = primary(replaced, [alternate(replacement)])
    monkeypatch.setattr("geotransfer_gap.corpus.run_german_200_batch.verify_source_identity", lambda _: [])

    selected, skipped = finalize.fallback_candidates(candidate, retained)

    assert selected == []
    assert skipped[0]["reason"] == "independence_conflict"
    assert skipped[0]["details"][0]["inclusive_window_overlap"] is True


def test_fallback_sharing_moving_actor_with_prior_fallback_is_skipped(monkeypatch):
    replaced = primary(row(1, 0, 225, [10]), [])
    earlier_fallback = row(2, 1000, 1225, [22])
    replacement = row(2, 2000, 2225, [22, 23])
    retained = finalize.retained_for_replacement([], [replaced], [earlier_fallback], replaced)
    candidate = primary(replaced, [alternate(replacement)])
    monkeypatch.setattr("geotransfer_gap.corpus.run_german_200_batch.verify_source_identity", lambda _: [])

    selected, skipped = finalize.fallback_candidates(candidate, retained)

    assert selected == []
    assert skipped[0]["reason"] == "independence_conflict"
    assert skipped[0]["details"][0]["inclusive_window_overlap"] is False
    assert skipped[0]["details"][0]["shared_moving_track_ids"] == [22]


def test_independence_conflict_uses_inclusive_endpoints_and_all_moving_actors():
    touching = row(11, 0, 225, [111])
    endpoint_overlap = row(11, 225, 450, [112])
    shared_actor_only = row(11, 1000, 1225, [111, 113])

    overlap_conflict = independence_conflicts(endpoint_overlap, [touching])[0]
    actor_conflict = independence_conflicts(shared_actor_only, [touching])[0]

    assert overlap_conflict["inclusive_window_overlap"] is True
    assert overlap_conflict["shared_moving_track_ids"] == []
    assert actor_conflict["inclusive_window_overlap"] is False
    assert actor_conflict["shared_moving_track_ids"] == [111]


def test_cohort_evidence_fails_closed_when_frozen_files_are_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(finalize, "PROJECT_ROOT", tmp_path)

    with pytest.raises(ValueError, match="Missing frozen German-200 cohort"):
        finalize.load_frozen_cohort(tmp_path / "unknown.json", [])
