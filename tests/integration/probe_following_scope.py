"""Source regressions for same-route heuristic resolution, not admission."""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import hashlib
import json
from pathlib import Path
from geotransfer_gap.maps.audit_following_scope import audit

HERE = PROJECT_ROOT


def main():
    cases = []
    for name, actor, expected, reason in [
        (
            "r01_e301_f20017",
            300,
            True,
            "Preceding vehicle turns ahead on the same approach; relative headings are compared at different route positions.",
        ),
        ("r12_e151_f12041", 141, True, "Straight same-lane preceding vehicle."),
        (
            "r01_e288_f19671",
            298,
            False,
            "Genuine oncoming movement lacks shared directed source ancestry.",
        ),
        (
            "r00_e366_f23240",
            365,
            False,
            "An adjacent/other-lane vehicle must not receive the same-route certificate.",
        ),
    ]:
        report = audit(project_path("pilot/oriented_v3") / name, [actor])
        actual = report["actors"][0]["same_route_following"]
        cases.append(
            {
                "scene": name,
                "actor_id": actor,
                "expected": expected,
                "passed": actual == expected,
                "reason": reason,
                "source_proof": report,
            }
        )
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result = {
        "audit_sha256": sha(project_path("audit_following_scope.py")),
        "probe_sha256": sha(Path(__file__)),
        "cases": cases,
        "passed": all((c["passed"] for c in cases)),
    }
    project_path("pilot/audits/source_following_scope_regressions.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps({"passed": result["passed"], "cases": len(cases)}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
