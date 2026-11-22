from collections import Counter

import pytest

from geotransfer_gap.verification_matrix import enumerate_slots


def test_cross_product_has_stable_identity_and_explicit_blocked_inputs():
    scenes = [
        {"name": f"scene-{i}", "group": "german" if i < 16 else "us",
         "source_hold_problem": None if i != 16 else "missing authoritative source"}
        for i in range(18)
    ]
    slots = enumerate_slots(scenes)
    assert slots == enumerate_slots(reversed(scenes))
    assert len(slots) == len({s["slot_id"] for s in slots}) == 504
    assert Counter(s["status"] for s in slots) == {"not_run": 492, "blocked": 12}
    assert Counter(s["startup"] for s in slots) == {"immediate": 288, "source_hold": 216}
    for slot in slots:
        assert slot["status"] == "blocked" if slot["scene"] == "scene-16" and slot["startup"] == "source_hold" else slot["status"] == "not_run"
        if slot["startup"] == "source_hold":
            assert slot["traffic"] != "expert"


def test_duplicate_episode_identity_is_rejected():
    scene = {"name": "repeated", "group": "german", "source_hold_problem": None}
    with pytest.raises(ValueError, match="duplicate"):
        enumerate_slots([scene, scene])
