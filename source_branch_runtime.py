"""Diagnostic logged background intent for native lane-branch selection only.

Preserves native lane centre geometry, control limits and the ego route builder.
No source position/heading teleportation and no extra map successors.
"""
import late_spawn_runtime as base


def load(initial_only=False):
    original=base.patched_header
    def patched(source,include_semantic_map=False):
        source=original(source,include_semantic_map=include_semantic_map)
        import background_route_intent
        source=background_route_intent.unpatch_header(source)
        anchor='static void build_route_for_agent(Drive* env, int agent_idx) {'
        helper=r'''
static float logged_branch_fit(Drive* env, Entity* agent, Entity* lane, int first_point) {
    int start=env->timestep,end=start;
    while(end<agent->array_size && agent->traj_valid[end]==1)end++;
    if(end-start<11 || lane->array_size<2)return 0.0f;
    float sum=0.0f,length=0.0f;int count=0;
    for(int p=first_point;p<lane->array_size;p++) {
        if(p>first_point)length+=hypotf(lane->traj_x[p]-lane->traj_x[p-1],lane->traj_y[p]-lane->traj_y[p-1]);
        if(length>10.0f)break;
        float best=INFINITY;int best_segment=-1;
        for(int t=start;t<end-1;t++) {
            float dx=agent->traj_x[t+1]-agent->traj_x[t],dy=agent->traj_y[t+1]-agent->traj_y[t];
            float size=dx*dx+dy*dy;if(size<0.000001f)continue;
            float u=((lane->traj_x[p]-agent->traj_x[t])*dx+(lane->traj_y[p]-agent->traj_y[t])*dy)/size;
            u=fmaxf(0.0f,fminf(1.0f,u));
            float ex=lane->traj_x[p]-agent->traj_x[t]-u*dx,ey=lane->traj_y[p]-agent->traj_y[t]-u*dy;
            float d=ex*ex+ey*ey;
            if(d<best){best=d;best_segment=t;}
        }
        // No preference beyond either end of the observed source corridor.
        if(best_segment>start && best_segment<end-2){sum+=fminf(best,100.0f);count++;}
    }
    return count ? sum/count : 0.0f;
}

'''
        source=base.replace_once(source,anchor,helper+anchor)
        if initial_only:
            return base.replace_once(source,
                '            float score = d2 + heading_weight * heading_weight * hdiff * hdiff;',
                '            float score = d2 + heading_weight * heading_weight * hdiff * hdiff;\n'
                '            if(agent_idx!=env->sdc_track_index)score+=logged_branch_fit(env,agent,lane,p);')
        source=base.replace_once(source,
            '                if (d2 < fallback_dist) {\n                    fallback_dist = d2;',
            '                float score=d2;\n'
            '                if(agent_idx!=env->sdc_track_index)score+=logged_branch_fit(env,agent,cand,0);\n'
            '                if (score < fallback_dist) {\n                    fallback_dist = score;')
        source=base.replace_once(source,
            '                if (d2 < best_exit_dist) {\n                    best_exit_dist = d2;',
            '                float score=d2;\n'
            '                if(agent_idx!=env->sdc_track_index)score+=logged_branch_fit(env,agent,cand,0);\n'
            '                if (score < best_exit_dist) {\n                    best_exit_dist = score;')
        return source
    try:
        base.patched_header=patched
        result=base.load()
        result['traffic_route_model']='diagnostic_source_intent_native_initial_lane' if initial_only else 'diagnostic_source_intent_native_branch_ranking'
        return result
    finally:base.patched_header=original
