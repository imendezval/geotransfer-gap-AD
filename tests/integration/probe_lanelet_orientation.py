"""Independent native Lanelet2 oracle for boundary orientation and road geometry.

Optional audit dependency: lanelet2==1.2.3. The converter does not depend on it.
The wheel may be installed to a temporary --target directory and supplied via
PYTHONPATH. No vehicle trajectories or scene IDs participate in normalization.
"""
from geotransfer_gap.maps import lanelet
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import csv
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import lanelet2
from geotransfer_gap.conversion import pilot_ind as p
HERE = PROJECT_ROOT

def main():
    seen = set()
    reports = []
    for recording in range(33):
        recording = recording
        meta = next(csv.DictReader((settings().source / f'data/{recording:02d}_recordingMeta.csv').open()))
        path, _ = lanelet.map_paths(meta, recording)
        if path in seen:
            continue
        seen.add(path)
        native, errors = lanelet2.io.loadRobust(str(path), lanelet2.projection.UtmProjector(lanelet2.io.Origin(50.0, 6.0)))
        if errors:
            raise ValueError(errors)
        osm = ET.parse(path).getroot()
        nodes = lanelet.project_nodes(osm, float(meta['xUtmOrigin']), float(meta['yUtmOrigin']))
        ways = {int(w.get('id')): [int(n.get('ref')) for n in w.findall('nd')] for w in osm.findall('way')}
        roads, lanes = lanelet.make_roads(meta, recording)
        mismatches = []
        reversal_errors = []
        outside = []
        changed = []
        collapsed = []
        rules = lanelet2.traffic_rules.create(lanelet2.traffic_rules.Locations.Germany, lanelet2.traffic_rules.Participants.VehicleBus)
        graph = lanelet2.routing.RoutingGraph(native, rules)
        native_edges = {(lid, n.id) for lid in lanes for n in graph.following(native.laneletLayer[lid]) if n.id in lanes}
        encoded_edges = {(road['id'], n) for road in roads if road['type'] == 'lane' for n in road['exit_lanes']}
        for lid, lane in lanes.items():
            oracle = native.laneletLayer[lid]
            expected = ([n.id for n in oracle.leftBound], [n.id for n in oracle.rightBound])
            actual = (lane['left_nodes'], lane['right_nodes'])
            if actual != expected:
                mismatches.append(lid)
            raw = (ways[lane['refs']['left']], ways[lane['refs']['right']])
            if raw != actual:
                changed.append(lid)
            for lr in (False, True):
                for rr in (False, True):
                    trial = lanelet.orient_road_boundaries(raw[0][::-1] if lr else raw[0], raw[1][::-1] if rr else raw[1], nodes)
                    if trial != expected:
                        reversal_errors.append([lid, lr, rr])
            old = [tuple(((a + b) / 2 for a, b in zip(lanelet.interpolate_polyline([nodes[i] for i in raw[0]], t), lanelet.interpolate_polyline([nodes[i] for i in raw[1]], t)))) for t in (0.0, 1.0)]
            if math.dist(*old) < 0.5 * math.dist(lane['coords'][0], lane['coords'][-1]):
                collapsed.append(lid)
            anchor_id = expected[0][0]
            anchor = oracle.leftBound[0]
            offset = (anchor.x - nodes[anchor_id][0], anchor.y - nodes[anchor_id][1])
            for index, xy in enumerate(lane['coords'][1:-1], start=1):
                if not lanelet2.geometry.inside(oracle, lanelet2.core.BasicPoint2d(xy[0] + offset[0], xy[1] + offset[1])):
                    outside.append([lid, index])
        reports.append({'map': str(path), 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'road_lanelets': len(lanes), 'orientation_mismatches': mismatches, 'storage_reversal_errors': reversal_errors, 'changed_lanelets': changed, 'old_collapsed_centerlines': collapsed, 'centerline_samples_outside_native_polygon': outside, 'topology_participant': 'VehicleBus (road+bus geometry; car access must be reviewed separately)', 'native_successors': len(native_edges), 'extra_successors': sorted(encoded_edges - native_edges), 'missing_successors': sorted(native_edges - encoded_edges)})
    result = {'oracle': 'lanelet2==1.2.3 native OSM loader', 'converter_sha256': hashlib.sha256(Path(p.__file__).read_bytes()).hexdigest(), 'maps': reports, 'passed': all((not r['orientation_mismatches'] and (not r['storage_reversal_errors']) and (not r['centerline_samples_outside_native_polygon']) and (not r['extra_successors']) and (not r['missing_successors']) for r in reports))}
    project_path('pilot/audits/step2_native_lanelet_orientation.json').write_text(json.dumps(result, indent=2) + '\n')
    for r in reports:
        print(Path(r['map']).name, 'lanes', r['road_lanelets'], 'changed', len(r['changed_lanelets']), 'native mismatches', len(r['orientation_mismatches']), 'reversal errors', len(r['storage_reversal_errors']), 'outside', len(r['centerline_samples_outside_native_polygon']))
    if not result['passed']:
        raise SystemExit(1)
if __name__ == '__main__':
    main()
