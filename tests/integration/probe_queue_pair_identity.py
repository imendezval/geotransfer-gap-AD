"""Real two-worker same-scene/dual-actor and producer-version resume regression."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
HERE = PROJECT_ROOT

def main():
    rows = json.loads(project_path('pilot/audits/third_family_source_selection_v1.json').read_text())['jobs']
    jobs = [r for r in rows if r['recording'] == 8 and r['ego'] == 119 and (r['first_frame'] == 7919) and (r['actor'] in (118, 120))]
    assert len(jobs) == 2
    evidence = project_path('pilot/probes/queue_pair_identity')
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='geo_queue_identity_', dir='/tmp') as folder:
        selection = Path(folder) / 'selection.json'
        ledger = Path(folder) / 'ledger.json'
        for version in (1, 2):
            selection.write_text(json.dumps({'selection': 'Pair-identity regression, not a corpus cohort.', 'regression_selection_version': version, 'jobs': jobs}, indent=2) + '\n')
            cmd = [sys.executable, str(project_path('run_oriented_candidate_queue.py')), '--selection', str(selection), '--ledger', str(ledger), '--limit', '2', '--workers', '2']
            for attempt in (0, 1):
                p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
                if p.returncode:
                    raise RuntimeError(p.stderr[-1500:])
                (evidence / f'version{version}_run{attempt}.log').write_text(p.stdout + p.stderr)
                result = json.loads(ledger.read_text())['results']
                assert len(result) == version * 2 and all((r['status'] == 'unresolved_semantics_screen' for r in result))
                assert all((sum((r['actor'] == actor for r in result)) == version for actor in (118, 120)))
                if attempt == 0:
                    before = sha(ledger)
                else:
                    assert sha(ledger) == before
        copied = evidence / 'retained_pair_versions.json'
        copied.write_bytes(ledger.read_bytes())
    report = {'passed': True, 'queue_sha256': sha(project_path('run_oriented_candidate_queue.py')), 'probe_sha256': sha(Path(__file__)), 'actors': [118, 120], 'same_scene': True, 'workers': 2, 'retained_results': 4, 'selection_versions': 2, 'resume_changed_ledger': False, 'ledger': str(copied), 'ledger_sha256': sha(copied)}
    project_path('pilot/audits/queue_pair_identity_regression.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'retained_pair_versions': 4, 'resume_stable': True, 'passed': True}))
if __name__ == '__main__':
    main()
