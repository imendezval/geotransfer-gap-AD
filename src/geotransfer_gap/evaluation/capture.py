"""Optional, hash-bound native episode evidence capture.

This module only copies values already exposed by the episode worker's
pre-step snapshot. It does not read simulator logs or change runtime state.
"""

import math
import re


CAPTURE_SCHEMA_VERSION = 1
CAPTURE_FILENAME = "evaluation_capture.json"


def _finite_number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"nonfinite or nonnumeric {label}")
    return value


def _check_finite(value):
    if isinstance(value, dict):
        for child in value.values():
            _check_finite(child)
    elif isinstance(value, list):
        for child in value:
            _check_finite(child)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("evaluation capture contains a nonfinite number")


def _world_offset(binary, state):
    """Match runtime.session.frame's first-valid-source-anchor convention."""
    anchor = next((i for i, obj in enumerate(binary["objects"])
                   if bool(obj["traj_valid"][0])), None)
    if anchor is None:
        raise ValueError("cannot capture coordinates without a source-valid anchor")
    obj = binary["objects"][anchor]
    entity = state["entities"][anchor]
    return anchor, (
        _finite_number(float(obj["traj_x"][0]) - float(entity["traj_x"][0]), "x offset"),
        _finite_number(float(obj["traj_y"][0]) - float(entity["traj_y"][0]), "y offset"),
    )


class EvaluationCapture:
    """Accumulate copied native event evidence at the existing pre-step hook."""

    def __init__(self, binary, native_settings):
        objects = binary.get("objects")
        if not isinstance(objects, (list, tuple)) or not objects:
            raise ValueError("capture requires the loaded binary scene")
        self._binary = binary
        self._id_by_index = tuple(int(obj["id"]) for obj in objects)
        if len(set(self._id_by_index)) != len(self._id_by_index):
            raise ValueError("capture binary has duplicate source actor IDs")
        self._settings = {
            key: native_settings[key]
            for key in ("dynamics_model", "action_type_flag", "episode_length",
                        "observation_width", "goal_behavior")
            if key in native_settings
        }
        if set(self._settings) != {
                "dynamics_model", "action_type_flag", "episode_length",
                "observation_width", "goal_behavior"}:
            raise ValueError("capture requires the supported native evaluation settings")
        self._observations = []

    def capture_pre_step(self, snapshot, native):
        """Copy identity and detector fields before the next native step."""
        state = native
        if isinstance(native, list):
            if len(native) != 1:
                raise ValueError("evaluation capture requires one native environment")
            state = native[0]
        anchor, offset = _world_offset(self._binary, state)
        rows = []
        for actor in snapshot.actors:
            index = actor.fixed_binary_index
            if not 0 <= index < len(self._id_by_index):
                raise ValueError("snapshot actor binary index is outside the scene")
            source_id = int(actor.source_id)
            if self._id_by_index[index] != source_id:
                raise ValueError("snapshot actor source identity differs from binary index")
            entity = state["entities"][index]
            collision_state = int(entity["collision_state"])
            raw_partner = int(entity["collided_with_index"])
            # BehaviorBench uses 1 for vehicle collision and 2 for offroad.
            # Detector centers and partner indexes are meaningful only for 1;
            # offroad must not inherit stale collision-position fields.
            vehicle_collision = collision_state == 1
            partner_index = raw_partner if vehicle_collision and raw_partner >= 0 else None
            partner_id = (self._id_by_index[partner_index]
                          if partner_index is not None and partner_index < len(self._id_by_index)
                          else None)
            if partner_index is not None and partner_index >= len(self._id_by_index):
                # Preserve the copied index while refusing to invent a source ID.
                partner_id = None
            center = other_center = None
            if vehicle_collision:
                center = [
                    _finite_number(float(entity["collision_x"]) + offset[0], "collision center x"),
                    _finite_number(float(entity["collision_y"]) + offset[1], "collision center y"),
                ]
                other_center = [
                    _finite_number(float(entity["collision_other_x"]) + offset[0], "partner center x"),
                    _finite_number(float(entity["collision_other_y"]) + offset[1], "partner center y"),
                ]
            goal = None
            if actor.native_present and actor.controller_eligible:
                goal = [
                    _finite_number(float(entity["goal_position_x"]) + offset[0], "goal x"),
                    _finite_number(float(entity["goal_position_y"]) + offset[1], "goal y"),
                ]
            generation = actor.lifetime_generation
            if generation is not None:
                generation = int(generation)
                if generation < 0:
                    raise ValueError("snapshot lifetime generation must be nonnegative")
            rows.append({
                "source_id": source_id,
                "binary_index": index,
                "lifetime_generation": generation,
                "collision_state": collision_state,
                "collision_partner_binary_index": partner_index,
                "collision_partner_source_id": partner_id,
                "collision_center_world_xy": center,
                "partner_center_world_xy": other_center,
                "navigation_goal_world_xy": goal,
            })
        self._observations.append({
            "step": int(snapshot.step),
            "coordinate_offset_world_minus_native_m": list(offset),
            "coordinate_anchor_binary_index": anchor,
            "actors": rows,
        })

    def build(self, trace, trace_sha256):
        """Bind the capture to the completed, byte-written canonical trace."""
        if not isinstance(trace_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", trace_sha256) is None:
            raise ValueError("capture requires the exact trace SHA-256")
        if len(self._observations) != trace.get("observation_frames"):
            raise ValueError("capture observation count differs from the trace")
        ego_id = next(int(actor["id"]) for actor in trace["frames"][0]["state"]["actors"]
                      if actor["binary_index"] == trace["ego_binary_index"])
        capture = {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "trace_sha256": trace_sha256,
            "scene": trace["scene"],
            "binary_sha256": trace["binary_sha256"],
            "ego_binary_index": trace["ego_binary_index"],
            "ego_source_id": ego_id,
            "ego_controller": trace["ego_controller"],
            "traffic_controller": trace["traffic_controller"],
            "traffic_startup": trace["traffic_startup"],
            "steps_semantics": trace["steps_semantics"],
            "requested_observation_frames": trace["requested_observation_frames"],
            "observation_frames": trace["observation_frames"],
            "terminal_reason": trace["terminal_reason"],
            "native_settings": self._settings,
            "coordinate_frame": {
                "native_frame": "BehaviorBench local scene coordinates",
                "trace_frame": "world coordinates produced by runtime.session.frame",
                "transform": "world_xy = native_xy + coordinate_offset_world_minus_native_m",
                "anchor_rule": "first binary actor with traj_valid[0], using its traj_x[0]/traj_y[0] and native traj_x[0]/traj_y[0]",
            },
            "observations": self._observations,
            "limitations": [
                "Collision positions are detector actor centers, not exact physical impact points.",
                "No upstream aggregate or per-agent log API was read; reset/index behavior is not needed for these copied fields.",
                "A null partner identity means the native detector supplied no valid mapped partner index.",
            ],
        }
        validate_evaluation_capture(capture, trace, trace_sha256)
        return capture


def validate_evaluation_capture(capture, trace, trace_sha256):
    """Check capture structure and exact trace/protocol/actor binding."""
    if not isinstance(capture, dict) or type(capture.get("schema_version")) is not int \
            or capture["schema_version"] != CAPTURE_SCHEMA_VERSION:
        raise ValueError("unsupported evaluation capture schema")
    _check_finite(capture)
    ego_id = next((int(actor["id"]) for actor in trace["frames"][0]["state"]["actors"]
                   if actor["binary_index"] == trace["ego_binary_index"]), None)
    if (capture.get("trace_sha256") != trace_sha256
            or capture.get("scene") != trace.get("scene")
            or capture.get("binary_sha256") != trace.get("binary_sha256")
            or capture.get("ego_binary_index") != trace.get("ego_binary_index")
            or capture.get("ego_controller") != trace.get("ego_controller")
            or capture.get("traffic_controller") != trace.get("traffic_controller")
            or capture.get("traffic_startup") != trace.get("traffic_startup")
            or capture.get("steps_semantics") != trace.get("steps_semantics")
            or capture.get("requested_observation_frames") != trace.get("requested_observation_frames")
            or capture.get("observation_frames") != trace.get("observation_frames")
            or capture.get("terminal_reason") != trace.get("terminal_reason")
            or type(capture.get("ego_source_id")) is not int or capture["ego_source_id"] != ego_id):
        raise ValueError("evaluation capture identity or protocol differs from trace")
    if (not isinstance(trace_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", trace_sha256) is None):
        raise ValueError("invalid exact trace SHA-256")
    observations = capture.get("observations")
    if not isinstance(observations, list) or len(observations) != len(trace.get("frames", [])):
        raise ValueError("evaluation capture observation count differs from trace")
    if not isinstance(capture.get("native_settings"), dict):
        raise ValueError("evaluation capture lacks native settings")
    coordinate = capture.get("coordinate_frame")
    if (not isinstance(coordinate, dict)
            or coordinate.get("transform") != "world_xy = native_xy + coordinate_offset_world_minus_native_m"):
        raise ValueError("unsupported evaluation capture coordinate transform")
    for step, (observation, frame) in enumerate(zip(observations, trace["frames"])):
        if (type(observation.get("step")) is not int or observation["step"] != step
                or frame.get("step") != step):
            raise ValueError(f"evaluation capture step differs at observation {step}")
        state_by_id = {int(row["id"]): row for row in frame["state"]["actors"]}
        assignment_by_id = {int(row["source_id"]): row for row in frame["actors"]}
        rows = observation.get("actors")
        if not isinstance(rows, list) or len(rows) != len(state_by_id):
            raise ValueError(f"evaluation capture actor count differs at observation {step}")
        offset = observation.get("coordinate_offset_world_minus_native_m")
        if (not isinstance(offset, list) or len(offset) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in offset)):
            raise ValueError(f"invalid evaluation capture coordinate offset at observation {step}")
        if (type(observation.get("coordinate_anchor_binary_index")) is not int
                or observation["coordinate_anchor_binary_index"] < 0
                or observation["coordinate_anchor_binary_index"] not in
                {row["binary_index"] for row in state_by_id.values()}):
            raise ValueError(f"invalid coordinate anchor at observation {step}")
        seen = set()
        for row in rows:
            source_id = row.get("source_id")
            if type(source_id) is not int or source_id in seen or source_id not in state_by_id:
                raise ValueError(f"invalid evaluation capture actor identity at observation {step}")
            seen.add(source_id)
            state = state_by_id[source_id]
            assignment = assignment_by_id.get(source_id)
            if (assignment is None or type(row.get("binary_index")) is not int
                    or row["binary_index"] != state.get("binary_index")
                    or (row.get("lifetime_generation") is not None
                        and (type(row["lifetime_generation"]) is not int
                             or row["lifetime_generation"] < 0))
                    or row.get("lifetime_generation") != assignment.get("lifetime_generation")):
                raise ValueError(f"evaluation capture actor/lifetime binding differs at observation {step}")
            collision_state = row.get("collision_state")
            if type(collision_state) is not int:
                raise ValueError(f"invalid native collision state at observation {step}")
            partner_index = row.get("collision_partner_binary_index")
            partner_id = row.get("collision_partner_source_id")
            if collision_state < 0:
                raise ValueError(f"invalid native collision state at observation {step}")
            if partner_index is None:
                if partner_id is not None:
                    raise ValueError(f"unmapped collision partner has a source ID at observation {step}")
            else:
                if type(partner_index) is not int or partner_index < 0:
                    raise ValueError(f"invalid collision partner index at observation {step}")
                partner = next((actor_id for actor_id, actor in state_by_id.items()
                                if actor.get("binary_index") == partner_index), None)
                if partner is None or partner_id != partner:
                    raise ValueError(f"collision partner identity differs at observation {step}")
            for key in ("collision_center_world_xy", "partner_center_world_xy", "navigation_goal_world_xy"):
                pair = row.get(key)
                if pair is not None and (not isinstance(pair, list) or len(pair) != 2
                                         or any(type(value) not in (int, float)
                                                or not math.isfinite(value) for value in pair)):
                    raise ValueError(f"invalid {key} at observation {step}")
            if collision_state == 1 and (row["collision_center_world_xy"] is None
                                         or row["partner_center_world_xy"] is None):
                raise ValueError(f"collision lacks detector centers at observation {step}")
            if collision_state != 1 and (partner_index is not None or partner_id is not None
                                         or row["collision_center_world_xy"] is not None
                                         or row["partner_center_world_xy"] is not None):
                raise ValueError(f"non-vehicle event carries vehicle collision data at observation {step}")
    return True
