"""Register Lanelet road-edge geometry to the inD aerial image for review.

Use the inD provider visualizer projection: x/(12*orthoPxToMeter),
-y/(12*orthoPxToMeter), with no fitted translation.
"""
from geotransfer_gap.maps import lanelet
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import hashlib
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from geotransfer_gap.validation.audit_physical_source import corners

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--focus-track', type=int)
    ap.add_argument('--focus-step', type=int, default=0)
    args = ap.parse_args()
    root = args.root.resolve()
    testing = root / 'testing'
    validation = json.loads((testing / 'validation.json').read_text())
    recording = int(validation['recording'])
    scene = json.loads(next(testing.glob('ind_*.json')).read_text())
    source = settings().source / 'data'
    meta_path = source / f'{recording:02d}_recordingMeta.csv'
    image_path = source / f'{recording:02d}_background.png'
    meta = next(csv.DictReader(meta_path.open()))
    scale = lanelet.background_pixel_scale(meta)
    rgb = np.asarray(Image.open(image_path).convert('RGB'))
    ego = scene['objects'][0]
    ox = oy = 0.0
    best = None
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.imshow(rgb)
    for road in scene['roads']:
        if road['type'] != 'road_edge':
            continue
        ax.plot([(v['x'] - ox) / scale for v in road['geometry']], [(oy - v['y']) / scale for v in road['geometry']], color='cyan', linewidth=0.6, alpha=0.75)
    for obj in scene['objects']:
        if obj['id'] != ego['id'] and obj['type'] != 'vehicle':
            continue
        valid = [i for i, v in enumerate(obj['valid']) if v]
        if not valid:
            continue
        i = valid[0]
        pos = obj['position'][i]
        ax.plot((pos['x'] - ox) / scale, (oy - pos['y']) / scale, 'ro' if obj['id'] == ego['id'] else 'y.', markersize=3)
    ax.plot([(v['x'] - ox) / scale for v, valid in zip(ego['position'], ego['valid']) if valid], [(oy - v['y']) / scale for v, valid in zip(ego['position'], ego['valid']) if valid], color='red', linewidth=2.0, alpha=0.85)
    if args.focus_track is not None:
        focus = next((obj for obj in scene['objects'] if obj['id'] == args.focus_track))
        if not focus['valid'][args.focus_step]:
            raise ValueError('Focus actor is not source-valid at this step')
        poly = corners(focus, args.focus_step)
        poly.append(poly[0])
        ax.plot([(x - ox) / scale for x, _ in poly], [(oy - y) / scale for _, y in poly], color='red', linewidth=2)
        ax.text((focus['position'][args.focus_step]['x'] - ox) / scale, (oy - focus['position'][args.focus_step]['y']) / scale, f'{args.focus_track}@{args.focus_step}', color='white', fontsize=9)
    physical_path = testing / 'physical_source_audit.json'
    if physical_path.exists():
        physical = json.loads(physical_path.read_text())
        by_id = {obj['id']: obj for obj in scene['objects']}
        for pair, item in list(physical.get('source_box_actor_overlaps', {}).items())[:8]:
            step = item['first_steps'][0]
            for track_id in map(int, pair.split('-')):
                obj = by_id[track_id]
                poly = corners(obj, step)
                poly.append(poly[0])
                ax.plot([(x - ox) / scale for x, _ in poly], [(oy - y) / scale for _, y in poly], color='orange', linewidth=1.2)
                center = obj['position'][step]
                ax.text((center['x'] - ox) / scale, (oy - center['y']) / scale, str(track_id), color='white', fontsize=6)
    ax.set_xlim(0, rgb.shape[1])
    ax.set_ylim(rgb.shape[0], 0)
    fig.tight_layout()
    suffix = f'_track_{args.focus_track}_step_{args.focus_step}' if args.focus_track is not None else ''
    figure = testing / f'source_image_registration{suffix}.png'
    fig.savefig(figure, dpi=130)
    plt.close(fig)
    report = {'recording': recording, 'background_sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(), 'binary_sha256': hashlib.sha256((testing / 'map_000000.bin').read_bytes()).hexdigest(), 'pixel_scale_m': scale, 'local_x_at_image_x0_m': float(ox), 'local_y_at_image_y0_m': float(oy), 'edge_fit_score': best, 'coordinate_rule': 'pixel_x=(local_x-ox)/scale; pixel_y=(oy-local_y)/scale', 'registration_is_estimate': False, 'schema_version': 2, 'coordinate_source': 'ika-rwth-aachen/drone-dataset-tools: tracks_import.py and visualizer_params.json (inD scale_down_factor=12)', 'overlay': str(figure)}
    (testing / f'source_image_registration{suffix}.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
if __name__ == '__main__':
    main()
