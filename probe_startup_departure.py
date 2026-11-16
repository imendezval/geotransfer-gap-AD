"""Isolated sustained-departure startup experiment; never grants admission."""
import argparse,hashlib,json,math,runpy,shutil,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent

def sustained_release_schedule(scene):
    schedule={};ego=scene.get('metadata',{}).get('sdc_track_index',0)
    for index,obj in enumerate(scene['objects']):
        if index==ego or obj['type']!='vehicle' or obj['mark_as_expert']:continue
        birth=next((t for t,v in enumerate(obj['valid'])if v),None)
        if birth is None:continue
        speed=[math.hypot(v['x'],v['y'])for v in obj['velocity']]
        # Include vehicles completing a stop during the observed startup history.
        # Eligibility never uses the ego route or any candidate identity.
        startup=range(birth,min(birth+11,len(obj['valid'])))
        if not any(obj['valid'][t] and speed[t]<1 for t in startup):continue
        points=[p for t,p in enumerate(obj['position'])if obj['valid'][t]]
        path=sum(math.dist((a['x'],a['y']),(b['x'],b['y']))for a,b in zip(points,points[1:]))
        if path<1:continue
        start=obj['position'][birth]
        release=next((t for t in range(birth+10,len(obj['valid'])-4)
            if all(obj['valid'][t:t+5]) and min(speed[t:t+5])>=2
            and math.dist((obj['position'][t]['x'],obj['position'][t]['y']),(start['x'],start['y']))>=1),len(obj['valid']))
        schedule[index]=release
    return schedule

def main():
    ap=argparse.ArgumentParser(__doc__);ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--output-root',type=Path,required=True);args=ap.parse_args()
    source,root=args.root.resolve(),args.output_root.resolve()
    if source==root:raise ValueError('Use a separate diagnostic root')
    t=root/'testing';t.mkdir(parents=True,exist_ok=True)
    for pattern in ('ind_*.json','map_000000.bin','validation.json','manifest.csv','rule_applicability_audit.json'):
        for p in (source/'testing').glob(pattern):shutil.copy2(p,t/p.name)
    import hybrid_traffic
    hybrid_traffic.release_schedule=sustained_release_schedule
    for script,extra in [('trace_eval_lifecycle.py',['--traffic-mode','hybrid_startup']),
                         ('audit_interaction_fidelity.py',['--traffic-mode','hybrid_startup']),
                         ('probe_counterfactual.py',['--require-hybrid','--report-name','counterfactual_departure_diagnostic.json'])]:
        sys.argv=[script,'--root',str(root),*extra];runpy.run_path(str(HERE/script),run_name='__main__')
    trace=json.loads((t/'lifecycle_trace_hybrid_startup.json').read_text())
    inter=json.loads((t/'interaction_fidelity_audit_hybrid_startup.json').read_text())
    cf=json.loads((t/'counterfactual_departure_diagnostic.json').read_text())
    scene=json.loads(next(t.glob('ind_*.json')).read_text());ego=scene['objects'][0]['id']
    result={'diagnostic_only':True,'source_root':str(source),'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'runtime_source_sha256':trace['runtime_source_sha256'],
        'preserved_actor_ids':[r['track_id']for r in inter['actor_opportunities']if r['preserved_for_claimed_interaction']],
        'background_losses':{k:v['cause']for k,v in trace['first_source_valid_losses'].items()if k!=str(ego)},
        'ego_loss':trace['first_source_valid_losses'].get(str(ego),{}).get('cause'),
        'counterfactual_passed':cf['passed'],'release_steps':trace['hybrid_release_steps_by_track_id']}
    (root/'diagnostic_summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)

if __name__=='__main__':main()
