from dataclasses import FrozenInstanceError
import importlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from geotransfer_gap.config import settings, tool_path, project_path, ensure_bench
from geotransfer_gap.artifacts import reference, resolve_reference
from geotransfer_gap.conversion.pipeline import ConversionConfig, enforce_actor_capacity
from geotransfer_gap.maps.lanelet import map_paths, lanelet_polygon
from geotransfer_gap.runtime.session import frame


def test_configuration_is_immutable_and_validates_task():
    c = ConversionConfig(recording=1, ego=5, first_frame=10)
    with pytest.raises(FrozenInstanceError):
        c.recording = 9
    with pytest.raises(ValueError):
        ConversionConfig(recording=1, ego=5, first_frame=10, goal_sample=90)
    with pytest.raises(ValueError):
        ConversionConfig(recording=1, ego=5, first_frame=10, exclude_track_ids=(5,))


def test_map_choice_has_no_recording_state():
    meta = {"locationId": "1"}
    a = map_paths(meta, 7)
    b = map_paths(meta, 12)
    c = map_paths(meta, 7)
    assert a == c and a != b and "construction" in str(b[0])


def test_opposite_boundary_storage_directions_form_same_polygon():
    left = [(0, 1), (2, 1)]
    right = [(0, -1), (2, -1)]
    assert lanelet_polygon(left, right) == lanelet_polygon(left, list(reversed(right)))


def test_capacity_never_silently_drops_actors():
    enforce_actor_capacity(128)
    with pytest.raises(ValueError):
        enforce_actor_capacity(129)


def test_artifact_reference_roundtrip_and_escape():
    path = settings().artifacts / "oriented_v3/example/testing/map_000000.bin"
    assert resolve_reference(reference(path)) == path.resolve()
    with pytest.raises(ValueError):
        resolve_reference({"root": "artifacts", "path": "../../escape"})


def test_registry_and_project_paths():
    assert tool_path("pilot_ind.py").name == "pipeline.py"
    assert project_path("pilot/oriented_v3") == settings().artifacts / "oriented_v3"


def test_config_file_override(monkeypatch, tmp_path):
    cfg = tmp_path / "paths.toml"
    cfg.write_text('[paths]\nsource="/tmp/geo-test-source"\n')
    monkeypatch.setenv("GEOTRANSFER_CONFIG", str(cfg))
    assert settings().source == Path("/tmp/geo-test-source")


def entity(x=0.0, y=0.0, removed=False):
    return dict(
        x=x,
        y=y,
        removed=removed,
        traj_x=[10.0],
        traj_y=[20.0],
        heading=0.0,
        width=2.0,
        length=4.0,
        vx=1.0,
        vy=0.0,
        collision_state=0,
        movement_mode=2,
        reached_goal_this_episode=True,
    )


def test_trace_nonzero_ego_and_absent_state_normalization():
    binary = {
        "sdc_track_index": 1,
        "objects": [
            dict(id=i, type=1, traj_valid=[1], traj_x=[-10010.0], traj_y=[20.0])
            for i in range(3)
        ],
    }
    a = entity()
    b = entity(2.0, 3.0)
    c = entity(-10000.0, -10000.0)
    c["heading"] = float("inf")
    out = frame({"entities": [a, b, c]}, binary, 5)
    assert out["actors"][1]["x"] == -10018.0
    assert out["actors"][0]["reached_goal"] is False
    assert out["actors"][1]["reached_goal"] is True
    assert out["actors"][2]["heading"] is None and not out["actors"][2]["present"]
    json.dumps(out, allow_nan=False)


def test_present_nonfinite_state_rejected():
    binary = {
        "sdc_track_index": 0,
        "objects": [dict(id=1, type=1, traj_valid=[1], traj_x=[10.0], traj_y=[20.0])],
    }
    e = entity()
    e["heading"] = float("nan")
    with pytest.raises(ValueError):
        frame({"entities": [e]}, binary, 0)


def test_imports_do_not_execute_commands():
    # Each command used to parse argv or run experiments while importing.
    code = """from geotransfer_gap.config import ensure_bench\nensure_bench()\nimport importlib\nfor name in ['validation.admit_scene','validation.validate_replay','validation.trace_eval_lifecycle','planners.run_pilot_eval','corpus.catalog_ind_windows','visualization.register_background']:\n importlib.import_module('geotransfer_gap.'+name)\nprint('safe')"""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "safe"


def test_cli_works_outside_project(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "geotransfer_gap", "scenes", "list"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert len(proc.stdout.splitlines()) == 16


def test_viewer_is_standalone_and_safe(tmp_path):
    from geotransfer_gap.visualization.viewer import build

    out = build("r07_e200_f25439", tmp_path / "view.html")
    body = out.read_text()
    assert "__DATA__" not in body and "data:image/png;base64," in body
    assert "https://" not in body and "fetch(" not in body
    assert "Source recording" in body and "Converted scene" in body
