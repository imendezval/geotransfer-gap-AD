"""Geometry-preserving sampling of supported map polylines before the unchanged SMART tokenizer.

Sparse polyline edges above10m are otherwise treated as missing-data gaps by the
upstream polyline splitter. Densify explicit consecutive edges in both US and German
inputs; retain the original endpoints/order and never invent a closing edge.
"""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import math
import numpy as np
from pufferlib.prediction.map_tokenizer import tokenize_roads as native_tokenize_roads

PROTOCOL_VERSION = "encoded_polyline_edge_sampling_max2m_v2"


def prepare_roads(roads):
    result = []
    for road in roads:
        if road.get("type", 4) not in (4, 5, 6, 8):
            result.append(road)
            continue
        points = np.column_stack((road["polyline_x"], road["polyline_y"])).astype(float)
        if len(points) < 2:
            result.append(road)
            continue
        dense = [points[0]]
        for a, b in zip(points, points[1:]):
            count = max(1, math.ceil(float(np.linalg.norm(b - a)) / 2.0))
            dense.extend((a + (b - a) * (i / count) for i in range(1, count)))
            dense.append(b)
        dense = np.asarray(dense)
        copy = dict(road)
        copy["polyline_x"] = dense[:, 0]
        copy["polyline_y"] = dense[:, 1]
        if "polyline_z" in road and len(road["polyline_z"]) == len(points):
            z = np.asarray(road["polyline_z"], dtype=float)
            zdense = [z[0]]
            for i, (a, b) in enumerate(zip(points, points[1:])):
                count = max(1, math.ceil(float(np.linalg.norm(b - a)) / 2.0))
                zdense.extend(
                    (z[i] + (z[i + 1] - z[i]) * (j / count) for j in range(1, count))
                )
                zdense.append(z[i + 1])
            copy["polyline_z"] = np.asarray(zdense)
        result.append(copy)
    return result


def tokenize_roads(roads, codebook):
    return native_tokenize_roads(prepare_roads(roads), codebook)
