from __future__ import annotations

import itertools
from dataclasses import dataclass
from functools import cached_property

from .models import Mode


@dataclass(frozen=True)
class DeviceInfo:
    modes: set[Mode]
    effects: list
    brightness_scale: tuple[int, int]
    temp_range: tuple[int, int] | None
    segments: list[list[int]] | None

    @cached_property
    def segment_byte_length(self):
        return (max(itertools.chain(*self.segments)).bit_length() + 7) // 8


def get_device_info(model: str):
    match model:
        case "H6053":
            return DeviceInfo(
                modes={Mode.MANUAL, Mode.SCENE},
                effects=[],
                brightness_scale=(1, 100),
                temp_range=(5000, 9000),
                segments=[
                    [1, 2, 3, 4, 5, 6],
                    [7, 8, 9, 10, 11, 12],
                ],
            )

        case _:
            return DeviceInfo(
                modes={Mode.MANUAL, Mode.SCENE},
                effects=[],
                brightness_scale=(1, 255),
                temp_range=None,
                segments=None,
            )
