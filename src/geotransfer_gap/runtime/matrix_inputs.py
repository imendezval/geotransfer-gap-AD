"""Resolve and validate the inputs used by a matrix worker."""

from geotransfer_gap.artifacts import read_json, reference, sha256
from geotransfer_gap.config import ensure_bench
from geotransfer_gap.runtime.startup_policy import source_hold_policy


def binary_path(root):
    return root / "testing/map_000000.bin"


def load_binary(root):
    ensure_bench()
    from pufferlib.prediction.binary_reader import read_binary_scenario

    return read_binary_scenario(str(binary_path(root)))


def load_source_hold(root, binary, steps):
    sources = sorted((root / "testing").glob("ind_*.json"))
    if len(sources) != 1:
        raise ValueError(
            f"source_hold requires exactly one authoritative source JSON in "
            f"{reference(root / 'testing')} (found {len(sources)})"
        )
    source, = sources
    startup = source_hold_policy(read_json(source), binary)
    if steps > startup.window:
        raise ValueError("source_hold steps exceed the authoritative source window")
    return source, startup


def fingerprint(path):
    return {"reference": reference(path), "sha256": sha256(path)}
