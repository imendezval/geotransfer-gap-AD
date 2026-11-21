"""Pure matrix startup decisions using the frozen release schedule."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

import numpy as np

from geotransfer_gap.runtime import hybrid_traffic


@dataclass(frozen=True)
class StartupPolicy:
    mode: Literal["immediate", "source_hold"] = "immediate"
    window: int = 0
    releases: Mapping[int, int] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "releases", MappingProxyType(dict(self.releases)))

    def held(self, binary_index: int, step: int) -> bool:
        release = self.releases.get(binary_index)
        return self.mode == "source_hold" and release is not None and step < release


_SOURCE_TYPES = {"vehicle": 1, "pedestrian": 2, "cyclist": 3}


def source_hold_policy(scene, binary) -> StartupPolicy:
    """Validate the authoritative JSON before delegating release computation."""
    try:
        source, objects = scene["objects"], binary["objects"]
        ego = scene["metadata"]["sdc_track_index"]
        if type(ego) is not int or ego != binary["sdc_track_index"] or not 0 <= ego < len(source):
            raise ValueError("ego index does not match the binary")
        if len(source) != len(objects):
            raise ValueError("actor count does not match the binary")
        ids = [o["id"] for o in source]
        if (any(type(i) is not int for i in ids) or len(set(ids)) != len(ids)
                or ids != [o["id"] for o in objects]):
            raise ValueError("source IDs do not match unique binary-index order")
        window = len(source[ego]["valid"])
        if not window:
            raise ValueError("empty source window")
        for index, (obj, expected) in enumerate(zip(source, objects, strict=True)):
            _validate_actor(obj, expected, window, index)
    except (KeyError, TypeError, IndexError, ValueError, OverflowError) as exc:
        raise ValueError(f"source_hold source/binary mismatch: {exc}") from exc

    return StartupPolicy("source_hold", window, hybrid_traffic.release_schedule(scene))


def _validate_actor(obj, expected, window, index):
    if _SOURCE_TYPES[obj["type"]] != expected["type"]:
        raise ValueError(f"actor type mismatch at binary index {index}")
    mark = obj["mark_as_expert"]
    if mark not in (0, 1) or mark != expected["mark_as_expert"]:
        raise ValueError(f"expert ownership mismatch at binary index {index}")

    valid = np.asarray(obj["valid"])
    if (valid.shape != (window,) or valid.dtype.kind not in "bui"
            or not np.array_equal(valid, expected["traj_valid"])):
        raise ValueError(f"validity timeline mismatch at binary index {index}")

    def check(values, field):
        series = np.asarray(values, dtype=np.float32)
        if (series.shape != (window,) or not np.isfinite(series).all()
                or not np.array_equal(series, expected[field])):
            raise ValueError(f"{field} timeline mismatch at binary index {index}")

    check(obj["heading"], "traj_heading")
    for field, prefix in (("position", ""), ("velocity", "v")):
        for axis in "xyz":
            check([p[axis] for p in obj[field]], f"traj_{prefix}{axis}")
