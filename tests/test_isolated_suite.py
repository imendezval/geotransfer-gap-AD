from pathlib import Path
from types import SimpleNamespace

import pytest

from geotransfer_gap.validation import suite


@pytest.mark.parametrize("error", [None, SystemExit(1), AssertionError(), KeyboardInterrupt()])
def test_suite_isolates_fixture_writes(tmp_path, monkeypatch, error):
    tree = tmp_path / "active"
    tree.mkdir()
    review = tree / "review.json"
    review.write_text("original")
    monkeypatch.setattr(suite, "settings", lambda: SimpleNamespace(
        artifacts=tree, runs=tmp_path / "runs", project=tmp_path))
    scratch_paths = []

    def checks(args, destination, env, project, artifacts):
        scratch_paths.append(artifacts)
        assert Path(env["GEOTRANSFER_ARTIFACTS"]) == artifacts != tree
        (artifacts / review.name).write_text("negative fixture")
        if error is not None:
            raise error

    monkeypatch.setattr(suite, "_run_checks", checks, raising=False)
    if error is None:
        suite.main([])
    else:
        with pytest.raises(type(error)):
            suite.main([])
    assert scratch_paths and not scratch_paths[0].exists()
    assert review.read_text() == "original"
