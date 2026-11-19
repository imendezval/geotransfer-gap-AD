"""Expert replay controller adapter with no native or environment side effects."""

from dataclasses import dataclass
from types import MappingProxyType

from geotransfer_gap.runtime.actor_index import ActorKey

from .controller_api import ControllerRole, ReplayIntent


@dataclass(frozen=True)
class ExpertController:
    role: ControllerRole
    name: str = "expert"

    def reset(self, episode_info):
        return None

    def observe(self, snapshot, visible_targets: frozenset[ActorKey]):
        return None

    def act(self, snapshot, eligible_targets: frozenset[ActorKey]):
        return MappingProxyType(
            {target: ReplayIntent() for target in eligible_targets}
        )

    def retire(self, actor: ActorKey, reason: str):
        return None
