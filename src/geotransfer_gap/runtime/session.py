"""Canonical single-scene runtime setup and read-only observation capture."""
import hashlib
from pathlib import Path
from geotransfer_gap.config import settings, ensure_bench

def short_alias(root):
    root=Path(root).resolve()
    alias=Path('/tmp')/('geo_scene_'+hashlib.sha256(str(root).encode()).hexdigest()[:12])
    if alias.is_symlink() and alias.resolve()!=root:
        raise RuntimeError(f'Unexpected scene alias: {alias}')
    if not alias.exists():alias.symlink_to(root,target_is_directory=True)
    return alias

def evaluation_env(root, **overrides):
    ensure_bench()
    from . import late_spawn_runtime
    late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    options=dict(data_root=str(short_alias(root)),split='testing',num_maps=1,num_agents=128,
                 episode_length=91,map_id=0,action_type='continuous',control_mode='control_evaluation',
                 goal_behavior=3,goal_radius=2.0,goal_speed=20.0,
                 ini_file=str(settings().bench/'pufferlib/config/evaluation.ini'),resample_frequency=0)
    options.update(overrides)
    return Drive(**options)

def frame(state, binary, step):
    """Use an observed source anchor, including for late actors and nonzero SDCs."""
    anchor=next(i for i,o in enumerate(binary['objects']) if o['traj_valid'][0])
    obj=binary['objects'][anchor];entity=state['entities'][anchor]
    ox=float(obj['traj_x'][0])-float(entity['traj_x'][0])
    oy=float(obj['traj_y'][0])-float(entity['traj_y'][0])
    actors=[]
    for i,obj in enumerate(binary['objects']):
        e=state['entities'][i]
        present=e['x']!=-10000.0 and not e['removed']
        actors.append(dict(id=int(obj['id']),binary_index=i,type=int(obj['type']),present=present,
                           x=float(e['x'])+ox if present else None,y=float(e['y'])+oy if present else None,
                           heading=float(e['heading']),width=float(e['width']),length=float(e['length']),
                           vx=float(e['vx']),vy=float(e['vy']),removed=bool(e['removed']),
                           collision_state=int(e['collision_state']),movement_mode=int(e['movement_mode']),
                           reached_goal=bool(e['reached_goal_this_episode'])))
    return dict(step=step,time_s=step*.1,actors=actors)
