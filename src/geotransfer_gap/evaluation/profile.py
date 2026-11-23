"""Load and identify version 1 of the offline measurement profile."""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import tomllib

from geotransfer_gap.config import settings


@dataclass(frozen=True)
class EvaluationProfile:
    canonical_json: bytes
    effective_sha256: str
    raw_sha256: str

    @property
    def values(self):
        return json.loads(self.canonical_json)

    @property
    def definition_version(self):
        return self.values["profile"]["definition_version"]


def _validate(value, template, path):
    field = ".".join(path) or "profile"
    if isinstance(template, dict):
        if type(value) is not dict or value.keys() != template.keys():
            raise ValueError(f"{field}: expected fields {', '.join(sorted(template))}")
        return {key: _validate(value[key], sample, (*path, key)) for key, sample in template.items()}
    if isinstance(template, list):
        if type(value) is not list or not value:
            raise ValueError(f"{field}: expected nonempty sensitivity array")
        values = [_validate(item, template[0], path) for item in value]
        if sorted(set(values)) != values:
            raise ValueError(f"{field}: expected strictly increasing sensitivity values")
        return values
    if type(template) is float:
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{field}: expected positive finite number")
        value = float(value)
    elif type(value) is not type(template):
        raise ValueError(f"{field}: expected {type(template).__name__}")
    if isinstance(template, (bool, str)) or path[0] in {"profile", "time"}:
        if field != "profile.id" and value != template:
            raise ValueError(f"{field}: unsupported value {value!r}")
        if field == "profile.id" and not value.strip():
            raise ValueError("profile.id must be nonempty")
    return value


def load_profile(path=None):
    """Read a complete profile, canonicalizing types before hashing its values."""
    default = settings().project / "configs/evaluation/default.toml"
    raw = (Path(path) if path is not None else default).read_bytes()
    try:
        values = _validate(
            tomllib.loads(raw.decode("utf-8")), tomllib.loads(default.read_text("utf-8")), ()
        )
    except OverflowError as exc:
        raise ValueError("Profile number exceeds finite range") from exc
    meta = values["profile"]
    if (meta["schema_version"], meta["definition_version"], meta["annotation_schema_version"]) != (1, "1.0.0", 1):
        raise ValueError("Unsupported profile, definition or annotation schema version")
    time = values["time"]
    if (time["primary_start_observation"] != time["warmup_transitions"]
            or (time["nominal_sample_interval_s"], time["warmup_transitions"],
                time["primary_last_observation_index"]) != (0.1, 10, 90)):
        raise ValueError("Primary window must begin immediately after warmup")
    ttc, near = values["safety"]["ttc"], values["safety"]["near_miss"]
    clearance = near["footprint_clearance_below_m"]
    if (ttc["primary_horizon_s"] not in ttc["sensitivity_horizons_s"]
            or near["ttc_below_s"] not in near["ttc_sensitivity_s"]
            or max(near["ttc_sensitivity_s"]) > min(ttc["sensitivity_horizons_s"])
            or clearance not in near["clearance_sensitivity_m"]
            or values["efficiency"]["stationary_speed_below_m_s"]
            not in values["efficiency"]["stationary_speed_sensitivity_m_s"]
            or 1.0 not in values["comfort"]["threshold_scale_sensitivity"]):
        raise ValueError("Profile primary thresholds and sensitivity variants are inconsistent")
    uncertainty = values["uncertainty"]
    if (uncertainty["bootstrap_seed"] < 0 or uncertainty["bootstrap_resamples"] < 1
            or not 0 < uncertainty["confidence_level"] < 1):
        raise ValueError("Invalid cluster bootstrap settings")
    canonical = json.dumps(values, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    return EvaluationProfile(canonical, hashlib.sha256(canonical).hexdigest(),
                             hashlib.sha256(raw).hexdigest())
