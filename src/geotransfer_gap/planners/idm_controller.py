"""Native IDM intent adapter; the scheduler is the only native writer."""

from dataclasses import dataclass, field
from types import MappingProxyType

from geotransfer_gap.runtime.actor_index import ActorKey

from .controller_api import ControllerRole, IDMIntent, IDMParameters


@dataclass(frozen=True)
class IDMController:
    role: ControllerRole
    target_velocity: float = 15.0
    parameters: IDMParameters = field(default_factory=IDMParameters)
    name: str = "idm"

    def __post_init__(self):
        # Validate once at adapter construction; the C binding receives only
        # finite per-actor target speeds and the immutable episode parameters.
        IDMIntent(self.target_velocity, self.parameters)

    def reset(self, episode_info):
        return None

    def observe(self, snapshot, visible_targets: frozenset[ActorKey]):
        return None

    def act(self, snapshot, eligible_targets: frozenset[ActorKey]):
        intent = IDMIntent(self.target_velocity, self.parameters)
        return MappingProxyType({target: intent for target in eligible_targets})

    def retire(self, actor: ActorKey, reason: str):
        return None
