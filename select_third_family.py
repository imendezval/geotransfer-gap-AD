"""Freeze source-only cyclist candidates; never inspect planner outcomes."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pilot_ind as p
from screen_source_tasks import sample, screen

HERE = Path(__file__).resolve().parent
A = HERE / 'pilot/audits'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sources = [A / (n + '.json') for n in
               ('body_task_selection', 'fine_phase_task_selection', 'footprint_task_selection')]
    manifest_path = A / 'step2_expanded_current_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    occupied = {(r['recording'], i) for r in manifest for i in r['moving_track_ids']}
    candidates = {}
    rejected = []
    for path in sources:
        for r in json.loads(path.read_text())['source_positive_pairs']:
            if r['actor_class'] == 'bicycle':
                candidates[tuple(r[k] for k in ('recording', 'ego', 'first_frame', 'actor'))] = r
    jobs = []
    source_hashes = {}
    for rec in sorted({k[0] for k in candidates}):
        paths = {n: p.SOURCE / f'data/{rec:02d}_{n}.csv'
                 for n in ('tracks', 'tracksMeta', 'recordingMeta')}
        source_hashes[str(rec)] = {n: sha(path) for n, path in paths.items()}
        with paths['tracksMeta'].open() as f:
            meta = {int(r['trackId']): r for r in csv.DictReader(f)}
        df = pd.read_csv(paths['tracks'], usecols=['frame', 'trackId', 'xCenter', 'yCenter',
                                                  'heading', 'xVelocity', 'yVelocity'])
        tracks = {int(i): g[['frame', 'xCenter', 'yCenter', 'heading', 'xVelocity', 'yVelocity']].to_numpy(float)
                  for i, g in df.groupby('trackId', sort=False)}
        def dimensions(i):
            m = meta[i]
            default = (1.8, .6) if m['class'] == 'bicycle' else (4.5, 1.8)
            return tuple(float(m[k]) if float(m[k]) > 0 else d
                         for k, d in zip(('length', 'width'), default))
        for key, r in candidates.items():
            if key[0] != rec:
                continue
            reason = None
            if any((rec, r[k]) in occupied for k in ('ego', 'actor')):
                reason = 'Shares moving ego/claimed actor with baseline anchors'
            frames = r['first_frame'] + np.arange(91) * 2.5
            ego = sample(tracks[r['ego']], frames)
            actor = sample(tracks[r['actor']], frames)
            path = float(np.linalg.norm(np.diff(ego[0], axis=0), axis=1).sum())
            displacement = float(np.linalg.norm(ego[0][-1] - ego[0][0]))
            end = int(np.flatnonzero(np.linalg.norm(ego[0] - ego[0][85], axis=1) <= 2)[0])
            if not ego[3].all() or path < 5 or displacement < 4 or end < 75:
                reason = reason or 'Source coverage/motion/goal timing fails frozen requirement'
            evidence = screen(ego, actor, 'bicycle', dimensions(r['ego']), dimensions(r['actor']))
            if evidence is None:
                reason = reason or 'No current physical source crossing'
            if reason:
                rejected.append({'recording': rec, 'ego': r['ego'], 'first_frame': r['first_frame'],
                                 'actor': r['actor'], 'reason': reason})
            else:
                jobs.append(dict(r, task_evidence=evidence, ego_path_m=path,
                                 source_displacement_m=displacement, goal_first_entry_step=end))
    jobs.sort(key=lambda r: (r['location'], round(r['task_evidence']['source_crossing_time_gap_s'], 3),
                            abs((r['task_evidence']['ego_path_crossing_step'] +
                                 r['task_evidence']['actor_path_crossing_step']) / 2 - 45),
                            r['recording'], r['ego'], r['first_frame'], r['actor']))
    result = {'schema_version': 1, 'selector_sha256': sha(Path(__file__)),
              'composition_sha256': sha(A / 'final_corpus_selection_v1.json'),
              'baseline_manifest_sha256': sha(manifest_path),
              'inputs': {str(path): sha(path) for path in sources}, 'source_hashes': source_hashes,
              'selection': 'Fixed prospective v1 source-only cyclist crossing order. Distinct tasks before alternate phases; all gates/manual review still required.',
              'source_pairs': len(candidates), 'source_rejections': rejected, 'jobs': jobs}
    (A / 'third_family_source_selection_v1.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'source_pairs': len(candidates), 'jobs': len(jobs),
                      'distinct_tasks': len({(r['recording'], r['ego'], r['actor']) for r in jobs}),
                      'rejected': len(rejected)}))


if __name__ == '__main__':
    main()
