"""Render offline galleries from saved campaign and evaluation records."""

from collections import Counter, defaultdict
from html import escape
import json
from os.path import relpath
from pathlib import Path
from urllib.parse import quote

from geotransfer_gap.artifacts import atomic_write_text, read_json, resolve_reference, sha256
from geotransfer_gap.config import settings
from geotransfer_gap.visualization.viewer import (
    _check_output, _evaluated_run, _indexed_attachments, _page_path,
    _scene_payload, _write_playback, build,
)


def _protocol(slot):
    return slot["ego"], slot["traffic"], slot["startup"]


def _protocol_order(pair):
    return pair[2], pair[0], pair[1]


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
    headings = '<th scope="col">Scene</th>' + "".join(
        f'<th scope="col">{escape(ego.upper())} / {escape(traffic.upper())}'
        f'<small>{escape(startup.replace("_", " "))}</small></th>'
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
    intro = (f"<p>{totals}</p>"
             "<p>Select a passing configuration to open its playback. Use the two menus for same-scene comparison.</p>"
             f"<p>{' · '.join(links)}</p>")
    _write_gallery(output, "Saved controller campaign", intro, headings, rows)


def _write_gallery(output, title, intro, headings, rows):
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output, f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
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
<h1>{title}</h1>
{intro}
<div class="grid" role="region" aria-label="Episode and protocol outcomes" tabindex="0">
<table><thead><tr>{headings}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></html>
""")


def render_campaign(campaign, output, *, scene=None, ego=None, traffic=None, startup=None,
                    evaluations=()):
    """Render accepted single-pass traces and link the persisted campaign report."""
    campaign, output = Path(campaign).resolve(), Path(output).resolve()
    evaluations = tuple(Path(path).expanduser().resolve() for path in evaluations)
    _check_output(output, campaign=campaign, evaluations=evaluations)
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
        _check_output(path, campaign=campaign, evaluations=evaluations,
                      directory=None if path == output else output)
        return _render_scene(inventory[scene], path, slots, evaluations)

    if output.suffix == ".html":
        raise ValueError("Choose an output directory for the campaign gallery")
    pages = {name: _page_path(output, name) for name, slots in sorted(scenes.items())
             if any(slot["status"] == "PASS" for slot in slots.values())}
    index = output / "index.html"
    if index in pages.values():
        raise ValueError("Campaign scene page collides with the gallery index")
    for path in (index, *pages.values()):
        _check_output(path, campaign=campaign, evaluations=evaluations, directory=output)
    output.mkdir(parents=True, exist_ok=True)
    for name, path in pages.items():
        _render_scene(inventory[name], path, scenes[name].values(), evaluations)
    _write_index(index, campaign, scenes, pages)
    return index


def _evaluation_gallery_rows(entries, pages):
    def cell(value):
        return escape(str(value)) if value is not None else "Not recorded"

    for entry in entries:
        result = entry["result"]
        scene = entry.get("scene")
        episode = result["episode_id"]
        protocol = " / ".join(cell(result["protocol"].get(role)) for role in ("ego", "traffic", "startup"))
        if scene in pages:
            path = quote(pages[scene].name, safe="")
            fragment = quote(episode, safe="")
            playback = f'<a href="{path}#episode={fragment}">Playback</a>'
        else:
            playback = cell(entry["status"])
        yield (f'<tr><th scope="row">{cell(episode)}</th><td>{cell(result.get("scene_id"))}</td>'
               f'<td>{protocol}</td><td>{cell(result["accounting"].get("execution_status"))}</td>'
               f'<td>{cell(result["accounting"].get("campaign_status"))}</td>'
               f'<td>{cell(result["evidence"].get("status"))} / {cell(result["evidence"].get("level"))}</td>'
               f'<td>{cell((result.get("metric_validity") or {}).get("status"))}</td>'
               f'<td>{cell((result.get("driving_outcome") or {}).get("outcome"))}</td><td>{playback}</td></tr>')


def _detached_bindings(evaluation, index):
    """Recover filenames of campaign-bound evidence without consulting current inventory."""
    from geotransfer_gap.evaluation.reporting import _evaluation_snapshot_bytes

    snapshot = json.loads(_evaluation_snapshot_bytes(evaluation, index))
    bindings = defaultdict(dict)
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("files"), list):
        raise ValueError("Saved evaluation input snapshot is malformed")
    for row in snapshot["files"]:
        if not isinstance(row, dict):
            raise ValueError("Saved evaluation input snapshot file entry is malformed")
        role, path = row.get("role"), row.get("path")
        if path and isinstance(role, str) and role.startswith("bound_evidence_"):
            path = Path(path)
            bindings[path.parent][role.removeprefix("bound_evidence_")] = {
                "path": path.name, "sha256": row.get("expected_sha256"),
            }
    return bindings


def render_evaluation(evaluation, output=None):
    """Render playback and account for every row in an existing indexed evaluation."""
    from geotransfer_gap.evaluation.reporting import _slug, read_indexed_evaluation

    evaluation, index, indexed = read_indexed_evaluation(evaluation)
    output = (Path(output).expanduser() if output is not None else
              settings().runs / "views/evaluations" / _slug(f"{evaluation.name}:{evaluation}"))
    selection = index.get("selection") or {}
    if not isinstance(selection, dict):
        raise ValueError("Saved evaluation selection is malformed")
    inputs = set()
    selection_root = selection.get("root")
    if selection_root is not None:
        if not isinstance(selection_root, str) or not selection_root:
            raise ValueError("Saved evaluation selection root is malformed")
        inputs.add(Path(selection_root))
    checks = {"evaluations": (evaluation,)}
    output = _check_output(output, inputs=inputs, **checks)
    if output.suffix == ".html" and len(indexed) != 1:
        raise ValueError("Choose an output directory for the multi-episode evaluation gallery")

    attachments = list(_indexed_attachments(evaluation, index, indexed))
    requires_detached_binding = selection.get("kind") == "saved_campaign" and any(
        row["result"]["evidence"].get("status") == "valid"
        and "attempt" not in ((row["result"].get("episode_metrics") or {}).get("input", {})
                              .get("evidence_sha256", {}))
        for row in attachments
    )
    detached_bindings = _detached_bindings(evaluation, index) if requires_detached_binding else {}
    entries, by_scene = [], defaultdict(list)
    for item in attachments:
        result = item["result"]
        evidence = result["evidence"]
        entry = {"result": result}
        entries.append(entry)
        if evidence.get("status") != "valid":
            entry["status"] = evidence.get("reason") or "No usable saved trace"
            if failure := result["accounting"].get("execution_failure"):
                entry["status"] += f" · {failure}"
            continue
        scene_ref = (result.get("episode_metrics") or {}).get("input", {}).get("scene")
        if not scene_ref:
            entry["status"] = "Unavailable · No scene identity was recorded for this trace"
            continue
        try:
            scene = resolve_reference(scene_ref)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            entry["status"] = f"Invalid scene identity · {exc}"
            continue
        inputs.add(scene)
        if isinstance(evidence.get("trace_path"), str) and evidence["trace_path"]:
            inputs.add(Path(evidence["trace_path"]))
        by_scene[scene].append((item, entry))

    checks["inputs"] = inputs
    _check_output(output, **checks)
    explicit_file = output.suffix == ".html"
    index_page = output if explicit_file else output / "index.html"
    gallery = _check_output(index_page, directory=None if explicit_file else output, **checks)
    targets = {}
    for scene in by_scene:
        if len(entries) == 1:
            page = output if explicit_file else _page_path(output, scene.name)
        else:
            page = _page_path(output, _slug(f"{scene.name}:{scene}"))
        targets[scene] = _check_output(page, directory=None if explicit_file else output, **checks)
    if len(set(targets.values())) != len(targets) or len(entries) > 1 and gallery in targets.values():
        raise ValueError("Evaluation gallery pages resolve to the same output path")

    pages = {}
    for scene, episodes in by_scene.items():
        runs, playback_inputs = [], set()
        binary = scene / "testing/map_000000.bin"
        try:
            digest = sha256(binary)
        except OSError:
            for _, entry in episodes:
                entry["status"] = f"Unavailable · Recorded scene binary is missing or unreadable: {binary}"
            continue
        for item, entry in episodes:
            try:
                run, files = _evaluated_run(item, scene, digest, detached_bindings)
            except FileNotFoundError as exc:
                entry["status"] = f"Unavailable · {exc}"
            except (OSError, ValueError, TypeError, KeyError) as exc:
                entry["status"] = f"Invalid playback evidence · {exc}"
            else:
                entry["scene"] = scene
                runs.append(run)
                playback_inputs.update(files)
        if not runs:
            continue
        repeated_names = Counter(run["name"] for run in runs)
        for run in runs:
            if repeated_names[run["name"]] > 1:
                run["name"] += f' ({run["evaluation"]["episode_id"]})'
        try:
            payload = _scene_payload(scene, digest, runs)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            for _, entry in episodes:
                if entry.pop("scene", None) is not None:
                    entry["status"] = f"Unavailable · Could not load recorded scene: {exc}"
            continue
        target = _check_output(targets[scene], inputs=playback_inputs)
        _write_playback(target, payload)
        pages[scene] = target
        if len(entries) == 1:
            return target
    headings = "".join(f'<th scope="col">{label}</th>' for label in (
        "Episode", "Scene", "Ego / Traffic / Startup", "Execution", "Campaign integration",
        "Saved evidence", "Metrics", "Driving outcome", "Playback",
    ))
    intro = ("<p>No episode can be rendered. Check the recorded trace and scene assets listed below.</p>"
             if not pages else "")
    _write_gallery(gallery, "Saved evaluation", intro, headings,
                   _evaluation_gallery_rows(entries, pages))
    return gallery
