"""Check false polygon association versus real directed yielding approaches."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import hashlib
import json
from pathlib import Path
from geotransfer_gap.maps.audit_directed_rule_scope import audit
HERE = PROJECT_ROOT
cases = []
for name, rule_ids, expected in [('r07_e200_f25439', {2169, 2177}, True), ('r09_e136_f11030', {2169, 2177}, True), ('r08_e20_f1308', {2169}, False), ('r14_e58_f4648', {2191, 2195}, False), ('r20_e416_f26946', {1202, 1208}, False)]:
    proof = audit(project_path('pilot/oriented_v3') / name)
    indexed = {r['rule_id']: r for r in proof['rules']}
    passed = all((indexed[i]['overlap_only_non_ego_yield_approach'] == expected for i in rule_ids))
    cases.append({'scene': name, 'rules': sorted(rule_ids), 'expected': expected, 'passed': passed})
    assert passed, cases[-1]
result = {'directed_scope_sha256': hashlib.sha256(project_path('audit_directed_rule_scope.py').read_bytes()).hexdigest(), 'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'cases': cases, 'passed': all((c['passed'] for c in cases))}
project_path('pilot/audits/directed_rule_scope_regressions.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
