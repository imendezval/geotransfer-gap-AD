"""Observed background route intent with a native-progress coverage guard.

Never modifies the controlled ego or its observations. Source-startup-held
vehicles retain native routing. Other vehicles use a contiguous logged route
only when it covers max(initial speed, native desired speed) * observed duration.
Native IDM controls acceleration/braking and collision response. The terminal
preview tangent is an explicit controller extrapolation, not source evidence.
"""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
PROTOCOL_VERSION = 'progress_covered_background_route_v1'
ANCHOR = '    agent->route_size = 0;\n\n    float ax = agent->x;'
REPLACEMENT = '    agent->route_size = 0;\n\n    /* Source intent for background traffic only. Keep the current source-valid\n       segment; never connect across an unobserved validity gap. */\n    int geo_start=env->timestep,geo_end=geo_start;\n    float geo_length=0.0f;\n    while(geo_end<agent->array_size && agent->traj_valid[geo_end]==1) {\n        if(geo_end>geo_start)geo_length+=hypotf(agent->traj_x[geo_end]-agent->traj_x[geo_end-1],agent->traj_y[geo_end]-agent->traj_y[geo_end-1]);\n        geo_end++;\n    }\n    float geo_speed_bound=fmaxf(hypotf(agent->vx,agent->vy),agent->idm_target_velocity);\n    float geo_duration=fmaxf(0.0f,(geo_end-geo_start-1)*env->dt);\n    int geo_startup_moving=1;\n    for(int t=geo_start;t<geo_end && t<geo_start+11;t++) {\n        if(hypotf(agent->traj_vx[t],agent->traj_vy[t])<1.0f)geo_startup_moving=0;\n    }\n    int geo_covered=geo_startup_moving && geo_duration>0.0f && geo_length+0.0001f>=geo_speed_bound*geo_duration;\n    if (agent_idx != env->sdc_track_index && geo_covered) {\n        float *rx = malloc(MAX_ROUTE_POINTS * sizeof(float));\n        float *ry = malloc(MAX_ROUTE_POINTS * sizeof(float));\n        int count = 0;\n        int start = env->timestep;\n        if (start > 0 && agent->traj_valid[start-1] == 1) start--;\n        for (int t=start; t<agent->array_size && count<MAX_ROUTE_POINTS; t++) {\n            if (agent->traj_valid[t] != 1) break;\n            if (count && hypotf(agent->traj_x[t]-rx[count-1],agent->traj_y[t]-ry[count-1]) < 0.01f) continue;\n            rx[count]=agent->traj_x[t]; ry[count]=agent->traj_y[t]; count++;\n        }\n        if (count>=2) {\n            /* Same terminal tangent extension as native lane routing. It is\n               traffic-model extrapolation, not a recovered source observation. */\n            float dx=rx[count-1]-rx[count-2], dy=ry[count-1]-ry[count-2];\n            float norm=hypotf(dx,dy);\n            int limit=count+30;\n            if (limit>MAX_ROUTE_POINTS) limit=MAX_ROUTE_POINTS;\n            while (norm>0.001f && count<limit) {\n                rx[count]=rx[count-1]+dx/norm;\n                ry[count]=ry[count-1]+dy/norm; count++;\n            }\n            count=resample_route_uniform(rx,ry,count,1.0f,MAX_ROUTE_POINTS);\n            if (count>=2) {\n                agent->route_x=realloc(rx,count*sizeof(float));\n                agent->route_y=realloc(ry,count*sizeof(float));\n                agent->route_heading=malloc(count*sizeof(float));\n                agent->route_size=count; agent->route_progress=0;\n                for (int t=0;t<count-1;t++) agent->route_heading[t]=atan2f(agent->route_y[t+1]-agent->route_y[t],agent->route_x[t+1]-agent->route_x[t]);\n                agent->route_heading[count-1]=agent->route_heading[count-2];\n                return;\n            }\n        }\n        free(rx); free(ry);\n    }\n\n    float ax = agent->x;'

def patch_header(source):
    if REPLACEMENT in source:
        return source
    if source.count(ANCHOR) != 1:
        raise ValueError('Background-route patch anchor is not unique')
    return source.replace(ANCHOR, REPLACEMENT, 1)

def unpatch_header(source):
    if REPLACEMENT in source:
        return source.replace(REPLACEMENT, ANCHOR, 1)
    if 'geo_startup_moving' in source:
        raise ValueError('Unknown background-route patch version')
    return source
