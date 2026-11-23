"""Render real trace bundles in offline Chromium and check displayed evidence."""

import argparse
from pathlib import Path

from geotransfer_gap.artifacts import read_json, sha256, write_json
from geotransfer_gap.evaluation.reporting import read_indexed_evaluation
from geotransfer_gap.visualization.viewer import build, normalize_trace


def probe(root, traces, output, browser_path, evaluations=()):
    from playwright.sync_api import sync_playwright

    output.mkdir(parents=True, exist_ok=True)
    artifact = build(root, output / "index.html", traces, evaluations=evaluations)
    evidence = []
    attached_events, attached_results = {}, {}
    for evaluation in evaluations:
        _, _, indexed = read_indexed_evaluation(evaluation)
        for result, events in indexed.values():
            digest = result.get("evidence", {}).get("trace_sha256")
            if digest:
                attached_events.setdefault(digest, events)
                attached_results.setdefault(digest, result)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_path, headless=True,
                                             args=["--no-sandbox"])
        # The generated page is entirely offline.
        context = browser.new_context(viewport={"width": 1600, "height": 1450}, offline=True)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(artifact.resolve().as_uri(), wait_until="load")
        assert page.locator("#title").text_content() == root.name
        option_count = page.locator("#mode option").count()
        for index, trace in enumerate(traces, option_count - len(traces)):
            record = read_json(trace)
            paths = [trace.with_name(n) for n in ("verification.json", "diagnostic.json")]
            sidecar, diagnostic = (read_json(path) if path.is_file() else None for path in paths)
            expected = normalize_trace(record, sidecar, diagnostic)
            page.select_option("#mode", str(index))
            if evaluations:
                assert page.locator("#evaluation-status").inner_text().startswith("Attached episode ")
                assert "profile " in page.locator("#evaluation-status").inner_text()
                assert "metrics " in page.locator("#evaluation-outcomes").inner_text()
                events = page.locator("#evaluation-event option")
                if events.count() > 1:
                    matching = attached_events.get(sha256(trace), [])
                    assert matching, f"No probe event record for {trace}"
                    expected_event = matching[0]
                    result = attached_results[sha256(trace)]
                    assert page.locator("#evaluation-metrics tr").count() == len(
                        result.get("episode_metrics", {}).get("metrics", []))
                    full_exposure = result.get("episode_metrics", {}).get("exposure", {}).get(
                        "windows", {}).get("full", {})
                    exposure_text = page.locator("#evaluation-exposure").inner_text()
                    assert f"{full_exposure.get('transition_count')} transitions" in exposure_text
                    assert f"{full_exposure.get('controlled_transition_count')} controlled transitions" in exposure_text
                    page.select_option("#evaluation-event", "0")
                    event_step = page.locator("#time").input_value()
                    event_detail = page.locator("#evaluation-event-detail").inner_text()
                    assert "attribution" in event_detail and "cause established" in event_detail
                    assert int(event_step) == expected_event["step"]
                    if expected_event.get("time_s") is not None:
                        assert f"{expected_event['time_s']} s" in event_detail
                    if "pose absent" in event_detail:
                        assert expected_event.get("pose_present") is False
                    event_actor = expected_event.get("actor") or {}
                    if type(event_actor.get("source_id")) is int:
                        assert page.locator("#actors tr.event-actor").count() >= 1
            if option_count > 1:
                page.select_option("#baseline", str((index - 1) % option_count))
            frames = expected["frames"]
            chosen = [frames[0], frames[-1]]
            for condition in (
                lambda a: a.get("effective_owner") == "source_hold_replay",
                lambda a: a.get("actual_release_step") is not None and any("released" in e for e in a["events"]),
                lambda a: a.get("startup_status") in {"scheduled_not_released", "held_through_window"},
                lambda a: any(e in a["events"] for e in ("source gap", "re-entry", "birth / became present")),
                lambda a: bool(a.get("collision_state") or a.get("removed")),
            ):
                match = next((f for f in frames if any(condition(a) for a in f["actors"])), None)
                if match:
                    chosen.append(match)
            for frame in {f["step"]: f for f in chosen}.values():
                step = frame["step"]
                page.locator("#time").evaluate("(input, value) => {input.value = value; input.dispatchEvent(new Event('input'));}", step)
                status = page.locator("#right-status").inner_text()
                assert f"Step {step}" in status
                assert f"Terminal: {record.get('terminal_reason', 'not recorded')}" in status
                for label, value in expected["config"].items():
                    label = "Ego" if label == "ego" else label
                    assert f"{label} {value if value is not None else 'not recorded'}" in status
                displayed = page.locator("#actors tr")
                assert displayed.count() == len(frame["actors"])
                for j, actor in enumerate(frame["actors"]):
                    cells = displayed.nth(j).locator("td").all_text_contents()
                    raw_frames = record["frames"]
                    raw_frame = next(f for f in raw_frames if f["step"] == step)
                    raw = next(a for a in raw_frame.get("state", raw_frame)["actors"] if a["id"] == actor["id"])
                    assert cells[0].split(" / ")[0] == str(raw["id"])
                    assert cells[0].split(" / ")[1] == str(raw.get("binary_index", "not recorded"))
                    if record["planner"] == "controller_matrix":
                        assignment = next(a for a in raw_frame["actors"] if a["source_id"] == raw["id"])
                        assert cells[0].split(" / ")[2] == str(
                            assignment["lifetime_generation"] if assignment["lifetime_generation"] is not None else "not recorded")
                        if assignment["effective_owner"] == "source_hold_replay":
                            assert "expert replay (source hold)" in cells[1]
                        if assignment["action"] is not None:
                            assert page.locator("#actors tr").nth(j).locator("td").nth(3).evaluate(
                                "(cell) => JSON.parse(cell.textContent)") == assignment["action"]
                    assert all(event in cells[-1] for event in actor["events"])
                evidence.append({"trace": str(trace), "step": step, "status": status,
                                 "events": page.locator("#events").inner_text()})
            # Keep an inspection image per trace, prioritizing a held or released frame.
            screenshot_frame = chosen[2] if len(chosen) > 2 else chosen[-1]
            page.locator("#time").evaluate("(input, value) => {input.value = value; input.dispatchEvent(new Event('input'));}",
                                           screenshot_frame["step"])
            page.screenshot(path=output / f"trace-{index}.png", full_page=True)
        assert not errors, errors
        if not (root / "testing/validation.json").is_file():
            assert "Source trajectory comparison unavailable" in page.locator("#limitations").inner_text()
        browser.close()
    write_json(output / "browser.json", {"html": str(artifact), "steps_checked": evidence})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--trace", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, action="append", default=[])
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = parser.parse_args(argv)
    probe(args.scene, args.trace, args.output, args.chrome, args.evaluation)


if __name__ == "__main__":
    main()
