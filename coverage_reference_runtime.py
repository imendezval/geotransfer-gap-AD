"""Diagnostic logged route only with enough observed path for native progress.

This is an explicit alternative traffic model, never silently substituted into
hybrid_startup admission. The controlled ego keeps the upstream route builder.
Source trajectories specify traffic intent; they are not planner observations.
"""
import late_spawn_runtime as base

def load():
    original=base.patched_header
    def patched(source,include_semantic_map=False):
        source=original(source,include_semantic_map=include_semantic_map)
        if 'geo_startup_moving' in source:return source
        anchor='    agent->route_size = 0;\n\n    float ax = agent->x;'
        replacement=r'''    agent->route_size = 0;

    /* Source intent for background traffic only. Keep the current source-valid
       segment; never connect across an unobserved validity gap. */
    int geo_start=env->timestep,geo_end=geo_start;
    float geo_length=0.0f;
    while(geo_end<agent->array_size && agent->traj_valid[geo_end]==1) {
        if(geo_end>geo_start)geo_length+=hypotf(agent->traj_x[geo_end]-agent->traj_x[geo_end-1],agent->traj_y[geo_end]-agent->traj_y[geo_end-1]);
        geo_end++;
    }
    float geo_speed_bound=fmaxf(hypotf(agent->vx,agent->vy),agent->idm_target_velocity);
    float geo_duration=fmaxf(0.0f,(geo_end-geo_start-1)*env->dt);
    int geo_startup_moving=1;
    for(int t=geo_start;t<geo_end && t<geo_start+11;t++) {
        if(hypotf(agent->traj_vx[t],agent->traj_vy[t])<1.0f)geo_startup_moving=0;
    }
    int geo_covered=geo_startup_moving && geo_duration>0.0f && geo_length+0.0001f>=geo_speed_bound*geo_duration;
    if (agent_idx != env->sdc_track_index && geo_covered) {
        float *rx = malloc(MAX_ROUTE_POINTS * sizeof(float));
        float *ry = malloc(MAX_ROUTE_POINTS * sizeof(float));
        int count = 0;
        int start = env->timestep;
        if (start > 0 && agent->traj_valid[start-1] == 1) start--;
        for (int t=start; t<agent->array_size && count<MAX_ROUTE_POINTS; t++) {
            if (agent->traj_valid[t] != 1) break;
            if (count && hypotf(agent->traj_x[t]-rx[count-1],agent->traj_y[t]-ry[count-1]) < 0.01f) continue;
            rx[count]=agent->traj_x[t]; ry[count]=agent->traj_y[t]; count++;
        }
        if (count>=2) {
            /* Same terminal tangent extension as native lane routing. It is
               traffic-model extrapolation, not a recovered source observation. */
            float dx=rx[count-1]-rx[count-2], dy=ry[count-1]-ry[count-2];
            float norm=hypotf(dx,dy);
            int limit=count+30;
            if (limit>MAX_ROUTE_POINTS) limit=MAX_ROUTE_POINTS;
            while (norm>0.001f && count<limit) {
                rx[count]=rx[count-1]+dx/norm;
                ry[count]=ry[count-1]+dy/norm; count++;
            }
            count=resample_route_uniform(rx,ry,count,1.0f,MAX_ROUTE_POINTS);
            if (count>=2) {
                agent->route_x=realloc(rx,count*sizeof(float));
                agent->route_y=realloc(ry,count*sizeof(float));
                agent->route_heading=malloc(count*sizeof(float));
                agent->route_size=count; agent->route_progress=0;
                for (int t=0;t<count-1;t++) agent->route_heading[t]=atan2f(agent->route_y[t+1]-agent->route_y[t],agent->route_x[t+1]-agent->route_x[t]);
                agent->route_heading[count-1]=agent->route_heading[count-2];
                return;
            }
        }
        free(rx); free(ry);
    }

    float ax = agent->x;'''
        return base.replace_once(source,anchor,replacement)
    try:
        base.patched_header=patched
        result=base.load()
        result['traffic_route_model']='diagnostic_progress_covered_background_reference'
        return result
    finally:base.patched_header=original
