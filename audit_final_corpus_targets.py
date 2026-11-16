"""Audit prospective composition and source anchors; never fills quotas with controls."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
A=HERE/'pilot/audits'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--manifest',type=Path,default=A/'step2_expanded_current_manifest.json')
    ap.add_argument('--output',type=Path,default=A/'final_corpus_target_audit.json');args=ap.parse_args()
    pointer=json.loads((A/'final_corpus_selection_current.json').read_text());selection=HERE/pointer['path']
    assert sha(selection)==pointer['sha256']
    config=json.loads(selection.read_text())
    assert sha(HERE/config['requirements_document'])==config['requirements_sha256']
    assert sha(HERE/config['protocol_amendment_document'])==config['protocol_amendment_sha256']
    anchor_path=HERE/config['source_anchor_manifest'];assert sha(anchor_path)==config['source_anchor_manifest_sha256']
    anchors=json.loads(anchor_path.read_text())['anchors'];rows=json.loads(args.manifest.read_text())
    indexed={r['root']:r for r in rows}
    retained=all(r['root']in indexed and indexed[r['root']]['binary_sha256']==r['binary_sha256']for r in anchors)
    families=collections.Counter();locations=collections.Counter();recordings=collections.Counter();density=collections.Counter();maneuvers=collections.Counter();cycles=[]
    details=[]
    for row in rows:
        t=Path(row['root'])/'testing';gate=t/f"admission_smart_{row['traffic_protocol']}.json"
        assert sha(gate)==row['admission_sha256'] and json.loads(gate.read_text())['research_admitted']
        expected='heldout_location_4'if row['location']==4 else'validation_recording'if row['recording']%5==0 else'adaptation_recording'
        assert row['split']==expected,(row['root'],row['split'])
        family=row['interaction_type_families'][0]if row['interaction_opportunity']else'uncontested_control'
        families[family]+=1;locations[str(row['location'])]+=1;recordings[row['recording']]+=1
        if family=='cyclist_crossing':cycles.append(row)
        scene=json.loads(next(t.glob('ind_*.json')).read_text());ego=scene['objects'][0];goal=ego['goalPosition']
        end=next(i for i,p in enumerate(ego['position'])if math.hypot(p['x']-goal['x'],p['y']-goal['y'])<=2)
        moving=[o for o in scene['objects']if o['id']!=ego['id']and o.get('source_window_path_length_m',0)>=1]
        maximum=max(sum(o['valid'][i]and math.hypot(o['position'][i]['x']-ego['position'][i]['x'],o['position'][i]['y']-ego['position'][i]['y'])<=30 for o in moving)for i in range(10,end+1))
        label='low'if maximum<=3 else'medium'if maximum<=8 else'high';density[label]+=1
        review=json.loads((t/'semantic_review_smart_hybrid_startup.json').read_text())
        maneuver=review.get('reviewed_task_maneuver','not_yet_structured');maneuvers[maneuver]+=1
        details.append({'root':row['root'],'family':family,'density':label,'maximum_source_nearby_moving_actors':maximum,
                        'source_goal_first_entry':end,'reviewed_maneuver':maneuver})
    criterion=config['third_family_run_standard']
    third_met=len(cycles)>=criterion['independent_admitted_cyclist_scenes']and len({r['recording']for r in cycles})>=criterion['minimum_recording_clusters']
    result={'producer_sha256':sha(Path(__file__)),'manifest_sha256':sha(args.manifest),'selection_sha256':sha(selection),
            'planning_schema_verified':True,'source_anchors_retained':retained,'scenes':len(rows),
            'family_counts':dict(families),'family_target_shortfalls':{k:max(0,v-families[k])for k,v in config['family_targets'].items()},
            'location_counts':dict(locations),'location_target_shortfalls':{k:max(0,v-locations[k])for k,v in config['location_targets'].items()},
            'recording_clusters':len(recordings),'maximum_scenes_per_recording':max(recordings.values()),
            'recording_cap_pass':max(recordings.values())<=config['maximum_scenes_per_recording'],
            'density_counts':dict(density),'reviewed_maneuver_counts':dict(maneuvers),
            'third_family_scenes':len(cycles),'third_family_recordings':sorted({r['recording']for r in cycles}),
            'third_family_run_standard_met':third_met,'final_corpus_complete':False,'source_details':details,
            'scope':'Composition and third-family feasibility audit; full50-scene/power/coverage requirements are not inferred from this milestone.'}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in ['scenes','family_counts','recording_clusters','source_anchors_retained','third_family_run_standard_met']}))
    if not retained or not third_met or not result['recording_cap_pass']:raise SystemExit(1)


if __name__=='__main__':main()
