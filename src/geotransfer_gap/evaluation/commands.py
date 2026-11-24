"""Lazy command handlers for offline saved-evidence evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from geotransfer_gap.config import settings


def _overlaps(left, right):
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _output_path(output, trace, profile_path, selected_scene):
    cfg = settings()
    runs = cfg.runs.resolve()
    destination = Path(output).expanduser().resolve()
    if destination == runs or not destination.is_relative_to(runs):
        raise ValueError(f"Evaluation output must be beneath configured runs: {runs}")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite evaluation output: {destination}")
    protected = (cfg.source.resolve(), cfg.artifacts.resolve(), cfg.bench.resolve(),
                 cfg.reference_data.resolve())
    for root in protected:
        if _overlaps(destination, root):
            raise ValueError(f"Evaluation output overlaps protected input root: {root}")
    input_paths = [Path(trace).expanduser().resolve(), Path(profile_path).expanduser().resolve()]
    for suffix in ("verification.json", "diagnostic.json", "attempt.json"):
        sidecar = input_paths[0].with_name(suffix)
        if sidecar.is_file():
            input_paths.append(sidecar.resolve())
    if selected_scene is not None:
        input_paths.append(selected_scene.resolve())
    for source in input_paths:
        if _overlaps(destination, source):
            raise ValueError(f"Evaluation output overlaps supplied input: {source}")
        if (source.is_file() and source.parent.is_relative_to(runs)
                and source.parent != runs and destination.is_relative_to(source.parent)):
            raise ValueError(f"Evaluation output must not be inside a saved run input directory: {source.parent}")
    # A fresh child of a saved run/campaign directory still overlaps that
    # archived evidence context even if the trace was selected elsewhere.
    ancestor = destination.parent
    while ancestor.is_relative_to(runs):
        if ancestor != runs and any((ancestor / marker).is_file() for marker in
                                    ("trace.json", "attempt.json", "verification.json",
                                     "campaign.json", "campaign_report.json", "report.json",
                                     "run.json", "manifest.json", "matrix.json", "inventory.json",
                                     "ledger.json")):
            raise ValueError(f"Evaluation output is nested in an existing run/evidence directory: {ancestor}")
        if ancestor == runs:
            break
        ancestor = ancestor.parent
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser("geotransfer evaluate")
    sub = parser.add_subparsers(dest="action", required=True)
    episode = sub.add_parser("episode", help="measure one existing saved trace")
    episode.add_argument("--trace", required=True, type=Path)
    episode.add_argument("--output", required=True, type=Path)
    episode.add_argument("--profile", type=Path)
    episode.add_argument("--scene", help="scene ID or scene root for identity checking")
    run = sub.add_parser("run", help="account for and evaluate an existing saved run or campaign")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--run", type=Path, help="existing run directory with run.json")
    source.add_argument("--campaign", type=Path, help="existing campaign directory with campaign.json")
    run.add_argument("--manifest", type=Path,
                     help="scene manifest required for legacy schema-2 runs, optional for schema 4")
    run.add_argument("--output", required=True, type=Path,
                     help="new evaluation directory beneath configured runs")
    run.add_argument("--profile", type=Path)
    report = sub.add_parser("report", help="rerender CSV and Markdown from saved evaluation results")
    report.add_argument("--evaluation", required=True, type=Path,
                        help="existing evaluation directory containing index.json")
    aggregate = sub.add_parser("aggregate", help="summarize a hash-checked saved evaluation")
    aggregate.add_argument("--evaluation", required=True, type=Path)
    aggregate.add_argument("--output", required=True, type=Path,
                            help="new output directory beneath configured runs")
    sensitivity = sub.add_parser("sensitivity", help="summarize frozen threshold variants from saved evidence")
    sensitivity.add_argument("--evaluation", required=True, type=Path)
    sensitivity.add_argument("--output", required=True, type=Path,
                             help="new output directory beneath configured runs")
    compare = sub.add_parser("compare", help="compare two hash-checked saved cohorts under a frozen source-only match")
    compare.add_argument("--left", required=True, type=Path, help="left PE09 evaluation directory")
    compare.add_argument("--right", required=True, type=Path, help="right PE09 evaluation directory")
    compare.add_argument("--config", type=Path,
                         help="frozen PE13 config (defaults to configs/evaluation/geographic_comparison.toml)")
    compare.add_argument("--output", required=True, type=Path,
                         help="new comparison directory beneath configured runs")
    args = parser.parse_args(argv)
    if args.action == "episode":
        from geotransfer_gap.evaluation.reporting import evaluate_trace

        index = evaluate_trace(trace=args.trace, scene=args.scene, output=args.output,
                               profile=args.profile)
        entry = index["episodes"][0]
        print(json.dumps({"index": str(args.output.expanduser().resolve() / "index.json"),
                          "trace_sha256": entry["trace_sha256"],
                          "evidence_level": entry["evidence_level"]}, indent=2))
        return index
    if args.action == "run":
        from geotransfer_gap.evaluation.reporting import evaluate_run

        if args.campaign is not None and args.manifest is not None:
            parser.error("--manifest applies to --run, not --campaign")
        index = evaluate_run(run=args.run, manifest=args.manifest,
                             campaign=args.campaign, output=args.output,
                             profile=args.profile)
        print(json.dumps({"index": str(args.output.resolve() / "index.json"),
                          "episodes": index["expected_episodes"],
                          "complete": index["complete"]}, indent=2))
        return index
    if args.action == "report":
        from geotransfer_gap.evaluation.reporting import render_report

        rendered = render_report(args.evaluation)
        print(json.dumps(rendered, indent=2))
        return rendered
    if args.action == "aggregate":
        from geotransfer_gap.evaluation.aggregate import aggregate_evaluation

        result = aggregate_evaluation(args.evaluation, args.output)
        print(json.dumps({"aggregate": str(result)}, indent=2))
        return result
    if args.action == "sensitivity":
        from geotransfer_gap.evaluation.aggregate import sensitivity_evaluation

        result = sensitivity_evaluation(args.evaluation, args.output)
        print(json.dumps({"sensitivity": str(result)}, indent=2))
        return result
    if args.action == "compare":
        from geotransfer_gap.evaluation.comparison import compare_saved_evaluations

        result = compare_saved_evaluations(args.left, args.right, args.output,
                                           config_path=args.config)
        summary = json.loads(result.read_text())
        print(json.dumps({"comparison": str(result), "status": summary["status"],
                          "matched_strata": summary["matching"]["matched_stratum_count"],
                          "reasons": summary["baseline_not_ready_reasons"]}, indent=2))
        return summary
    parser.error("unsupported evaluation action")
