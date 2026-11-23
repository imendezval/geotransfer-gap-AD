"""Read saved episode evidence without importing the execution stack."""

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import math
from pathlib import Path
import re

from geotransfer_gap.artifacts import sha256


class EvidenceLevel(StrEnum):
    ARCHIVED_ATTESTED = "archived_attested"
    TRACE_ONLY_DIAGNOSTIC = "trace_only_diagnostic"


class SavedEvidenceError(ValueError):
    """Supplied saved evidence is invalid or cannot be read."""


class UnsupportedTraceSchema(SavedEvidenceError):
    """The trace or sidecar version is outside the supported layouts."""


@dataclass(frozen=True)
class Playback:
    report: dict
    verification: dict | None
    diagnostic: dict | None
    hashes: dict[str, str]
    attempt: dict | None
    bound: bool
    evaluation_capture: dict | None = None
    evaluation_capture_bound: bool = False


@dataclass(frozen=True)
class SavedTrace:
    playback: Playback
    evidence_level: EvidenceLevel
    ego_source_id: int
    producer_revision: str | None

    def frames(self):
        """Return recorded values with lifecycle and assignment fields joined by ID."""
        verification = self.playback.verification
        if not self.playback.bound:
            verification = None
        return iter_frames(self.playback.report, verification)


def iter_frames(report, verification=None):
    """Project both raw layouts without adding viewer labels or inferring metadata."""
    matrix = report.get("planner") == "controller_matrix"
    life = {
        row["step"]: {actor["source_id"]: actor for actor in row["actors"]}
        for row in (verification or {}).get("lifecycle", [])
    }
    for record in report["frames"]:
        state = record["state"] if matrix else record
        assignments = {a["source_id"]: a for a in record["actors"]} if matrix else {}
        lifecycle = life.get(record["step"], {})
        actors = []
        for raw in state["actors"]:
            sid = raw["id"]
            actor = {**raw, **lifecycle.get(sid, {}), **assignments.get(sid, {})}
            actor.setdefault("lifetime_generation", None)
            actor.setdefault("action", None)
            actors.append(actor)
        yield {**state, "actors": actors, "transition_applied": record.get("transition_applied")}


def _json_object(data, path):
    value = json.loads(data)
    if not isinstance(value, dict):
        raise SavedEvidenceError(f"Expected a JSON object: {path}")
    return value


def read_playback(path, digest=None, expected=None, *, verify_all_files=False):
    """Shared byte binding and coherence checks used by offline playback."""
    path = Path(path)
    paths = {"trace": path, "provenance": path.with_name("verification.json"),
             "diagnostic": path.with_name("diagnostic.json"),
             "attempt": path.with_name("attempt.json"),
             "evaluation_capture": path.with_name("evaluation_capture.json")}
    data = {key: file.read_bytes() for key, file in paths.items()
            if key == "trace" or file.is_file()
            and (key != "evaluation_capture" or verify_all_files)}
    hashes = {key: hashlib.sha256(value).hexdigest() for key, value in data.items()}
    attempt = _json_object(data["attempt"], paths["attempt"]) if "attempt" in data else None
    recorded = ((attempt or {}).get("evidence") or {}).get("files")
    if (attempt or {}).get("status") == "passed" and not recorded:
        raise SavedEvidenceError(f"Passed attempt has no playback hashes: {paths['attempt']}")
    if (attempt or {}).get("status") == "passed":
        requested_capture = (attempt.get("scene_config") or {}).get("capture_evaluation") is True
        if requested_capture != bool(recorded and "evaluation_capture" in recorded):
            raise SavedEvidenceError("Passed attempt capture request and evidence binding disagree")
    if recorded is not None and expected is not None:
        kinds = set(expected) | {"trace", "provenance"} if verify_all_files else ("trace", "provenance")
        if any(expected.get(kind) != recorded.get(kind) for kind in kinds):
            raise SavedEvidenceError(f"Campaign and attempt playback hashes disagree: {paths['attempt']}")
    binding = recorded if recorded is not None else expected
    if binding is not None:
        kinds = {"trace"}
        if not verify_all_files or (attempt or {}).get("status") == "passed":
            kinds.add("provenance")
        if verify_all_files:
            kinds.update(binding)
        for kind in sorted(kinds):
            entry = binding.get(kind, {})
            if kind in paths:
                file = paths[kind]
                actual = hashes.get(kind)
            else:
                name = entry.get("path")
                if not isinstance(name, str) or Path(name).name != name or name in {"", ".", ".."}:
                    raise SavedEvidenceError(f"Invalid saved evidence filename: {name!r}")
                file = path.with_name(name)
                actual = sha256(file) if file.is_file() else None
            if actual is None or file.name != entry.get("path") or actual != entry.get("sha256"):
                raise SavedEvidenceError(f"Playback hash or file differs from saved evidence: {file}")
            hashes[kind] = actual

    report = _json_object(data["trace"], path)
    if digest is not None and report["binary_sha256"] != digest:
        raise SavedEvidenceError("Trace binary differs from viewed scene")
    digest = report["binary_sha256"]
    evidence = _json_object(data["provenance"], paths["provenance"]) if "provenance" in data else None
    if evidence is not None:
        fields = (("scene", "scene"), ("ego", "ego_controller"), ("traffic", "traffic_controller"),
                  ("startup", "traffic_startup"), ("driving_outcome", "terminal_reason"))
        if (report["planner"] != "controller_matrix"
                or evidence.get("inputs", {}).get("binary", {}).get("sha256") != digest
                or any(evidence.get(sidecar) != report.get(trace) for sidecar, trace in fields)
                or ("lifecycle" in evidence and [row["step"] for row in evidence["lifecycle"]]
                    != [frame["step"] for frame in report["frames"]])):
            raise SavedEvidenceError(f"Verification sidecar differs from viewed trace: {paths['provenance']}")
    diagnostic = _json_object(data["diagnostic"], paths["diagnostic"]) if "diagnostic" in data else None
    if diagnostic is not None:
        if diagnostic.get("binary_sha256") != digest:
            raise SavedEvidenceError("Diagnostic binary differs from viewed scene")
        if ("traffic_protocol" in diagnostic and "traffic_protocol" in report
                and diagnostic["traffic_protocol"] != report["traffic_protocol"]):
            raise SavedEvidenceError("Diagnostic traffic protocol differs from viewed trace")
    evaluation_capture = (_json_object(data["evaluation_capture"], paths["evaluation_capture"])
                          if "evaluation_capture" in data else None)
    capture_bound = bool(verify_all_files and binding is not None
                         and "evaluation_capture" in binding and "evaluation_capture" in hashes)
    bound = (binding is not None and {"trace", "provenance"} <= binding.keys()) or (
        evidence is not None and evidence.get("trace_sha256") == hashes["trace"]
    )
    return Playback(report, evidence, diagnostic, hashes, attempt, bound,
                    evaluation_capture, capture_bound)


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _index(rows, key):
    by_id = {}
    if not isinstance(rows, list):
        raise SavedEvidenceError("Expected actor rows as a JSON array")
    for row in rows:
        sid = row[key]
        if type(sid) is not int or sid in by_id or not _integer(row.get("binary_index")):
            raise SavedEvidenceError("Invalid or duplicate actor identity")
        by_id[sid] = row
    return by_id


def _validate_layout(saved):
    report, verification = saved.report, saved.verification
    diagnostic = saved.diagnostic
    version, planner = report.get("schema_version"), report.get("planner")
    if type(version) is not int or version not in {2, 3}:
        raise UnsupportedTraceSchema(f"Unsupported trace schema: {version!r}")
    matrix = version == 3
    if planner not in ({"controller_matrix"} if matrix else {"expert", "smart"}):
        raise UnsupportedTraceSchema(f"Unsupported planner for trace schema {version}: {planner!r}")
    if not _digest(report["binary_sha256"]) or not _integer(report["ego_binary_index"]):
        raise SavedEvidenceError("Invalid binary or ego identity")
    frames = report["frames"]
    if not isinstance(frames, list) or not frames:
        raise SavedEvidenceError("Trace needs a nonempty frame array")
    scene = report.get("scene")
    if scene is not None and not (
            isinstance(scene, dict) and isinstance(scene.get("root"), str)
            and isinstance(scene.get("path"), str) and scene["path"]):
        raise SavedEvidenceError("Invalid recorded scene reference")
    if matrix:
        if scene is None:
            raise SavedEvidenceError("Missing matrix scene identity")
        requested = report["requested_observation_frames"]
        if (not _integer(requested, 1) or not len(frames) <= requested <= 91
                or not _integer(report["observation_frames"], 1)
                or report["observation_frames"] != len(frames)
                or not _integer(report["transitions"]) or report["transitions"] != len(frames) - 1
                or report["steps_semantics"] != "observation_frames"
                or not _integer(report["warmup_replay_frames"])
                or report["warmup_replay_frames"] != 10
                or report["terminal_reason"] not in {
                    "horizon", "ego_absent", "ego_removed", "ego_collision", "ego_offroad"
                }
                or report["terminal_reason"] == "horizon" and len(frames) != requested):
            raise SavedEvidenceError("Inconsistent matrix observation horizon")
        if (any(report[key] not in {"expert", "idm", "ppo", "smart"}
                for key in ("ego_controller", "traffic_controller"))
                or report["traffic_startup"] not in {"immediate", "source_hold"}
                or (report["traffic_startup"], report["traffic_controller"]) == ("source_hold", "expert")):
            raise SavedEvidenceError("Unsupported matrix controller/startup protocol")
    if verification is not None:
        if type(verification.get("schema_version")) is not int or verification["schema_version"] != 2:
            raise UnsupportedTraceSchema("Unsupported verification sidecar schema")
        if (verification.get("source_hold_prior") != report.get("startup_policy")
                or verification.get("requested_observation_frames", requested) != requested):
            raise SavedEvidenceError("Verification horizon or startup schedule differs from trace")
        native_length = verification.get("native", {}).get("episode_length")
        if native_length is not None and (not _integer(native_length, 1) or native_length < requested):
            raise SavedEvidenceError("Requested horizon exceeds verification episode length")
        runtime_digest = verification.get("software", {}).get("runtime_source_digest")
        trace_runtime = report.get("runtime", {}).get("runtime_source_sha256")
        if runtime_digest is not None and trace_runtime is not None and runtime_digest != trace_runtime:
            raise SavedEvidenceError("Verification runtime source identity differs from trace")
        if verification.get("trace_sha256", saved.hashes["trace"]) != saved.hashes["trace"]:
            raise SavedEvidenceError("Verification trace hash mismatch")

    capture = saved.evaluation_capture
    attempt = saved.attempt
    if attempt is not None and attempt.get("status") == "passed":
        requested_capture = (attempt.get("scene_config") or {}).get("capture_evaluation") is True
        if requested_capture and capture is None:
            raise SavedEvidenceError("Passed capture-enabled attempt is missing evaluation capture")
        if not requested_capture and capture is not None and saved.evaluation_capture_bound:
            raise SavedEvidenceError("Capture evidence is bound to an attempt that did not request it")
    if capture is not None:
        try:
            from geotransfer_gap.evaluation.capture import validate_evaluation_capture

            validate_evaluation_capture(capture, report, saved.hashes["trace"],
                                        verification=verification)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise SavedEvidenceError(f"Invalid evaluation capture: {exc}") from exc

    if diagnostic is not None:
        if type(diagnostic.get("schema_version")) is not int or diagnostic["schema_version"] != 1:
            raise UnsupportedTraceSchema("Unsupported legacy diagnostic schema")
        if planner != "smart" or diagnostic.get("trace_sha256", saved.hashes["trace"]) != saved.hashes["trace"]:
            raise SavedEvidenceError("Legacy diagnostic differs from saved trace")
        timeline = diagnostic.get("timeline", [])
        ticks = [row["step"] for row in timeline]
        if any(not _integer(tick) or tick >= len(frames) for tick in ticks) or ticks != sorted(set(ticks)):
            raise SavedEvidenceError("Legacy diagnostic timeline differs from saved trace")

    identities = None
    prior_time = None
    lifecycle = (verification or {}).get("lifecycle")
    if lifecycle is not None and (not isinstance(lifecycle, list) or len(lifecycle) != len(frames)):
        raise SavedEvidenceError("Invalid lifecycle observation count")
    for step, record in enumerate(frames):
        state = record["state"] if matrix else record
        if (not _integer(state["step"]) or state["step"] != step
                or not _integer(record["step"]) or record["step"] != step
                or matrix and record["transition_applied"] is not (step + 1 < len(frames))):
            raise SavedEvidenceError(f"Invalid step or transition at observation {step}")
        time = state.get("time_s")
        if time is not None:
            if (type(time) not in (int, float) or not math.isfinite(time) or time < 0
                    or prior_time is not None and time <= prior_time):
                raise SavedEvidenceError(f"Invalid observation timestamp at step {step}")
            prior_time = time
        actors = _index(state["actors"], "id")
        for actor in actors.values():
            if type(actor.get("present")) is not bool:
                raise SavedEvidenceError(f"Invalid actor presence at step {step}")
            for key in ("x", "y", "vx", "vy", "heading", "length", "width"):
                if actor.get(key) is not None and type(actor[key]) not in (int, float):
                    raise SavedEvidenceError(f"Invalid actor {key} at step {step}")
        current = {sid: row["binary_index"] for sid, row in actors.items()}
        if identities is None:
            identities = current
        if (current != identities or len(set(current.values())) != len(current)
                or report["ego_binary_index"] not in current.values()):
            raise SavedEvidenceError(f"Inconsistent actors or missing ego at step {step}")
        if matrix:
            assignments = _index(record["actors"], "source_id")
            _check_actor_metadata(assignments, actors, current, step)
            if lifecycle is not None:
                life = _index(lifecycle[step]["actors"], "source_id")
                _check_actor_metadata(life, actors, current, step)
                active = lifecycle[step].get("active_agent_indices")
                if active is not None and (
                        not isinstance(active, list) or any(not _integer(i) for i in active)
                        or len(set(active)) != len(active) or not set(active).issubset(current.values())):
                    raise SavedEvidenceError(f"Invalid active binary indices at step {step}")
                for sid, metadata in life.items():
                    assignment = assignments[sid]
                    if ("lifetime_generation" in metadata and "lifetime_generation" in assignment
                            and metadata["lifetime_generation"] != assignment["lifetime_generation"]):
                        raise SavedEvidenceError(f"Lifecycle generation mismatch at step {step}, actor {sid}")
                    slot = assignment.get("slot")
                    if active is not None and slot is not None and (
                            not _integer(slot) or slot >= len(active) or active[slot] != current[sid]):
                        raise SavedEvidenceError(f"Lifecycle slot mismatch at step {step}, actor {sid}")
    ego_id = next(sid for sid, index in identities.items() if index == report["ego_binary_index"])
    if "ego_source_id" in report and report["ego_source_id"] != ego_id:
        raise SavedEvidenceError("Trace ego source identity disagrees with binary index")
    return ego_id


def _check_actor_metadata(rows, actors, identities, step):
    if {sid: row["binary_index"] for sid, row in rows.items()} != identities:
        raise SavedEvidenceError(f"Actor metadata identity mismatch at step {step}")
    for sid, row in rows.items():
        state = actors[sid]
        if any(row[key] != state[key] for key in row.keys() & state.keys()):
            raise SavedEvidenceError(f"Actor metadata changes raw state at step {step}, actor {sid}")
        generation = row.get("lifetime_generation")
        if generation is not None and not _integer(generation):
            raise SavedEvidenceError(f"Invalid lifetime generation at step {step}")


def _check_finite(value):
    if isinstance(value, dict):
        for child in value.values():
            _check_finite(child)
    elif isinstance(value, list):
        for child in value:
            _check_finite(child)
    elif isinstance(value, float) and not math.isfinite(value):
        raise SavedEvidenceError("Saved JSON contains a nonfinite number")


def load_saved_trace(path, *, expected_files=None, expected_binary_sha256=None,
                     expected_scene=None, expected_ego_source_id=None,
                     producer_revision=None, input_paths=None, campaign_slot=None):
    """Read an episode with optional externally selected campaign/input identities.

    A passed parent attempt binds the trace and verification bytes. File hashes
    alone establish byte integrity. The caller can supply a recorded campaign
    revision since older attempts do not carry Git revisions. A selected
    persisted campaign slot can supply a parent attestation for its single
    run. Campaign selection and inventory accounting belong to its caller.
    """
    try:
        if campaign_slot is not None:
            single = campaign_slot["single"]
            if (campaign_slot.get("status") != "PASS" or single.get("status") != "passed"
                    or campaign_slot.get("exact_parity") is not True or producer_revision is None
                    or campaign_slot.get("integration_validity") != "validated_exact"
                    or expected_scene is None or expected_binary_sha256 is None):
                raise SavedEvidenceError("Campaign slot needs passing evidence and recorded scene identities")
            if expected_files is not None and expected_files != single["files"]:
                raise SavedEvidenceError("Supplied hashes disagree with the campaign slot")
            expected_files = single["files"]
        saved = read_playback(path, expected_binary_sha256, expected_files, verify_all_files=True)
        for record in (saved.report, saved.verification, saved.diagnostic, saved.attempt,
                       saved.evaluation_capture):
            _check_finite(record)
        ego_id = _validate_layout(saved)
        report, verification, attempt = saved.report, saved.verification, saved.attempt
        if expected_scene is not None and report.get("scene") != expected_scene:
            raise SavedEvidenceError("Trace scene differs from selected scene")
        if expected_ego_source_id is not None and ego_id != expected_ego_source_id:
            raise SavedEvidenceError("Trace ego differs from selected scene")
        if producer_revision is not None and (
                not isinstance(producer_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", producer_revision)):
            raise SavedEvidenceError("Invalid recorded producer revision")
        inputs = dict((verification or {}).get("inputs", {}))
        inputs.setdefault("binary", {"sha256": report["binary_sha256"]})
        for key, entry in inputs.items():
            if not _digest(entry.get("sha256")):
                raise SavedEvidenceError(f"Invalid recorded input hash: {key}")
        for key, file in (input_paths or {}).items():
            if key not in inputs or sha256(file) != inputs[key]["sha256"]:
                raise SavedEvidenceError(f"Saved input hash mismatch: {key}")

        level = EvidenceLevel.TRACE_ONLY_DIAGNOSTIC
        if campaign_slot is not None:
            if (verification is None or not {"trace", "provenance"} <= expected_files.keys()
                    or attempt is not None and attempt.get("status") != "passed"
                    or expected_scene["path"].split("/")[-1] != campaign_slot["scene"]
                    or any(campaign_slot[key] != report[field] for key, field in (
                        ("ego", "ego_controller"), ("traffic", "traffic_controller"),
                        ("startup", "traffic_startup"),
                    ))):
                raise SavedEvidenceError("Campaign slot differs from the selected episode")
            level = EvidenceLevel.ARCHIVED_ATTESTED
        if attempt is not None and attempt.get("status") == "passed":
            config = attempt["scene_config"]
            evidence = attempt["evidence"]
            if (attempt.get("schema_version") != 1 or type(attempt.get("exit_code")) is not int
                    or attempt["exit_code"] != 0 or attempt.get("signal") is not None
                    or verification is None
                    or evidence.get("integration_validity") != "validated_trace_and_provenance"
                    or config["inputs"] != verification["inputs"]
                    or config["steps"] != report["requested_observation_frames"]
                    or any(config[key] != report[key] for key in
                           ("scene", "ego_controller", "traffic_controller", "traffic_startup"))):
                raise SavedEvidenceError("Passed attempt does not attest to this trace and protocol")
            level = EvidenceLevel.ARCHIVED_ATTESTED
        if level is EvidenceLevel.ARCHIVED_ATTESTED:
            models = verification.get("model_provenance", {})
            learned = {report["ego_controller"], report["traffic_controller"]} & {"ppo", "smart"}
            if models.keys() != learned:
                raise SavedEvidenceError("Model evidence does not match saved controllers")
            binding = (attempt["evidence"]["files"] if attempt and attempt.get("status") == "passed"
                       else expected_files)
            for model, filename in models.items():
                if binding.get(model, {}).get("path") != filename:
                    raise SavedEvidenceError(f"Missing bound model provenance: {model}")
        return SavedTrace(saved, level, ego_id, producer_revision)
    except SavedEvidenceError:
        raise
    except (OSError, KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise SavedEvidenceError(f"Malformed or unreadable saved evidence at {path}: {exc}") from exc
