"""Index saved campaign results and render them through the offline viewer."""

from collections import Counter, defaultdict
from html import escape
from os.path import relpath
from pathlib import Path
from urllib.parse import quote

from geotransfer_gap.artifacts import read_json, resolve_reference
from geotransfer_gap.visualization.viewer import build


def _protocol(slot):
    return slot["ego"], slot["traffic"], slot["startup"]


def _protocol_order(pair):
    return pair[2], pair[0], pair[1]


def _check_output(path, campaign, evaluations=()):
    target = path.resolve()
    if target.is_relative_to(campaign):
        raise ValueError("Choose a viewer output outside the saved campaign")
    for evaluation in evaluations:
        if target.is_relative_to(Path(evaluation).resolve()):
            raise ValueError("Choose a viewer output outside attached evaluation evidence")


def _render_scene(scene, output, slots, evaluations=()):
    traces, campaign_status = {}, {}
    for slot in slots:
        if slot["status"] != "PASS":
            continue
        saved = slot["single"]
        files = saved["files"]
        path = Path(saved["directory"]) / files["trace"]["path"]
        if path in traces:
            raise ValueError(f"multiple campaign slots reference {path}")
        traces[path] = files
        campaign_status[path] = slot["status"]
    return build(resolve_reference(scene["root"]), output, traces, files_by_trace=traces,
                 evaluations=evaluations, campaign_status_by_trace=campaign_status)


def _write_index(output, campaign, scenes, pages):
    columns = sorted({pair for slots in scenes.values() for pair in slots}, key=_protocol_order)
    headings = "".join(f'<th scope="col">{ego.upper()} / {traffic.upper()}'
                       f'<small>{startup.replace("_", " ")}</small></th>'
                       for ego, traffic, startup in columns)
    counts = Counter(slot["status"] for slots in scenes.values() for slot in slots.values())
    totals = " · ".join(f"{counts[key]} {label}" for key, label in (
        ("PASS", "passed"), ("FAIL", "failed"), ("BLOCKED", "blocked"), ("NOT_RUN", "not run")
    ))
    rows = []
    for name, slots in sorted(scenes.items()):
        page = quote(pages[name].name) if name in pages else None
        heading = f'<a href="{page}">{escape(name)}</a>' if page else escape(name)
        cells = [f'<th scope="row">{heading}</th>']
        for pair in columns:
            slot = slots.get(pair)
            if slot is None:
                cells.append('<td>—</td>')
            elif slot["status"] == "PASS":
                anchor = quote(" / ".join(pair), safe="")
                cells.append(f'<td><a class="pass" href="{page}#pair={anchor}">Pass</a></td>')
            else:
                reason = escape(slot.get("reason") or slot.get("mismatch") or "", quote=True)
                status = escape(slot["status"].replace("_", " ").capitalize())
                cells.append(f'<td class="status" title="{reason}">{status}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    links = [
        f'<a href="{quote(relpath(campaign / file, output.parent))}">{label}</a>'
        for file, label in (("verification_matrix.json", "Verification matrix"), ("summary.md", "Campaign summary"))
        if (campaign / file).is_file()
    ]
    output.write_text(f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Saved controller campaign</title>
<style>
body{{font:15px system-ui;margin:24px;background:#f3f6fa;color:#1d2937}} a{{color:#174a78}}
.grid{{overflow:auto;max-height:78vh;border:1px solid #ccd7e4}}
table{{background:white;border-spacing:0;text-align:center;font-size:13px}}
th,td{{padding:8px;border-bottom:1px solid #ccd7e4}}
thead th{{position:sticky;top:0;background:#e8eff7;z-index:1;min-width:75px}}
tbody th,thead th:first-child{{position:sticky;left:0;background:#e8eff7;text-align:left;white-space:nowrap}}
thead th:first-child{{z-index:3}} small{{display:block;font-weight:normal}}
.pass{{display:block;background:#e5f4eb;color:#183d2b;padding:5px;border-radius:4px}}
.status{{color:#6e4212;background:#fcf1dc}}
</style>
<h1>Saved controller campaign</h1>
<p>{totals}</p>
<p>Select a passing configuration to open its playback. Use the two menus for same-scene comparison.</p>
<p>{' · '.join(links)}</p>
<div class="grid" role="region" aria-label="Scene and protocol outcomes" tabindex="0">
<table><thead><tr><th scope="col">Scene</th>{headings}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></html>
""")


def render_campaign(campaign, output, *, scene=None, ego=None, traffic=None, startup=None,
                    evaluations=()):
    """Render accepted single-pass traces and link the persisted campaign report."""
    campaign, output = Path(campaign).resolve(), Path(output).resolve()
    evaluations = tuple(Path(path).expanduser().resolve() for path in evaluations)
    _check_output(output, campaign, evaluations)
    inventory = read_json(campaign / "campaign.json")["inventory"]["scenes"]
    inventory = {row["name"]: row for row in inventory}
    scenes = defaultdict(dict)
    filters = ego, traffic, startup
    for slot in read_json(campaign / "verification_matrix.json")["slots"]:
        name = slot["scene"]
        pair = _protocol(slot)
        if ((scene is not None and name != scene)
                or any(value is not None and value != actual for value, actual in zip(filters, pair, strict=True))):
            continue
        if name not in inventory or Path(name).name != name or name in {".", ".."} or not name:
            raise ValueError(f"Unknown or invalid campaign scene {name!r}")
        if pair in scenes[name]:
            raise ValueError(f"Duplicate campaign slot for {name} {pair}")
        scenes[name][pair] = slot
    if not scenes:
        raise ValueError("No saved campaign slots match that selection")

    if scene is not None:
        slots = scenes[scene].values()
        if not any(slot["status"] == "PASS" for slot in slots):
            reasons = sorted({slot.get("reason") or slot["status"] for slot in slots})
            raise ValueError(f"No passing playback for {scene}. " + "; ".join(reasons))
        path = output if output.suffix == ".html" else output / f"{scene}.html"
        _check_output(path, campaign, evaluations)
        return _render_scene(inventory[scene], path, slots, evaluations)

    if output.suffix == ".html":
        raise ValueError("Choose an output directory for the campaign gallery")
    pages = {name: output / f"{name}.html" for name, slots in sorted(scenes.items())
             if any(slot["status"] == "PASS" for slot in slots.values())}
    index = output / "index.html"
    for path in (index, *pages.values()):
        _check_output(path, campaign, evaluations)
    output.mkdir(parents=True, exist_ok=True)
    for name, path in pages.items():
        _render_scene(inventory[name], path, scenes[name].values(), evaluations)
    _write_index(index, campaign, scenes, pages)
    return index
