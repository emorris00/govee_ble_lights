from dataclasses import dataclass
from enum import StrEnum, auto


class Mode(StrEnum):
    MUSIC = auto()
    MANUAL = auto()
    SCENE = auto()
    DIY = auto()


@dataclass
class SegmentState:
    on: bool = False
    brightness: int = 0
    color: tuple[int, int, int] = (0, 0, 0)
    temp: int | None = None


@dataclass
class DeviceState(SegmentState):
    mode: Mode | None = None
    effect: str | None = None
