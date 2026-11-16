"""US mechanical parity for source-guided traffic; never research admission."""
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np
import pilot_ind as p
import source_guided_traffic as traffic
import late_spawn_runtime
HERE=Path(__file__).resolve().parent

def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--us-json',type=Path,required=True);ap.add_argument('--output-root',type=Path,required=True);ap.add_argument('--steps',type=int,default=50);args=ap.parse_args();scene=json.loads(args.us_json.read_text());root=args.output_root.resolve();t=root/'testing';t.mkdir(parents=True,exist_ok=True);binary=t/'map_000000.bin';p.load_source_writer()(scene,str(binary),0,trajectory_length=91);(t/'ind_us_source.json').write_text(json.dumps(scene,indent=2)+'\n')
 sys.path.insert(0,str(p.BENCH));runtime=late_spawn_runtime.load()
 from pufferlib.ocean.drive.drive import Drive
 from pufferlib.ocean.drive import binding
 key=hashlib.sha256((str(root)+str(args.us_json.resolve())).encode()).hexdigest()[:12];alias=Path('/tmp')/('geo_speed_us_'+key)
 if not alias.exists():alias.symlink_to(root,target_is_directory=True)
 env=Drive(data_root=str(alias),split='testing',num_maps=1,num_agents=128,episode_length=91,map_id=0,action_type='continuous',control_mode='control_evaluation',goal_behavior=3,ini_file=str(p.BENCH/'pufferlib/config/evaluation.ini'),resample_frequency=0);ego=scene['metadata']['sdc_track_index'];schedule=traffic.release_schedule(scene);rows=[];terminal=None;actual_calls=[];setter=binding.vec_set_idm_target_velocity
 def capture(vec,slots,target):
  actual_calls.append((tuple(slots),target));return setter(vec,slots,target)
 binding.vec_set_idm_target_velocity=capture
 try:
  env.reset();state=env.get_state()[0];anchor=next(i for i,o in enumerate(scene['objects']) if i!=ego and o['valid'][0]);origin=(scene['objects'][anchor]['position'][0]['x']-state['entities'][anchor]['traj_x'][0],scene['objects'][anchor]['position'][0]['y']-state['entities'][anchor]['traj_y'][0])
  for step in range(min(args.steps,90)):
   state=env.get_state()[0];entity=state['entities'][ego]
   if entity['removed'] or entity['x']==-10000.:
    terminal={'step':step,'collision_state':entity['collision_state']};break
   slots={index:slot for slot,index in enumerate(state['active_agent_indices'])};binding.vec_set_movement_mode(env.c_envs,[slots[ego]],2);actual_calls.clear();traffic.apply(env,scene,schedule,step,binding);after=env.get_state()[0];expected={}
   for index,o in enumerate(scene['objects']):
    e=state['entities'][index]
    if index==ego or o['type']!='vehicle' or o['mark_as_expert'] or index not in slots or not o['valid'][step] or e['x']==-10000. or e['removed'] or (index in schedule and step<schedule[index]):continue
    q=o['position'][step];v=o['velocity'][step];h=o['heading'][step];error=(q['x']-e['x']-origin[0])*math.cos(h)+(q['y']-e['y']-origin[1])*math.sin(h);expected[(slots[index],)]=min(30.,max(0.,math.hypot(v['x'],v['y'])+error))
   got=dict(actual_calls);error=max((abs(got[k]-value) for k,value in expected.items() if k in got),default=0.)
   modes=[{'track_id':scene['objects'][i]['id'],'mode':after['entities'][i]['movement_mode'],'expected_mode':2 if step<release else 1} for i,release in schedule.items() if i in slots and after['entities'][i]['x']!=-10000. and step in (0,release-1,release)]
   rows.append({'step':step,'target_slots_match':set(got)==set(expected),'max_target_error_mps':error,'ego_slot_not_guided':(slots[ego],) not in got,'target_calls':len(got),'mode_checks':modes})
   env.step(np.zeros((env.num_agents,2),dtype=np.float32))
 finally:binding.vec_set_idm_target_velocity=setter;env.close()
 passed=len(rows)>=20 and sum(r['target_calls'] for r in rows)>0 and all(r['target_slots_match'] and r['ego_slot_not_guided'] and r['max_target_error_mps']<.01 and all(m['mode']==m['expected_mode'] for m in r['mode_checks']) for r in rows)
 report={'diagnostic_only':True,'source_json_sha256':hashlib.sha256(args.us_json.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'traffic_module_sha256':hashlib.sha256((HERE/'source_guided_traffic.py').read_bytes()).hexdigest(),'runtime':runtime,'source_ego_index':ego,'origin_from_non_ego_source_anchor':origin,'target_tolerance_mps':.01,'mechanical_parity_pass':passed,'ego_terminal':terminal,'scope':'Source release modes and desired-speed targets, independently checked against a non-ego coordinate anchor; not a US research cohort or geographic policy score.','rows':rows};(root/'mechanical_parity.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':passed,'ego_index':ego,'steps':len(rows),'targets_checked':sum(r['target_calls'] for r in rows),'terminal':terminal}));assert passed

if __name__=='__main__':main()
