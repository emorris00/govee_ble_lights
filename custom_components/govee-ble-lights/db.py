from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Optional

from .models import Mode


@dataclass(frozen=True)
class Scene:
    name: str
    code: int
    data: str | None


@dataclass(frozen=True)
class DeviceInfo:
    model: str
    modes: set[Mode]
    brightness_scale: tuple[int, int]
    temp_range: tuple[int, int] | None
    segments: list[list[int]] | None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @cached_property
    def scenes(self) -> list[Scene]:
        result = []
        effects_data = json.loads(Path(Path(__file__).parent / "jsons" / (self.model + ".json")).read_text("utf-8"))

        for category in effects_data["data"]["categories"]:
            for scene in category["scenes"]:
                for light_effect in scene["lightEffects"]:
                    name = " - ".join([category["categoryName"], scene["sceneName"], light_effect["scenceName"]])
                    code = int(light_effect["sceneCode"])
                    data: Optional[str] = light_effect["scenceParam"]

                    if special_effect := next(
                        (x for x in light_effect["specialEffect"] if self.model in x["supportSku"]), None
                    ):
                        data = special_effect["scenceParam"]

                    result.append(Scene(name=name, code=code, data=data))
        return result

    @cached_property
    def segment_byte_length(self):
        if not self.segments:
            return 0
        return (max(itertools.chain(*self.segments)).bit_length() + 7) // 8


def get_device_info(model: str):
    match model:
        case "H6053":
            return DeviceInfo(
                model=model,
                modes={Mode.MANUAL, Mode.SCENE},
                brightness_scale=(1, 100),
                temp_range=(5000, 9000),
                segments=[
                    [1, 2, 3, 4, 5, 6],
                    [7, 8, 9, 10, 11, 12],
                ],
                effects={},
            )

        case _:
            return DeviceInfo(
                modes={Mode.MANUAL, Mode.SCENE},
                effects=[],
                brightness_scale=(1, 255),
                temp_range=None,
                segments=None,
            )
