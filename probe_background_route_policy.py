"""Compare production/native route building, including nonzero US ego identities."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root,step,native,output):
    sys.path.insert(0,str(HERE.parent/'behavior-bench'))
    import late_spawn_runtime as runtime
    import background_route_intent
    if native:
        original=runtime.patched_header
        runtime.patched_header=lambda source,include_semantic_map=False: background_route_intent.unpatch_header(original(source,include_semantic_map=include_semantic_map))
    info=runtime.load()
    from pufferlib.prediction.binary_reader import read_binary_scenario
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding
    import hybrid_traffic
    binary=read_binary_scenario(str(root/'testing/map_000000.bin'));ego=binary['sdc_track_index']
    scene={'metadata':{'sdc_track_index':ego},'objects':[]}
    for o in binary['objects']:
        scene['objects'].append({'id':o['id'],'type':{1:'vehicle',2:'pedestrian',3:'cyclist'}[o['type']],
            'mark_as_expert':o['mark_as_expert'],'valid':o['traj_valid'].tolist(),
            'position':[{'x':float(x),'y':float(y)}for x,y in zip(o['traj_x'],o['traj_y'])],
            'velocity':[{'x':float(x),'y':float(y)}for x,y in zip(o['traj_vx'],o['traj_vy'])]})
    alias=Path('/tmp')/('geo_route_policy_'+hashlib.sha256(str(root).encode()).hexdigest()[:12])
    if not alias.exists():alias.symlink_to(root,target_is_directory=True)
    env=Drive(data_root=str(alias),split='testing',num_maps=1,num_agents=128,episode_length=91,
        map_id=0,action_type='continuous',control_mode='control_evaluation',goal_behavior=3,
        ini_file=str(HERE.parent/'behavior-bench/pufferlib/config/evaluation.ini'),resample_frequency=0)
    try:
        env.reset();schedule=hybrid_traffic.release_schedule(scene)
        for t in range(step+1):
            state=env.get_state()[0];active=state['active_agent_indices']
            if ego in active:binding.vec_set_movement_mode(env.c_envs,[active.index(ego)],2)
            hybrid_traffic.apply(env,scene,schedule,t,binding)
            if t<step:env.step(np.zeros((env.num_agents,2),dtype=np.float32))
        entities=env.get_state()[0]['entities']
        routes={str(o['id']):list(zip(entities[i]['route_x'] or [],entities[i]['route_y'] or []))
                for i,o in enumerate(scene['objects'])}
        result={'runtime':info,'ego_binary_index':ego,'ego_track_id':scene['objects'][ego]['id'],
                'binary_sha256':sha(root/'testing/map_000000.bin'),'routes':routes}
        output.write_text(json.dumps(result,indent=2)+'\n')
    finally:env.close()


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--snapshot-root',type=Path);ap.add_argument('--step',type=int,default=0)
    ap.add_argument('--native',action='store_true');ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    if args.snapshot_root:
        snapshot(args.snapshot_root.resolve(),args.step,args.native,args.output);return
    directory=HERE/'pilot/probes/background_route_policy';directory.mkdir(parents=True,exist_ok=True)
    cases=[]
    for name,root,step,actor,expected in [
        ('late_fast_vehicle',HERE/'pilot/oriented_v3/r01_e280_f18833',14,281,True),
        ('short_logged_bus_route',HERE/'pilot/oriented_v3/r07_e200_f25439',0,198,False),
        ('us_ego74',HERE/'pilot/probes/us_hybrid_1002fdc9826fc6d1',0,None,None),
        ('us_ego12',HERE/'pilot/probes/us_smart_negative_world_739e0513c6f7cfe8',0,None,None)]:
        snapshots=[]
        for native in (True,False):
            path=directory/(name+('_native'if native else '_production')+'.json')
            proc=subprocess.run([sys.executable,str(Path(__file__)),'--snapshot-root',str(root),'--step',str(step),
                                 '--output',str(path),*(['--native']if native else[])],capture_output=True,text=True)
            if proc.returncode:raise RuntimeError(proc.stderr[-1500:])
            snapshots.append(json.loads(path.read_text()))
        old,new=snapshots;key=str(new['ego_track_id']);a=np.asarray(old['routes'][key]);b=np.asarray(new['routes'][key])
        error=float(np.linalg.norm(a-b,axis=1).max())if a.shape==b.shape and a.size else 0. if a.shape==b.shape else float('inf')
        changed=(old['routes'][str(actor)]!=new['routes'][str(actor)])if actor is not None else None
        passed=error<=1e-5 and (expected is None or changed==expected)
        cases.append({'case':name,'ego_binary_index':new['ego_binary_index'],'ego_route_error_m':error,
                      'actor':actor,'background_route_changed':changed,'expected_change':expected,'passed':passed})
        if not passed:raise AssertionError(cases[-1])
    import background_route_intent,late_spawn_runtime
    result={'route_policy_sha256':sha(Path(background_route_intent.__file__)),'probe_sha256':sha(Path(__file__)),
            'runtime_source_sha256':late_spawn_runtime.load()['runtime_source_sha256'],
            'cases':cases,'passed':all(c['passed']for c in cases)}
    (HERE/'pilot/audits/background_route_policy_regressions.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
