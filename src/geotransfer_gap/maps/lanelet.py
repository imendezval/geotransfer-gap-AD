from geotransfer_gap.config import settings
import math
import subprocess
import xml.etree.ElementTree as ET
import numpy as np
SOURCE = settings().source
MAPS = {1: ('01_bendplatz/location1.osm', '01_bendplatz/bendplatz.xodr'), 2: ('02_frankenburg/location2.osm', '02_frankenburg/frankenburg.xodr'), 3: ('03_heckstrasse/location3.osm', '03_heckstrasse/heckstrasse.xodr'), 4: ('04_aseag/location4.osm', '04_aseag/aseag.xodr')}

def map_paths(recording_meta, recording):
    location = int(recording_meta['locationId'])
    if location == 1 and 11 <= recording <= 17:
        return (SOURCE / 'maps/lanelets/01_bendplatz_constuction/location1_construction.osm', SOURCE / 'maps/opendrive/01_bendplatz_constuction/bendplatz_construction.xodr')
    lanelet, opendrive = MAPS[location]
    return (SOURCE / 'maps/lanelets' / lanelet, SOURCE / 'maps/opendrive' / opendrive)

def background_pixel_scale(recording_meta):
    """Provider inD visualizer downsamples orthophotos by twelve."""
    return float(recording_meta['orthoPxToMeter']) * 12.0

def polyline_length(coords):
    return float(sum((math.dist(a, b) for a, b in zip(coords, coords[1:]))))

def lanelet_polygon(left, right):
    """Join boundaries even when the source ways have opposite directions."""
    same = math.dist(left[0], right[0]) + math.dist(left[-1], right[-1])
    opposite = math.dist(left[0], right[-1]) + math.dist(left[-1], right[0])
    aligned_right = list(reversed(right)) if opposite < same else list(right)
    return list(left) + list(reversed(aligned_right))

def orient_road_boundaries(left_ids, right_ids, nodes):
    """Orient OSM ways using Lanelet2 geometry::align's left/right rule.

    OSM way storage direction is independent of lane travel direction. Keep
    original node identities for directed connectivity; never infer direction
    from recorded vehicle motion. Native-loader parity is audited separately.
    """
    left, right = (list(left_ids), list(right_ids))
    if min(len(left), len(right)) < 2:
        raise ValueError('Road lanelet needs two nondegenerate boundaries')

    def middle(ids):
        if len(ids) > 2:
            return nodes[ids[len(ids) // 2]]
        a, b = (nodes[ids[0]], nodes[ids[-1]])
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    def signed_distance(ids, point):
        coords = [nodes[i] for i in ids]
        best = None
        for index, (a, b) in enumerate(zip(coords, coords[1:])):
            dx, dy = (b[0] - a[0], b[1] - a[1])
            size2 = dx * dx + dy * dy
            if size2 == 0:
                continue
            t = max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / size2))
            projected = (a[0] + t * dx, a[1] + t * dy)
            distance = math.dist(point, projected)
            if best is None or distance < best[0]:
                best = (distance, index, t)
        if best is None:
            raise ValueError('Road boundary has zero length')
        distance, index, t = best
        a, b = coords[index:index + 2]

        def is_left(u, v, q):
            return (v[0] - u[0]) * (q[1] - u[1]) - (v[1] - u[1]) * (q[0] - u[0]) > 0
        side = is_left(a, b, point)
        if t == 1.0 and index + 2 < len(coords):
            following = coords[index + 2]
            if side != is_left(b, following, point) and side == is_left(a, b, following):
                side = not side
        return distance if side else -distance
    if signed_distance(left, middle(right)) >= 0:
        left.reverse()
    if signed_distance(right, middle(left)) <= 0:
        right.reverse()
    return (left, right)

def interpolate_polyline(coords, fraction):
    target = fraction * polyline_length(coords)
    for a, b in zip(coords, coords[1:]):
        length = math.dist(a, b)
        if target <= length or b == coords[-1]:
            t = min(1.0, max(0.0, target / length)) if length else 0.0
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        target -= length
    return coords[-1]

def point_polyline_distance(point, coords):
    px, py = point
    best = float('inf')
    for (ax, ay), (bx, by) in zip(coords, coords[1:]):
        dx, dy = (bx - ax, by - ay)
        denom = dx * dx + dy * dy
        t = min(1.0, max(0.0, ((px - ax) * dx + (py - ay) * dy) / denom)) if denom else 0.0
        best = min(best, math.hypot(px - ax - t * dx, py - ay - t * dy))
    return best

def project_nodes(osm, origin_x, origin_y):
    nodes = osm.findall('node')
    payload = ''.join((f"{n.get('lon')} {n.get('lat')}\n" for n in nodes))
    proc = subprocess.run(['cs2cs', '-f', '%.7f', '+proj=longlat', '+datum=WGS84', '+to', '+proj=utm', '+zone=32', '+datum=WGS84'], input=payload, text=True, capture_output=True, check=True)
    projected = [line.split() for line in proc.stdout.splitlines()]
    assert len(projected) == len(nodes)
    return {int(n.get('id')): (float(p[0]) - origin_x, float(p[1]) - origin_y) for n, p in zip(nodes, projected)}

def make_roads(recording_meta, recording, edge_mode='all', emit_crosswalks=False):
    lanelet_path, _ = map_paths(recording_meta, recording)
    osm = ET.parse(lanelet_path).getroot()
    nodes = project_nodes(osm, float(recording_meta['xUtmOrigin']), float(recording_meta['yUtmOrigin']))
    ways = {}
    way_nodes = {}
    way_types = {}
    for way in osm.findall('way'):
        wid = int(way.get('id'))
        way_nodes[wid] = [int(nd.get('ref')) for nd in way.findall('nd')]
        ways[wid] = [nodes[nid] for nid in way_nodes[wid]]
        way_types[wid] = {t.get('k'): t.get('v') for t in way.findall('tag')}
    lanes = {}
    for rel in osm.findall('relation'):
        tags = {t.get('k'): t.get('v') for t in rel.findall('tag')}
        if tags.get('type') != 'lanelet' or tags.get('subtype') not in ('road', 'bus_lane'):
            continue
        refs = {m.get('role'): int(m.get('ref')) for m in rel.findall('member') if m.get('type') == 'way'}
        if 'left' not in refs or 'right' not in refs:
            continue
        left_ids, right_ids = orient_road_boundaries(way_nodes[refs['left']], way_nodes[refs['right']], nodes)
        left, right = ([nodes[i] for i in left_ids], [nodes[i] for i in right_ids])
        n = max(2, math.ceil(max(polyline_length(left), polyline_length(right)) / 2) + 1)
        coords = []
        for t in np.linspace(0, 1, n):
            a, b = (interpolate_polyline(left, float(t)), interpolate_polyline(right, float(t)))
            coords.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        lanes[int(rel.get('id'))] = {'coords': coords, 'refs': refs, 'left_nodes': left_ids, 'right_nodes': right_ids, 'width': math.dist(interpolate_polyline(left, 0.5), interpolate_polyline(right, 0.5))}
    roads = []
    for lid, lane in lanes.items():
        end = lane['coords'][-1]
        a = np.array(lane['coords'][-1]) - np.array(lane['coords'][-2])
        exits = []
        for next_id, other in lanes.items():
            if lid == next_id:
                continue
            start = other['coords'][0]
            b = np.array(other['coords'][1]) - np.array(start)
            left_shared = lane['left_nodes'][-1] == other['left_nodes'][0]
            right_shared = lane['right_nodes'][-1] == other['right_nodes'][0]
            shared = left_shared and right_shared
            near = math.dist(end, start) <= 1.0
            aligned = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)) > 0.5
            if aligned and shared and near:
                exits.append(next_id)
        roads.append({'id': lid, 'type': 'lane', 'map_element_id': 2, 'geometry': [{'x': x, 'y': y, 'z': 0.0} for x, y in lane['coords']], 'width': lane['width'], 'exit_lanes': sorted(exits)})
    edge_types = {'all': ('road_border', 'curbstone'), 'road_border_only': ('road_border',), 'none': ()}[edge_mode]
    for wid, coords in ways.items():
        if way_types[wid].get('type') in edge_types:
            roads.append({'id': wid, 'type': 'road_edge', 'map_element_id': 15, 'geometry': [{'x': x, 'y': y, 'z': 0.0} for x, y in coords]})
    if emit_crosswalks:
        for rel in osm.findall('relation'):
            rel_tags = {tag.get('k'): tag.get('v') for tag in rel.findall('tag')}
            if rel_tags.get('type') != 'lanelet' or rel_tags.get('subtype') != 'crosswalk':
                continue
            refs = {member.get('role'): int(member.get('ref')) for member in rel.findall('member') if member.get('type') == 'way'}
            if 'left' not in refs or 'right' not in refs:
                raise ValueError(f"Crosswalk {rel.get('id')} lacks left/right boundaries")
            polygon = lanelet_polygon(ways[refs['left']], ways[refs['right']])
            if len(polygon) < 4:
                raise ValueError(f"Crosswalk {rel.get('id')} has fewer than four vertices")
            roads.append({'id': int(rel.get('id')), 'type': 'crosswalk', 'map_element_id': 18, 'geometry': [{'x': x, 'y': y, 'z': 0.0} for x, y in polygon]})
    return (roads, lanes)
