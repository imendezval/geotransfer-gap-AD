"""Conservative same-direction dashed-boundary lane-change permissions.

These are source route permissions, never IDM following successors. Bus-access
and mixed/solid markings are excluded; optional native oracle checks the subset.
"""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import xml.etree.ElementTree as ET

def edges(lanes, osm_path):
    osm = ET.parse(osm_path).getroot()
    way_tags = {int(w.get('id')): {t.get('k'): t.get('v') for t in w.findall('tag')} for w in osm.findall('way')}
    lane_tags = {int(r.get('id')): {t.get('k'): t.get('v') for t in r.findall('tag')} for r in osm.findall('relation')}
    result = []
    for source, lane in lanes.items():
        st = lane_tags[source]
        if st.get('subtype') != 'road' or any((k.startswith('participant:') or k in ('access', 'vehicle', 'motor_vehicle') for k in st)):
            continue
        for target, other in lanes.items():
            if source == target:
                continue
            tt = lane_tags[target]
            if tt.get('subtype') != 'road' or any((k.startswith('participant:') or k in ('access', 'vehicle', 'motor_vehicle') for k in tt)):
                continue
            for side, opposite in [('left', 'right'), ('right', 'left')]:
                shared = lane['refs'][side]
                if shared != other['refs'][opposite]:
                    continue
                if lane[side + '_nodes'] != other[opposite + '_nodes']:
                    continue
                tags = way_tags[shared]
                if tags.get('type') == 'line_thin' and tags.get('subtype') == 'dashed':
                    result.append({'source': source, 'target': target, 'side': side, 'shared_boundary_way': shared, 'tags': tags})
    counts = {}
    for row in result:
        key = (row['source'], row['side'])
        counts[key] = counts.get(key, 0) + 1
    return [row for row in result if counts[row['source'], row['side']] == 1]
