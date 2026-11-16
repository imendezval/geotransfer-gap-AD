"""Check source lane access for each admitted ego; routing geometry is not permission.

Conservatively rejects explicit access/participant restrictions and non-road lanes.
This supplements manual rule review, rather than interpreting all German rules.
"""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

def audit(root):
    t = root / 'testing'
    contract = json.loads((t / 'evaluation_contract_expert.json').read_text())
    source = Path(contract['files']['source_lanelet2_map']['path'])
    map_path = t / 'map_audit.json'
    mapping = json.loads(map_path.read_text())
    relations = {int(r.attrib['id']): {x.attrib['k']: x.attrib['v'] for x in r.findall('tag')} for r in ET.parse(source).findall('relation')}
    occupied = sorted({i for s in mapping['ego_samples'] for i in s['occupied_lanelets']})
    issues = []
    if mapping['source_map_sha256'] != sha(source):
        issues.append({'reason': 'Map occupancy audit refers to an obsolete source map'})
    for lane in occupied:
        tags = relations[lane]
        if tags.get('subtype') != 'road':
            issues.append({'lanelet': lane, 'reason': 'Not an ordinary road lane', 'tags': tags})
        restricted = {k: v for k, v in tags.items() if k.startswith(('participant:', 'access:', 'vehicle:', 'motor_vehicle:')) or k in ('access', 'vehicle', 'motor_vehicle', 'bus', 'psv')}
        if restricted:
            issues.append({'lanelet': lane, 'reason': 'Explicit access tags require review', 'tags': restricted})
    if any((not s['occupied_lanelets'] for s in mapping['ego_samples'])):
        issues.append({'reason': 'An ego source sample has no occupied lane'})
    return {'root': str(root.resolve()), 'source_map_sha256': sha(source), 'map_audit_sha256': sha(map_path), 'occupied_lanelets': occupied, 'lanelet_tags': {str(i): relations[i] for i in occupied}, 'issues': issues, 'passed': bool(occupied) and (not issues)}

def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    rows = [audit(Path(r['root'])) for r in json.loads(args.manifest.read_text())]
    result = {'tool_sha256': sha(Path(__file__)), 'manifest_sha256': sha(args.manifest), 'scenes': rows, 'passed': all((r['passed'] for r in rows)), 'scope': 'Source ego lane access only; applicable rules still require per-scene review.'}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'scenes': len(rows), 'passed': result['passed']}))
    if not result['passed']:
        raise SystemExit(1)
if __name__ == '__main__':
    main()
