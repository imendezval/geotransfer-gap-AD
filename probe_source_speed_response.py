"""Synthetic controller reactivity and ego-future isolation for traffic guidance.

This is explicitly not a source-faithful/admitted scene. The same traffic code
runs as in US/German diagnostics. All mutations stay in this synthetic root.
"""
import copy,hashlib,json,sys
from pathlib import Path
import numpy as np
import pilot_ind as p
import source_guided_traffic as traffic
import late_spawn_runtime
HERE=Path(__file__).resolve().parent

def main():
 root=HERE/'pilot/probes/source_speed_controller_response';t=root/'testing';t.mkdir(parents=True,exist_ok=True)
 def obj(i,x,goal):
  return {'id':i,'type':'vehicle','length':4.5,'width':1.8,'height':1.6,'mark_as_expert':0,'valid':[1]*91,'position':[{'x':x+.5*k,'y':0.,'z':0.} for k in range(91)],'velocity':[{'x':5.,'y':0.,'z':0.} for k in range(91)],'heading':[0.]*91,'goalPosition':{'x':goal,'y':0.,'z':0.},'source_window_path_length_m':45.}
 scene={'metadata':{'sdc_track_index':0,'tracks_to_predict':[]},'objects':[obj(1,40.,82.5),obj(2,10.,1000.)],'roads':[{'id':101,'type':'lane','map_element_id':2,'width':6.,'exit_lanes':[],'geometry':[{'x':float(x),'y':0.,'z':0.} for x in range(0,151,2)]}]+[{'id':i,'type':'road_edge','map_element_id':15,'geometry':[{'x':float(x),'y':y,'z':0.} for x in (0,150)]} for i,y in [(201,-3.),(202,3.)]]}
 p.load_source_writer()(scene,str(t/'map_000000.bin'),0,trajectory_length=91);(t/'ind_synthetic_response.json').write_text(json.dumps(scene,indent=2)+'\n')
 sys.path.insert(0,str(p.BENCH));runtime=late_spawn_runtime.load()
 from pufferlib.ocean.drive.drive import Drive
 from pufferlib.ocean.drive import binding
 alias=Path('/tmp/geo_source_speed_response')
 if not alias.exists():alias.symlink_to(root,target_is_directory=True)
 def run(inject):
  env=Drive(data_root=str(alias),split='testing',num_maps=1,num_agents=128,episode_length=91,map_id=0,action_type='continuous',control_mode='control_evaluation',goal_behavior=3,ini_file=str(p.BENCH/'pufferlib/config/evaluation.ini'),resample_frequency=0);rows=[]
  try:
   env.reset();schedule=traffic.release_schedule(scene)
   for step in range(80):
    state=env.get_state()[0];slots={idx:s for s,idx in enumerate(state['active_agent_indices'])}
    binding.vec_set_movement_mode(env.c_envs,[slots[0]],0 if inject and step>=10 else 2)
    traffic.apply(env,scene,schedule,step,binding)
    if inject and step==10:
     follower=env.get_state()[0]['entities'][1];binding.vec_set_positions(env.c_envs,[slots[0]],[follower['x']+25.],[follower['y']],[follower['heading']])
    state=env.get_state()[0];f=state['entities'][1];e=state['entities'][0];rows.append({'step':step,'speed_mps':float(np.hypot(f['vx'],f['vy'])),'x':f['x'],'removed':bool(f['removed']),'collision_state':f['collision_state'],'ego_x':e['x']})
    env.step(np.zeros((env.num_agents,2),dtype=np.float32))
  finally:env.close()
  return rows
 before=run(False);after=run(True)
 reduction=max(a['speed_mps']-b['speed_mps'] for a,b in zip(before[10:41],after[10:41]));no_collision=all(not r['removed'] and not r['collision_state'] for r in after);finite=all(np.isfinite([r['speed_mps'],r['x']]).all() for r in after)
 # Independent ego-future isolation, including a nonzero source ego index.
 checks=[]
 for ego_idx in (0,1):
  data=copy.deepcopy(scene)
  if ego_idx:data['objects'].reverse();data['metadata']['sdc_track_index']=1
  state={'active_agent_indices':[0,1],'entities':[{'x':o['position'][0]['x'],'y':0.,'removed':0,'traj_x':[o['position'][0]['x']],'traj_y':[0.]} for o in data['objects']]}
  class Env:
   c_envs=None
   def get_state(self):return [state]
  class Binding:
   def __init__(self):self.calls=[]
   def vec_set_movement_mode(self,*args):pass
   def vec_set_idm_target_velocity(self,env,slots,speed):self.calls.append((slots,speed))
  env=Env();one=Binding();traffic.apply(env,data,{},0,one)
  mutated=copy.deepcopy(data);mutated['objects'][ego_idx]['position'][1:]=[{'x':999999.,'y':999999.,'z':0.}]*90;mutated['objects'][ego_idx]['velocity'][1:]=[{'x':999.,'y':999.,'z':0.}]*90
  two=Binding();traffic.apply(env,mutated,{},0,two);checks.append({'ego_index':ego_idx,'future_invariant':one.calls==two.calls,'ego_slot_not_controlled':all(ego_idx not in slots for slots,_ in one.calls)})
 report={'diagnostic_only':True,'runtime':runtime,'module_sha256':hashlib.sha256((HERE/'source_guided_traffic.py').read_bytes()).hexdigest(),'source_speed_reduction_within3s_mps':reduction,'follower_no_collision_or_removal':no_collision,'finite':finite,'ego_future_isolation':checks,'passed':reduction>1 and no_collision and finite and all(c['future_invariant'] and c['ego_slot_not_controlled'] for c in checks),'baseline':before,'stationary_leader':after};(HERE/'pilot/audits/step2_source_speed_response.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('baseline','stationary_leader')}));assert report['passed']

if __name__=='__main__':main()
