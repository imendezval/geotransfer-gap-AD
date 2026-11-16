"""Render an aerial/source-map rule and traffic montage for manual review."""

from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from PIL import Image
from geotransfer_gap.validation.audit_physical_source import corners
from geotransfer_gap.maps.audit_rule_applicability import tags, polygon_of


def render(root, steps):
    testing = root / "testing"
    scene = json.loads(next(testing.glob("ind_*.json")).read_text())
    validation = json.loads((testing / "validation.json").read_text())
    audit = json.loads((testing / "rule_applicability_audit.json").read_text())
    registration = json.loads((testing / "source_image_registration.json").read_text())
    recording = validation["recording"]
    source = settings().source / "data"
    meta = next(csv.DictReader((source / f"{recording:02d}_recordingMeta.csv").open()))
    osm_path, _ = map_geometry.map_paths(meta, recording)
    osm = ET.parse(osm_path).getroot()
    nodes = map_geometry.project_nodes(
        osm, float(meta["xUtmOrigin"]), float(meta["yUtmOrigin"])
    )
    ways = {
        int(w.get("id")): [nodes[int(n.get("ref"))] for n in w.findall("nd")]
        for w in osm.findall("way")
    }
    relations = {int(r.get("id")): r for r in osm.findall("relation")}
    scale, ox, oy = (
        registration[k]
        for k in ("pixel_scale_m", "local_x_at_image_x0_m", "local_y_at_image_y0_m")
    )

    def pixel(point):
        return ((point[0] - ox) / scale, (oy - point[1]) / scale)

    rgb = Image.open(source / f"{recording:02d}_background.png").convert("RGB")
    ego = scene["objects"][0]
    ego_path = [pixel((v["x"], v["y"])) for v in ego["position"]]
    ex = [x for x, _ in ego_path]
    ey = [y for _, y in ego_path]
    xmin, xmax = (max(0, min(ex) - 150), min(rgb.width, max(ex) + 150))
    ymin, ymax = (max(0, min(ey) - 130), min(rgb.height, max(ey) + 130))
    fig, axs = plt.subplots(2, 2, figsize=(13, 10))
    crosswalks = {r["lanelet_id"] for r in audit["ego_box_crosswalk_contacts"]}
    sign_ids = {sign["id"] for sign in audit["nearby_source_signs"]}
    for ax, step in zip(axs.flat, steps):
        ax.imshow(rgb)
        for rid in crosswalks:
            poly = polygon_of(relations[rid], ways)
            if poly:
                ax.add_patch(
                    Polygon(
                        [pixel(pt) for pt in poly],
                        closed=True,
                        facecolor="yellow",
                        edgecolor="black",
                        alpha=0.42,
                    )
                )
                x, y = pixel(poly[0])
                ax.text(x, y, f"crosswalk {rid}", color="black", fontsize=8)
        for index, sign_id in enumerate(sorted(sign_ids)):
            for xy in ways.get(sign_id, []):
                x, y = pixel(xy)
                ax.plot(x, y, marker="*", color="magenta", markersize=12)
                ax.text(
                    x + 5,
                    y - 5 - 10 * index,
                    f"sign {sign_id}",
                    color="magenta",
                    fontsize=8,
                )
        ax.plot(ex, ey, color="red", linewidth=1.5, alpha=0.8)
        for obj in scene["objects"]:
            if not obj["valid"][step]:
                continue
            x, y = pixel((obj["position"][step]["x"], obj["position"][step]["y"]))
            if not (xmin - 20 <= x <= xmax + 20 and ymin - 20 <= y <= ymax + 20):
                continue
            color = (
                "red"
                if obj["id"] == ego["id"]
                else "deepskyblue" if obj["type"] == "vehicle" else "lime"
            )
            ax.add_patch(
                Polygon(
                    [pixel(pt) for pt in corners(obj, step)],
                    closed=True,
                    fill=False,
                    edgecolor=color,
                    linewidth=2,
                )
            )
            ax.text(
                x + 3,
                y - 4,
                str(obj["id"]),
                color=color,
                fontsize=8,
                bbox=dict(facecolor="black", alpha=0.4, pad=0.5),
            )
        ax.set(
            xlim=(xmin, xmax),
            ylim=(ymax, ymin),
            title=f"Source step {step} ({step / 10:.1f} s)",
        )
        ax.axis("off")
    fig.tight_layout()
    path = testing / "rule_review_montage.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--steps", type=int, nargs=4, default=(0, 35, 60, 83))
    args = ap.parse_args()
    render(args.root.resolve(), args.steps)
