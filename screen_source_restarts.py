"""Source-only restart tasks missed by a post-warmup braking screen.

Requires a sustained stopped leader and slow ego after warmup, then leader
restart and ego progress. The entire goal disk must lie beyond the stopped
leader's collision interval. No policy outcomes or evaluator traces are read.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pilot_ind as p
from screen_source_tasks import sample


def restart(ego, leader, ego_length, leader_length, ego_width=0., leader_width=0., *, moving_queue=False):
    ep, ev, eh, em = ego
    lp, lv, lh, lm = leader
    if not all(np.isfinite(x).all()for x in (ep,ev,eh,lp,lv,lh)):
        return None
    end = int(np.flatnonzero(np.linalg.norm(ep - ep[85], axis=1) <= 2)[0])
    if end < 75:
        return None
    es, ls = np.linalg.norm(ev, axis=1), np.linalg.norm(lv, axis=1)
    forward = np.column_stack((np.cos(eh), np.sin(eh)))
    delta = lp - ep
    along = (delta * forward).sum(axis=1)
    lateral = abs(delta[:, 0] * -np.sin(eh) + delta[:, 1] * np.cos(eh))
    heading = abs((lh - eh + np.pi) % (2 * np.pi) - np.pi)
    close = em & lm & (along > 2) & (along < 20) & (lateral < 1.5) & (heading < .25)
    for first in range(10, end - 20):
        last = first + 9
        leader_limit,ego_limit=(2.,2.) if moving_queue else (.5,1.)
        phase=close[first:last+1] & (ls[first:last+1] < leader_limit) & (es[first:last+1] < ego_limit)
        if moving_queue:
            phase &= along[first:last+1]-(ego_length+leader_length)/2<=5
            if np.all((ls[first:last+1]<.5)&(es[first:last+1]<1)):continue
        if not np.all(phase):
            continue
        leader_floor=float(ls[first:last+1].max())+2 if moving_queue else 1.5
        ego_floor=float(es[first:last+1].max())+1.5 if moving_queue else 1.5
        starts = [t for t in range(last+1, end-9)
                  if np.all(lm[t:t+5]) and np.all(ls[t:t+5] > leader_floor)]
        if not starts:
            continue
        release = starts[0]
        direction = forward[last]
        # A later turn does not invalidate a stopped-leader response. Bound
        # the complete goal disk and any ego orientation in the stop frame.
        turn = abs((eh[:end+1] - eh[last] + np.pi) % (2*np.pi) - np.pi)
        lead_angle=lh[last]-eh[last]
        leader_extent=(leader_length*abs(np.cos(lead_angle))+leader_width*abs(np.sin(lead_angle)))/2
        clearance = float((ep[85]-lp[last]) @ direction - 2
                          - np.hypot(ego_length,ego_width)/2 - leader_extent)
        if clearance <= 0:
            continue
        if not np.any(es[release:end+1] > ego_floor):
            continue
        evidence={'kind': 'lead_vehicle_constrained_following' if moving_queue else 'lead_vehicle_stop_and_restart',
                'stopped_interval': [first, last], 'leader_restart_step': release,
                'source_goal_first_entry_step': end,
                'goal_disk_beyond_stopped_leader_collision_interval_m': clearance,
                'maximum_source_task_heading_change_rad': float(turn.max())}
        if moving_queue:
            evidence['constrained_interval']=evidence.pop('stopped_interval')
            evidence['leader_departure_step']=evidence.pop('leader_restart_step')
            evidence['maximum_phase_leader_speed_mps']=float(ls[first:last+1].max())
            evidence['maximum_phase_ego_speed_mps']=float(es[first:last+1].max())
        return evidence
    return None


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--selection', type=Path, nargs='+', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--task',choices=('stop_restart','moving_queue'),default='stop_restart')
    args = ap.parse_args()
    rows, seen, inputs = [], set(), []
    for path in args.selection:
        data = json.loads(path.read_text())
        inputs.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        for row in data['source_pairs_before_dedup']:
            key = tuple(row[k] for k in ('recording', 'ego', 'first_frame', 'actor'))
            if key in seen or row['actor_class'] not in ('car', 'truck_bus'):
                continue
            seen.add(key)
            rows.append(row)
    positives = []
    for rec in sorted({r['recording'] for r in rows}):
        todo = [r for r in rows if r['recording'] == rec]
        ids = {r[k] for r in todo for k in ('ego', 'actor')}
        df = pd.read_csv(p.SOURCE/f'data/{rec:02d}_tracks.csv',
                         usecols=['frame','trackId','xCenter','yCenter','heading','xVelocity','yVelocity'])
        tracks = {int(i): g[['frame','xCenter','yCenter','heading','xVelocity','yVelocity']].to_numpy(float)
                  for i,g in df[df.trackId.isin(ids)].groupby('trackId',sort=False)}
        with (p.SOURCE/f'data/{rec:02d}_tracksMeta.csv').open() as stream:
            dimensions = {int(r['trackId']):(float(r['length']),float(r['width'])) for r in csv.DictReader(stream)}
        for row in todo:
            frames = row['first_frame'] + np.arange(91)*2.5
            evidence = restart(sample(tracks[row['ego']],frames),sample(tracks[row['actor']],frames),
                               dimensions[row['ego']][0],dimensions[row['actor']][0],
                               dimensions[row['ego']][1],dimensions[row['actor']][1],
                               moving_queue=args.task=='moving_queue')
            if evidence:
                positives.append(dict(row, task_evidence=evidence))
        print('recording',rec,'restart positives',len(positives),flush=True)
    positives.sort(key=lambda r:(r['location'],r['recording'],r['ego'],
                                abs(r['task_evidence'].get('leader_restart_step',r['task_evidence'].get('leader_departure_step',45))-45),r['first_frame']))
    jobs, windows = [], set()
    for r in positives:
        key = tuple(r[k] for k in ('recording','ego','first_frame'))
        if key not in windows:
            windows.add(key)
            jobs.append(r)
    result = {'schema_version':1,'screen_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'selection':'Sustained10-sample stopped leader/slow ego after warmup, aligned same-lane stop geometry, then5-sample leader restart and ego progress; full2m goal disk plus any ego orientation beyond the stopped leader OBB support plane; source goal first entry>=75. Later turns are allowed, with directed route/goal/manual review still required. All source-positive windows retained, final independent count deduplicated. No policy outcomes.',
              'inputs':inputs,'screened_source_pairs':len(rows),'source_positive_pairs':positives,'jobs':jobs}
    if args.task=='moving_queue':
        result['selection']='Source constrained-following cohort:10samples after warmup with aligned leader/ego below2m/s and longitudinal body gap<=5m, followed by sustained leader speed rise>2m/s and ego speed rise>1.5m/s; exclude phases already qualifying as a stationary restart. The complete goal disk/any ego orientation must lie beyond the leader reference collision envelope; source goal first entry>=75. Later turns allowed. Source selection only; unchanged fidelity/semantic/model gates and final independence rules.'
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('restart jobs',len(jobs))


if __name__ == '__main__':
    main()
