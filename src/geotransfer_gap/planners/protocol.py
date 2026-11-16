"""One producer registry for SMART input and execution contracts in both domains."""

from pathlib import Path
from geotransfer_gap.artifacts import sha256
from geotransfer_gap.config import settings, tool_path


def input_paths():
    bench = settings().bench
    return dict(
        adapter=tool_path("faithful_smart.py"),
        probe=tool_path("probe_smart_map_transfer.py"),
        map_preprocessing=tool_path("faithful_map.py"),
        smart_planner=bench / "pufferlib/planning/smart.py",
        tokenizer=bench / "pufferlib/prediction/map_tokenizer.py",
        training_dataset=bench / "pufferlib/prediction/dataset.py",
        map_codebook=bench / "pufferlib/prediction/smart/tokens/map_traj_token5.pkl",
        motion_codebook=bench
        / "pufferlib/prediction/smart/tokens/cluster_frame_5_2048.pkl",
        evaluation_ini=bench / "pufferlib/config/evaluation.ini",
        protocol=Path(__file__),
    )


def execution_hashes():
    names = (
        "faithful_smart.py",
        "faithful_map.py",
        "background_route_intent.py",
        "hybrid_traffic.py",
        "probe_faithful_smart_closed_loop.py",
        "session.py",
    )
    return {
        **{name: sha256(tool_path(name)) for name in names},
        "protocol.py": sha256(Path(__file__)),
    }
