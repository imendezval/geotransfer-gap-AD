"""Finite result records for offline measurements."""

from dataclasses import asdict, dataclass
from enum import StrEnum
import json

from geotransfer_gap.artifacts import write_json


class AssessmentStatus(StrEnum):
    VALID = "valid"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    UNDEFINED = "undefined"
    INVALID = "invalid"


class CriterionOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class MetricResult:
    metric_id: str
    definition_version: str
    status: AssessmentStatus
    reason: str
    value: float | int | bool | str | dict | list | None = None
    units: str | dict[str, str] | None = None
    criterion_outcome: CriterionOutcome = CriterionOutcome.NOT_ASSESSED
    interpretation: str | None = None
    eligible_samples: int | None = None
    eligible_duration_s: float | None = None
    window: str | None = None
    actors: tuple[tuple[int, int | None], ...] = ()
    evidence_refs: tuple[dict, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self):
        if (not isinstance(self.status, AssessmentStatus)
                or not isinstance(self.criterion_outcome, CriterionOutcome)):
            raise ValueError("Use an assessment status and criterion outcome")
        if not all(isinstance(text, str) and text.strip()
                   for text in (self.metric_id, self.definition_version, self.reason)):
            raise ValueError("Metric identity, definition version and reason are required")
        if self.status is not AssessmentStatus.VALID and (
                self.value is not None or self.criterion_outcome is not CriterionOutcome.NOT_ASSESSED):
            raise ValueError("Nonvalid assessments require null value and an unassessed criterion")
        if self.value is None and self.status is AssessmentStatus.VALID and not self.interpretation:
            raise ValueError("A valid result without a value requires a quantity interpretation")
        if self.eligible_samples is not None and (
                type(self.eligible_samples) is not int or self.eligible_samples < 0):
            raise ValueError("Eligible sample count must be a nonnegative integer")
        if self.eligible_duration_s is not None and (
                type(self.eligible_duration_s) not in (int, float) or self.eligible_duration_s < 0):
            raise ValueError("Eligible duration must be nonnegative")
        self.to_dict()

    def to_dict(self):
        """Return ordinary JSON types and reject nonfinite nested data."""
        return json.loads(json.dumps(asdict(self), allow_nan=False))

    def write(self, path):
        write_json(path, self.to_dict())
