from pathlib import Path

import pytest

from geotransfer_gap.runtime.matrix_inputs import load_binary, load_source_hold
from geotransfer_gap.config import settings


@pytest.mark.parametrize("name,count", [
    ("us_hybrid_1002fdc9826fc6d1", 9),
    ("us_smart_negative_world_739e0513c6f7cfe8", 2),
])
def test_pinned_us_source_matches_binary(name, count):
    cfg = settings()
    root = cfg.artifacts / "probes" / name
    source = cfg.reference_data / "gpudrive/validation" / f"WOMD_v1.3_{name.rsplit('_', 1)[-1]}.json"
    if not source.is_file() or not (root / "testing/map_000000.bin").is_file():
        pytest.skip("licensed US fixture unavailable")
    selected, policy = load_source_hold(root, load_binary(root), 91)
    assert selected == source
    assert policy.window == 91 and len(policy.releases) == count
