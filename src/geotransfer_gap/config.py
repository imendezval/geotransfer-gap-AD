"""Explicit project/dependency locations; no filesystem writes on import."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import tomllib
PROJECT_ROOT = Path(os.environ.get('GEOTRANSFER_PROJECT', Path(__file__).resolve().parents[2])).resolve()

@dataclass(frozen=True)
class Settings:
    project: Path
    source: Path
    bench: Path
    artifacts: Path
    runs: Path
    cache: Path
    weights: Path

def settings() -> Settings:
    path = Path(os.environ.get('GEOTRANSFER_CONFIG', PROJECT_ROOT / 'configs/local.toml'))
    data = tomllib.loads(path.read_text()).get('paths', {}) if path.is_file() else {}

    def value(key, default):
        p = Path(os.environ.get('GEOTRANSFER_' + key.upper(), data.get(key, str(default)))).expanduser()
        return (PROJECT_ROOT / p).resolve() if not p.is_absolute() else p.resolve()
    bench = value('bench', PROJECT_ROOT.parent / 'behavior-bench')
    return Settings(PROJECT_ROOT, value('source', PROJECT_ROOT.parent / 'data/levelxdata/inD-dataset-v1.1'), bench, value('artifacts', PROJECT_ROOT / 'artifacts'), value('runs', PROJECT_ROOT / 'runs'), value('cache', Path('/tmp/geotransfer-cache')), value('weights', bench / 'weights/SMART_epoch_030.pt'))

def registry():
    return json.loads(Path(__file__).with_name('tool_registry.json').read_text())

def tool_path(name):
    name = str(name)
    return PROJECT_ROOT / registry()[name]

def project_path(name):
    name = str(name)
    if name in registry():
        return tool_path(name)
    path = Path(name)
    if path.parts and path.parts[0] == 'pilot':
        return settings().artifacts.joinpath(*path.parts[1:])
    return PROJECT_ROOT / path

def ensure_bench():
    """Load only the configured BB checkout; callers invoke before backend imports."""
    path = str(settings().bench)
    if path not in sys.path:
        sys.path.insert(0, path)
