"""Reproduce or validate both US interface references and publish their aggregate.

Mechanical diagnostics only: no matched cohort or US research admission claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
BENCH=HERE.parent/'behavior-bench'
sys.path.insert(0,str(BENCH))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--roots',type=Path,nargs='+',default=[HERE/'pilot/probes/us_hybrid_1002fdc9826fc6d1',HERE/'pilot/probes/us_smart_negative_world_739e0513c6f7cfe8'])
    ap.add_argument('--reuse-current',action='store_true',help='Validate current producer/runtime/model hashes before aggregating existing diagnostics.')
    args=ap.parse_args()
    import late_spawn_runtime,hybrid_traffic,faithful_map
    runtime=late_spawn_runtime.load();roots=[r.resolve()for r in args.roots]
    logs=HERE/'pilot/probes/us_reference_checks';logs.mkdir(parents=True,exist_ok=True)
    protocol={k:sha(HERE/k)for k in ('faithful_smart.py','faithful_map.py','background_route_intent.py','hybrid_traffic.py','probe_faithful_smart_closed_loop.py')}
    inputs={'adapter':HERE/'faithful_smart.py','probe':HERE/'probe_smart_map_transfer.py',
        'map_preprocessing':HERE/'faithful_map.py','smart_planner':BENCH/'pufferlib/planning/smart.py',
        'tokenizer':BENCH/'pufferlib/prediction/map_tokenizer.py','training_dataset':BENCH/'pufferlib/prediction/dataset.py',
        'map_codebook':BENCH/'pufferlib/prediction/smart/tokens/map_traj_token5.pkl',
        'motion_codebook':BENCH/'pufferlib/prediction/smart/tokens/cluster_frame_5_2048.pkl',
        'evaluation_ini':BENCH/'pufferlib/config/evaluation.ini'}
    expected={k:sha(v)for k,v in inputs.items()};results=[]
    for root in roots:
        if not args.reuse_current:
            for tool,extra in [('probe_smart_map_transfer.py',['--us-binary',str(roots[0]/'testing/map_000000.bin'),'--all-actors','--inference','--steps','81']),
                               ('probe_faithful_smart_closed_loop.py',['--steps','50'])]:
                with(logs/(root.name+'_'+tool+'.log')).open('w')as stream:
                    p=subprocess.run([sys.executable,str(HERE/tool),'--root',str(root),*extra],stdout=stream,stderr=subprocess.STDOUT)
                if p.returncode:raise RuntimeError('US reference producer failed: '+root.name+'/'+tool)
        t=root/'testing';input_path=t/'smart_map_transfer_all_actors_probe.json'
        probe=json.loads(input_path.read_text());features=probe['source_feature_audit']
        assert probe['runtime_source_sha256']==runtime['runtime_source_sha256']
        assert probe['protocol_file_sha256']==expected
        assert probe['checkpoint_sha256']==sha(BENCH/'weights/SMART_epoch_030.pt')
        assert probe['maps']['german']['binary_sha256']==sha(t/'map_000000.bin')
        assert probe['map_encoding_protocol']==faithful_map.PROTOCOL_VERSION
        assert probe['inference_finite'] and probe['future_mutation_invariant_at_reset']
        assert features['presence_mismatches']==features['class_mismatches']==0
        assert all(features[k]<.01 for k in ('max_position_error_m','max_local_position_error_m',
                   'max_heading_error_rad','max_dimension_error_m','max_evaluator_velocity_error_mps'))
        assert probe['map_frame_position_error_m']<.01 and probe['perturbed_ego_input_error_m']<.01
        path=t/'smart_all_actors_closed_loop_hybrid_startup.json';report=json.loads(path.read_text())
        assert report['runtime']['runtime_source_sha256']==runtime['runtime_source_sha256']
        assert report['protocol_sha256']==protocol and report['binary_sha256']==sha(t/'map_000000.bin')
        bad=[r['step']for r in report['timeline']if r.get('prediction_refreshed')and not r['identity_match']]
        assert not bad and any(r.get('prediction_refreshed')for r in report['timeline'])
        results.append({'root':str(root),'report_sha256':sha(path),'input_probe_sha256':sha(input_path),
                        'identity_errors':bad,'runtime':report['runtime'],'steps':len(report['timeline'])})
    output={'producer_sha256':sha(Path(__file__)),'traffic_version':hybrid_traffic.PROTOCOL_VERSION,
            'map_encoding_protocol':faithful_map.PROTOCOL_VERSION,'diagnostic_only':True,'results':results,'passed':True,
            'scope':'Same source-state/map/traffic/canonical execution checks on two US references; not matched research data or upstream training equivalence.'}
    (HERE/'pilot/audits/step2_velocity_us_closed_loop_parity.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({'references':len(results),'passed':True}))


if __name__=='__main__':main()
