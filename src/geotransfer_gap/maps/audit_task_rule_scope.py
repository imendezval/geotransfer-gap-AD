"""Conservative stop-line scope proof for a bounded straight approach task.

A stop sign is not waived because it is distant. This proves that the entire
2m goal region plus vehicle circumradius and the source task footprint remain
upstream of every referenced stop line. Ambiguous/curved cases stay unresolved.
"""
from geotransfer_gap.maps import lanelet
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import csv
import json
import math
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
from geotransfer_gap.validation.audit_physical_source import corners

def stop_scope(root):
    t = root / 'testing'
    scene_path = next(t.glob('ind_*.json'))
    scene = json.loads(scene_path.read_text())
    ego = scene['objects'][0]
    audit = json.loads((t / 'rule_applicability_audit.json').read_text())
    v = json.loads((t / 'validation.json').read_text())
    recording = v['recording']
    meta = next(csv.DictReader((settings().source / f"data/{v['recording']:02d}_recordingMeta.csv").open()))
    path, _ = lanelet.map_paths(meta, recording)
    osm = ET.parse(path).getroot()
    nodes = lanelet.project_nodes(osm, float(meta['xUtmOrigin']), float(meta['yUtmOrigin']))
    ways = {int(w.get('id')): [nodes[int(n.get('ref'))] for n in w.findall('nd')] for w in osm.findall('way')}
    relations = {int(r.get('id')): r for r in osm.findall('relation')}
    goal = ego['goalPosition']
    end = next((i for i, pt in enumerate(ego['position']) if ego['valid'][i] and math.hypot(pt['x'] - goal['x'], pt['y'] - goal['y']) <= 2), 90)
    heading = ego['heading'][end]
    direction = (math.cos(heading), math.sin(heading))
    radius = math.hypot(ego['length'], ego['width']) / 2
    results = []
    for rule in audit['governing_regulatory_elements']:
        if not (any((m['role'] == 'yield' for m in rule['ego_members'])) and any((s.get('subtype') == 'de206' for s in rule.get('signs', [])))):
            continue
        lines = [int(m.get('ref')) for m in relations[rule['id']].findall('member') if m.get('type') == 'way' and m.get('role') == 'ref_line']
        proof = []
        for lid in lines:
            coords = ways[lid]
            dx, dy = (coords[-1][0] - coords[0][0], coords[-1][1] - coords[0][1])
            norm = math.hypot(dx, dy)
            if norm < 1e-06:
                continue
            normal = (-dy / norm, dx / norm)
            if normal[0] * direction[0] + normal[1] * direction[1] < 0:
                normal = (-normal[0], -normal[1])
            alignment = normal[0] * direction[0] + normal[1] * direction[1]
            off_plane = max((abs((xy[0] - coords[0][0]) * normal[0] + (xy[1] - coords[0][1]) * normal[1]) for xy in coords))
            signed = lambda xy: (xy[0] - coords[0][0]) * normal[0] + (xy[1] - coords[0][1]) * normal[1]
            task_max = max((signed(xy) for i in range(end + 1) if ego['valid'][i] for xy in corners(ego, i)))
            goal_max = signed((goal['x'], goal['y'])) + 2 + radius
            h_error = max((abs((h - heading + math.pi) % (2 * math.pi) - math.pi) for h in ego['heading'][:end + 1]))
            progress = signed((goal['x'], goal['y'])) - signed((ego['position'][0]['x'], ego['position'][0]['y']))
            ok = alignment > 1e-06 and progress > 0.01 and (off_plane < 0.01) and (task_max < -0.01) and (goal_max < -0.01) and (h_error < 0.35)
            proof.append({'reference_line_id': lid, 'normal_direction_alignment': alignment, 'source_progress_toward_stop_plane_m': progress, 'maximum_reference_line_off_plane_m': off_plane, 'maximum_source_task_footprint_signed_distance_m': task_max, 'maximum_goal_region_vehicle_signed_distance_m': goal_max, 'maximum_task_heading_change_rad': h_error, 'entire_task_and_goal_upstream': ok})
        results.append({'rule_id': rule['id'], 'source_task_end_step': end, 'reference_lines': proof, 'stop_obligation_outside_task': bool(lines) and len(proof) == len(lines) and all((x['entire_task_and_goal_upstream'] for x in proof))})
    return {'schema_version': 1, 'scene_sha256': hashlib.sha256(scene_path.read_bytes()).hexdigest(), 'source_map_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'scope_tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'rules': results}
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--root', type=Path, required=True)
    args = ap.parse_args()
    result = stop_scope(args.root.resolve())
    path = args.root / 'testing/source_task_rule_scope.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
