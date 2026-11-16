"""Shared artifact I/O, stable scene identity and path-independent references."""
import hashlib
import json
from pathlib import Path
from .config import settings

def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text())

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    temp.replace(path)

def manifest_path():
    return settings().artifacts / 'audits/step2_expanded_current_manifest.json'

def scenes(manifest=None):
    return read_json(manifest or manifest_path())

def scene_root(identifier):
    path = Path(identifier)
    if path.is_dir():
        return path.resolve()
    matches = [r for r in scenes() if r['name'] == identifier]
    if len(matches) != 1:
        raise ValueError(f'Unknown or ambiguous scene: {identifier}')
    return resolve_reference(matches[0]['root'])

def reference(path):
    path = Path(path).resolve()
    for kind, base in [('artifacts', settings().artifacts), ('source', settings().source), ('bench', settings().bench), ('project', settings().project)]:
        if path.is_relative_to(base):
            return {'root': kind, 'path': path.relative_to(base).as_posix()}
    raise ValueError(f'Artifact outside configured roots: {path}')

def resolve_reference(value):
    if isinstance(value, str):
        return Path(value).resolve()
    roots = {k: getattr(settings(), k) for k in ('project', 'artifacts', 'source', 'bench')}
    path = (roots[value['root']] / value['path']).resolve()
    if not path.is_relative_to(roots[value['root']]):
        raise ValueError('Reference escapes configured root')
    return path
