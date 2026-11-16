"""Shared artifact I/O, stable scene identity and path-independent references."""

import hashlib
import json
from pathlib import Path
from .config import settings


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def manifest_path():
    return settings().artifacts / "audits/step2_expanded_current_manifest.json"


def scenes(manifest=None):
    path = Path(manifest) if manifest else settings().artifacts / "corpus/current.json"
    if not path.exists():
        path = manifest_path()
    return read_manifest(path)


def scene_root(identifier):
    if isinstance(identifier, dict):
        return resolve_reference(identifier)
    path = resolve_reference(str(identifier))
    if path.is_dir():
        return path.resolve()
    matches = [r for r in scenes() if r["name"] == identifier]
    if len(matches) != 1:
        raise ValueError(f"Unknown or ambiguous scene: {identifier}")
    return resolve_reference(matches[0]["root"])


def reference(path):
    path = Path(path).resolve()
    for kind, base in [
        ("artifacts", settings().artifacts),
        ("source", settings().source),
        ("reference_data", settings().reference_data),
        ("bench", settings().bench),
        ("project", settings().project),
    ]:
        if path.is_relative_to(base):
            return {"root": kind, "path": path.relative_to(base).as_posix()}
    raise ValueError(f"Artifact outside configured roots: {path}")


def resolve_reference(value):
    if isinstance(value, str):
        path = Path(value)
        # Historical evidence keeps its original bytes and paths. Resolve only
        # this project's documented directory rename, then verify content hashes.
        parts = path.parts
        if "geotransfer-AD-gap" in parts:
            tail = parts[parts.index("geotransfer-AD-gap") + 1 :]
            if tail and tail[0] == "pilot":
                return settings().artifacts.joinpath(*tail[1:]).resolve()
            return settings().project.joinpath(*tail).resolve()
        if parts and parts[0] == "pilot":
            return settings().artifacts.joinpath(*parts[1:]).resolve()
        return path.resolve()
    roots = {
        k: getattr(settings(), k)
        for k in ("project", "artifacts", "source", "bench", "reference_data")
    }
    path = (roots[value["root"]] / value["path"]).resolve()
    if not path.is_relative_to(roots[value["root"]]):
        raise ValueError("Reference escapes configured root")
    return path


def evidence_current(gate):
    """Validate every recorded dependency, resolving portable references when present."""
    files = gate.get("evidence_files")
    if files is not None:
        return bool(files) and all(
            (
                resolve_reference(f["reference"]).is_file()
                and sha256(resolve_reference(f["reference"])) == f["sha256"]
                for f in files
            )
        )
    return bool(gate.get("evidence_sha256")) and all(
        (
            Path(p).is_file() and sha256(p) == h
            for p, h in gate["evidence_sha256"].items()
        )
    )


def portable_manifest(rows):
    return {
        "schema_version": 2,
        "scenes": [{**r, "root": reference(r["root"])} for r in rows],
    }


def read_manifest(path):
    value = read_json(path)
    rows = value["scenes"] if isinstance(value, dict) else value
    return [{**r, "root": str(resolve_reference(r["root"]))} for r in rows]
