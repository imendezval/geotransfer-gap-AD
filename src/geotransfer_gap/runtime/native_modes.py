"""Python names for the pinned Drive native movement-mode enum."""

from enum import IntEnum


class NativeMovementMode(IntEnum):
    DYNAMICS = 0
    IDM = 1
    EXPERT_REPLAY = 2
