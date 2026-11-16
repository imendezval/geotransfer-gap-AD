"""Regression fixtures for bounded-task stop scope; no admission is granted."""
import hashlib,json
from pathlib import Path
from audit_task_rule_scope import stop_scope

HERE=Path(__file__).resolve().parent

def main():
 cases=[]
 for name,expected,reason in [('r30_e292_f19024',True,'Entire task and goal-vehicle envelope remain upstream; this scene still has separate technical failures.'),('r30_e150_f10554',False,'Actual source does not reach the stop line, but its full goal region could encroach: retain exclusion.'),('r32_e425_f22924',False,'Source task actually reaches the stop line.'),('r14_e335_f21969',False,'Stop line reached in the construction map; source map selection must use the recording.')]:
  root=HERE/'pilot/oriented_v3'/name;report=stop_scope(root);actual=bool(report['rules']) and all(r['stop_obligation_outside_task'] for r in report['rules']);cases.append({'root':str(root),'expected':expected,'actual':actual,'passed':actual==expected,'reason':reason,'scope':report})
 result={'scope_tool_sha256':hashlib.sha256((HERE/'audit_task_rule_scope.py').read_bytes()).hexdigest(),'cases':cases,'passed':all(c['passed'] for c in cases)};(HERE/'pilot/audits/step2_stop_scope_regressions.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'passed':result['passed'],'cases':len(cases)}));assert result['passed']

if __name__=='__main__':main()
