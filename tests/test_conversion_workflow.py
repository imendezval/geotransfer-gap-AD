from concurrent.futures import ThreadPoolExecutor

import pytest

from geotransfer_gap.conversion import workflow


def files(staging, binary=b"ok"):
    root = staging / "testing"
    root.mkdir()
    for name in ("ind_scene.json", "manifest.csv", "validation.json", "overlay.png"):
        (root / name).write_text("fixture")
    (root / "map_000000.bin").write_bytes(binary)


def test_atomic_conversion_reuse_and_conflicts(tmp_path):
    root = tmp_path / "out"
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: workflow.publish_conversion(root, files), range(2)))
    with pytest.raises(ValueError):
        workflow.publish_conversion(root, lambda temp: files(temp, b"different"))
    assert (root / "testing/map_000000.bin").read_bytes() == b"ok"
    (root / "testing/ind_stale.json").write_text("stale")
    with pytest.raises(ValueError):
        workflow.publish_conversion(root, files)


@pytest.mark.parametrize("failure", [ValueError(), KeyboardInterrupt()])
def test_conversion_failure_never_publishes(tmp_path, failure):
    root = tmp_path / "out"
    def fail(temp):
        files(temp)
        raise failure
    with pytest.raises(type(failure)):
        workflow.publish_conversion(root, fail)
    assert not (root / "testing").exists()


@pytest.mark.parametrize("frames", [(0, 1, 4, 5), (0, 1, 1, 2), (1, 0)])
def test_source_window_rejects_bad_frame_sequence(frames):
    with pytest.raises(ValueError, match="track 42"):
        workflow.validate_continuity({42: [{"frame": x} for x in frames]})


def test_source_window_accepts_consecutive_frames():
    workflow.validate_continuity({42: [{"frame": str(x)} for x in range(40, 44)]})
