"""Ensure source visibility re-entry never revives physics-removed traffic."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'behavior-bench'))
import late_spawn_runtime
from pufferlib.prediction.binary_reader import read_binary_scenario

def main():
    ap=argparse.ArgumentParser(__doc__);ap.add_argument('--root',type=Path,required=True);args=ap.parse_args()
    root=args.root.resolve();bp=root/'testing/map_000000.bin';binary=read_binary_scenario(str(bp))
    runtime=late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding
    alias=Path('/tmp')/('geo_scene_'+hashlib.sha256(str(root).encode()).hexdigest()[:12])
    if not alias.exists():alias.symlink_to(root,target_is_directory=True)
    env=Drive(data_root=str(alias),split='testing',num_maps=1,num_agents=128,episode_length=91,map_id=0,
        action_type='continuous',control_mode='control_evaluation',goal_behavior=3,
        ini_file=str(HERE.parent/'behavior-bench/pufferlib/config/evaluation.ini'),resample_frequency=0)
    cases=[]
    try:
        for kind in ('continuous_validity','later_source_reentry'):
            env.reset();state=env.get_state()[0];active=state['active_agent_indices'];ego=binary['sdc_track_index'];e=state['entities'][ego]
            candidates=[i for i in active if i!=ego and binary['objects'][i]['type']==1
                and np.hypot(state['entities'][i]['x']-e['x'],state['entities'][i]['y']-e['y'])>20]
            continuous=[i for i in candidates if all(binary['objects'][i]['traj_valid'][:31])]
            if kind=='continuous_validity':
                first,partner=continuous[:2];end=6;gap=return_step=None
            else:
                choices=[]
                for i in candidates:
                    valid=binary['objects'][i]['traj_valid']
                    gap=next((t for t in range(3,25) if not valid[t] and all(valid[:t])),None)
                    returned=next((t for t in range(gap+1,28) if valid[t]),None) if gap is not None else None
                    if returned is not None and any(j>i for j in continuous):choices.append((i,gap,returned))
                first,gap,return_step=choices[0];partner=next(j for j in continuous if j>first);end=return_step+3
            chosen=[first,partner];slots=[active.index(i) for i in chosen];target=state['entities'][first]
            binding.vec_set_movement_mode(env.c_envs,list(range(env.num_agents)),2)
            binding.vec_set_movement_mode(env.c_envs,slots,0)
            binding.vec_set_positions(env.c_envs,slots,[target['x']]*2,[target['y']]*2,[target['heading']]*2)
            rows=[]
            for step in range(1,end+1):
                env.step(np.zeros((env.num_agents,2),dtype=np.float32));entity=env.get_state()[0]['entities'][first]
                rows.append({'step':step,'source_valid':bool(binary['objects'][first]['traj_valid'][step]),
                    'present':entity['x']!=-10000.0,'removed':entity['removed'],'collision_state':entity['collision_state']})
            passed=rows[0]['removed']==1 and rows[0]['collision_state']==1 and all(not r['present'] for r in rows)
            cases.append({'case':kind,'source_track_id':binary['objects'][first]['id'],'source_gap':gap,'source_return':return_step,
                'passed':passed,'timeline':rows})
    finally:env.close()
    report={'schema_version':1,'runtime_source_sha256':runtime['runtime_source_sha256'],
        'binary_sha256':hashlib.sha256(bp.read_bytes()).hexdigest(),'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'cases':cases,'passed':all(c['passed'] for c in cases)}
    (HERE/'pilot/audits/runtime_source_reentry_regression.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'cases':[{k:v for k,v in c.items() if k!='timeline'} for c in cases]}))
    if not report['passed']:sys.exit(1)

if __name__=='__main__':main()
