import numpy as np

from geotransfer_gap.corpus.source_only_protocol import (
    independence_conflicts,
    source_context_actors,
    source_window_identity,
    source_window_identity_sha256,
    split_label,
)


def test_source_window_identity_is_canonical_and_inclusive():
    from_catalog = {
        "recording": 8,
        "location": 3,
        "ego_track_id": 119,
        "first_frame": 7919,
    }
    from_selector = {
        "recording": "8",
        "location": "3",
        "ego": "119",
        "first_frame": "7919",
        "last_frame": "8144",
    }

    assert source_window_identity(from_catalog) == {
        "recording": 8,
        "location": 3,
        "ego_track_id": 119,
        "first_frame": 7919,
        "last_frame": 8144,
    }
    assert source_window_identity_sha256(from_catalog) == source_window_identity_sha256(
        from_selector
    )
    assert source_window_identity_sha256(dict(from_catalog, last_frame=8143)) != source_window_identity_sha256(from_catalog)


def test_source_context_reuses_converter_actor_and_movement_rules():
    start = 10
    rows = {
        # Exactly 1m raw path: moving under the converter's >=1m threshold.
        1: np.array([[10, 0, 0, 0, 0, 0], [235, 1, 0, 0, 0, 0]], dtype=float),
        # Included context actor, but stationary under the movement threshold.
        2: np.array([[10, 3, 0, 0, 0, 0], [235, 3.5, 0, 0, 0, 0]], dtype=float),
        # One raw row does not become a converted actor.
        3: np.array([[10, 5, 0, 0, 0, 0]], dtype=float),
        # Unsupported source class is dropped by the converter.
        4: np.array([[10, 7, 0, 0, 0, 0], [235, 9, 0, 0, 0, 0]], dtype=float),
        # Two raw rows but only one valid sample in the 91-step interval.
        5: np.array([[10, 11, 0, 0, 0, 0], [11, 12, 0, 0, 0, 0]], dtype=float),
    }
    meta = {
        1: {"class": "car"},
        2: {"class": "pedestrian"},
        3: {"class": "bicycle"},
        4: {"class": "motorcycle"},
        5: {"class": "bicycle"},
    }
    actors = source_context_actors(
        {"recording": 0, "location": 4, "ego": 1, "first_frame": start}, rows, meta
    )

    assert [actor["track_id"] for actor in actors] == [1, 2]
    assert actors[0]["moving"] is True
    assert actors[0]["source_window_path_m"] == 1.0
    assert actors[0]["valid_samples"] == 91
    assert actors[1]["moving"] is False


def test_independence_checks_inclusive_windows_and_all_moving_context_tracks():
    prior = {
        "recording": 4,
        "location": 2,
        "ego_track_id": 10,
        "first_frame": 0,
        "last_frame": 225,
        "moving_track_ids": [10, 11, 12],
    }
    touching = {
        "recording": 4,
        "location": 2,
        "ego_track_id": 20,
        "first_frame": 225,
        "last_frame": 450,
        "moving_track_ids": [20],
    }
    adjacent = dict(touching, first_frame=226, last_frame=451)
    shared_actor = dict(adjacent, moving_track_ids=[12, 20])

    overlap = independence_conflicts(touching, [prior])
    assert overlap[0]["inclusive_window_overlap"] is True
    assert overlap[0]["shared_moving_track_ids"] == []
    assert independence_conflicts(adjacent, [prior]) == []
    assert independence_conflicts(shared_actor, [prior])[0]["shared_moving_track_ids"] == [12]
    assert independence_conflicts(dict(adjacent, recording=5), [prior]) == []


def test_split_policy_holds_location_four_and_uses_recording_mod_five_elsewhere():
    assert split_label(4, 1) == "heldout_location_4"
    assert split_label(2, 10) == "validation_recording"
    assert split_label(1, 11) == "adaptation_recording"
