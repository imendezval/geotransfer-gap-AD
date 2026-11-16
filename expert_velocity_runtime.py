"""Isolated diagnostic repair: source-expert pose and velocity share a timestep.

Native move_expert updates pose only. Stale velocity is then consumed by IDM
leader detection and by an expert-to-IDM transition. No source intent, desired
speed, route geometry or reactive controller is otherwise changed.
"""
import late_spawn_runtime as base


def load():
    original = base.patched_header

    def patched(source, include_semantic_map=False):
        source = original(source, include_semantic_map=include_semantic_map)
        if '    agent->vx = agent->traj_vx[t];\n    agent->vy = agent->traj_vy[t];' in source:
            return source  # The production runtime now includes this repair.
        return base.replace_once(source,
            '    agent->z = agent->traj_z[t];\n    agent->heading = agent->traj_heading[t];',
            '    agent->z = agent->traj_z[t];\n'
            '    agent->vx = agent->traj_vx[t];\n'
            '    agent->vy = agent->traj_vy[t];\n'
            '    agent->vz = agent->traj_vz[t];\n'
            '    agent->heading = agent->traj_heading[t];')

    try:
        base.patched_header = patched
        result = base.load()
        result['expert_velocity_repair_diagnostic'] = True
        return result
    finally:
        base.patched_header = original
