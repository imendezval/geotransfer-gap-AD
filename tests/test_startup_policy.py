import copy

import numpy as np
import pytest

from geotransfer_gap.runtime import hybrid_traffic
from geotransfer_gap.runtime.startup_policy import StartupPolicy, source_hold_policy


def startup_scene():
    size = 30
    objects = []
    for i, (birth, depart, speed, kind, marked) in enumerate([
        (0, 0, 3., "vehicle", 0),          # ego
        (3, 15, 3., "vehicle", 0),         # late held birth, then release
        (0, 8, .8, "vehicle", 0),          # moves but never qualifies
        (0, 0, 3., "vehicle", 0),          # moving from birth
        (0, 0, .1, "vehicle", 0),          # low-displacement exclusion
        (0, 15, 3., "vehicle", 1),         # permanently expert owned
        (0, 15, 3., "pedestrian", 0),
        (0, 15, 3., "cyclist", 0),
    ]):
        objects.append(dict(
            id=100+i, type=kind, mark_as_expert=marked,
            valid=[int(t >= birth) for t in range(size)],
            position=[dict(x=max(t-depart+1, 0)*speed/10, y=i, z=0) for t in range(size)],
            velocity=[dict(x=speed if t >= depart else 0, y=0, z=0) for t in range(size)],
            heading=[0] * size,
        ))
    scene = {"metadata": {"sdc_track_index": 0}, "objects": objects}
    binary = {"sdc_track_index": 0, "objects": [
        dict(id=o["id"], mark_as_expert=o["mark_as_expert"],
             type={"vehicle": 1, "pedestrian": 2, "cyclist": 3}[o["type"]],
             traj_valid=o["valid"], traj_heading=np.array(o["heading"], dtype=np.float32),
             **{f"traj_{prefix}{axis}": np.array([v[axis] for v in o[field]], dtype=np.float32)
                for field, prefix in (("position", ""), ("velocity", "v"))
                for axis in "xyz"})
        for o in objects]}
    return scene, binary


def test_frozen_release_boundary_and_exclusions(monkeypatch):
    scene, binary = startup_scene()
    expected = hybrid_traffic.release_schedule(scene)
    calls = []
    monkeypatch.setattr(hybrid_traffic, "release_schedule", lambda s: calls.append(s) or expected)
    policy = source_hold_policy(scene, binary)
    assert calls == [scene]
    assert policy.releases == expected == {1: 18, 2: 30}
    assert policy.held(1, 2)
    assert policy.held(1, 17) and not policy.held(1, 18)
    assert policy.held(2, 29) and not policy.held(2, 30)
    assert all(not policy.held(i, 10) for i in (0, 3, 4, 5, 6, 7))
    assert not StartupPolicy().held(1, 10)


@pytest.mark.parametrize("field", ["order", "ego", "type", "mark", "length", "mask", "position", "velocity", "heading"])
def test_inconsistent_source_cannot_compute_release_schedule(field, monkeypatch):
    scene, binary = startup_scene()
    scene = copy.deepcopy(scene)
    obj = scene["objects"][1]
    if field == "order":
        scene["objects"].reverse()
    elif field == "ego":
        scene["metadata"]["sdc_track_index"] = 1
    elif field == "type":
        obj["type"] = "pedestrian"
    elif field == "mark":
        obj["mark_as_expert"] = 1
    elif field == "length":
        obj["velocity"].pop()
    elif field == "mask":
        obj["valid"][20] = 0
    elif field in ("position", "velocity"):
        obj[field][20]["x"] += 1
    else:
        obj["heading"][20] = 1
    monkeypatch.setattr(hybrid_traffic, "release_schedule",
                        lambda _: pytest.fail("computed before validating source"))
    with pytest.raises(ValueError, match="source_hold"):
        source_hold_policy(scene, binary)
