"""Diagnostic logged background-route intent, optionally with speed intent.

Separate output/runtime; cannot admit. Controlled ego route is unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import sys

HERE=Path(__file__).resolve().parent


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--output-root',type=Path,required=True)
    ap.add_argument('--speed-intent',action='store_true')
    ap.add_argument('--selective',action='store_true')
    ap.add_argument('--branch-only',action='store_true')
    ap.add_argument('--initial-only',action='store_true')
    ap.add_argument('--progress-covered',action='store_true')
    args=ap.parse_args()
    root=args.output_root.resolve();source=args.root.resolve()
    if root==source:raise ValueError('Separate diagnostic output required')
    t=root/'testing';t.mkdir(parents=True,exist_ok=True)
    for pattern in ('ind_*.json','map_000000.bin','validation.json','manifest.csv','rule_applicability_audit.json'):
        for path in (source/'testing').glob(pattern):shutil.copy2(path,t/path.name)
    import source_reference_runtime
    import selective_reference_runtime
    import source_branch_runtime
    import coverage_reference_runtime
    import late_spawn_runtime
    runtime=coverage_reference_runtime.load() if args.progress_covered else source_branch_runtime.load(initial_only=True) if args.initial_only else (source_branch_runtime if args.branch_only else selective_reference_runtime if args.selective else source_reference_runtime).load()
    late_spawn_runtime.load=lambda:runtime
    if args.speed_intent:
        import source_guided_traffic,hybrid_traffic
        hybrid_traffic.apply=source_guided_traffic.apply
    for script,extra in [('trace_eval_lifecycle.py',['--traffic-mode','hybrid_startup']),
                         ('audit_interaction_fidelity.py',['--traffic-mode','hybrid_startup']),
                         ('probe_counterfactual.py',['--require-hybrid','--report-name','counterfactual_route_diagnostic.json'])]:
        sys.argv=[script,'--root',str(root),*extra]
        runpy.run_path(str(HERE/script),run_name='__main__')
    trace=json.loads((t/'lifecycle_trace_hybrid_startup.json').read_text())
    inter=json.loads((t/'interaction_fidelity_audit_hybrid_startup.json').read_text())
    cf=json.loads((t/'counterfactual_route_diagnostic.json').read_text())
    scene=json.loads(next(t.glob('ind_*.json')).read_text());ego=scene['objects'][0]['id']
    result={'diagnostic_only':True,'source_root':str(source),'speed_intent':args.speed_intent,'selective':args.selective,'branch_only':args.branch_only,'initial_only':args.initial_only,'progress_covered':args.progress_covered,
            'runtime':runtime,'preserved_actor_ids':[a['track_id']for a in inter['actor_opportunities']if a['preserved_for_claimed_interaction']],
            'background_losses':{k:v['cause']for k,v in trace['first_source_valid_losses'].items()if k!=str(ego)},
            'ego_loss':trace['first_source_valid_losses'].get(str(ego),{}).get('cause'),
            'observed_steps':trace['observed_steps'],
            'counterfactual_passed':cf['passed'],
            'producer_sha256':{n:hashlib.sha256((HERE/n).read_bytes()).hexdigest()for n in
                ('source_reference_runtime.py','selective_reference_runtime.py','source_branch_runtime.py','coverage_reference_runtime.py','source_guided_traffic.py','hybrid_traffic.py',Path(__file__).name)}}
    (root/'diagnostic_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
