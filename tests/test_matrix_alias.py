from pathlib import Path

import pytest

from geotransfer_gap.runtime.episode_worker import prepare_scene_alias


def test_same_target_alias_race_is_idempotent(tmp_path, monkeypatch):
    from geotransfer_gap.runtime import session

    root = tmp_path / "root"
    root.mkdir()
    alias = tmp_path / "alias"

    def race(_):
        if not alias.is_symlink():
            alias.symlink_to(root, target_is_directory=True)
            raise FileExistsError("created by another process")
        return alias

    monkeypatch.setattr(session, "short_alias", race)
    assert prepare_scene_alias(root) == alias


def test_conflicting_existing_regular_alias_is_rejected(tmp_path, monkeypatch):
    from geotransfer_gap.runtime import session

    alias = tmp_path / "alias"
    alias.mkdir()
    root = tmp_path / "root"
    monkeypatch.setattr(session, "short_alias", lambda _: alias)
    with pytest.raises(RuntimeError, match="alias"):
        prepare_scene_alias(Path(root))
