"""General source-startup hold, then IDM traffic protocol.

The same rule can be applied to any binary with expert trajectories, including
US evaluation scenes: a vehicle initially stopped at birth stays on expert
replay until sustained source departure: five valid samples at >=2 m/s,
at least 1 m displacement and 1 s after birth. This also includes vehicles
completing a stop in the first eleven observed startup samples. Without such
a departure they remain replayed through the window. Other moving vehicles
use IDM; VRUs and parked vehicles use expert replay. Source departure is an
explicit background-intent prior, not a fully reactive traffic model.
"""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import math

PROTOCOL_VERSION = "startup_sustained_departure_route_coverage_v2"


def release_schedule(scene):
    schedule = {}
    ego = scene.get("metadata", {}).get("sdc_track_index", 0)
    for index, obj in enumerate(scene["objects"]):
        if index == ego or obj["type"] != "vehicle" or obj["mark_as_expert"]:
            continue
        birth = next((t for t, v in enumerate(obj["valid"]) if v), None)
        if birth is None:
            continue
        speed = [math.hypot(v["x"], v["y"]) for v in obj["velocity"]]
        startup = range(birth, min(birth + 11, len(obj["valid"])))
        if not any((obj["valid"][t] and speed[t] < 1 for t in startup)):
            continue
        points = [p for t, p in enumerate(obj["position"]) if obj["valid"][t]]
        path = sum(
            (
                math.dist((a["x"], a["y"]), (b["x"], b["y"]))
                for a, b in zip(points, points[1:])
            )
        )
        if path < 1:
            continue
        start = obj["position"][birth]
        release = next(
            (
                t
                for t in range(birth + 10, len(obj["valid"]) - 4)
                if all(obj["valid"][t : t + 5])
                and min(speed[t : t + 5]) >= 2
                and (
                    math.dist(
                        (obj["position"][t]["x"], obj["position"][t]["y"]),
                        (start["x"], start["y"]),
                    )
                    >= 1
                )
            ),
            len(obj["valid"]),
        )
        schedule[index] = release
    return schedule


def apply(env, scene, schedule, step, binding):
    """Assign modes to current actor slots, including newly spawned actors."""
    state = env.get_state()[0]
    slots = {
        entity_index: slot
        for slot, entity_index in enumerate(state["active_agent_indices"])
    }
    by_mode = {1: [], 2: []}
    ego_index = scene.get("metadata", {}).get("sdc_track_index", 0)
    for index, obj in enumerate(scene["objects"]):
        if index == ego_index:
            continue
        slot = slots.get(index)
        if slot is None or state["entities"][index]["x"] == -10000.0:
            continue
        mode = (
            2
            if obj["type"] != "vehicle"
            or obj["mark_as_expert"]
            or (index in schedule and step < schedule[index])
            else 1
        )
        by_mode[mode].append(slot)
    for mode, selected in by_mode.items():
        if selected:
            binding.vec_set_movement_mode(env.c_envs, selected, mode)
    return {
        str(scene["objects"][i]["id"]): step < release
        for i, release in schedule.items()
        if i in slots
    }
