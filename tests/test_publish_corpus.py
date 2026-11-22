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


@pytest.mark.parametrize("has_gate", [False, True])
def test_publication_does_not_replace_current_when_selected_evidence_is_missing_or_stale(
        tmp_path, monkeypatch, has_gate):
    import sys

    monkeypatch.setenv("GEOTRANSFER_ARTIFACTS", str(tmp_path))
    current = tmp_path / "corpus/current.json"
    write_json(current, manifest("a", "b"))
    digest = sha256(current)
    scene = tmp_path / "candidate"
    (scene / "testing").mkdir(parents=True)
    if has_gate:
        write_json(scene / "testing/admission_smart_hybrid_startup.json", {"contract": {"old": True}})
        monkeypatch.setattr(builder.scene_contract, "build", lambda *args: {"new": True})
    selection = tmp_path / "selection.json"
    write_json(selection, {"jobs": [{"root": str(scene), "role": "control"}]})
    monkeypatch.setattr(sys, "argv", ["builder", "--selection", str(selection),
                                    "--output-prefix", str(tmp_path / "preview"), "--publish-current",
                                    "--expected-current-sha256", digest])
    with pytest.raises(ValueError, match="stale or missing"):
        builder.main()
    assert sha256(current) == digest
    assert (tmp_path / "preview_summary.json").is_file()
