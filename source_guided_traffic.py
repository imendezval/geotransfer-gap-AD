"""Experimental source-speed-guided hybrid traffic, without ego future input.

Nominal source speed plus along-track feedback supplies IDM's desired speed.
IDM retains its acceleration limits, collision handling and leading-actor brake
response. No position/heading is teleported and no actor is hidden. The source
reference is an explicit traffic prior, not an unchanged-BehaviorBench claim.
"""
import math
import hybrid_traffic

_assign_modes=hybrid_traffic.apply
release_schedule=hybrid_traffic.release_schedule
GAIN_PER_SECOND=1.0
MAX_TARGET_SPEED_MPS=30.0

def apply(env,scene,schedule,step,binding):
    held=_assign_modes(env,scene,schedule,step,binding)
    state=env.get_state()[0]
    slots={index:slot for slot,index in enumerate(state['active_agent_indices'])}
    ego=scene.get('metadata',{}).get('sdc_track_index',0)
    anchor=state['entities'][ego]
    origin=(scene['objects'][ego]['position'][0]['x']-anchor['traj_x'][0],
            scene['objects'][ego]['position'][0]['y']-anchor['traj_y'][0])
    for index,obj in enumerate(scene['objects']):
        if index==ego or obj['type']!='vehicle' or obj['mark_as_expert']:continue
        if index in schedule and step<schedule[index]:continue
        slot=slots.get(index)
        if slot is None or not obj['valid'][step]:continue
        entity=state['entities'][index]
        if entity['x']==-10000.0 or entity['removed']:continue
        reference=obj['position'][step];velocity=obj['velocity'][step];heading=obj['heading'][step]
        dx=reference['x']-(entity['x']+origin[0]);dy=reference['y']-(entity['y']+origin[1])
        error=dx*math.cos(heading)+dy*math.sin(heading)
        target=min(MAX_TARGET_SPEED_MPS,max(0.,math.hypot(velocity['x'],velocity['y'])+GAIN_PER_SECOND*error))
        binding.vec_set_idm_target_velocity(env.c_envs,[slot],float(target))
    return held
