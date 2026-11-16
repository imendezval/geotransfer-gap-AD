"""Source-only event-centred cyclist search across all33 inD recordings.

Complements track-birth stride catalogs, retaining fixed horizon/task standards.
No evaluator/planner outputs are read. Complete pair/rejection ledger retained.
"""
import csv
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import pilot_ind as p
from screen_source_tasks import sample, screen

A = Path(__file__).resolve().parent / 'pilot/audits'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--offset-stride',type=int,default=25)
    ap.add_argument('--offset-radius',type=int,default=50)
    ap.add_argument('--output',type=Path,default=A/'third_family_event_selection_v1.json')
    args=ap.parse_args()
    if args.offset_stride<=0 or args.offset_radius<0:raise ValueError('Invalid source phase grid')
    manifest = json.loads((A / 'step2_expanded_current_manifest.json').read_text())
    occupied = {(r['recording'], i) for r in manifest for i in r['moving_track_ids']}
    jobs, rejected, inputs = [], [], {}
    for rec in range(33):
        tracks_path = p.SOURCE / f'data/{rec:02d}_tracks.csv'
        meta_path = p.SOURCE / f'data/{rec:02d}_tracksMeta.csv'
        recording_path = p.SOURCE / f'data/{rec:02d}_recordingMeta.csv'
        inputs[str(rec)] = {str(path): sha(path) for path in (tracks_path, meta_path, recording_path)}
        location = int(next(csv.DictReader(recording_path.open()))['locationId'])
        meta = {int(r['trackId']): r for r in csv.DictReader(meta_path.open())}
        df = pd.read_csv(tracks_path, usecols=['frame', 'trackId', 'xCenter', 'yCenter',
                                              'heading', 'xVelocity', 'yVelocity'])
        tracks = {int(i): g[['frame', 'xCenter', 'yCenter', 'heading', 'xVelocity', 'yVelocity']].to_numpy(float)
                  for i, g in df.groupby('trackId', sort=False)}
        cars = [i for i, m in meta.items() if m['class'] in ('car', 'truck_bus')
                and (rec, i) not in occupied and tracks[i][-1, 0] - tracks[i][0, 0] >= 225]
        bikes = [i for i, m in meta.items() if m['class'] == 'bicycle' and (rec, i) not in occupied]
        def dims(i):
            default = (1.8, .6) if meta[i]['class'] == 'bicycle' else (4.5, 1.8)
            return tuple(float(meta[i][k]) if float(meta[i][k]) > 0 else d
                         for k, d in zip(('length', 'width'), default))
        for ego_id in cars:
            et = tracks[ego_id]
            for actor_id in bikes:
                at = tracks[actor_id]
                first, last = max(et[0, 0], at[0, 0]), min(et[-1, 0], at[-1, 0])
                if last < first:
                    continue
                times = np.arange(first, last + 1, 5)
                exy = np.column_stack([np.interp(times, et[:, 0], et[:, k]) for k in (1, 2)])
                axy = np.column_stack([np.interp(times, at[:, 0], at[:, k]) for k in (1, 2)])
                gaps = np.linalg.norm(exy - axy, axis=1)
                nearest = int(gaps.argmin())
                if gaps[nearest] > 12:
                    continue
                centre = int(math.floor(times[nearest] - 45 * 2.5))
                for offset in range(-args.offset_radius,args.offset_radius+1,args.offset_stride):
                    start = centre + offset
                    reason = None
                    frames = start + np.arange(91) * 2.5
                    ego, actor = sample(et, frames), sample(at, frames)
                    path = float(np.linalg.norm(np.diff(ego[0], axis=0), axis=1).sum())
                    displacement = float(np.linalg.norm(ego[0][-1] - ego[0][0]))
                    end = int(np.flatnonzero(np.linalg.norm(ego[0] - ego[0][85], axis=1) <= 2)[0])
                    if not ego[3].all() or path < 5 or displacement < 4 or end < 75:
                        reason = 'Source coverage/motion/goal timing'
                    evidence = None if reason else screen(ego, actor, 'bicycle', dims(ego_id), dims(actor_id))
                    if evidence is None:
                        reason = reason or 'No physical crossing at supported angle/timing'
                    identity = {'recording': rec, 'location': location, 'ego': ego_id,
                                'actor': actor_id, 'first_frame': start}
                    if reason:
                        rejected.append(dict(identity, reason=reason))
                    else:
                        turn = abs((ego[2][85] - ego[2][0] + math.pi) % (2 * math.pi) - math.pi)
                        jobs.append(dict(identity, actor_class='bicycle', role='vru_encounter_candidate',
                                         task_evidence=evidence, ego_path_m=path,
                                         source_displacement_m=displacement, goal_first_entry_step=end,
                                         source_nearest_step=int(round((times[nearest] - start) / 2.5)),
                                         source_center_gap_m=float(gaps[nearest]), source_net_turn_rad=float(turn)))
        print('recording', rec, 'positive windows', len(jobs), flush=True)
    jobs.sort(key=lambda r: (r['location'], r['source_net_turn_rad'] >= .35,
                            round(r['task_evidence']['source_crossing_time_gap_s'], 3),
                            abs((r['task_evidence']['ego_path_crossing_step'] +
                                 r['task_evidence']['actor_path_crossing_step']) / 2 - 45),
                            r['recording'], r['ego'], r['first_frame'], r['actor']))
    result = {'schema_version': 1, 'selector_sha256': sha(Path(__file__)),
              'composition_sha256': sha(A / 'final_corpus_selection_v1.json'),
              'baseline_manifest_sha256': sha(A / 'step2_expanded_current_manifest.json'),
              'selection': 'All33 recordings, nearest source pair event within12m at5-frame sampling; event-centred45 plus uniform source-frame offsets explicitly recorded in source_phase_offsets. Current coverage/motion/goal and source-body crossing screen. Straight source routes first inside each location; source/fidelity selection only.',
              'source_phase_offsets':list(range(-args.offset_radius,args.offset_radius+1,args.offset_stride)), 'source_hashes': inputs, 'jobs': jobs, 'source_rejections': rejected}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'windows': len(jobs), 'tasks': len({(r['recording'], r['ego'], r['actor']) for r in jobs})}))


if __name__ == '__main__':
    main()
