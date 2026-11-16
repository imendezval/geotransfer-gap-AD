"""Freeze source-only candidates from corrected map indexes before policy runs."""
import argparse
import csv
import math
import hashlib
import json
from pathlib import Path
from collections import Counter

HERE=Path(__file__).resolve().parent

def main():
    specs=[('loc4','all_moving_windows_loc4_stride50.json'),('loc1','all_moving_windows_loc1_stride50.json'),('loc23','all_moving_windows_loc23_stride50.json')]
    ap=argparse.ArgumentParser(__doc__);ap.add_argument('--catalog',type=Path);ap.add_argument('--map-preflight',type=Path);ap.add_argument('--output',type=Path,default=HERE/'pilot/audits/step2_oriented_source_selection.json');args=ap.parse_args()
    if bool(args.catalog)!=bool(args.map_preflight):ap.error('Supply both catalog and map-preflight')
    candidates=[];provenance={};actor_meta={}
    def radius(rec,tid):
        if rec not in actor_meta:
            with (HERE.parent/f"data/levelxdata/inD-dataset-v1.1/data/{rec:02d}_tracksMeta.csv").open() as stream:actor_meta[rec]={int(x["trackId"]):x for x in csv.DictReader(stream)}
        m=actor_meta[rec][tid];defaults=(.6,.6) if m["class"]=="pedestrian" else (1.8,.6) if m["class"]=="bicycle" else (4.5,1.8)
        length=float(m["length"]);width=float(m["width"]);return .5*math.hypot(length if length>0 else defaults[0],width if width>0 else defaults[1])
    pairs=[(HERE/'pilot/audits'/name,HERE/'pilot/audits'/f'source_map_preflight_{group}_oriented_v3.json') for group,name in specs]
    if args.catalog:pairs=[(args.catalog,args.map_preflight)]
    for catalog,index in pairs:
        provenance[str(catalog)]=hashlib.sha256(catalog.read_bytes()).hexdigest();provenance[str(index)]=hashlib.sha256(index.read_bytes()).hexdigest()
        passing={(r['recording'],r['ego_track_id'],r['first_frame']) for r in json.loads(index.read_text())['windows'] if r['outside_sample_count']==0 and r['directed_route'] and r.get('source_track_complete')}
        for r in json.loads(catalog.read_text())['windows']:
            if (r['recording'],r['ego_track_id'],r['first_frame']) not in passing or r['source_rejection'] is not None:continue
            for actor in r['nearest_actors']:
                if not actor['moving'] or actor.get('source_actor_window_path_m',0)<2 or actor['minimum_timed_center_distance_m']>5+radius(r['recording'],r['ego_track_id'])+radius(r['recording'],actor['track_id']) or not 15<=actor['nearest_step']<=70:continue
                kind='vehicle_response_candidate' if actor['class'] in ('car','truck_bus') else 'vru_encounter_candidate'
                candidates.append({'recording':r['recording'],'location':r['location'],'ego':r['ego_track_id'],'first_frame':r['first_frame'],'actor':actor['track_id'],'actor_class':actor['class'],'source_nearest_step':actor['nearest_step'],'source_center_gap_m':actor['minimum_timed_center_distance_m'],'ego_path_m':r['ego_path_m'],'goal_first_entry_step':r['first_goal_radius_step'],'role':kind})
    # Prefer a centered encounter and a long actor source track. A single
    # window per ego and candidate actor prevents duplicate clips dominating.
    candidates.sort(key=lambda r:(abs(r['source_nearest_step']-45),r['source_center_gap_m'],r['recording'],r['ego'],r['first_frame']))
    seen_ego=set();seen_actor=set();selected=[]
    for r in candidates:
        e=(r['recording'],r['ego']);a=(r['recording'],r['actor'])
        if e in seen_ego or a in seen_actor:continue
        seen_ego.add(e);seen_actor.add(a);selected.append(r)
    # Bound the first full-gate cohort by source strata, not outcomes.
    cohort=[]
    for loc in (1,2,3,4):
        for role in ('vru_encounter_candidate','vehicle_response_candidate'):
            pool=[r for r in selected if r['location']==loc and r['role']==role]
            cohort.extend(pool[:12])
    report={'schema_version':1,'selection':'Corrected source map pass; moving actor path>=2m, timed center gap within5m plus both source body circumradii, encounter steps15–70, source goal first entry>=75. Rank nearest step to45 then source distance. One ego and actor per recording in selection. First12 per location x VRU/vehicle stratum, before policy outcomes. This is screening, not admission.','provenance_sha256':provenance,'eligible_source_pairs':len(candidates),'source_pairs_before_dedup':candidates,'deduplicated_source_candidates':len(selected),'jobs':cohort,'remaining_source_queue':selected}
    path=args.output;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2)+'\n')
    print('source pairs',len(candidates),'dedup',len(selected),'cohort',len(cohort),'strata',dict(Counter((r['location'],r['role']) for r in cohort)))

if __name__=='__main__':main()
