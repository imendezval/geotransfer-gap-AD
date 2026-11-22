"""Guarded conversion entry point around the frozen inD producer."""

import argparse
import fcntl
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from geotransfer_gap.artifacts import sha256


def validate_continuity(tracks):
    for actor_id, rows in tracks.items():
        frames = [int(row["frame"]) for row in rows]
        for previous, current in zip(frames, frames[1:]):
            if current != previous + 1:
                raise ValueError(f"Non-consecutive source frames for track {actor_id}: {previous}, {current}")


def _files(testing):
    sources = list(testing.glob("ind_*.json"))
    paths = sources + [testing / name for name in
                       ("map_000000.bin", "manifest.csv", "validation.json", "overlay.png")]
    if (len(sources) != 1 or testing.is_symlink()
            or not all(path.is_file() and not path.is_symlink() for path in paths)):
        raise ValueError(f"Incomplete or ambiguous conversion at {testing}")
    return {path.name: sha256(path) for path in paths}


def publish_conversion(root, produce):
    root.mkdir(parents=True, exist_ok=True)
    testing = root / "testing"
    with (root / ".conversion.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = _files(testing) if testing.exists() or testing.is_symlink() else None
        with TemporaryDirectory(prefix=".conversion-", dir=root) as directory:
            stage = Path(directory)
            produce(stage)
            produced = _files(stage / "testing")
            if existing is None:
                (stage / "testing").rename(testing)
            elif existing != produced:
                raise ValueError(f"Existing conversion differs at {testing}; use a new output root")


def main(argv):
    from geotransfer_gap.conversion.pipeline import ConversionConfig, Converter
    from geotransfer_gap.sources.ind import load_tracks

    producer = [sys.executable, "-m", "geotransfer_gap.conversion.pipeline"]
    if any(option in ("-h", "--help") for option in argv):
        subprocess.run([*producer, "--help"], check=True)
        return
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--recording", type=int, required=True)
    parser.add_argument("--first-frame", type=int, required=True)
    parser.add_argument("--ego", type=int, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    options, remaining = parser.parse_known_args(argv)
    config = ConversionConfig(recording=options.recording, first_frame=options.first_frame,
                              ego=options.ego)
    root = options.output_root.resolve()
    frames = Converter(config, root).frames

    def produce(stage):
        tracks, _, _ = load_tracks(config, frames)
        validate_continuity(tracks)
        subprocess.run([*producer, "--recording", str(config.recording), "--ego", str(config.ego),
                        "--first-frame", str(config.first_frame), "--output-root", str(stage),
                        *remaining], check=True)

    try:
        publish_conversion(root, produce)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
