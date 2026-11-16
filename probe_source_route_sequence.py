"""Source sequence positives and genuine route/prohibition negatives."""
import hashlib
import json
from pathlib import Path
from audit_source_route_sequence import audit

HERE=Path(__file__).resolve().parent
cases=[]
for name,lateral,expected in [('r01_e280_f18833',True,True),('r01_e280_f18833',False,False),
                              ('r17_e127_f8136',True,False),('r07_e200_f25439',False,True)]:
    result=audit(HERE/'pilot/oriented_v3'/name,allow_lane_changes=lateral)
    passed=result['source_path_legal']==expected
    cases.append({'scene':name,'lane_changes_enabled':lateral,'expected_legal':expected,
                  'first_failure':result['first_failure'],'passed':passed})
    assert passed,cases[-1]
result={'route_sequence_sha256':hashlib.sha256((HERE/'audit_source_route_sequence.py').read_bytes()).hexdigest(),
        'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':cases,'passed':True}
(HERE/'pilot/audits/source_route_sequence_regressions.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
