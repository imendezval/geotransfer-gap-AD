"""Synthetic contracts for PE05 mapped-surface and lane diagnostics."""

import math
import hashlib
import json
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest
pytest.importorskip(
    "shapely", reason="install the optional evaluation-geometry extra for map metrics"
)
from shapely.affinity import rotate, translate
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

import geotransfer_gap.evaluation.context as context_owner
from geotransfer_gap.evaluation.context import (
    LaneCenterline,
    MapContext,
    _surface_unions,
    build_map_context,
    select_source_lanelet_map,
)
from geotransfer_gap.evaluation.map_metrics import measure_map_metrics
from geotransfer_gap.evaluation.profile import load_profile
from geotransfer_gap.maps import lanelet


EGO = 41
PROFILE = load_profile()
REPORT = {"terminal_reason": "horizon"}


def actor(x, y, *, heading=0.0, vx=1.0, vy=0.0, length=2.0, width=1.0,
          present=True, generation=0, source_valid=True):
    return {
        "id": EGO, "present": present,
        "x": float(x) if present else None, "y": float(y) if present else None,
        "heading": heading if present else None,
        "vx": vx if present else None, "vy": vy if present else None,
        "length": length, "width": width,
        "lifetime_generation": generation, "source_valid": source_valid,
    }


def episode(states, *, terminal="horizon"):
    frames = []
    for index, state in enumerate(states):
        frames.append({
            "step": index, "time_s": index / 10,
            "transition_applied": index < len(states) - 1,
            "actors": [state],
        })
    masks = [{"step": index, "time_s": index / 10,
              "present": state.get("present", False)}
             for index, state in enumerate(states)]
    exposure = {
        "observation_masks": masks,
        "windows": {
            "full": {"post_terminal_trajectory_unobserved": terminal != "horizon"},
            "primary": {"post_terminal_trajectory_unobserved": terminal != "horizon"},
        },
    }
    return frames, exposure, {**REPORT, "terminal_reason": terminal}


def context(road, coverage=None, lanes=()):
    return MapContext(
        status="valid", reason="synthetic hash-bound polygon fixture",
        road_union=road, coverage_union=coverage if coverage is not None else road,
        lanes=tuple(lanes), coverage_scope="synthetic_explicit_surface_coverage",
    )


def result(frames, exposure, ctx, *, report=None):
    measured = measure_map_metrics(frames, EGO, PROFILE, exposure, ctx)
    return measured["metrics"]


def metric(rows, metric_id, window="full"):
    return next(item for item in rows
                if item["metric_id"] == metric_id and item["window"] == window)


def test_adjacent_lanelet_seam_is_union_interior_not_outside():
    road = unary_union([box(0, -2, 2, 2), box(2, -2, 4, 2)])
    frames, exposure, _ = episode([actor(2, 0), actor(2.1, 0)])
    measured = metric(result(frames, exposure, context(road)),
                      "safety.map_footprint_outside")
    assert measured["status"] == "valid"
    assert measured["value"]["outside_observation_count"] == 0
    assert measured["value"]["outside_area_m2"]["maximum"] == pytest.approx(0)


def test_exact_area_and_excursion_when_center_is_inside_but_footprint_crosses_edge():
    road = box(0, -5, 10, 5)
    frames, exposure, _ = episode([actor(0.25, 0), actor(0.25, 0)])
    measured = metric(result(frames, exposure, context(road)),
                      "safety.map_footprint_outside")
    row = measured["value"]["samples"][0]
    assert row["outside_indicator"] is True
    assert row["outside_area_m2"] == pytest.approx(0.75)
    assert row["maximum_footprint_boundary_excursion_m"] == pytest.approx(0.75)
    assert row["boundary_excursion_sampling_underestimate_bound_m"] == 0.01


def test_concave_surface_uses_polygon_difference_not_corner_membership():
    road = Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)])
    coverage = box(-1, -1, 5, 5)
    frames, exposure, _ = episode([actor(3, 3), actor(3, 3)])
    measured = metric(result(frames, exposure, context(road, coverage)),
                      "safety.map_footprint_outside")
    assert measured["value"]["samples"][0]["outside_area_m2"] == pytest.approx(2.0)
    assert measured["value"]["samples"][0]["outside_indicator"] is True


def test_footprint_enclosing_a_hole_reports_area_but_zero_boundary_excursion():
    road = Polygon(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        holes=[[(4.5, 4.5), (5.5, 4.5), (5.5, 5.5), (4.5, 5.5)]],
    )
    coverage = road
    frames, exposure, _ = episode([actor(6, 5, length=4, width=3)] * 2)
    measured = metric(result(frames, exposure, context(road, coverage)),
                      "safety.map_footprint_outside")
    row = measured["value"]["samples"][0]
    assert row["outside_area_m2"] == pytest.approx(1.0)
    assert row["maximum_footprint_boundary_excursion_m"] == pytest.approx(0.0)


def test_map_coverage_gap_is_unavailable_and_not_counted_as_road_departure():
    road = box(0, -2, 2, 2)
    coverage = unary_union([box(0, -2, 2, 2), box(6, -2, 8, 2)])
    frames, exposure, _ = episode([actor(1, 0), actor(5, 0), actor(7, 0)])
    measured = metric(result(frames, exposure, context(road, coverage)),
                      "safety.map_footprint_outside")
    assert measured["status"] == "valid"
    assert measured["value"]["coverage"]["unavailable_map_gap_observations"] == 1
    gap = measured["value"]["samples"][1]
    assert gap["status"] == "unavailable"
    assert "outside area is unknown" in gap["reason"]
    assert "outside_indicator" not in gap


def test_missing_map_context_keeps_spatial_results_null():
    frames, exposure, _ = episode([actor(0, 0), actor(0, 0)])
    rows = result(frames, exposure,
                  MapContext(status="unavailable", reason="source map missing"))
    spatial = metric(rows, "safety.map_footprint_outside")
    assert spatial["status"] == "unavailable"
    assert spatial["value"] is None
    assert spatial["criterion_outcome"] == "not_assessed"
    assert metric(rows, "trajectory.lane_lateral_offset")["value"] is None


def test_mixed_known_and_missing_lifetime_refs_work_with_both_map_contexts():
    frames, exposure, _ = episode([
        actor(0, 0, generation=None),
        actor(0.1, 0, generation=0),
    ])
    expected_refs = [[EGO, None], [EGO, 0]]

    unavailable_rows = result(
        frames, exposure, MapContext(status="unavailable", reason="map unavailable")
    )
    assert metric(unavailable_rows, "safety.map_footprint_outside")["actors"] == expected_refs
    assert metric(unavailable_rows, "trajectory.lane_lateral_offset")["actors"] == expected_refs

    road = box(-10, -5, 10, 5)
    lane = LaneCenterline(7, ((-10, 0), (10, 0)), 3.0, ())
    supported_rows = result(frames, exposure, context(road, road, [lane]))
    outside = metric(supported_rows, "safety.map_footprint_outside")
    lateral = metric(supported_rows, "trajectory.lane_lateral_offset")
    assert outside["status"] == "valid"
    assert outside["actors"] == expected_refs
    assert lateral["actors"] == expected_refs


def test_outside_duration_uses_supported_left_intervals_and_terminal_removal_censors():
    road = box(0, -5, 10, 5)
    coverage = box(-5, -10, 15, 10)
    frames, exposure, _ = episode([actor(-2, 0), actor(-2, 0), actor(-2, 0)])
    measured = metric(result(frames, exposure, context(road, coverage)),
                      "safety.map_footprint_outside")
    assert measured["value"]["observed_outside_duration_s"] == pytest.approx(0.2)

    removed = actor(0, 0, present=False)
    frames, exposure, report = episode([actor(-2, 0), removed], terminal="ego_collision")
    measured = metric(result(frames, exposure, context(road, coverage), report=report),
                      "safety.map_footprint_outside")
    assert measured["value"]["observed_outside_duration_s"] is None
    assert measured["value"]["observed_outside_duration_status"] == \
        "unavailable_no_supported_pose_intervals"
    assert any("censored" in item for item in measured["limitations"])


def test_footprint_dimension_reuse_matches_pe04_same_lifetime_support():
    road = box(-10, -10, 10, 10)
    first, second = actor(0, 0, length=4, width=2), actor(0, 0, length=None, width=None)
    frames, exposure, _ = episode([first, second])
    measured = metric(result(frames, exposure, context(road)),
                      "safety.map_footprint_outside")
    supported = measured["value"]["samples"][1]["dimension_support"]
    assert supported["source"] == "same_actor_lifetime_constant_observations"
    assert supported["imputed_fields"] == ["length", "width"]

    for row in (first, second):
        row.pop("lifetime_generation")
    frames, exposure, _ = episode([first, second])
    measured = metric(result(frames, exposure, context(road)),
                      "safety.map_footprint_outside")
    assert measured["value"]["samples"][1]["status"] == "unavailable"


def test_invalid_supplied_footprint_is_invalid_not_unavailable_or_zero():
    road = box(-10, -10, 10, 10)
    frames, exposure, _ = episode([actor(0, 0, length=0), actor(0, 0, length=0)])
    measured = metric(result(frames, exposure, context(road)),
                      "safety.map_footprint_outside")
    assert measured["status"] == "invalid"
    assert measured["value"] is None


def test_reversed_way_storage_uses_existing_lanelet_boundary_orientation(monkeypatch):
    osm = ET.fromstring("""<osm>
      <node id='1'/><node id='2'/><node id='3'/><node id='4'/>
      <node id='5'/><node id='6'/><node id='7'/><node id='8'/>
      <way id='10'><nd ref='2'/><nd ref='1'/></way>
      <way id='11'><nd ref='3'/><nd ref='4'/></way>
      <way id='12'><nd ref='5'/><nd ref='6'/></way>
      <way id='13'><nd ref='7'/><nd ref='8'/></way>
      <relation id='50'><member type='way' ref='10' role='left'/>
        <member type='way' ref='11' role='right'/>
        <tag k='type' v='lanelet'/><tag k='subtype' v='road'/></relation>
      <relation id='51'><member type='way' ref='10' role='left'/>
        <member type='way' ref='11' role='right'/>
        <tag k='type' v='lanelet'/><tag k='subtype' v='crosswalk'/></relation>
      <relation id='60'><member type='way' ref='12' role='left'/>
        <member type='way' ref='13' role='right'/>
        <tag k='type' v='lanelet'/><tag k='subtype' v='walkway'/></relation>
    </osm>""")
    coordinates = {
        1: (0.0, 1.0), 2: (10.0, 1.0),
        3: (0.0, -1.0), 4: (10.0, -1.0),
        5: (0.0, 5.0), 6: (10.0, 5.0),
        7: (0.0, 3.0), 8: (10.0, 3.0),
    }
    monkeypatch.setattr(lanelet, "project_nodes",
                        lambda *_args: coordinates)
    road, coverage, types = _surface_unions(
        osm, {"xUtmOrigin": 0, "yUtmOrigin": 0}, lanelet, Polygon, unary_union
    )
    assert road.area == pytest.approx(20.0)
    assert road.covers(Point(5, 0))
    assert not road.covers(Point(5, 4))
    assert coverage.covers(Point(5, 4))
    assert types == {50: "road", 51: "crosswalk", 60: "walkway"}


def test_recording_specific_construction_map_selector_is_preserved():
    normal = select_source_lanelet_map({"locationId": "1"}, 10)
    construction = select_source_lanelet_map({"locationId": "1"}, 11)
    assert "construction" not in str(normal)
    assert "construction" in str(construction)
    assert normal != construction


def test_missing_source_scene_or_map_is_unavailable_not_zero(tmp_path):
    missing_scene = build_map_context(tmp_path / "no_scene", "a" * 64)
    assert missing_scene.status == "unavailable"
    assert missing_scene.road_union is None


def _synthetic_scene_map_context(tmp_path, monkeypatch, *, selected_variant="construction"):
    root = tmp_path / "scene"
    testing = root / "testing"
    testing.mkdir(parents=True)
    (testing / "map_000000.bin").write_bytes(b"synthetic binary")
    binary_hash = hashlib.sha256(b"synthetic binary").hexdigest()
    (testing / "validation.json").write_text('{"recording":11,"location":1}')
    source = tmp_path / "source"
    data = source / "data"
    data.mkdir(parents=True)
    (data / "11_recordingMeta.csv").write_text(
        "recordingId,locationId,xUtmOrigin,yUtmOrigin\n11,1,0,0\n"
    )
    metadata_path = data / "11_recordingMeta.csv"
    standard = tmp_path / "location1.osm"
    construction = tmp_path / "location1_construction.osm"
    osm = """<osm>
      <node id='1'/><node id='2'/><node id='3'/><node id='4'/>
      <way id='10'><nd ref='2'/><nd ref='1'/></way>
      <way id='11'><nd ref='3'/><nd ref='4'/></way>
      <relation id='50'><member type='way' ref='10' role='left'/>
        <member type='way' ref='11' role='right'/>
        <tag k='type' v='lanelet'/><tag k='subtype' v='road'/></relation>
    </osm>"""
    standard.write_text(osm)
    construction.write_text(osm + "\n<!-- construction variant -->\n")
    chosen = construction if selected_variant == "construction" else standard
    selected_hash = hashlib.sha256(construction.read_bytes()).hexdigest()
    (testing / "map_semantics_audit.json").write_text(
        json.dumps({"binary_sha256": binary_hash,
                    "lanelet_source_sha256": selected_hash})
    )
    (testing / "evaluation_contract_expert.json").write_text(json.dumps({
        "schema_version": 2, "recording": 11, "scene_root": str(root.resolve()),
        "files": {
            "scene_binary": {"sha256": binary_hash},
            "source_lanelet2_map": {"sha256": selected_hash},
            "source_recording_meta_csv": {
                "sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
            },
        },
    }))
    artifacts = tmp_path / "artifacts"
    manifest = artifacts / "corpus" / "current.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("[]\n")
    row = {
        "name": "synthetic_r11", "root": str(root.resolve()),
        "recording": 11, "location": 1,
        "binary_sha256": binary_hash, "source_map_sha256": selected_hash,
    }
    monkeypatch.setattr(context_owner, "settings", lambda: SimpleNamespace(
        source=source, artifacts=artifacts,
    ))
    monkeypatch.setattr(context_owner, "read_manifest", lambda _path: [row])
    monkeypatch.setattr(context_owner, "select_source_lanelet_map",
                        lambda _metadata, _recording: chosen)
    monkeypatch.setattr(lanelet, "map_paths", lambda _metadata, _recording: (chosen, chosen))
    monkeypatch.setattr(lanelet, "project_nodes", lambda *_args: {
        1: (0.0, 1.0), 2: (10.0, 1.0), 3: (0.0, -1.0), 4: (10.0, -1.0),
    })
    return root, binary_hash, construction, standard


def test_scene_context_hash_binds_recording_specific_construction_map(tmp_path, monkeypatch):
    root, binary_hash, _construction, _standard = _synthetic_scene_map_context(
        tmp_path, monkeypatch
    )
    selected = build_map_context(root, binary_hash)
    assert selected.status == "valid"
    assert selected.identity["construction_variant"] == "location1_construction"
    assert selected.identity["source_map_sha256"]
    assert selected.identity["evaluation_contract_sha256"]
    assert selected.road_union.area == pytest.approx(20.0)


def test_wrong_construction_variant_fails_hash_binding(tmp_path, monkeypatch):
    root, binary_hash, _construction, _standard = _synthetic_scene_map_context(
        tmp_path, monkeypatch, selected_variant="standard"
    )
    selected = build_map_context(root, binary_hash)
    assert selected.status == "invalid"
    assert "manifest" in selected.reason


def test_recording_origin_change_invalidates_the_saved_source_contract(tmp_path, monkeypatch):
    root, binary_hash, _construction, _standard = _synthetic_scene_map_context(
        tmp_path, monkeypatch
    )
    metadata_path = tmp_path / "source" / "data" / "11_recordingMeta.csv"
    metadata_path.write_text("recordingId,locationId,xUtmOrigin,yUtmOrigin\n11,1,1,0\n")
    selected = build_map_context(root, binary_hash)
    assert selected.status == "invalid"
    assert "evaluation contract" in selected.reason


def test_absent_evaluation_contract_keeps_map_metrics_unavailable(tmp_path, monkeypatch):
    root, binary_hash, _construction, _standard = _synthetic_scene_map_context(
        tmp_path, monkeypatch
    )
    (root / "testing" / "evaluation_contract_expert.json").unlink()
    selected = build_map_context(root, binary_hash)
    assert selected.status == "unavailable"
    assert "evaluation_contract_missing" in selected.reason


def test_opposite_directed_lanelets_are_disambiguated_by_observed_heading():
    east = LaneCenterline(10, ((-10, 0), (10, 0)), 3.0, (11,))
    west = LaneCenterline(11, ((10, 0), (-10, 0)), 3.0, (10,))
    road = box(-20, -2, 20, 2)
    frames, exposure, _ = episode([actor(0, 0, heading=0), actor(0, 0.1, heading=0)])
    rows = result(frames, exposure, context(road, road, [east, west]))
    lane = metric(rows, "trajectory.lane_heading_deviation")["value"]["samples"][0]
    assert lane["lanelet_ids"] == [10]
    assert lane["successor_lanelet_ids"] == [11]
    assert lane["heading_deviation_rad"] == pytest.approx(0)


def test_low_speed_and_equal_crossing_directions_remain_undefined():
    horizontal = LaneCenterline(1, ((-10, 0), (10, 0)), 3.0, ())
    vertical = LaneCenterline(2, ((0, -10), (0, 10)), 3.0, ())
    road = box(-20, -20, 20, 20)
    frames, exposure, _ = episode([actor(0, 0, vx=0, vy=0), actor(0, 0, vx=0, vy=0)])
    rows = result(frames, exposure, context(road, road, [horizontal, vertical]))
    diagnostic = metric(rows, "trajectory.lane_lateral_offset")
    assert diagnostic["status"] == "undefined"
    assert "low_speed" in diagnostic["reason"]


def test_rigid_transform_preserves_outside_area_excursion_and_lane_offset():
    road = box(-10, -2, 10, 2)
    coverage = box(-20, -10, 20, 10)
    lane = LaneCenterline(7, ((-10, 0), (10, 0)), 4.0, ())
    frames, exposure, _ = episode([actor(0, 2.5), actor(0.1, 2.5)])
    before = result(frames, exposure, context(road, coverage, [lane]))
    angle, dx, dy = 0.73, 123.4, -51.2
    transformed_road = translate(rotate(road, angle, origin=(0, 0), use_radians=True), dx, dy)
    transformed_coverage = translate(rotate(coverage, angle, origin=(0, 0), use_radians=True), dx, dy)
    transformed_lane = LaneCenterline(
        7,
        tuple((dx + x * math.cos(angle) - y * math.sin(angle),
               dy + x * math.sin(angle) + y * math.cos(angle))
              for x, y in lane.points),
        lane.width_m,
        lane.successors,
    )
    transformed_states = []
    for state in [actor(0, 2.5), actor(0.1, 2.5)]:
        transformed_states.append(actor(
            dx + state["x"] * math.cos(angle) - state["y"] * math.sin(angle),
            dy + state["x"] * math.sin(angle) + state["y"] * math.cos(angle),
            heading=state["heading"] + angle,
            vx=state["vx"] * math.cos(angle) - state["vy"] * math.sin(angle),
            vy=state["vx"] * math.sin(angle) + state["vy"] * math.cos(angle),
        ))
    after_frames, after_exposure, _ = episode(transformed_states)
    after = result(after_frames, after_exposure,
                   context(transformed_road, transformed_coverage, [transformed_lane]))
    before_map = metric(before, "safety.map_footprint_outside")["value"]
    after_map = metric(after, "safety.map_footprint_outside")["value"]
    assert after_map["outside_area_m2"]["maximum"] == pytest.approx(
        before_map["outside_area_m2"]["maximum"])
    assert after_map["maximum_footprint_boundary_excursion_m"] == pytest.approx(
        before_map["maximum_footprint_boundary_excursion_m"])
    assert metric(after, "trajectory.lane_lateral_offset")["value"]["mean"] == pytest.approx(
        metric(before, "trajectory.lane_lateral_offset")["value"]["mean"])


def test_episode_composition_keeps_native_offroad_and_map_metrics_separate():
    from geotransfer_gap.evaluation.episode import evaluate_episode

    class Playback:
        report = {"schema_version": 3, "planner": "controller_matrix",
                  "binary_sha256": "a" * 64, "ego_binary_index": 0,
                  "ego_source_id": EGO, "requested_observation_frames": 2,
                  "terminal_reason": "horizon"}
        hashes = {"trace": "b" * 64}
        bound = False
        evaluation_capture = None
        evaluation_capture_bound = False

    saved = SimpleNamespace(
        playback=Playback(), ego_source_id=EGO,
        evidence_level=SimpleNamespace(value="trace_only_diagnostic"),
        producer_revision=None,
        frames=lambda: [
            {"step": i, "time_s": i * 0.1, "transition_applied": i == 0,
             "actors": [{**actor(0, 0), "collision_state": 0 if i == 0 else 2,
                         "reached_goal": False}]}
            for i in range(2)
        ],
    )
    result_value, _ = evaluate_episode(saved, PROFILE, map_context=MapContext(
        status="unavailable", reason="map source unavailable"))
    ids = {row["metric_id"] for row in result_value["metrics"]}
    assert "safety.native_offroad_onsets" in ids
    assert "safety.map_footprint_outside" in ids
    native = metric(result_value["metrics"], "safety.native_offroad_onsets")
    assert native["value"]["observed_onset_count"] == 1
    assert native["value"]["geometry_channel"] == "independent_from_safety.map_footprint_outside"
    assert metric(result_value["metrics"], "safety.map_footprint_outside")["status"] == "unavailable"
