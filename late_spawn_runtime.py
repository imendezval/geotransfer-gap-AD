"""Build and load an isolated experimental BehaviorBench C extension.

The source tree remains untouched. The build is cached under /tmp by source hash.
Only use this runtime for scenes whose validity masks include late arrivals.
"""

import hashlib
import importlib.util
import fcntl
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
BENCH = HERE.parent / "behavior-bench"


def replace_once(source, old, new):
    assert source.count(old) == 1, f"Patch anchor matched {source.count(old)} times: {old[:80]}"
    return source.replace(old, new)


def patched_header(source, include_semantic_map=False):
    source = replace_once(source,
        "if (entity->traj_valid[env->init_steps] != 1) {\n            continue;\n        }",
        "if (entity->traj_valid[env->init_steps] != 1) {\n"
        "            int future = 0;\n"
        "            for (int t = env->init_steps + 1; t < entity->array_size; t++)\n"
        "                if (entity->traj_valid[t] == 1) { future = 1; break; }\n"
        "            if (!future) continue;\n"
        "        }")
    source = replace_once(source,
        "bool is_controlled = should_control_agent(env, i, has_traffic_mix);",
        "if (entity->mark_as_expert && env->collision_shrink > 0.0f && env->collision_shrink < 1.0f) {\n"
        "            entity->width *= env->collision_shrink;\n"
        "            entity->length *= env->collision_shrink;\n"
        "        }\n"
        "        bool is_controlled = entity->mark_as_expert ? false : should_control_agent(env, i, has_traffic_mix);")
    source = replace_once(source,
        "if (entity->type == PEDESTRIAN || entity->type == CYCLIST) {\n                env->num_actors++;",
        "if (entity->type == PEDESTRIAN || entity->type == CYCLIST || entity->mark_as_expert) {\n                env->num_actors++;")
    source = replace_once(source,
        "if (is_active) {\n                e->removed = 1;\n            }\n            e->collided_before_goal = 0;",
        "/* A future actor is dormant, not removed. */\n"
        "            e->removed = 0; e->stopped = 0;\n"
        "            e->collision_state = 0; e->collided_with_index = -1;\n"
        "            e->respawn_timestep = -1; e->respawn_count = 0;\n"
        "            e->metrics_array[COLLISION_IDX] = 0.0f;\n"
        "            e->metrics_array[OFFROAD_IDX] = 0.0f;\n"
        "            e->metrics_array[REACHED_GOAL_IDX] = 0.0f;\n"
        "            e->collided_before_goal = 0;")
    source = replace_once(source,
        "if (env->entities[expert_idx].x == INVALID_POSITION)\n            continue;\n        if (env->entities[expert_idx].movement_mode",
        "if (env->entities[expert_idx].x == INVALID_POSITION &&\n"
        "            env->entities[expert_idx].traj_valid[env->timestep] != 1) continue;\n"
        "        int geo_born = 0;\n"
        "        if (env->entities[expert_idx].x == INVALID_POSITION) {\n"
        "            if (!geo_is_birth(&env->entities[expert_idx], env->timestep)) continue;\n"
        "            geo_spawn_actor(env, expert_idx, env->timestep);\n"
        "            geo_born = 1;\n"
        "        }\n"
        "        if (env->entities[expert_idx].movement_mode")
    source = replace_once(source,
        "if (env->entities[expert_idx].movement_mode == MOVEMENT_IDM || env->idm_others) {\n            move_idm(env, expert_idx);",
        "if (env->entities[expert_idx].type == VEHICLE &&\n"
        "            !env->entities[expert_idx].mark_as_expert &&\n"
        "            (env->entities[expert_idx].movement_mode == MOVEMENT_IDM || env->idm_others)) {\n"
        "            if (!geo_born) move_idm(env, expert_idx);")
    source = replace_once(source,
        "env->entities[agent_idx].collision_state = 0;\n        float prev_vx = env->entities[agent_idx].vx;",
        "Entity *geo_agent = &env->entities[agent_idx];\n"
        "        int geo_born = 0;\n"
        "        if (geo_agent->x != INVALID_POSITION && geo_agent->traj_valid[env->timestep] != 1) {\n"
        "            geo_retire_actor(geo_agent);\n"
        "            continue;\n"
        "        }\n"
        "        if (geo_agent->x == INVALID_POSITION) {\n"
        "            if (geo_agent->traj_valid[env->timestep] != 1) continue;\n"
        "            if (!geo_is_birth(geo_agent, env->timestep)) continue;\n"
        "            geo_spawn_actor(env, agent_idx, env->timestep);\n"
        "            geo_born = 1;\n"
        "        }\n"
        "        env->entities[agent_idx].collision_state = 0;\n"
        "        float prev_vx = env->entities[agent_idx].vx;")
    source = replace_once(source,
        "if (env->entities[agent_idx].movement_mode == MOVEMENT_IDM) {\n            move_idm(env, agent_idx);\n        } else if (env->entities[agent_idx].movement_mode == MOVEMENT_EXPERT) {",
        "if (env->entities[agent_idx].movement_mode == MOVEMENT_IDM) {\n"
        "            if (!geo_born) move_idm(env, agent_idx);\n"
        "        } else if (env->entities[agent_idx].movement_mode == MOVEMENT_EXPERT) {")
    source = replace_once(source,
        "} else {\n            move_dynamics(env, i, agent_idx);\n        }\n\n        // Compute acceleration",
        "} else {\n            if (!geo_born) move_dynamics(env, i, agent_idx);\n        }\n\n        // Compute acceleration")
    source = replace_once(source,
        "if (env->entities[agent_idx].removed == 1 || env->entities[agent_idx].stopped == 1) { // if the agents got removed/stopped",
        "if (env->entities[agent_idx].x == INVALID_POSITION || env->entities[agent_idx].removed == 1 || env->entities[agent_idx].stopped == 1) { // if the agents got removed/stopped")
    source = replace_once(source,
        "if (ego_entity->type > 3)\n            break;",
        "if (ego_entity->type > 3)\n            break;\n"
        "        if (ego_entity->x == INVALID_POSITION) continue;")
    # A source-valid expert traffic actor is background truth, not a scored
    # planner. It must remain present even when the evaluator's goal radius or
    # curb collision rules would remove a policy-controlled actor. The ego
    # retains ordinary evaluator metrics and termination behavior.
    source = replace_once(source,
        "        compute_agent_metrics(env, agent_idx, x);\n    }\n    compute_observations(env);",
        "        if (agent_idx == env->sdc_track_index)\n"
        "            compute_agent_metrics(env, agent_idx, x);\n"
        "    }\n    compute_observations(env);")
    source = replace_once(source,
        "        compute_agent_metrics(env, agent_idx, i); // sets collision_state/stopped/removed flags for current agent for collision and offroad, not for goal_behavior!",
        "        if (agent_idx != env->sdc_track_index &&\n"
        "            env->entities[agent_idx].movement_mode == MOVEMENT_EXPERT) {\n"
        "            continue; // Source-valid expert background follows its track.\n"
        "        }\n"
        "        compute_agent_metrics(env, agent_idx, i); // sets collision_state/stopped/removed flags for current agent for collision and offroad, not for goal_behavior!")
    # A traffic actor may approach its continuation goal before its source
    # validity ends. In GOAL_REMOVE evaluation, keep it alive until source
    # exit; retain collision and off-road handling for interactive traffic.
    source = replace_once(source,
        "            } else if (env->goal_behavior == GOAL_REMOVE) {\n"
        "                if (env->entities[agent_idx].removed != 1)",
        "            } else if (env->goal_behavior == GOAL_REMOVE &&\n"
        "                       agent_idx != env->sdc_track_index) {\n"
        "                env->entities[agent_idx].current_goal_reached = 1;\n"
        "                env->entities[agent_idx].goals_reached_this_episode += 1.0f;\n"
        "            } else if (env->goal_behavior == GOAL_REMOVE) {\n"
        "                if (env->entities[agent_idx].removed != 1)")
    helper = """
static int geo_is_birth(Entity *e, int t) {
    /* Source visibility may resume; a physics removal must remain permanent. */
    return !e->collided_before_goal && e->traj_valid[t] &&
        (t == 0 || !e->traj_valid[t - 1]);
}

static void geo_retire_actor(Entity *e) {
    e->x = INVALID_POSITION; e->y = INVALID_POSITION; e->z = 0.0f;
    e->vx = 0.0f; e->vy = 0.0f; e->vz = 0.0f;
    e->valid = 0; e->removed = 1; e->collision_state = 0;
}

static void geo_spawn_actor(Drive *env, int index, int t) {
    Entity *e = &env->entities[index];
    e->x = e->traj_x[t]; e->y = e->traj_y[t]; e->z = e->traj_z[t];
    e->vx = e->traj_vx[t]; e->vy = e->traj_vy[t]; e->vz = e->traj_vz[t];
    e->heading = e->traj_heading[t];
    e->heading_x = cosf(e->heading); e->heading_y = sinf(e->heading);
    e->valid = 1; e->removed = 0; e->stopped = 0;
    e->collision_state = 0; e->collided_with_index = -1;
    e->a_long = 0; e->a_lat = 0; e->jerk_long = 0; e->jerk_lat = 0;
    e->steering_angle = 0; e->wheelbase = 0.6f * e->length;
    e->route_progress = 0;
    if (e->type == VEHICLE && !e->mark_as_expert && e->movement_mode == MOVEMENT_IDM)
        build_route_for_agent(env, index);
}

"""
    source = replace_once(source, "void c_step(Drive *env) {", helper + "void c_step(Drive *env) {")
    if include_semantic_map:
        # The upstream neighbor cache indexes only ROAD_LANE/LINE/EDGE (4-6),
        # although its binary reader and observation encoder know types 7/8.
        # Include sign/crosswalk polylines without changing observation shape.
        old_single_line = "if (env->entities[i].type > 3 && env->entities[i].type < 7) {"
        assert source.count(old_single_line) == 2
        source = source.replace(old_single_line,
                                "if (env->entities[i].type > 3 && env->entities[i].type < 9) {")
        source = replace_once(source,
            "if (env->entities[i].type > 3 &&\n            env->entities[i].type < 7) { // NOTE: Only Road Edges, Lines, and Lanes in grid map",
            "if (env->entities[i].type > 3 &&\n            env->entities[i].type < 9) { // Include sign and crosswalk geometry in observations")
    # Native expert replay moves pose but leaves velocity at its previous
    # value. IDM leader detection and an expert-to-IDM release must see the
    # same observed source timestep as the replayed pose.
    source = replace_once(source,
        '    agent->z = agent->traj_z[t];\n    agent->heading = agent->traj_heading[t];',
        '    agent->z = agent->traj_z[t];\n'
        '    agent->vx = agent->traj_vx[t];\n'
        '    agent->vy = agent->traj_vy[t];\n'
        '    agent->vz = agent->traj_vz[t];\n'
        '    agent->heading = agent->traj_heading[t];')
    # The initial snapshot must be consistent too: native reset zeros the
    # velocity of non-controlled actors, including moving expert VRUs.
    source = replace_once(source,
        '        if (is_active == 0) {\n'
        '            e->vx = 0;\n            e->vy = 0;\n            e->vz = 0;\n'
        '            e->collided_before_goal = 0;',
        '        if (is_active == 0) {\n'
        '            e->vx = e->traj_vx[step];\n'
        '            e->vy = e->traj_vy[step];\n'
        '            e->vz = e->traj_vz[step];\n'
        '            e->collided_before_goal = 0;')
    import background_route_intent
    return background_route_intent.patch_header(source)


def load(include_semantic_map=False):
    header = BENCH / "pufferlib/ocean/drive/drive.h"
    binding = BENCH / "pufferlib/ocean/drive/binding.c"
    patched = patched_header(header.read_text(), include_semantic_map=include_semantic_map)
    build_inputs = [patched.encode(), binding.read_bytes(),
                    (BENCH / "pufferlib/ocean/env_binding.h").read_bytes(),
                    (BENCH / "pufferlib/ocean/env_config.h").read_bytes(),
                    (BENCH / "inih-r62/ini.c").read_bytes(),
                    b"-O2 -fopenmp -DPLATFORM_DESKTOP -fwrapv"]
    digest = hashlib.sha256(b"\0".join(build_inputs)).hexdigest()[:16]
    root = Path("/tmp") / f"geotransfer_late_{digest}"
    root.mkdir(parents=True, exist_ok=True)
    suffix = __import__("sysconfig").get_config_var("EXT_SUFFIX")
    binary = root / f"binding{suffix}"
    with (root / "build.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        build_dir = root / "src"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "drive.h").write_text(patched)
        (build_dir / "binding.c").write_text(binding.read_text())
        env_binding = root / "env_binding.h"
        if not env_binding.exists():
            env_binding.symlink_to(BENCH / "pufferlib/ocean/env_binding.h")
        if not binary.exists():
            setup = root / "setup.py"
            setup.write_text("from setuptools import setup, Extension\n"
                "import numpy\n"
                "setup(name='geo_late_binding', ext_modules=[Extension('binding', "
                "sources=['src/binding.c', " + repr(str(BENCH / "inih-r62/ini.c")) + "], "
                "include_dirs=[numpy.get_include(), " + repr(str(BENCH / "raylib-5.5_linux_amd64/include")) + ", " + repr(str(BENCH / "pufferlib/ocean")) + "], "
                "extra_objects=[" + repr(str(BENCH / "raylib-5.5_linux_amd64/lib/libraylib.a")) + "], "
                "extra_compile_args=['-O2','-fopenmp','-DPLATFORM_DESKTOP',"
                "'-DINI_START_COMMENT_PREFIXES=\\\"#\\\"','-DINI_INLINE_COMMENT_PREFIXES=\\\"#\\\"'], "
                "extra_link_args=['-fopenmp','-fwrapv'])])\n")
            subprocess.run([sys.executable, str(setup), "build_ext", "--inplace"], cwd=root, check=True)
    spec = importlib.util.spec_from_file_location("pufferlib.ocean.drive.binding", binary)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[spec.name] = module
    return {"runtime_source_sha256": digest, "runtime_binary": str(binary)}
