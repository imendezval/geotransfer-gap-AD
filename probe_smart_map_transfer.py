"""Verify the actual SMART map path and one CPU inference; never grants admission."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "behavior-bench"))
import late_spawn_runtime
from pufferlib.prediction.binary_reader import read_binary_scenario
from pufferlib.prediction.map_tokenizer import load_map_codebook
from faithful_map import tokenize_roads,PROTOCOL_VERSION as MAP_ENCODING_PROTOCOL

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--us-binary", type=Path, required=True)
    ap.add_argument("--inference", action="store_true")
    ap.add_argument("--all-actors", action="store_true")
    ap.add_argument("--steps", type=int, default=1)
    args = ap.parse_args()
    np.random.seed(0)
    torch.manual_seed(0)
    root = args.root.resolve()
    weights = HERE.parent / "behavior-bench/weights/SMART_epoch_030.pt"
    codebook = load_map_codebook()
    report = {"schema_version": 1, "diagnostic_only": True, "checkpoint_sha256": sha(weights), "maps": {}}
    protocol_paths = {"adapter": HERE / "faithful_smart.py", "probe": Path(__file__),
        'map_preprocessing':HERE/'faithful_map.py',
        "smart_planner": HERE.parent / "behavior-bench/pufferlib/planning/smart.py",
        "tokenizer": HERE.parent / "behavior-bench/pufferlib/prediction/map_tokenizer.py",
        "training_dataset": HERE.parent / "behavior-bench/pufferlib/prediction/dataset.py",
        "map_codebook": HERE.parent / "behavior-bench/pufferlib/prediction/smart/tokens/map_traj_token5.pkl",
        "motion_codebook": HERE.parent / "behavior-bench/pufferlib/prediction/smart/tokens/cluster_frame_5_2048.pkl",
        "evaluation_ini": HERE.parent / "behavior-bench/pufferlib/config/evaluation.ini"}
    report["protocol_file_sha256"] = {key:sha(path) for key,path in protocol_paths.items()}
    report['map_encoding_protocol']=MAP_ENCODING_PROTOCOL
    report["seed"] = 0
    report["traffic_mode"] = "expert_replay"
    report["history_protocol"] = "10 observed expert warmup steps, then observed pose history"
    report["warmup_steps"] = 10
    for name, path in (("german", root / "testing/map_000000.bin"), ("us", args.us_binary.resolve())):
        binary = read_binary_scenario(str(path))
        tokens = tokenize_roads(binary["roads"], codebook)["pt_token"]
        report["maps"][name] = {"binary_sha256": sha(path), "crosswalk_roads": sum(r["type"] == 8 for r in binary["roads"]),
            "crosswalk_tokens": int((tokens["type"] == 8).sum()), "crosswalk_polygon_tokens": int((tokens["pl_type"] == 3).sum())}
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.planning.smart import SMARTPlanner, SMARTConfig
    if args.all_actors:
        from faithful_smart import FaithfulSMARTPlanner
        SMARTPlanner = FaithfulSMARTPlanner
    alias = Path("/tmp") / ("geo_scene_" + hashlib.sha256(str(root).encode()).hexdigest()[:12])
    if not alias.exists():
        alias.symlink_to(root, target_is_directory=True)
    env = Drive(data_root=str(alias), split="testing", num_maps=1, num_agents=128,
        episode_length=91, map_id=0, action_type="continuous", control_mode="control_evaluation",
        goal_behavior=3, goal_radius=2.0, goal_speed=20.0,
        ini_file=str(HERE.parent / "behavior-bench/pufferlib/config/evaluation.ini"), resample_frequency=0)
    report['evaluator_goal'] = {'radius_m':env.goal_radius, 'max_speed_mps':env.goal_speed}
    try:
        env.reset()
        binary_scene = read_binary_scenario(str(root / "testing/map_000000.bin"))
        ego_index = binary_scene["sdc_track_index"]
        ego_slot = env.get_state()[0]["active_agent_indices"].index(ego_index)
        planner = SMARTPlanner(env, ego_index if args.all_actors else ego_slot, np.array([-4, -1], dtype=np.float32), np.array([4, 1], dtype=np.float32),
            SMARTConfig(weights_path=str(weights), device="cpu", greedy=True))
        planner._load_map()
        report['planner_config'] = {'history_steps':planner.config.num_historical_steps,
            'prediction_interval_steps':planner.config.repredict_interval,'dt':planner.config.dt,
            'greedy':planner.config.greedy,'device':str(planner.device)}
        origin = np.asarray(getattr(planner, 'input_frame_origin', [0.0,0.0]))
        report['input_frame_origin_world_m'] = origin.tolist()
        raw_map = tokenize_roads(binary_scene['roads'], codebook)['pt_token']['position'].numpy()
        actual_map = planner.map_data['pt_token']['position'].numpy()
        report['map_frame_position_error_m'] = float(np.max(np.linalg.norm(actual_map[:,:2].astype(float)+origin-raw_map[:,:2],axis=1)))
        feature_audit = {"steps": [], "presence_mismatches": 0, "class_mismatches": 0,
                         "max_position_error_m": 0.0, "max_local_position_error_m": 0.0,
                         "max_heading_error_rad": 0.0, "max_dimension_error_m": 0.0,
                         "max_evaluator_velocity_error_mps": 0.0}
        def audit_source_features(step, states=None):
            if not args.all_actors:
                return
            values = planner._get_agent_states() if states is None else states
            entities = planner._state()['entities']
            feature_audit['steps'].append(step)
            for index, obj in enumerate(binary_scene['objects']):
                expected = bool(obj['traj_valid'][step])
                present = values[3][index] > 0
                feature_audit['presence_mismatches'] += int(expected != present)
                if not (expected and present):
                    continue
                feature_audit['class_mismatches'] += int(values[6][index] != obj['type'])
                feature_audit['max_evaluator_velocity_error_mps'] = max(
                    feature_audit['max_evaluator_velocity_error_mps'],
                    float(np.hypot(entities[index]['vx']-obj['traj_vx'][step],
                                   entities[index]['vy']-obj['traj_vy'][step])))
                feature_audit['max_local_position_error_m'] = max(feature_audit['max_local_position_error_m'],
                    float(np.hypot(values[0][index]-entities[index]['x'], values[1][index]-entities[index]['y'])))
                feature_audit['max_position_error_m'] = max(feature_audit['max_position_error_m'],
                    float(np.hypot(values[0][index]+origin[0]-obj['traj_x'][step],values[1][index]+origin[1]-obj['traj_y'][step])))
                feature_audit['max_heading_error_rad'] = max(feature_audit['max_heading_error_rad'],
                    float(abs((values[2][index]-obj['traj_heading'][step]+np.pi)%(2*np.pi)-np.pi)))
                feature_audit['max_dimension_error_m'] = max(feature_audit['max_dimension_error_m'],
                    float(abs(values[3][index]-obj['width'])),float(abs(values[4][index]-obj['length'])))
        report['source_feature_audit'] = feature_audit
        report["actual_planner_crosswalk_tokens"] = int((planner.map_data["pt_token"]["type"] == 8).sum())
        scene = binary_scene
        state = env.get_state()[0]
        active = list(range(len(scene["objects"]))) if args.all_actors else state["active_agent_indices"]
        report["smart_input_source_track_ids"] = [scene["objects"][i]["id"] for i in active]
        report["source_actors_omitted_from_smart_state"] = [obj["id"] for i, obj in enumerate(scene["objects"]) if i not in active]
        states = planner._get_agent_states()
        audit_source_features(0, states)
        report["nonfinite_smart_input_headings"] = int(np.count_nonzero(~np.isfinite(states[2])))
        if args.all_actors:
            planner._observed_step = 0
            speeds = np.zeros(states[5], dtype=np.float32)
            planner._bootstrap_speeds_from_state(speeds, states[5])
            saved = []
            for obj in planner._scenario_objects:
                for key in ("traj_x", "traj_y", "traj_vx", "traj_vy"):
                    saved.append((obj, key, obj[key].copy()))
                    obj[key][1:] += 10000
            try:
                changed = planner._get_agent_states()
                changed_speeds = np.zeros(states[5], dtype=np.float32)
                planner._bootstrap_speeds_from_state(changed_speeds, states[5])
                report["future_mutation_invariant_at_reset"] = bool(all(np.array_equal(a,b) for a,b in zip(states[:5],changed[:5])) and np.array_equal(speeds,changed_speeds))
            finally:
                for obj,key,value in saved:
                    obj[key][:] = value
            from pufferlib.ocean.drive import binding
            original_ego = env.get_state()[0]["entities"][ego_index]
            binding.vec_set_positions(env.c_envs, [ego_slot], [original_ego["x"]+1], [original_ego["y"]], [original_ego["heading"]])
            moved = planner._get_agent_states()
            report["perturbed_ego_input_error_m"] = float(np.hypot(moved[0][ego_index]-states[0][ego_index]-1, moved[1][ego_index]-states[1][ego_index]))
            env.reset()
        report["present_smart_input_source_track_ids"] = [scene["objects"][active[i]]["id"] for i in range(states[5]) if states[3][i] > 0]
        report["runtime_source_sha256"] = runtime["runtime_source_sha256"]
        if args.inference:
            slot = ego_slot
            start_step = 0
            if args.all_actors:
                from pufferlib.ocean.drive import binding
                binding.vec_set_movement_mode(env.c_envs, list(range(env.num_agents)), 2)
                for step in range(10):
                    x,y,h,w,l,n,types = planner._get_agent_states()
                    audit_source_features(step, (x,y,h,w,l,n,types))
                    planner.history.append(x,y,h,w,l,n,types)
                    env.step(np.zeros((env.num_agents,2),dtype=np.float32))
                start_step = 10
            action = planner.plan(current_step=start_step, obs=np.array(env.observations[slot], copy=True))
            audit_source_features(start_step)
            report["initial_action"] = np.asarray(action).tolist()
            report["inference_finite"] = bool(np.isfinite(action).all())
            report["actual_model_source_track_ids"] = [scene["objects"][active[int(i)]]["id"] for i in planner._valid_agent_map]
            if args.steps > 1:
                from pufferlib.ocean.drive import binding
                binding.vec_set_movement_mode(env.c_envs, list(range(env.num_agents)), 2)
                report["rollout"] = []
                for step in range(start_step+1, args.steps):
                    env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
                    current = env.get_state()[0]
                    if current["entities"][ego_index]["removed"]:
                        break
                    slot = current["active_agent_indices"].index(ego_index)
                    action = planner.plan(current_step=step, obs=np.array(env.observations[slot], copy=True))
                    audit_source_features(step)
                    model_ids = [scene["objects"][active[int(i)]]["id"] for i in planner._valid_agent_map]
                    expected = [obj["id"] for i, obj in enumerate(scene["objects"])
                                if current["entities"][i]["x"] != -10000.0 and not current["entities"][i]["removed"]]
                    report["rollout"].append({"step": step, "finite_action": bool(np.isfinite(action).all()), "model_track_ids": model_ids,
                        "prediction_refreshed": planner._prediction_step == step,
                        "present_evaluator_track_ids": expected,
                        "identity_match": set(expected) == set(model_ids)})
        if args.all_actors:
            env.reset()
            planner.reset()
            ready = planner.prepare_step(0)
            current_states = planner._get_agent_states()
            last = planner.history.num_steps - 1
            report["prepare_step_bootstrap"] = {"ready": bool(ready), "history_steps": planner.history.num_steps,
                "current_positions_match": bool(np.allclose(planner.history.position[:current_states[5], last, 0], current_states[0])
                    and np.allclose(planner.history.position[:current_states[5], last, 1], current_states[1])),
                "finite_headings": bool(np.isfinite(planner.history.heading).all())}
    finally:
        env.close()
    name = "smart_map_transfer_all_actors_probe.json" if args.all_actors else "smart_map_transfer_probe.json"
    (root / "testing" / name).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
