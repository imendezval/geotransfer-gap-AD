"""Progressive source screens and full technical gates for a frozen candidate queue.

Never grants research admission. Manual source review and SMART model-input
proof are separate. Resume skips only records bound to unchanged sources/tools.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import fcntl

HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def scene_key(row):return (row['recording'],row['ego'],row['first_frame'])

def candidate_key(row):return (*scene_key(row),row['actor'])

def unsupported_rules(a):
    flags=[]
    for rule in a.get('governing_regulatory_elements',[]):
        if not any(m['role']=='yield' for m in rule['ego_members']):continue
        if any(s.get('subtype')=='de206' for s in rule.get('signs',[])):flags.append('ego_stop_sign_requires_stop_even_without_conflicting_traffic')
        for actor in a.get('priority_lane_traffic',[]):
            if actor.get('actor_source_path_m',0)>1 and actor.get('minimum_spatial_box_gap_m',float('inf'))<=2 and any(actor.get('priority_lanelet_steps',{}).get(str(lid)) for lid in rule['priority_lanelets']):
                flags.append(f"rule_{rule['id']}_priority_{actor['type']}_{actor['track_id']}_spatial_conflict")
    for key,prefix in [('oncoming_turn_conflicts','implicit_oncoming_turn_priority'),('slow_ego_fast_crosspath_conflicts','slow_ego_fast_crosspath'),('yield_lane_fast_crosspath_conflicts','yield_lane_fast_crosspath')]:
        flags.extend(f"{prefix}_{x['type']}_{x['track_id']}" for x in a.get(key,[]))
    return sorted(set(flags))

def main():
    ap=argparse.ArgumentParser(__doc__);ap.add_argument('--selection',type=Path,default=HERE/'pilot/audits/step2_oriented_source_selection.json');ap.add_argument('--ledger',type=Path,default=HERE/'pilot/audits/step2_oriented_candidate_ledger.json');ap.add_argument('--limit',type=int,default=12);ap.add_argument('--workers',type=int,default=2);ap.add_argument('--one-faithful-window-per-task',action='store_true',help='Defer alternate windows after a technically admitted, primary-actor-preserved window; manual/research review remains mandatory.');args=ap.parse_args()
    os.chdir(HERE)
    selection=json.loads(args.selection.read_text());jobs=selection['jobs']
    # Round-robin source strata; no planner outcomes participate in ordering.
    groups={}
    for r in jobs:groups.setdefault((r['location'],r['role']),[]).append(r)
    jobs=[groups[k][i] for i in range(max(map(len,groups.values()),default=0)) for k in sorted(groups) if i<len(groups[k])]
    def task_key(r):return (r['recording'],r['ego'],r['actor'])
    if args.one_faithful_window_per_task:
        tasks={}
        for r in jobs:tasks.setdefault(task_key(r),[]).append(r)
        jobs=[tasks[k][i] for i in range(max(map(len,tasks.values()),default=0)) for k in tasks if i<len(tasks[k])]
    tools=['pilot_ind.py','admit_scene.py','audit_scene.py','audit_rule_applicability.py','audit_map_semantics.py','audit_physical_source.py','late_spawn_runtime.py','hybrid_traffic.py','audit_task_rule_scope.py','audit_following_scope.py',Path(__file__).name]
    fingerprints={n:sha(HERE/n) for n in tools};fingerprints['selection']=sha(args.selection)
    fingerprints['variant_selection_mode']='one_faithful_per_task' if args.one_faithful_window_per_task else 'all_windows'
    previous=json.loads(args.ledger.read_text()) if args.ledger.exists() else {'results':[]}
    rows=previous['results'];done={candidate_key(r) for r in rows if r.get('screen_fingerprints')==fingerprints}
    remaining=[r for r in jobs if candidate_key(r) not in done]
    print('remaining chunk',len(remaining),'total selection',len(jobs),flush=True)
    env=dict(os.environ,MPLCONFIGDIR=os.environ.get('MPLCONFIGDIR','/tmp/geotransfer_mpl'),OMP_NUM_THREADS='2')
    scene_locks={scene_key(row):threading.Lock() for row in jobs}
    def run(row):
        # Actor opportunities can share a converted root. Preserve both
        # assessments and serialize their filesystem mutations.
        with scene_locks[scene_key(row)]:
            root=HERE/'pilot/oriented_v3'/f"r{row['recording']:02d}_e{row['ego']}_f{row['first_frame']}"
            root.mkdir(parents=True,exist_ok=True)
            # Also coordinate independent queue processes sharing this scene.
            with(root/'.candidate_queue.lock').open('a')as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                try:return run_scene(row)
                finally:fcntl.flock(lock,fcntl.LOCK_UN)
    def run_scene(row):
        row=dict(row);rec,ego,first=row['recording'],row['ego'],row['first_frame'];root=HERE/'pilot/oriented_v3'/f'r{rec:02d}_e{ego}_f{first}';t=root/'testing';root.mkdir(parents=True,exist_ok=True)
        row.update(root=str(root),screen_fingerprints=fingerprints)
        def command(script,extra=()):
            proc=subprocess.run([sys.executable,str(HERE/script),'--root',str(root),*extra],env=env,capture_output=True,text=True);(root/(script+'.log')).write_text(proc.stdout+proc.stderr);return proc
        proc=subprocess.run([sys.executable,str(HERE/'pilot_ind.py'),'--recording',str(rec),'--ego',str(ego),'--first-frame',str(first),'--goal-sample','85','--late-mode','runtime_spawn','--static-crop-radius','1000000','--parked-as-static-expert','--emit-crosswalks','--output-root',str(root)],env=env,capture_output=True,text=True);(root/'conversion.log').write_text(proc.stdout+proc.stderr)
        if proc.returncode:row.update(status='conversion_failure',error=proc.stderr[-1000:]);return row
        for script in ['audit_scene.py','audit_map_semantics.py','audit_rule_applicability.py']:
            proc=command(script)
            if proc.returncode:row.update(status='source_audit_error',error=proc.stderr[-1000:]);return row
        m=json.loads((t/'map_audit.json').read_text());a=json.loads((t/'rule_applicability_audit.json').read_text())
        row['source_unsupported_rule_flags']=unsupported_rules(a)
        if m['ego_samples_outside_lanelet_polygons'] or not m['occupied_start_to_occupied_goal_reachable']:
            row.update(status='source_geometry_rejection',outside_steps=m['ego_samples_outside_lanelet_polygons'],directed_route=m['occupied_start_to_occupied_goal_reachable']);return row
        # These are exactly the hard rule classes the current SMART gate
        # cannot resolve. Crosswalks are intentionally not rejected here.
        if row['source_unsupported_rule_flags']:
            pending=set(row['source_unsupported_rule_flags'])
            if 'ego_stop_sign_requires_stop_even_without_conflicting_traffic' in pending:
                proc=command('audit_task_rule_scope.py')
                if proc.returncode==0:
                    scope=json.loads((t/'source_task_rule_scope.json').read_text())
                    scoped=bool(scope['rules']) and all(x['stop_obligation_outside_task'] for x in scope['rules'])
                    row['stop_scope_requires_explicit_manual_review']=scoped
                    if scoped:pending.remove('ego_stop_sign_requires_stop_even_without_conflicting_traffic')
            from audit_following_scope import heuristic_flags
            flag_actors=heuristic_flags(a)
            ids=sorted({flag_actors[x] for x in pending if x in flag_actors})
            if ids:
                proc=command('audit_following_scope.py',['--actors',*map(str,ids)])
                if proc.returncode==0:
                    proof=json.loads((t/'source_following_scope.json').read_text())
                    certified={x['actor_id'] for x in proof['actors'] if x['same_route_following']}
                    row['same_route_following_requires_manual_review']=sorted(certified)
                    pending={x for x in pending if not(x in flag_actors and flag_actors[x] in certified)}
            row['unresolved_rule_flags_after_source_proofs']=sorted(pending)
            if pending:
                row.update(status='unresolved_semantics_screen',note='Current SMART hard-rule exclusion; no model run. Source interpretation may be revisited, never silently admitted.');return row
        proc=command('audit_physical_source.py')
        if proc.returncode:row.update(status='physical_audit_error',error=proc.stderr[-1000:]);return row
        physical=json.loads((t/'physical_source_audit.json').read_text())
        if str(ego) in physical.get('source_box_boundary_contacts',{}):row.update(status='source_ego_boundary_rejection');return row
        details=physical.get('source_box_actor_overlap_details',{})
        if any(not d.get('reviewable_annotation_overlap') for d in details.values()):
            row.update(status='unreviewable_source_overlap',overlaps=list(details));return row
        proc=command('admit_scene.py',['--traffic-protocol','hybrid_startup'])
        gate=t/'admission_hybrid_startup.json'
        if not gate.exists():row.update(status='technical_gate_error',error=proc.stderr[-1000:]);return row
        d=json.loads(gate.read_text());interaction=json.loads((t/'interaction_fidelity_audit_hybrid_startup.json').read_text())
        row.update(status='awaiting_manual_review' if d['technical_admitted'] else 'technical_rejection',technical_admitted=d['technical_admitted'],technical_gate_reasons=d['exclusion_reasons'],preserved_actor_ids=[x['track_id'] for x in interaction['actor_opportunities'] if x['preserved_for_claimed_interaction']],candidate_actor_fidelity=next((x for x in interaction['actor_opportunities'] if x['track_id']==row['actor']),None))
        return row
    faithful={task_key(r) for r in rows if r.get('screen_fingerprints')==fingerprints
        and r.get('technical_admitted') and (r.get('candidate_actor_fidelity') or {}).get('preserved_for_claimed_interaction')}
    attempted=0
    def record(row):
        nonlocal rows,attempted
        rows=[r for r in rows if not(candidate_key(r)==candidate_key(row)
              and r.get('screen_fingerprints')==fingerprints)]+[row]
        if row.get('technical_admitted') and (row.get('candidate_actor_fidelity') or {}).get('preserved_for_claimed_interaction'):faithful.add(task_key(row))
        attempted+=1
        report={'schema_version':2,'selection_sha256':sha(args.selection),
            'record_identity':'recording/ego/frame/actor/producer-fingerprints; scene writes serialized',
            'variant_selection_mode':fingerprints['variant_selection_mode'],'results':rows}
        args.ledger.parent.mkdir(parents=True,exist_ok=True)
        temporary=args.ledger.with_name(args.ledger.name+'.tmp')
        temporary.write_text(json.dumps(report,indent=2)+'\n');temporary.replace(args.ledger)
        print(Path(row['root']).name,row['status'],row.get('preserved_actor_ids',[]),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        if not args.one_faithful_window_per_task:
            for row in pool.map(run,remaining[:args.limit]):record(row)
        else:
            while remaining and attempted<args.limit:
                batch=[];later=[];batch_tasks=set();batch_scenes=set()
                for r in remaining:
                    key=task_key(r)
                    if key in faithful:continue
                    if len(batch)<min(args.workers,args.limit-attempted) and key not in batch_tasks and scene_key(r) not in batch_scenes:
                        batch.append(r);batch_tasks.add(key);batch_scenes.add(scene_key(r))
                    else:later.append(r)
                remaining=later
                if not batch:break
                for row in pool.map(run,batch):record(row)
    print('attempted',attempted,'faithful tasks',len(faithful),
        'unprocessed viable variants',sum(task_key(r) not in faithful and
            candidate_key(r) not in
            {candidate_key(x) for x in rows if x.get('screen_fingerprints')==fingerprints} for r in remaining),flush=True)

if __name__=='__main__':main()
