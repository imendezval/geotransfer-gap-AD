"""Convert and validate an inD recording window for BehaviorBench.

Run from anywhere with: python pilot_ind.py [--recording N --ego N --first-frame N]
The script uses the unmodified save_map_binary function from BehaviorBench's drive.py.
"""
from __future__ import annotations
from geotransfer_gap.maps.lanelet import background_pixel_scale, interpolate_polyline, lanelet_polygon, make_roads, map_paths, orient_road_boundaries, point_polyline_distance, polyline_length, project_nodes
from geotransfer_gap.conversion.binary import load_source_writer, read_binary
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import ast
import argparse
import csv
import hashlib
import json
import math
import subprocess
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
HERE = PROJECT_ROOT
ROOT = HERE.parent
SOURCE = settings().source
BENCH = settings().bench

def enforce_actor_capacity(count):
    if count > 128:
        raise ValueError(f'Scene has {count} actors; BehaviorBench supports at most 128')
from dataclasses import dataclass

@dataclass(frozen=True)
class ConversionConfig:
    recording: int
    ego: int
    first_frame: int
    goal_sample: int = 85
    edge_mode: str = 'all'
    late_mode: str = 'runtime_spawn'
    static_crop_radius: float = 1000000.0
    exclude_track_ids: tuple[int, ...] = ()
    parked_as_static_expert: bool = True
    background_goal_mode: str = 'continue'
    background_goal_min_distance: float = 5.0
    emit_crosswalks: bool = True

    def __post_init__(self):
        if not 10 <= self.goal_sample <= 85:
            raise ValueError('Goal sample must leave at least 0.5s for registration')
        if self.ego in self.exclude_track_ids:
            raise ValueError('Cannot exclude ego track')

class Converter:

    def __init__(self, config, output_root):
        self.config = config
        self.output = Path(output_root).resolve() / 'testing'
        self.frames = np.arange(91, dtype=float) * 2.5 + config.first_frame
        self.scene_name = f'ind_{config.recording:02d}_track_{config.ego}_frame_{config.first_frame}'

    def source_tracks(self):
        tracks = {}
        with (SOURCE / f'data/{self.config.recording:02d}_tracks.csv').open() as f:
            for row in csv.DictReader(f):
                frame = int(row['frame'])
                if self.config.first_frame <= frame <= math.ceil(self.frames[-1]):
                    tracks.setdefault(int(row['trackId']), []).append(row)
        with (SOURCE / f'data/{self.config.recording:02d}_tracksMeta.csv').open() as f:
            meta = {int(r['trackId']): r for r in csv.DictReader(f)}
        with (SOURCE / f'data/{self.config.recording:02d}_recordingMeta.csv').open() as f:
            recording_meta = next(csv.DictReader(f))
        return (tracks, meta, recording_meta)

    def make_object(self, track_id, rows, meta):
        src_frames = np.array([int(r['frame']) for r in rows])
        if len(src_frames) < 2:
            return None
        valid = (self.frames >= src_frames[0]) & (self.frames <= src_frames[-1])
        if valid.sum() < 2:
            return None

        def series(key):
            return np.interp(self.frames, src_frames, [float(r[key]) for r in rows])
        x, y, vx, vy = (series(k) for k in ('xCenter', 'yCenter', 'xVelocity', 'yVelocity'))
        angles = np.unwrap(np.deg2rad([float(r['heading']) for r in rows]))
        heading = np.interp(self.frames, src_frames, angles)
        cls = meta['class']
        kind = {'car': 'vehicle', 'truck_bus': 'vehicle', 'pedestrian': 'pedestrian', 'bicycle': 'cyclist'}.get(cls)
        if kind is None:
            return None
        source_length, source_width = (float(meta['length']), float(meta['width']))
        source_xy = [(float(r['xCenter']), float(r['yCenter'])) for r in rows]
        source_path_length = sum((math.dist(a, b) for a, b in zip(source_xy, source_xy[1:])))
        source_max_speed = max((math.hypot(float(r['xVelocity']), float(r['yVelocity'])) for r in rows))
        defaults = {'pedestrian': (0.6, 0.6), 'cyclist': (1.8, 0.6), 'vehicle': (4.5, 1.8)}
        length = source_length if source_length > 0 else defaults[kind][0]
        width = source_width if source_width > 0 else defaults[kind][1]
        positions = [{'x': float(a), 'y': float(b), 'z': 0.0} for a, b in zip(x, y)]
        velocities = [{'x': float(a), 'y': float(b), 'z': 0.0} for a, b in zip(vx, vy)]
        last = int(np.flatnonzero(valid)[-1])
        return {'id': track_id, 'type': kind, 'length': length, 'width': width, 'height': 1.6 if kind == 'vehicle' else 1.7, 'dimension_imputed': source_length <= 0 or source_width <= 0, 'source_window_path_length_m': source_path_length, 'source_window_max_speed_mps': source_max_speed, 'position': positions, 'velocity': velocities, 'heading': heading.tolist(), 'valid': valid.astype(int).tolist(), 'goalPosition': positions[last], 'mark_as_expert': 0}

    def continued_background_goal(self, obj):
        """Put a non-ego continuation goal beyond the recorded track end.

    The source validity mask still controls actor retirement. This goal only
    prevents GOAL_REMOVE from erasing a traffic actor before its source exit.
    """
        valid = [i for i, value in enumerate(obj['valid']) if value]
        last = valid[-1]
        first_recent = valid[max(0, len(valid) - 6)]
        end = obj['position'][last]
        recent = obj['position'][first_recent]
        dx, dy = (end['x'] - recent['x'], end['y'] - recent['y'])
        norm = math.hypot(dx, dy)
        if norm < 0.5:
            dx, dy = (math.cos(obj['heading'][last]), math.sin(obj['heading'][last]))
            norm = 1.0
        ux, uy = (dx / norm, dy / norm)
        for multiplier in (1.0, 1.6, 2.4, 4.0, 6.0):
            distance = multiplier * self.config.background_goal_min_distance
            goal = {'x': end['x'] + ux * distance, 'y': end['y'] + uy * distance, 'z': 0.0}
            if all((math.dist((obj['position'][i]['x'], obj['position'][i]['y']), (goal['x'], goal['y'])) > 4.0 for i in valid)):
                return goal
        raise ValueError(f"No continuation goal clear of track {obj['id']}")

    def validate(self, data, binary, lanes, recording_meta):
        assert binary['sdc_track_index'] == 0
        assert len(binary['objects']) == len(data['objects'])
        assert len(binary['roads']) == len(data['roads'])
        source_crosswalks = {road['id']: road for road in data['roads'] if road['type'] == 'crosswalk'}
        binary_crosswalks = {road['id']: road for road in binary['roads'] if road['type'] == 8}
        assert source_crosswalks.keys() == binary_crosswalks.keys()
        for crosswalk_id, source_crosswalk in source_crosswalks.items():
            encoded = binary_crosswalks[crosswalk_id]
            assert len(encoded['polyline_x']) == len(source_crosswalk['geometry'])
            for source_point, x, y in zip(source_crosswalk['geometry'], encoded['polyline_x'], encoded['polyline_y']):
                assert math.dist((source_point['x'], source_point['y']), (x, y)) < 0.01
        assert len(self.frames) == 91 and float(recording_meta['frameRate']) == 25.0
        _, opendrive_path = map_paths(recording_meta, self.config.recording)
        odr_header = ET.parse(opendrive_path).getroot().find('header')
        odr_offset = odr_header.find('offset')
        origin_delta = math.dist((float(odr_offset.get('x')), float(odr_offset.get('y'))), (float(recording_meta['xUtmOrigin']), float(recording_meta['yUtmOrigin'])))
        assert origin_delta < 0.1
        errors = []
        for src, obj in zip(data['objects'], binary['objects']):
            assert obj['id'] == src['id']
            for axis in ('x', 'y'):
                expected = np.array([p[axis] for p in src['position']])
                actual = obj[f'traj_{axis}']
                errors.append(float(np.max(abs(expected - actual))))
            assert np.array_equal(obj['traj_valid'], src['valid'])
            assert np.max(abs(np.array(src['heading']) - obj['traj_heading'])) < 1e-05
            assert np.max(abs(np.array([v['x'] for v in src['velocity']]) - obj['traj_vx'])) < 1e-05
        ego = data['objects'][0]
        ego_pts = [(p['x'], p['y']) for p in ego['position']]
        lane_lines = [lane['coords'] for lane in lanes.values()]
        lane_distances = [min((point_polyline_distance(pt, line) for line in lane_lines)) for pt in ego_pts]
        lane_by_id = {r['id']: r for r in binary['roads'] if r['type'] == 4}
        assert all((e in lane_by_id for r in lane_by_id.values() for e in r['exit_lanes']))
        goal_pt = (ego['goalPosition']['x'], ego['goalPosition']['y'])
        nearest_lanes = [min(lanes, key=lambda lid: point_polyline_distance(pt, lanes[lid]['coords'])) for pt in (ego_pts[0], goal_pt)]
        reachable = {nearest_lanes[0]}
        frontier = [nearest_lanes[0]]
        while frontier:
            for next_id in lane_by_id[frontier.pop()]['exit_lanes']:
                if next_id not in reachable:
                    reachable.add(next_id)
                    frontier.append(next_id)
        return {'recording': self.config.recording, 'location': int(recording_meta['locationId']), 'ego_track': self.config.ego, 'first_frame': self.config.first_frame, 'late_arriving_objects': sum((not obj['valid'][0] for obj in data['objects'])), 'edge_mode': self.config.edge_mode, 'source_hz': 25, 'scenario_hz': 10, 'duration_seconds': 9.0, 'opendrive_csv_origin_delta_m': origin_delta, 'objects': len(data['objects']), 'roads': len(data['roads']), 'emitted_crosswalk_ids': sorted(source_crosswalks), 'imputed_dimension_track_ids': [obj['id'] for obj in data['objects'] if obj['dimension_imputed']], 'lanes': len(lanes), 'lane_connections': sum((len(r['exit_lanes']) for r in lane_by_id.values())), 'max_binary_position_error_m': max(errors), 'ego_start': ego['position'][0], 'ego_goal': ego['goalPosition'], 'ego_start_goal_distance_m': math.dist(tuple((ego['position'][0][k] for k in ('x', 'y'))), tuple((ego['goalPosition'][k] for k in ('x', 'y')))), 'ego_lane_distance_median_m': float(np.median(lane_distances)), 'ego_lane_distance_max_m': max(lane_distances), 'ego_start_lane': nearest_lanes[0], 'ego_goal_lane': nearest_lanes[1], 'ego_goal_lane_reachable_by_successors': nearest_lanes[1] in reachable, 'binary_round_trip': 'passed'}

    def plot_scene(self, data, lanes):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 8))
        for lane in lanes.values():
            x, y = zip(*lane['coords'])
            ax.plot(x, y, color='#888888', linewidth=0.7)
        for obj in data['objects']:
            points = [p for p, valid in zip(obj['position'], obj['valid']) if valid]
            if not points:
                continue
            color = '#d62728' if obj['id'] == self.config.ego else '#1f77b4'
            ax.plot([p['x'] for p in points], [p['y'] for p in points], color=color, linewidth=2.5 if obj['id'] == self.config.ego else 0.9, alpha=0.9)
        ego = data['objects'][0]
        ax.scatter([ego['position'][0]['x'], ego['goalPosition']['x']], [ego['position'][0]['y'], ego['goalPosition']['y']], c=['green', 'red'])
        ax.set(xlabel='inD local x (m)', ylabel='inD local y (m)', title=f'inD recording {self.config.recording:02d}, ego track {self.config.ego}, frames {self.config.first_frame}–{int(self.frames[-1])}')
        ax.set_aspect('equal')
        ego_x = [p['x'] for p in ego['position']]
        ego_y = [p['y'] for p in ego['position']]
        ax.set_xlim(min(ego_x) - 50, max(ego_x) + 50)
        ax.set_ylim(min(ego_y) - 50, max(ego_y) + 50)
        fig.tight_layout()
        fig.savefig(self.output / 'overlay.png', dpi=150)
        plt.close(fig)

    def run(self):
        self.output.mkdir(parents=True, exist_ok=True)
        tracks, meta, recording_meta = self.source_tracks()
        candidate_objects = []
        for track_id in sorted(tracks, key=lambda x: (x != self.config.ego, x)):
            obj = self.make_object(track_id, tracks[track_id], meta[track_id])
            if obj is not None:
                candidate_objects.append(obj)
        ego_positions = candidate_objects[0]['position']
        objects = []
        excluded = []
        for obj in candidate_objects:
            valid_positions = [p for p, valid in zip(obj['position'], obj['valid']) if valid]
            path_length = sum((math.dist((a['x'], a['y']), (b['x'], b['y'])) for a, b in zip(valid_positions, valid_positions[1:])))
            max_speed = max((math.hypot(v['x'], v['y']) for v, valid in zip(obj['velocity'], obj['valid']) if valid))
            stationary = path_length < 0.5 and max_speed < 0.1 and (obj['source_window_path_length_m'] < 0.5) and (obj['source_window_max_speed_mps'] < 0.1)
            closest_to_ego = min((math.dist((p['x'], p['y']), (ep['x'], ep['y'])) for p, ep, valid in zip(obj['position'], ego_positions, obj['valid']) if valid))
            if self.config.parked_as_static_expert and obj['type'] == 'vehicle' and stationary:
                obj['mark_as_expert'] = 1
            if obj['id'] in self.config.exclude_track_ids or (obj['id'] != self.config.ego and stationary and (closest_to_ego > self.config.static_crop_radius)):
                excluded.append(obj['id'])
            else:
                objects.append(obj)
        assert objects and objects[0]['id'] == self.config.ego and all(objects[0]['valid'])
        if self.config.background_goal_mode == 'continue':
            for obj in objects[1:]:
                if obj['type'] == 'vehicle' and (not obj['mark_as_expert']):
                    obj['goalPosition'] = self.continued_background_goal(obj)
        enforce_actor_capacity(len(objects))
        source_late_ids = [obj['id'] for obj in objects if not obj['valid'][0]]
        if source_late_ids and self.config.late_mode == 'reject':
            raise ValueError(f'Late arrivals need simulator spawn support: {source_late_ids}')
        if source_late_ids and self.config.late_mode == 'bootstrap_probe':
            for obj in objects:
                if obj['id'] in source_late_ids:
                    obj['valid'][0] = 1
        assert self.config.late_mode == 'runtime_spawn' or all((obj['valid'][0] for obj in objects))
        objects[0]['goalPosition'] = objects[0]['position'][self.config.goal_sample]
        roads, lanes = make_roads(recording_meta, self.config.recording, self.config.edge_mode, self.config.emit_crosswalks)
        data = {'name': self.scene_name, 'scenario_id': self.scene_name, 'metadata': {'sdc_track_index': 0, 'tracks_to_predict': []}, 'objects': objects, 'roads': roads, 'tl_states': {}}
        json_path = self.output / f'{self.scene_name}.json'
        json_path.write_text(json.dumps(data, separators=(',', ':')))
        bin_path = self.output / 'map_000000.bin'
        load_source_writer()(data, str(bin_path), 0, trajectory_length=91)
        binary = read_binary(bin_path)
        report = self.validate(data, binary, lanes, recording_meta)
        report['binary_sha256'] = hashlib.sha256(bin_path.read_bytes()).hexdigest()
        report['excluded_distant_static_track_ids'] = excluded
        report['static_crop_radius_m'] = self.config.static_crop_radius
        report['explicit_excluded_track_ids'] = sorted(self.config.exclude_track_ids)
        report['parked_as_static_expert_track_ids'] = [obj['id'] for obj in objects if obj['mark_as_expert']]
        report['stationary_rule'] = {'sampled_path_length_max_m': 0.5, 'sampled_speed_max_mps': 0.1, 'source_rate_path_length_max_m': 0.5, 'source_rate_speed_max_mps': 0.1}
        report['background_goal_mode'] = self.config.background_goal_mode
        report['background_goal_min_distance_m'] = self.config.background_goal_min_distance
        report['source_late_arriving_track_ids'] = source_late_ids
        report['late_mode'] = self.config.late_mode
        report['ego_goal_sample'] = self.config.goal_sample
        (self.output / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
        with (self.output / 'manifest.csv').open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['new_filename', 'original_filename', 'ego_agent_idx', 'map_id'])
            w.writeheader()
            w.writerow({'new_filename': bin_path.name, 'original_filename': bin_path.name, 'ego_agent_idx': 0, 'map_id': 0})
        self.plot_scene(data, lanes)
        print(json.dumps(report, indent=2))

def main():
    parser = argparse.ArgumentParser(description='Convert an inD source window with explicit configuration.')
    parser.add_argument('--recording', type=int, required=True)
    parser.add_argument('--ego', type=int, required=True)
    parser.add_argument('--first-frame', type=int, required=True)
    parser.add_argument('--goal-sample', type=int, default=85)
    parser.add_argument('--edge-mode', choices=['all', 'road_border_only', 'none'], default='all')
    parser.add_argument('--late-mode', choices=['reject', 'bootstrap_probe', 'runtime_spawn'], default='runtime_spawn')
    parser.add_argument('--static-crop-radius', type=float, default=1000000.0)
    parser.add_argument('--exclude-track-ids', type=int, nargs='*', default=[])
    parser.add_argument('--parked-as-static-expert', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--background-goal-mode', choices=['source_end', 'continue'], default='continue')
    parser.add_argument('--background-goal-min-distance', type=float, default=5.0)
    parser.add_argument('--emit-crosswalks', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = vars(parser.parse_args())
    output = args.pop('output_root')
    args['exclude_track_ids'] = tuple(args['exclude_track_ids'])
    Converter(ConversionConfig(**args), output).run()
if __name__ == '__main__':
    main()
