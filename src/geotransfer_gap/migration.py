"""Explicit, checksum-bound migration evidence. Never manufactures semantic reviews."""

from functools import lru_cache
import argparse
import contextlib
import io
import json
from pathlib import Path
import tarfile
from .artifacts import read_json, write_json, sha256, scenes
from .config import settings

BASELINE = "migration/legacy_reports.json"


def baseline_scenes():
    recipes = read_json(settings().project / "configs/scenes.json")["scenes"]
    return [
        {
            "name": r["scene_id"],
            "root": str(settings().artifacts / "oriented_v3" / r["scene_id"]),
            "binary_sha256": r["binary_sha256"],
        }
        for r in recipes
    ]


@lru_cache(maxsize=1)
def snapshot():
    """Read original evidence from the verified archive, including regression fixtures."""
    out = settings().artifacts / BASELINE
    if out.exists():
        return read_json(out)
    names = {r["name"] for r in baseline_scenes()} | {
        "r00_e365_f22735",
        "r31_e312_f20353",
        "r20_e416_f26946",
    }
    records = {}
    with tarfile.open(settings().project / "archive/legacy-v1.tar.gz") as archive:
        for member in archive:
            if (
                member.isfile()
                and member.name.startswith(
                    (
                        "pilot/oriented_v3/",
                        "pilot/probes/us_",
                        "pilot/validated/faithful_intersection04/",
                    )
                )
                and member.name.endswith(".json")
            ):
                if (
                    member.name.startswith("pilot/oriented_v3/")
                    and member.name.split("/")[2] not in names
                ):
                    continue
                try:
                    records[member.name] = json.load(archive.extractfile(member))
                except (ValueError, UnicodeDecodeError):
                    continue
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, allow_nan=True))
    return records


def original(root, name):
    key = (
        "pilot/"
        + Path(root).relative_to(settings().artifacts).as_posix()
        + "/testing/"
        + name
    )
    return snapshot()[key]


PROVENANCE = {
    "schema_version",
    "scope_tool_sha256",
    "lane_change_tool_sha256",
    "audit_sha256",
    "probe_sha256",
    "converter_sha256",
    "map_audit_sha256",
    "rule_audit_sha256",
    "idm_trace_sha256",
    "following_scope_sha256",
    "task_rule_scope_sha256",
    "source_route_sequence_sha256",
    "directed_rule_scope_sha256",
    "scene_root",
    "root",
    "runtime_binary",
    "path",
    "reference",
    "scene_reference",
}


def semantic_projection(value):
    if isinstance(value, dict):
        return {
            k: semantic_projection(v) for k, v in value.items() if k not in PROVENANCE
        }
    if isinstance(value, list):
        return [semantic_projection(v) for v in value]
    return value


def compare(root, name):
    before = original(root, name)
    after = read_json(Path(root) / "testing" / name)
    if semantic_projection(before) != semantic_projection(after):
        keys = sorted(set(before) | set(after))
        changed = [
            k
            for k in keys
            if k not in PROVENANCE
            and semantic_projection(before.get(k)) != semantic_projection(after.get(k))
        ]
        raise ValueError(
            f"Substantive evidence changed: {Path(root).name}/{name}: {changed}"
        )
    return {"artifact": name, "semantic_equal": True}


def carry_review(root):
    """Rebind existing reviewed certificates only after exact substantive equivalence."""
    root = Path(root).resolve()
    t = root / "testing"
    name = "semantic_review_smart_hybrid_startup.json"
    old = original(root, name)
    checks = []
    for name in [
        "rule_applicability_audit.json",
        "map_audit.json",
        "physical_source_audit.json",
        "interaction_fidelity_audit_hybrid_startup.json",
    ]:
        checks.append(compare(root, name))
    if (
        sha256(t / "map_000000.bin") != old["binary_sha256"]
        or sha256(t / old["source_image"]) != old["source_image_sha256"]
    ):
        raise ValueError("Reviewed binary/image changed")
    review = dict(old)
    certificates = {
        "following_scope_sha256": "source_following_scope.json",
        "task_rule_scope_sha256": "source_task_rule_scope.json",
        "directed_rule_scope_sha256": "source_directed_rule_scope.json",
        "source_route_sequence_sha256": "source_route_sequence.json",
    }
    for field, file in certificates.items():
        if field in old:
            checks.append(compare(root, file))
            review[field] = sha256(t / file)
    if sha256(t / "rule_applicability_audit.json") != old["rule_audit_sha256"]:
        raise ValueError("Reviewed rule audit changed")
    if (
        read_json(t / "interaction_fidelity_audit_hybrid_startup.json")[
            "source_evidence_digest"
        ]
        != old["interaction_source_digest"]
    ):
        raise ValueError("Reviewed source interaction changed")
    name = "semantic_review_smart_hybrid_startup.json"
    write_json(t / name, review)
    proof = {
        "schema_version": 2,
        "status": "existing_review_carried_by_equivalence",
        "scene": root.name,
        "original_review": original(root, name),
        "original_archive_sha256": sha256(
            settings().project / "archive/legacy-v1.sha256.json"
        ),
        "review_sha256": sha256(t / name),
        "checks": checks,
        "scope": "Preserves the original review conclusions and wording. Only certificate provenance is rebound; no new review decision.",
    }
    write_json(t / "migration_review_equivalence.json", proof)
    return proof


def conversion_check():
    from .conversion.pipeline import ConversionConfig, Converter
    import tempfile

    results = []
    with tempfile.TemporaryDirectory(prefix="geo_conversion_", dir="/tmp") as folder:
        for row in baseline_scenes():
            t = Path(row["root"]) / "testing"
            v = read_json(t / "validation.json")
            out = Path(folder) / row["name"]
            cfg = ConversionConfig(
                recording=v["recording"],
                ego=v["ego_track"],
                first_frame=v["first_frame"],
                goal_sample=v["ego_goal_sample"],
                edge_mode=v["edge_mode"],
                late_mode=v["late_mode"],
                static_crop_radius=v["static_crop_radius_m"],
                exclude_track_ids=tuple(v["explicit_excluded_track_ids"]),
                parked_as_static_expert=True,
                background_goal_mode=v["background_goal_mode"],
                background_goal_min_distance=v["background_goal_min_distance_m"],
                emit_crosswalks=True,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                Converter(cfg, out).run()
            checks = {
                n: (t / n).read_bytes() == (out / "testing" / n).read_bytes()
                for n in [
                    "map_000000.bin",
                    "manifest.csv",
                    next(t.glob("ind_*.json")).name,
                ]
            }
            if not all(checks.values()):
                raise ValueError("Conversion mismatch: " + row["name"])
            results.append({"scene": row["name"], "checks": checks})
    result = {"passed": True, "scenes": results}
    write_json(
        settings().artifacts / "audits/migration_conversion_equivalence.json", result
    )
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("action", choices=["snapshot", "conversion", "execution", "review"])
    ap.add_argument("--root", type=Path)
    args = ap.parse_args(argv)
    if args.action == "snapshot":
        print("Original reports preserved:", len(snapshot()))
    elif args.action == "conversion":
        print("Byte-identical conversions:", len(conversion_check()["scenes"]))
    elif args.action == "execution":
        print("Exact old/new execution matches:", len(execution_check()["scenes"]))
    else:
        if not args.root:
            ap.error("--root required")
        print(json.dumps(carry_review(args.root), indent=2))


def legacy_checkout():
    """Restore verified reference code in /tmp, with external dependencies linked."""
    import hashlib

    base = settings().cache / (
        "geotransfer-reference-"
        + sha256(settings().project / "archive/legacy-v1.sha256.json")[:12]
    )
    root = base / "geotransfer-AD-gap"
    if not (root / "probe_faithful_smart_closed_loop.py").exists():
        root.mkdir(parents=True, exist_ok=True)
        expected = read_json(settings().project / "archive/legacy-v1.sha256.json")
        with tarfile.open(settings().project / "archive/legacy-v1.tar.gz") as archive:
            for member in archive:
                if (
                    member.isfile()
                    and "/" not in member.name
                    and member.name.endswith(".py")
                ):
                    content = archive.extractfile(member).read()
                    if hashlib.sha256(content).hexdigest() != expected[member.name]:
                        raise ValueError("Corrupt archived source")
                    (root / member.name).write_bytes(content)
    for name, target in [
        ("behavior-bench", settings().bench),
        ("data", settings().project.parent / "data"),
    ]:
        path = base / name
        if not path.exists():
            path.symlink_to(target, target_is_directory=True)
    resources = root / "resources"
    if not resources.exists():
        resources.symlink_to(
            settings().bench / "pufferlib/resources", target_is_directory=True
        )
    return root


def execution_check():
    import concurrent.futures
    import shutil
    import subprocess
    import sys
    import tempfile

    legacy_checkout()
    destination = settings().artifacts / "migration/captures"
    destination.mkdir(parents=True, exist_ok=True)
    capture = settings().project / "tests/integration/migration_capture.py"

    def one(row):
        with tempfile.TemporaryDirectory(
            prefix="geo_equivalence_", dir="/tmp"
        ) as folder:
            root = Path(folder) / row["name"]
            t = root / "testing"
            t.mkdir(parents=True)
            source = Path(row["root"]) / "testing"
            for pattern in ["map_000000.bin", "manifest.csv", "ind_*.json"]:
                for path in source.glob(pattern):
                    shutil.copy2(path, t / path.name)
            outputs = {}
            for version in ["old", "new"]:
                out = destination / (row["name"] + "_" + version + ".json")
                with out.with_suffix(".log").open("w") as log:
                    subprocess.run(
                        [
                            sys.executable,
                            str(capture),
                            "--implementation",
                            version,
                            "--root",
                            str(root),
                            "--output",
                            str(out),
                        ],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
                outputs[version] = read_json(out)
            checks = {k: outputs["old"][k] == outputs["new"][k] for k in outputs["old"]}
            if not all(checks.values()):
                raise ValueError(
                    "Execution changed: " + row["name"] + ": " + str(checks)
                )
            return {
                "scene": row["name"],
                "checks": checks,
                "old_sha256": sha256(destination / (row["name"] + "_old.json")),
                "new_sha256": sha256(destination / (row["name"] + "_new.json")),
                "prediction_refreshes": len(outputs["new"]["model_input_sha256"]),
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(one, baseline_scenes()))
    report = {
        "passed": True,
        "scenes": results,
        "scope": "Exact inference tensor hashes, actions, actor identity and meaningful simulator-state traces. Unborn numeric storage and background goal flags are undefined in native state and normalized, never used as evidence.",
    }
    write_json(
        settings().artifacts / "audits/migration_execution_equivalence.json", report
    )
    return report
