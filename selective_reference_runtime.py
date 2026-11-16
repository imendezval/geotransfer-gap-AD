"""Diagnostic: correct sustained logged-route disagreement, retaining native routes otherwise."""
import late_spawn_runtime as base


def load():
    original=base.patched_header
    def patched(source,include_semantic_map=False):
        source=original(source,include_semantic_map=include_semantic_map)
        import background_route_intent
        source=background_route_intent.unpatch_header(source)
        source=base.replace_once(source,'static void build_route_for_agent(Drive* env, int agent_idx) {',
                                 'static void build_native_route_for_agent(Drive* env, int agent_idx) {')
        anchor='// Build lane routes for all active agents — called after set_start_position in c_reset'
        wrapper=r'''
static void build_route_for_agent(Drive* env, int agent_idx) {
    build_native_route_for_agent(env, agent_idx);
    Entity* agent=&env->entities[agent_idx];
    if (agent_idx==env->sdc_track_index || agent->removed || agent->x==INVALID_POSITION || agent->route_size<2) return;
    int start=env->timestep, run=0, mismatch=0;
    float tolerance=fmaxf(0.5f,agent->width*0.5f);
    for (int t=start;t<agent->array_size;t++) {
        if (agent->traj_valid[t]!=1) break;
        float best=INFINITY;
        for (int k=0;k<agent->route_size-1;k++) {
            float dx=agent->route_x[k+1]-agent->route_x[k],dy=agent->route_y[k+1]-agent->route_y[k];
            float size=dx*dx+dy*dy;
            if(size<0.000001f) continue;
            float u=((agent->traj_x[t]-agent->route_x[k])*dx+(agent->traj_y[t]-agent->route_y[k])*dy)/size;
            u=fmaxf(0.0f,fminf(1.0f,u));
            float distance=hypotf(agent->traj_x[t]-agent->route_x[k]-u*dx,agent->traj_y[t]-agent->route_y[k]-u*dy);
            if(distance<best) best=distance;
        }
        run=best>tolerance ? run+1 : 0;
        if(run>=5) {mismatch=1;break;}
    }
    if(!mismatch) return;
    float* rx=malloc(MAX_ROUTE_POINTS*sizeof(float));
    float* ry=malloc(MAX_ROUTE_POINTS*sizeof(float));
    int count=0;
    if(start>0 && agent->traj_valid[start-1]==1) start--;
    for(int t=start;t<agent->array_size && count<MAX_ROUTE_POINTS;t++) {
        if(agent->traj_valid[t]!=1) break;
        if(count && hypotf(agent->traj_x[t]-rx[count-1],agent->traj_y[t]-ry[count-1])<0.01f) continue;
        rx[count]=agent->traj_x[t];ry[count]=agent->traj_y[t];count++;
    }
    if(count<2) {free(rx);free(ry);return;}
    float dx=rx[count-1]-rx[count-2],dy=ry[count-1]-ry[count-2],norm=hypotf(dx,dy);
    int limit=count+30;if(limit>MAX_ROUTE_POINTS)limit=MAX_ROUTE_POINTS;
    while(norm>0.001f && count<limit) {rx[count]=rx[count-1]+dx/norm;ry[count]=ry[count-1]+dy/norm;count++;}
    count=resample_route_uniform(rx,ry,count,1.0f,MAX_ROUTE_POINTS);
    if(count<2) {free(rx);free(ry);return;}
    free(agent->route_x);free(agent->route_y);free(agent->route_heading);
    agent->route_x=realloc(rx,count*sizeof(float));agent->route_y=realloc(ry,count*sizeof(float));
    agent->route_heading=malloc(count*sizeof(float));agent->route_size=count;agent->route_progress=0;
    for(int t=0;t<count-1;t++)agent->route_heading[t]=atan2f(agent->route_y[t+1]-agent->route_y[t],agent->route_x[t+1]-agent->route_x[t]);
    agent->route_heading[count-1]=agent->route_heading[count-2];
}

'''
        return base.replace_once(source,anchor,wrapper+anchor)
    try:
        base.patched_header=patched
        result=base.load()
        result['traffic_route_model']='diagnostic_sustained_native_route_disagreement'
        return result
    finally:base.patched_header=original
