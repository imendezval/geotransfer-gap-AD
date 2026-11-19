"""Side-effect-free controller inputs, outputs and role contract."""

from dataclasses import dataclass
import math
from typing import Literal, Mapping, Protocol, runtime_checkable

from geotransfer_gap.runtime.actor_index import ActorKey


ControllerRole = Literal["ego", "traffic"]
ControllerName = Literal["expert", "idm", "ppo", "smart"]


@dataclass(frozen=True)
class ReplayIntent:
    """Ask the scheduler to advance this actor with native expert replay."""

    kind: Literal["replay"] = "replay"


@dataclass(frozen=True)
class IDMParameters:
    """Episode-global IDM dynamics parameters supported by the local binding."""

    min_gap: float = 1.0
    headway_time: float = 1.5
    accel_max: float = 1.0
    decel_max: float = 2.0

    def __post_init__(self):
        values = (self.min_gap, self.headway_time, self.accel_max, self.decel_max)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("IDM parameters must be finite")
        if self.min_gap < 0 or self.headway_time < 0:
            raise ValueError("IDM min_gap and headway_time must be nonnegative")
        if self.accel_max <= 0 or self.decel_max <= 0:
            raise ValueError("IDM accel_max and decel_max must be positive")


@dataclass(frozen=True)
class IDMIntent:
    """Ask the scheduler to set per-actor target speed and native IDM mode."""

    target_velocity: float = 15.0
    parameters: IDMParameters = IDMParameters()
    kind: Literal["idm"] = "idm"

    def __post_init__(self):
        if not math.isfinite(self.target_velocity) or self.target_velocity < 0:
            raise ValueError("IDM target_velocity must be finite and nonnegative")


@dataclass(frozen=True)
class DynamicsIntent:
    """Normalized continuous action; the scheduler owns native slot writes."""

    action: tuple[float, float]
    kind: Literal["dynamics"] = "dynamics"

    def __post_init__(self):
        try:
            action = tuple(float(value) for value in self.action)
        except (TypeError, ValueError) as exc:
            raise ValueError("dynamics action must contain two numeric values") from exc
        if len(action) != 2 or not all(math.isfinite(value) for value in action):
            raise ValueError("dynamics action must contain two finite values")
        if any(value < -1.0 or value > 1.0 for value in action):
            raise ValueError("normalized dynamics action must be within [-1, 1]")
        object.__setattr__(self, "action", action)


ActionIntent = ReplayIntent | IDMIntent | DynamicsIntent


@runtime_checkable
class Controller(Protocol):
    """A role adapter that reads snapshots and returns intents without side effects."""

    role: ControllerRole
    name: ControllerName

    def reset(self, episode_info: Mapping[str, object]) -> None: ...

    def observe(
        self,
        snapshot,
        visible_targets: frozenset[ActorKey],
    ) -> None: ...

    def act(
        self,
        snapshot,
        eligible_targets: frozenset[ActorKey],
    ) -> Mapping[ActorKey, ActionIntent]: ...

    def retire(self, actor: ActorKey, reason: str) -> None: ...
