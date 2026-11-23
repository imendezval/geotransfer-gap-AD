"""Resolve and validate the inputs used by a matrix worker."""

from pathlib import Path
from tempfile import TemporaryDirectory

from geotransfer_gap.artifacts import read_json, reference, sha256
from geotransfer_gap.config import ensure_bench, settings
from geotransfer_gap.runtime.startup_policy import source_hold_policy


US_REFERENCES = {
    "us_hybrid_1002fdc9826fc6d1": "105a45498ea7edf1d92e2664814b1b94b93f772209cf36ff233c950895ed0828",
    "us_smart_negative_world_739e0513c6f7cfe8": "a4aa356dbd348f50154dd38272518f0819084eeb1112f23b4e48be4f6e071859",
}
_US_SOURCE_HASHES = {
    "1002fdc9826fc6d1": "6066ee226e853a297daee997886b60e07fd88ccbb2f5d2b1c13504d9b6db76d4",
    "739e0513c6f7cfe8": "5a5dc42c5a3803584e517bc6fdadd76f13a712d1a23683787897591a51a38191",
}


def _qualified_womd(root, packaged):
    from geotransfer_gap.conversion.binary import load_source_writer

    suffix = root.name.rsplit("_", 1)[-1]
    base = settings().reference_data / "gpudrive"
    candidates = sorted(base.glob(f"*/WOMD_v1.3_{suffix}.json"))
    expected = base / "validation" / f"WOMD_v1.3_{suffix}.json"
    if packaged or candidates != [expected]:
        raise ValueError(f"source_hold requires one unambiguous WOMD source at {expected}")
    if sha256(expected) != _US_SOURCE_HASHES[suffix]:
        raise ValueError(f"WOMD source hash mismatch: {expected}")
    scene = read_json(expected)
    with TemporaryDirectory() as temp:
        encoded = Path(temp) / "map.bin"
        load_source_writer()(scene, str(encoded), 0, trajectory_length=91)
        if sha256(encoded) != US_REFERENCES[root.name] or sha256(binary_path(root)) != US_REFERENCES[root.name]:
            raise ValueError("WOMD writer output differs from the pinned binary")
    for actor in scene["objects"]:
        for sample in actor["velocity"]:
            sample.setdefault("z", 0.0)  # Exact upstream writer default, verified by the roundtrip.
    return expected, scene


def binary_path(root):
    return root / "testing/map_000000.bin"


def load_binary(root):
    ensure_bench()
    from pufferlib.prediction.binary_reader import read_binary_scenario

    return read_binary_scenario(str(binary_path(root)))


def load_source_hold(root, binary, steps):
    sources = sorted((root / "testing").glob("ind_*.json"))
    if root.name in US_REFERENCES:
        source, scene = _qualified_womd(root, sources)
    elif len(sources) == 1:
        source, = sources
        scene = read_json(source)
    else:
        raise ValueError(
            f"source_hold requires exactly one authoritative source JSON in "
            f"{reference(root / 'testing')} (found {len(sources)})"
        )
    startup = source_hold_policy(scene, binary)
    if steps > startup.window:
        raise ValueError("source_hold steps exceed the authoritative source window")
    return source, startup


def fingerprint(path):
    return {"reference": reference(path), "sha256": sha256(path)}



def slot_id(scene, ego, traffic, startup):
    return f"{scene}:{ego}:{traffic}:{startup}"


def preflight_inputs(root, name, expected_hash, steps, *, check_source_hold):
    """Check scene inputs before scheduling a worker."""
    binary = fingerprint(binary_path(root))
    if expected_hash and binary["sha256"] != expected_hash:
        raise ValueError(f"stale manifest binary: {name}")
    inputs = {"binary": binary}
    problem = None
    if check_source_hold:
        try:
            source, _ = load_source_hold(root, load_binary(root), steps)
            inputs["source_hold"] = fingerprint(source)
        except (ValueError, OSError) as exc:
            problem = str(exc)
    return inputs, problem
