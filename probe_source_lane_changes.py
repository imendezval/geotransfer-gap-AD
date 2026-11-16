"""Independent native Germany/Vehicle check of conservative lateral permissions."""
import csv
import hashlib
import json
from pathlib import Path
import lanelet2
import pilot_ind as p
from source_lane_changes import edges

HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def reachable(graph,start,goal):
    seen={start};pending=[start]
    while pending:
        for target in graph.get(pending.pop(),[]):
            if target not in seen:seen.add(target);pending.append(target)
    return goal in seen


def main():
    seen=set();reports=[];fixture=None
    for rec in range(33):
        p.RECORDING=rec
        meta=next(csv.DictReader((p.SOURCE/f'data/{rec:02d}_recordingMeta.csv').open()))
        path,_=p.map_paths(meta)
        if path in seen:continue
        seen.add(path);roads,lanes=p.make_roads(meta);candidate=edges(lanes,path)
        native,errors=lanelet2.io.loadRobust(str(path),lanelet2.projection.UtmProjector(lanelet2.io.Origin(50.,6.)))
        if errors:raise ValueError(errors)
        rules=lanelet2.traffic_rules.create(lanelet2.traffic_rules.Locations.Germany,lanelet2.traffic_rules.Participants.Vehicle)
        routing=lanelet2.routing.RoutingGraph(native,rules);expected=set();forbidden=set()
        for lane in lanes:
            for method in (routing.left,routing.right):
                target=method(native.laneletLayer[lane])
                if target is not None:expected.add((lane,target.id))
            for method in (routing.leftRelations,routing.rightRelations):
                for relation in method(native.laneletLayer[lane],False):
                    if str(relation.relationType).startswith('Adjacent'):
                        forbidden.add((lane,relation.lanelet.id))
        encoded={(e['source'],e['target'])for e in candidate}
        bad_permission=[(s,t)for s,t in encoded if not rules.canChangeLane(native.laneletLayer[s],native.laneletLayer[t])]
        report={'map':str(path),'source_sha256':sha(path),'encoded_edges':candidate,
                'extra_routing_edges':sorted(encoded-expected),'forbidden_edges_encoded':sorted(encoded&forbidden),
                'native_permission_failures':bad_permission,'conservative_omissions':sorted(expected-encoded)}
        reports.append(report)
        if int(meta['locationId'])==4:
            graph={r['id']:set(r['exit_lanes'])for r in roads if r['type']=='lane'}
            before=reachable(graph,1085,1047)
            for s,t in encoded:graph[s].add(t)
            native_path=routing.shortestPath(native.laneletLayer[1085],native.laneletLayer[1047],0,True)
            fixture={'start':1085,'goal':1047,'following_only':before,'with_legal_changes':reachable(graph,1085,1047),
                     'native_legal_path':[r.id for r in native_path]if native_path is not None else[]}
    passed=all(not r['extra_routing_edges'] and not r['forbidden_edges_encoded'] and not r['native_permission_failures']for r in reports)
    passed=passed and fixture and not fixture['following_only'] and fixture['with_legal_changes'] and bool(fixture['native_legal_path'])
    result={'lane_change_tool_sha256':sha(HERE/'source_lane_changes.py'),'probe_sha256':sha(Path(__file__)),
            'converter_sha256':sha(Path(p.__file__)),'oracle':'lanelet2==1.2.3 Germany Vehicle left/right and canChangeLane',
            'scope':'Conservative unambiguous dashed-boundary subset; omitted ambiguous/mixed markings remain unsupported. No lateral edges are inserted as IDM successors.',
            'maps':reports,'legal_route_fixture':fixture,'passed':bool(passed)}
    (HERE/'pilot/audits/source_lane_change_native_oracle.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'maps':len(reports),'lateral_edges':sum(len(r['encoded_edges'])for r in reports),'passed':bool(passed),'fixture':fixture}))
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
