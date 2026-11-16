"""Source certificate for rules associated through overlapping lane polygons.

Never waives a yield obligation on a direction-compatible ego approach. Requires
a connected, direction-compatible native route for every source sample and
explicit traversal of a protected lane of the very same relation. No model data.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pilot_ind as p


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root):
    t = root / 'testing'
    scene_path = next(t.glob('ind_*.json'))
    scene = json.loads(scene_path.read_text())
    ego = scene['objects'][0]
    validation = json.loads((t / 'validation.json').read_text())
    p.RECORDING = int(validation['recording'])
    meta_path = p.SOURCE / f"data/{int(validation['recording']):02d}_recordingMeta.csv"
    meta = next(csv.DictReader(meta_path.open()))
    roads, lanes = p.make_roads(meta)
    successors = {r['id']: set(r['exit_lanes']) for r in roads if r['type'] == 'lane'}
    mapping = json.loads((t / 'map_audit.json').read_text())
    rules = json.loads((t / 'rule_applicability_audit.json').read_text())
    if sha(p.map_paths(meta)[0]) != rules['lanelet_source_sha256']:
        raise ValueError('Directed route and rule audit use different source map variants')
    compatible = []
    for row in mapping['ego_samples']:
        step = row['step']
        xy = np.array([ego['position'][step]['x'], ego['position'][step]['y']])
        choices = []
        for lane in row['occupied_lanelets']:
            if lane not in lanes:
                continue
            coords = np.asarray(lanes[lane]['coords'])
            vectors = np.diff(coords, axis=0)
            lengths = (vectors * vectors).sum(axis=1)
            fractions = np.clip(((xy - coords[:-1]) * vectors).sum(axis=1) /
                                np.maximum(lengths, 1e-12), 0, 1)
            distances = np.linalg.norm(coords[:-1] + fractions[:, None] * vectors - xy, axis=1)
            nearest = int(distances.argmin())
            heading = math.atan2(vectors[nearest, 1], vectors[nearest, 0])
            error = abs((heading - ego['heading'][step] + math.pi) % (2 * math.pi) - math.pi)
            if error <= .35:
                choices.append(lane)
        compatible.append(set(choices))
    paths = {lane: [lane] for lane in compatible[0]} if compatible else {}
    for choices in compatible[1:]:
        updated = {}
        for lane in sorted(choices):
            for prior, route in sorted(paths.items()):
                if lane == prior or lane in successors.get(prior, set()):
                    updated[lane] = route if lane == prior else route + [lane]
                    break
        paths = updated
    route = next(iter(paths.values()), [])
    results = []
    for rule in rules['governing_regulatory_elements']:
        yield_ids = {m['id'] for m in rule['ego_members'] if m['role'] == 'yield'}
        protected = set(rule['priority_lanelets'])
        yield_steps = [i for i, choices in enumerate(compatible) if choices & yield_ids]
        protected_steps = [i for i, choices in enumerate(compatible) if choices & protected]
        certified = bool(route and yield_ids and protected_steps and not yield_steps
                         and not (set(route) & yield_ids) and set(route) & protected)
        results.append({'rule_id': rule['id'], 'yield_lanelets': sorted(yield_ids),
                        'direction_compatible_yield_steps': yield_steps,
                        'direction_compatible_protected_steps': protected_steps,
                        'overlap_only_non_ego_yield_approach': certified})
    return {'schema_version': 1, 'audit_sha256': sha(Path(__file__)),
            'source_map_sha256': rules['lanelet_source_sha256'],
            'scene_sha256': sha(scene_path), 'map_audit_sha256': sha(t / 'map_audit.json'),
            'rule_audit_sha256': sha(t / 'rule_applicability_audit.json'),
            'source_recording_meta_sha256': sha(meta_path),
            'direction_tolerance_rad': .35, 'complete_native_directed_route': route,
            'all_source_samples_covered': bool(route), 'rules': results,
            'scope': 'False association through overlapping polygons only; any direction-compatible yielding sample prevents certification. Manual review required.'}


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--root', type=Path, required=True)
    args = ap.parse_args()
    result = audit(args.root.resolve())
    (args.root / 'testing/source_directed_rule_scope.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'route': result['complete_native_directed_route'],
                      'certified_rules': [r['rule_id'] for r in result['rules']
                                          if r['overlap_only_non_ego_yield_approach']]}))


if __name__ == '__main__':
    main()
