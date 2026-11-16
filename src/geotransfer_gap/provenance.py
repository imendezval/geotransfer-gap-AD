"""Producer identities include extracted implementation dependencies."""

import hashlib
import json
from pathlib import Path
from .artifacts import sha256
from .config import tool_path


def converter_fingerprint():
    names = (
        "pilot_ind.py",
        "ind.py",
        "lanelet.py",
        "binary.py",
        "config.py",
        "artifacts.py",
    )
    dependencies = {name: sha256(tool_path(name)) for name in names}
    dependencies["provenance.py"] = sha256(Path(__file__))
    return hashlib.sha256(json.dumps(dependencies, sort_keys=True).encode()).hexdigest()
