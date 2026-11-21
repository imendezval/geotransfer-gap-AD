from dataclasses import FrozenInstanceError
from itertools import product
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from geotransfer_gap import execution


CONTROLLERS = ("expert", "idm", "ppo", "smart")


def parse_protocol(*options):
    args = execution.build_parser().parse_args(["--scene", "fixture", *options])
    return execution.normalize_protocol(args)


@pytest.mark.parametrize(
    "ego,traffic,startup",
    [
        (ego, traffic, startup)
        for ego, traffic in product(CONTROLLERS, repeat=2)
        for startup in ("immediate", "source_hold")
        if not (traffic == "expert" and startup == "source_hold")
    ],
)
def test_all_28_new_controller_protocols_are_normalized(ego, traffic, startup):
    protocol = parse_protocol(
        "--ego",
        ego,
        "--traffic",
        traffic,
        "--traffic-startup",
        startup,
    )

    assert isinstance(protocol, execution.RunProtocol)
    assert protocol.selection == "matrix"
    assert (protocol.ego, protocol.traffic, protocol.traffic_startup) == (
        ego,
        traffic,
        startup,
    )
    with pytest.raises(FrozenInstanceError):
        protocol.ego = "expert"


def test_new_pair_startup_defaults_to_immediate():
    protocol = parse_protocol("--ego", "smart", "--traffic", "idm")
    assert protocol.traffic_startup == "immediate"


@pytest.mark.parametrize(
    "options",
    [
        ("--planner", "smart", "--planner", "expert"),
        ("--ego", "smart", "--ego", "ppo"),
        ("--traffic", "idm", "--traffic", "ppo"),
        ("--traffic-startup", "immediate", "--traffic-startup", "source_hold"),
    ],
)
def test_conflicting_repeated_selectors_are_rejected(options):
    with pytest.raises(SystemExit):
        execution.build_parser().parse_args(["--scene", "fixture", *options])


@pytest.mark.parametrize(
    "options",
    [
        ("--ego", "ppo"),
        ("--traffic-startup", "source_hold"),
        ("--ego", "smart", "--traffic", "hybrid_startup"),
        ("--ego", "smart", "--traffic", "idm", "--planner", "smart"),
        ("--ego", "expert", "--traffic", "idm", "--planner", "expert"),
        ("--ego", "smart", "--traffic", "expert", "--traffic-startup", "source_hold"),
        ("--planner", "smart", "--traffic", "expert"),
        ("--planner", "smart", "--traffic", "ppo"),
        ("--planner", "smart", "--traffic", "smart"),
        ("--planner", "expert", "--traffic", "idm"),
        ("--planner", "expert", "--traffic", "hybrid_startup"),
        ("--planner", "smart", "--traffic-startup", "immediate"),
        ("--planner", "bb"),
        ("--planner", "smart", "--bb-args", "--planner.type", "pdm"),
        ("--planner", "bb", "--diagnostic", "--traffic", "idm"),
        ("--preset", "smart_hybrid_baseline", "--traffic", "idm"),
        ("--preset", "smart_hybrid_baseline", "--planner", "expert"),
        ("--preset", "smart_hybrid_baseline", "--ego", "smart", "--traffic", "idm"),
    ],
)
def test_contradictory_or_unsupported_selection_is_rejected(options):
    with pytest.raises(ValueError):
        parse_protocol(*options)


def test_legacy_defaults_and_hybrid_alias_keep_legacy_meaning():
    default = parse_protocol()
    assert default.selection == "legacy"
    assert default.legacy_planner == "smart"
    assert (default.ego, default.traffic, default.traffic_startup) == (
        "smart",
        "idm",
        "source_hold",
    )
    assert default.legacy_traffic == "hybrid_startup"

    explicit_alias = parse_protocol("--planner", "smart", "--traffic", "hybrid_startup")
    assert explicit_alias.legacy_planner == "smart"
    assert explicit_alias.legacy_traffic == "hybrid_startup"
    assert (explicit_alias.traffic, explicit_alias.traffic_startup) == (
        "idm",
        "source_hold",
    )


def test_legacy_smart_idm_is_immediate_and_expert_remains_full_replay():
    smart_idm = parse_protocol("--planner", "smart", "--traffic", "idm")
    assert smart_idm.legacy_planner == "smart"
    assert (smart_idm.traffic, smart_idm.traffic_startup) == ("idm", "immediate")

    expert = parse_protocol("--planner", "expert")
    assert expert.legacy_planner == "expert"
    assert (expert.ego, expert.traffic) == ("expert", "expert")


def test_named_baseline_is_exact_legacy_alias():
    preset = parse_protocol("--preset", "smart_hybrid_baseline")
    legacy = parse_protocol("--planner", "smart", "--traffic", "hybrid_startup")
    assert preset.selection == "legacy"
    assert preset.preset == "smart_hybrid_baseline"
    assert (
        preset.legacy_planner,
        preset.ego,
        preset.traffic,
        preset.traffic_startup,
        preset.legacy_traffic,
    ) == (
        legacy.legacy_planner,
        legacy.ego,
        legacy.traffic,
        legacy.traffic_startup,
        legacy.legacy_traffic,
    )


def test_bb_bridge_preserves_remainder_arguments():
    protocol = parse_protocol(
        "--planner",
        "bb",
        "--diagnostic",
        "--bb-args",
        "--planner.type",
        "pdm",
        "--traffic.type",
        "expert",
    )
    assert protocol.selection == "bb"
    assert protocol.legacy_planner == "bb"
    assert protocol.diagnostic is True
    assert protocol.bb_args == ("--planner.type", "pdm", "--traffic.type", "expert")


def test_bb_bridge_main_passes_remainder_to_existing_runner(monkeypatch, tmp_path):
    scene = tmp_path / "scene"
    scene.mkdir()
    destination = tmp_path / "run"
    calls = []

    def create_run(_):
        destination.mkdir()
        return destination

    monkeypatch.setattr(execution, "scene_root", lambda _: scene)
    monkeypatch.setattr(execution, "new_run", create_run)
    monkeypatch.setattr(execution, "settings", lambda: SimpleNamespace(bench=tmp_path))
    monkeypatch.setattr(execution, "tool_path", lambda _: tmp_path / "run_pilot_eval.py")
    monkeypatch.setattr(execution, "reference", lambda _: {"root": "artifacts", "path": "scene"})
    monkeypatch.setattr(execution.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    execution.main(
        [
            "--scene",
            str(scene),
            "--planner",
            "bb",
            "--diagnostic",
            "--bb-args",
            "--planner.type",
            "pdm",
            "--traffic.type",
            "expert",
        ]
    )

    assert calls[0][0][0][-4:] == [
        "--planner.type",
        "pdm",
        "--traffic.type",
        "expert",
    ]
    assert calls[0][1]["env"]["GEOTRANSFER_ALLOW_UNVALIDATED"] == "1"


def test_manifest_selection_and_diagnostic_are_protocol_fields():
    args = execution.build_parser().parse_args(
        ["--manifest", "scenes.json", "--planner", "smart", "--diagnostic"]
    )
    protocol = execution.normalize_protocol(args)
    assert protocol.scene is None
    assert protocol.manifest == Path("scenes.json")
    assert protocol.diagnostic is True


def test_help_describes_new_and_legacy_selectors(capsys):
    with pytest.raises(SystemExit) as result:
        execution.main(["--help"])
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    for option in ("--ego", "--traffic", "--traffic-startup", "--preset", "--bb-args"):
        assert option in help_text
    assert "smart_hybrid_baseline" in help_text


def test_invalid_protocol_does_not_create_run_directory(monkeypatch, tmp_path, capsys):
    runs = tmp_path / "runs"
    monkeypatch.setenv("GEOTRANSFER_RUNS", str(runs))
    scene = Path(__file__).resolve().parents[1] / "artifacts/oriented_v3/r07_e200_f25439"

    with pytest.raises(SystemExit) as result:
        execution.main(
            [
                "--scene",
                str(scene),
                "--ego",
                "smart",
                "--traffic",
                "expert",
                "--traffic-startup",
                "source_hold",
            ]
        )

    assert result.value.code == 2
    assert "source_hold" in capsys.readouterr().err
    assert not runs.exists()


@pytest.mark.parametrize(
    "selection,diagnostic_requested",
    [("scene", False), ("scene", True), ("manifest", False)],
)
@pytest.mark.parametrize("ego,traffic", list(product(CONTROLLERS, repeat=2)))
def test_matrix_run_metadata_never_claims_research_admission(
    monkeypatch, tmp_path, selection, diagnostic_requested, ego, traffic
):
    scene = tmp_path / "scene"
    scene.mkdir()
    destination = tmp_path / "matrix-run"
    calls = []

    def create_run(label):
        assert label == f"{ego}_{traffic}"
        destination.mkdir()
        return destination

    monkeypatch.setattr(execution, "scene_root", lambda _: scene)
    monkeypatch.setattr(execution, "new_run", create_run)
    monkeypatch.setattr(execution, "reference", lambda _: {"root": "project", "path": "scene"})
    monkeypatch.setattr(execution, "sha256", lambda _: "binary-hash")
    if selection == "manifest":
        monkeypatch.setattr(
            execution,
            "read_manifest",
            lambda _: [
                {"name": "scene", "root": str(scene), "binary_sha256": "binary-hash"}
            ],
        )
    monkeypatch.setattr(
        execution.subprocess,
        "run",
        lambda cmd, **kwargs: calls.append((cmd, kwargs)),
    )

    options = (
        ["--scene", str(scene)]
        if selection == "scene"
        else ["--manifest", str(tmp_path / "manifest.json")]
    )
    if diagnostic_requested:
        options.append("--diagnostic")
    result = execution.main(
        options + ["--ego", ego, "--traffic", traffic, "--steps", "12"]
    )

    assert result == destination
    assert calls[0][0][1:3] == ["-m", "geotransfer_gap.runtime.episode_worker"]
    command = calls[0][0]
    assert command[command.index("--ego") + 1] == ego
    assert command[command.index("--traffic") + 1] == traffic
    assert calls[0][1]["check"] is True
    assert (destination / "scene/trace.json").parent.is_dir()
    assert (destination / "run.json").is_file()
    run_record = json.loads((destination / "run.json").read_text())
    row = run_record["results"][0]
    assert run_record["diagnostic_only"] is True
    assert row["diagnostic_only"] is True
    assert run_record["diagnostic_requested"] is diagnostic_requested
    assert row["diagnostic_requested"] is diagnostic_requested
    assert run_record["research_admission_status"] == "not_established"
    assert row["research_admission_status"] == "not_established"


def test_legacy_expert_selector_still_uses_legacy_replay_path(monkeypatch, tmp_path):
    scene = tmp_path / "scene"
    scene.mkdir()
    destination = tmp_path / "expert-run"
    replay_calls = []

    def create_run(label):
        assert label == "expert"
        destination.mkdir()
        return destination

    monkeypatch.setattr(execution, "scene_root", lambda _: scene)
    monkeypatch.setattr(execution, "new_run", create_run)
    monkeypatch.setattr(execution, "reference", lambda _: {"root": "project", "path": "scene"})
    monkeypatch.setattr(execution, "replay", lambda root, output: replay_calls.append((root, output)))

    execution.main(["--scene", str(scene), "--planner", "expert"])

    assert replay_calls == [(scene, destination / "scene/trace.json")]
    record = json.loads((destination / "run.json").read_text())
    assert record["schema_version"] == 2
    assert "selection" not in record
    assert record["results"][0]["diagnostic_only"] is True


@pytest.mark.parametrize("ego,traffic", list(product(CONTROLLERS, ("idm", "ppo", "smart"))))
def test_source_hold_pairs_reach_worker_as_diagnostic(monkeypatch, tmp_path, ego, traffic):
    scene = tmp_path / "scene"
    scene.mkdir()
    out = tmp_path / "run"
    calls = []

    def new_run(label):
        out.mkdir()
        return out

    monkeypatch.setattr(execution, "scene_root", lambda _: scene)
    monkeypatch.setattr(execution, "new_run", new_run)
    monkeypatch.setattr(execution, "reference", lambda _: {"root": "project", "path": "scene"})
    monkeypatch.setattr(execution.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    execution.main(["--scene", str(scene), "--ego", ego, "--traffic", traffic,
                    "--traffic-startup", "source_hold"])
    command, = calls
    assert command[command.index("--traffic-startup") + 1] == "source_hold"
    record = json.loads((out / "run.json").read_text())["results"][0]
    assert record["traffic_startup"] == "source_hold"
    assert record["diagnostic_only"] and record["research_admission_status"] == "not_established"
