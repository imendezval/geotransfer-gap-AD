"""Compare isolated expert-velocity repair with unchanged hybrid traffic.

All outputs live in a separate diagnostic root. This cannot grant admission.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import sys

HERE = Path(__file__).resolve().parent


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--output-root',type=Path,required=True)
    args=ap.parse_args()
    source,root=args.root.resolve(),args.output_root.resolve()
    if source==root:raise ValueError('Use a separate diagnostic root')
    t=root/'testing';t.mkdir(parents=True,exist_ok=True)
    for pattern in ('ind_*.json','map_000000.bin','validation.json','manifest.csv','rule_applicability_audit.json'):
        for path in (source/'testing').glob(pattern):shutil.copy2(path,t/path.name)
    import expert_velocity_runtime,late_spawn_runtime
    original=late_spawn_runtime.load
    # Build before replacing the loader, avoiding recursion in the diagnostic.
    runtime=expert_velocity_runtime.load()
    late_spawn_runtime.load=lambda **kwargs:runtime
    try:
        for script,extra in [('trace_eval_lifecycle.py',['--traffic-mode','hybrid_startup']),
                             ('audit_interaction_fidelity.py',['--traffic-mode','hybrid_startup']),
                             ('probe_counterfactual.py',['--require-hybrid','--report-name','counterfactual_expert_velocity_diagnostic.json'])]:
            sys.argv=[script,'--root',str(root),*extra]
            runpy.run_path(str(HERE/script),run_name='__main__')
    finally:late_spawn_runtime.load=original
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    trace=json.loads((t/'lifecycle_trace_hybrid_startup.json').read_text())
    interaction=json.loads((t/'interaction_fidelity_audit_hybrid_startup.json').read_text())
    cf=json.loads((t/'counterfactual_expert_velocity_diagnostic.json').read_text())
    scene=json.loads(next(t.glob('ind_*.json')).read_text())
    import math
    errors=[]
    for obj in scene['objects']:
        for row in trace['timeline'][str(obj['id'])]:
            if row['source_valid'] and row['present'] and row['movement_mode']==2:
                v=obj['velocity'][row['step']]
                errors.append(abs(row['sim_speed_mps']-math.hypot(v['x'],v['y'])))
    result={'diagnostic_only':True,'source_root':str(source),'runtime':runtime,
            'probe_sha256':sha(Path(__file__)),'runtime_wrapper_sha256':sha(HERE/'expert_velocity_runtime.py'),
            'expert_state_samples':len(errors),'maximum_expert_speed_error_mps':max(errors,default=None),
            'preserved_actor_ids':[x['track_id']for x in interaction['actor_opportunities']if x['preserved_for_claimed_interaction']],
            'nominal_background_losses':{k:v['cause']for k,v in trace['first_source_valid_losses'].items()if k!=str(scene['objects'][0]['id'])},
            'nominal_ego_loss':trace['first_source_valid_losses'].get(str(scene['objects'][0]['id'])),
            'counterfactual_passed':cf['passed'],'observed_steps':trace['observed_steps']}
    (root/'diagnostic_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='nominal_ego_loss'}),flush=True)


if __name__=='__main__':main()
