"""Run the mandatory Step 1 admission gate on prefilter-passing Step 2 scenes."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import json
import subprocess
from pathlib import Path
HERE = PROJECT_ROOT
PYTHON = '/home/inigo/miniconda3/envs/bb_pufferdrive/bin/python'

def main(screen, output):
    rows = json.loads(screen.read_text())['results']
    results = json.loads(output.read_text()) if output.is_file() else []
    done = {x['name'] for x in results}
    for row in rows:
        if row['exclusion_reasons'] or row['name'] in done:
            continue
        root = Path(row.get('root') or project_path('pilot/corpus/candidates') / row['name'])
        proc = subprocess.run([PYTHON, str(project_path('admit_scene.py')), '--root', str(root)], capture_output=True, text=True)
        path = root / 'testing/admission.json'
        report = json.loads(path.read_text()) if path.is_file() else None
        item = {'name': row['name'], 'root': str(root), 'technical_admitted': bool(report and report['technical_admitted']), 'research_admitted': bool(report and report['research_admitted']), 'exclusion_reasons': report['exclusion_reasons'] if report else ['gate_crash'], 'error': (proc.stderr or '')[-500:]}
        results.append(item)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2) + '\n')
        print(item, flush=True)
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--screen', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    main(args.screen, args.output)
