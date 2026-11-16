"""Check supported polyline geometry preservation and tokenizer visibility in both domains."""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE = PROJECT_ROOT
sys.path.insert(0, str(settings().bench))
from pufferlib.prediction.binary_reader import read_binary_scenario
from pufferlib.prediction.map_tokenizer import (
    tokenize_roads as upstream,
    load_map_codebook,
)
from geotransfer_gap.planners import faithful_map


def main():
    codebook = load_map_codebook()
    results = []
    names = [
        "pilot/oriented_v3/r01_e280_f18833",
        "pilot/oriented_v3/r07_e200_f25439",
        "pilot/oriented_v3/r12_e151_f12041",
        "pilot/oriented_v3/r20_e416_f26946",
        "pilot/oriented_v3/r32_e391_f21356",
        "pilot/probes/us_hybrid_1002fdc9826fc6d1",
        "pilot/probes/us_smart_negative_world_739e0513c6f7cfe8",
    ]
    for name in names:
        path = project_path(name) / "testing/map_000000.bin"
        scene = read_binary_scenario(str(path))
        old_missing = []
        new_missing = []
        intrinsic_short = []
        maximum = 0.0
        count = 0
        crosswalks = 0
        for road in scene["roads"]:
            if road["type"] not in (4, 5, 6, 8):
                continue
            if road["type"] == 8:
                crosswalks += 1
            count += 1
            original = np.column_stack((road["polyline_x"], road["polyline_y"])).astype(
                float
            )
            saved = original.copy()
            prepared = faithful_map.prepare_roads([road])[0]
            dense = np.column_stack((prepared["polyline_x"], prepared["polyline_y"]))
            assert np.array_equal(
                saved, np.column_stack((road["polyline_x"], road["polyline_y"]))
            )
            assert all((any((np.array_equal(v, p) for p in dense)) for v in original))
            assert (
                np.linalg.norm(np.diff(dense, axis=0), axis=1).max(initial=0)
                <= 2.0 + 1e-09
            )
            vectors = np.diff(original, axis=0)
            sizes = np.maximum((vectors * vectors).sum(1), 1e-15)
            length = float(np.linalg.norm(vectors, axis=1).sum())
            if len(original) < 2:
                intrinsic_short.append(
                    {"id": road["id"], "type": road["type"], "length_m": 0.0}
                )
                continue
            fractions = np.clip(
                (
                    (dense[:, None, :] - original[None, :-1, :]) * vectors[None, :, :]
                ).sum(2)
                / sizes,
                0,
                1,
            )
            distances = np.linalg.norm(
                original[None, :-1, :]
                + fractions[:, :, None] * vectors[None, :, :]
                - dense[:, None, :],
                axis=2,
            )
            error = float(distances.min(1).max())
            maximum = max(maximum, error)
            assert error < 1e-08
            before = upstream([road], codebook)["pt_token"]["type"]
            after = faithful_map.tokenize_roads([road], codebook)["pt_token"]["type"]
            dropped_before = not len(before) or not all(
                (int(t) == road["type"] for t in before)
            )
            dropped_after = not len(after) or not all(
                (int(t) == road["type"] for t in after)
            )
            if length <= 0.5 + 1e-08:
                if dropped_after:
                    intrinsic_short.append(
                        {"id": road["id"], "type": road["type"], "length_m": length}
                    )
            else:
                if dropped_before:
                    old_missing.append({"id": road["id"], "type": road["type"]})
                if dropped_after:
                    new_missing.append({"id": road["id"], "type": road["type"]})
        results.append(
            {
                "binary": str(path),
                "binary_sha256": sha(path),
                "polylines": count,
                "crosswalks": crosswalks,
                "previously_dropped_representable_polylines": old_missing,
                "missing_after_preprocessing": new_missing,
                "intrinsic_resolution_omissions": intrinsic_short,
                "maximum_polyline_geometry_error_m": maximum,
                "passed": not new_missing,
            }
        )
    result = {
        "map_preprocessor_sha256": sha(Path(faithful_map.__file__)),
        "probe_sha256": sha(Path(__file__)),
        "maps": results,
        "passed": all((r["passed"] for r in results)),
        "scope": "Consecutive-edge densification preserves supplied polyline geometry and vertices; no closing edge/new semantic class is added. Same processing in both domains; <=0.5m standalone segments are an explicit native tokenizer resolution limit.",
    }
    project_path("pilot/audits/faithful_map_regressions.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "maps": len(results),
                "crosswalks": sum((r["crosswalks"] for r in results)),
                "polylines": sum((r["polylines"] for r in results)),
                "restored": sum(
                    (
                        len(r["previously_dropped_representable_polylines"])
                        for r in results
                    )
                ),
                "intrinsic_short": sum(
                    (len(r["intrinsic_resolution_omissions"]) for r in results)
                ),
                "passed": result["passed"],
            }
        )
    )
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
