"""Non-admitting full-trace experiment for source-speed-guided hybrid traffic.

Copies minimal inputs to a separate diagnostic root. Nominal admission traces
are never overwritten. Each invocation isolates its Python/C runtime state.
"""
import argparse,hashlib,json,os,runpy,shutil,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent

def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output-root',type=Path,required=True);ap.add_argument('--lateral-offset-m',type=float,default=0);ap.add_argument('--counterfactual',action='store_true',help='Also run the complete expert/interactive ego-perturbation lifecycle probe; diagnostic only.');args=ap.parse_args();original=args.root.resolve();root=args.output_root.resolve()
 if root==original:raise ValueError('Diagnostic root must differ from source root')
 t=root/'testing';t.mkdir(parents=True,exist_ok=True)
 for pattern in ('ind_*.json','map_000000.bin','validation.json','manifest.csv','rule_applicability_audit.json'):
  for f in (original/'testing').glob(pattern):shutil.copy2(f,t/f.name)
 import source_guided_traffic,hybrid_traffic
 hybrid_traffic.apply=source_guided_traffic.apply
 sys.argv=['trace_eval_lifecycle.py','--root',str(root),'--traffic-mode','hybrid_startup']
 if args.lateral_offset_m:sys.argv+=['--lateral-offset-m',str(args.lateral_offset_m)]
 runpy.run_path(str(HERE/'trace_eval_lifecycle.py'),run_name='__main__')
 suffix=f'_shift{args.lateral_offset_m:g}_at0' if args.lateral_offset_m else ''
 tracepath=t/f'lifecycle_trace_hybrid_startup{suffix}.json'
 if not tracepath.exists():raise ValueError('Trace suffix mismatch: '+str(list(t.glob('lifecycle_trace*'))))
 report=json.loads(tracepath.read_text());report.update(traffic_mode='hybrid_source_speed_diagnostic',diagnostic_only=True,traffic_module_sha256=hashlib.sha256((HERE/'source_guided_traffic.py').read_bytes()).hexdigest())
 if not args.lateral_offset_m:
  from audit_interaction_fidelity import audit
  audit(root,'hybrid_startup')
  interaction=json.loads((t/'interaction_fidelity_audit_hybrid_startup.json').read_text());interaction.update(traffic_mode='hybrid_source_speed_diagnostic',diagnostic_only=True);(t/'interaction_fidelity_source_speed_diagnostic.json').write_text(json.dumps(interaction,indent=2)+'\n');(t/'interaction_fidelity_audit_hybrid_startup.json').unlink()
  original_inter=original/'testing/interaction_fidelity_audit_hybrid_startup.json';before=json.loads(original_inter.read_text()) if original_inter.exists() else {};comparison={'original_root':str(original),'diagnostic_root':str(root),'diagnostic_only':True,'guidance_sha256':report['traffic_module_sha256'],'before_preserved':[a['track_id'] for a in before.get('actor_opportunities',[]) if a['preserved_for_claimed_interaction']],'after_preserved':[a['track_id'] for a in interaction['actor_opportunities'] if a['preserved_for_claimed_interaction']],'source_valid_losses':report['first_source_valid_losses']};(root/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n');print(json.dumps(comparison),flush=True)
 (t/f'lifecycle_trace_source_speed_diagnostic{suffix}.json').write_text(json.dumps(report,indent=2)+'\n');tracepath.unlink()
 if args.counterfactual:
  name='counterfactual_source_speed_diagnostic.json'
  sys.argv=['probe_counterfactual.py','--root',str(root),'--require-hybrid','--report-name',name]
  runpy.run_path(str(HERE/'probe_counterfactual.py'),run_name='__main__')
  path=t/name;cf=json.loads(path.read_text());mode='hybrid_source_speed_diagnostic'
  cf['modes'][mode]=cf['modes'].pop('hybrid_startup')
  cf['required_evaluator_modes']=['expert',mode]
  cf.update(diagnostic_only=True,traffic_protocol=mode,
   traffic_module_sha256=report['traffic_module_sha256'],
   diagnostic_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
   counterfactual_probe_sha256=hashlib.sha256((HERE/'probe_counterfactual.py').read_bytes()).hexdigest())
  path.write_text(json.dumps(cf,indent=2)+'\n')
  print(json.dumps({'counterfactual_diagnostic_only':True,'passed':cf['passed'],
   'lifecycle_by_mode':{k:v['lifecycle_passed'] for k,v in cf['modes'].items()}}),flush=True)

if __name__=='__main__':main()
