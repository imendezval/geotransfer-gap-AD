import pytest

from geotransfer_gap.artifacts import read_json, sha256, write_json
from geotransfer_gap.corpus import build_smart_pilot_manifest as builder


def manifest(*names):
    return {"schema_version": 2, "scenes": [{"name": name, "root": name} for name in names]}


def test_publication_requires_nonempty_unique_and_expected_current(tmp_path):
    path = tmp_path / "current.json"
    original = manifest("a", "b")
    write_json(path, original)
    digest = sha256(path)
    for candidate, expected in ((manifest(), digest), (manifest("a", "a"), digest), (manifest("a"), None),
                                (manifest("a"), "stale")):
        with pytest.raises(ValueError):
            builder.publish_current(path, candidate, expected)
        assert sha256(path) == digest
    builder.publish_current(path, original, None)
    assert sha256(path) == digest
    builder.publish_current(path, manifest("a"), digest)
    assert read_json(path) == manifest("a")


def test_publication_writer_failure_does_not_replace_current(tmp_path, monkeypatch):
    path = tmp_path / "current.json"
    write_json(path, manifest("a"))
    digest = sha256(path)
    def fail(*_):
        raise KeyboardInterrupt
    monkeypatch.setattr(builder, "write_json", fail, raising=False)
    with pytest.raises(KeyboardInterrupt):
        builder.publish_current(path, manifest("b"), digest)
    assert sha256(path) == digest
