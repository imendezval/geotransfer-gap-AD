"""Render pair-specific stationary overlap evidence using same-site recordings.

The target aerial is used where it covers both cars. A reference recording may
fill a source-image crop only when both stationary tracks match in local map
coordinates and dimensions. This never changes the converted scene.
"""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import argparse
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from PIL import Image
from geotransfer_gap.validation.audit_physical_source import corners

def scene(root):
    testing = root / 'testing'
    return json.loads(next(testing.glob('ind_*.json')).read_text())

def registration(root):
    return json.loads((root / 'testing/source_image_registration.json').read_text())

def point(obj):
    p = obj['position'][0]
    return (p['x'], p['y'])

def distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

def stationary(obj):
    return obj['type'] == 'vehicle' and obj['mark_as_expert'] and (obj['source_window_path_length_m'] < 0.5)

def render(target_root, reference_root):
    target = scene(target_root)
    reference = scene(reference_root)
    target_registration = registration(target_root)
    reference_registration = registration(reference_root)
    target_recording = target_registration['recording']
    reference_recording = reference_registration['recording']
    source = settings().source / 'data'
    meta = [next(csv.DictReader((source / f'{r:02d}_recordingMeta.csv').open())) for r in (target_recording, reference_recording)]
    if any((meta[0][k] != meta[1][k] for k in ('locationId', 'xUtmOrigin', 'yUtmOrigin'))):
        raise ValueError('Reference recording must use the same location and UTM origin')
    audit = json.loads((target_root / 'testing/physical_source_audit.json').read_text())
    target_objects = {obj['id']: obj for obj in target['objects']}
    reference_objects = [obj for obj in reference['objects'] if stationary(obj)]
    pairs = []
    for pair_id, detail in audit['source_box_actor_overlap_details'].items():
        if not detail['reviewable_annotation_overlap']:
            raise ValueError(f'Unreviewable overlap {pair_id}')
        ids = detail['track_ids']
        matches = []
        for track_id in ids:
            actor = target_objects[track_id]
            candidates = sorted(reference_objects, key=lambda other: distance(point(actor), point(other)))
            if candidates:
                other = candidates[0]
                center_error = distance(point(actor), point(other))
                dimension_error = max((abs(actor[k] - other[k]) for k in ('length', 'width')))
                if center_error <= 0.4 and dimension_error <= 0.5:
                    matches.append({'target_track_id': track_id, 'reference_track_id': other['id'], 'center_error_m': center_error, 'maximum_dimension_error_m': dimension_error})
        use_reference = len(matches) == 2 and len({x['reference_track_id'] for x in matches}) == 2
        pairs.append({'pair_id': pair_id, 'target_track_ids': ids, 'aerial_recording': reference_recording if use_reference else target_recording, 'cross_record_matches': matches if use_reference else []})
    fig, axes = plt.subplots(len(pairs), 1, figsize=(8, 4.2 * len(pairs)), squeeze=False)
    for ax, pair in zip(axes.flat, pairs):
        recording = pair['aerial_recording']
        reg = reference_registration if recording == reference_recording else target_registration
        image_path = source / f'{recording:02d}_background.png'
        rgb = Image.open(image_path).convert('RGB')

        def pixel(xy):
            return ((xy[0] - reg['local_x_at_image_x0_m']) / reg['pixel_scale_m'], (reg['local_y_at_image_y0_m'] - xy[1]) / reg['pixel_scale_m'])
        actors = [target_objects[i] for i in pair['target_track_ids']]
        center_pixels = [pixel(point(actor)) for actor in actors]
        cx = sum((x for x, _ in center_pixels)) / 2
        cy = sum((y for _, y in center_pixels)) / 2
        ax.imshow(rgb)
        for actor in actors:
            poly = [pixel(xy) for xy in corners(actor, 0)]
            ax.add_patch(Polygon(poly, closed=True, fill=False, edgecolor='orange', linewidth=2))
            x, y = pixel(point(actor))
            ax.text(x, y - 8, f"target {actor['id']}", color='yellow', fontsize=10, bbox=dict(facecolor='black', alpha=0.6, pad=1))
        ax.set(xlim=(cx - 110, cx + 110), ylim=(cy + 75, cy - 75), title=f"Target pair {pair['pair_id']} on recording {recording} aerial")
        ax.axis('off')
    fig.tight_layout()
    image_out = target_root / 'testing/physical_overlap_evidence.png'
    fig.savefig(image_out, dpi=160)
    plt.close(fig)
    report = {'schema_version': 1, 'target_recording': target_recording, 'target_binary_sha256': sha(target_root / 'testing/map_000000.bin'), 'target_physical_audit_sha256': sha(target_root / 'testing/physical_source_audit.json'), 'target_background_sha256': sha(source / f'{target_recording:02d}_background.png'), 'target_registration_sha256': sha(target_root / 'testing/source_image_registration.json'), 'reference_recording': reference_recording, 'reference_background_sha256': sha(source / f'{reference_recording:02d}_background.png'), 'reference_tracks_sha256': sha(source / f'{reference_recording:02d}_tracks.csv'), 'reference_registration_sha256': sha(reference_root / 'testing/source_image_registration.json'), 'reference_scene_root': str(reference_root), 'pairs': pairs, 'image': image_out.name, 'image_sha256': sha(image_out)}
    output = target_root / 'testing/physical_overlap_evidence.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'image': str(image_out), 'pairs': pairs}, indent=2))
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--reference-root', type=Path, required=True)
    args = ap.parse_args()
    render(args.root.resolve(), args.reference_root.resolve())
