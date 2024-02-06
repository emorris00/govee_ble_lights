from __future__ import annotations

import array
import logging
import re

from enum import IntEnum
import bleak_retry_connector

from bleak import BleakClient
from homeassistant.components import bluetooth
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from pathlib import Path
import json
from .govee_utils import prepareSinglePacketData, prepareMultiplePacketsData
import base64

_LOGGER = logging.getLogger(__name__)

UUID_CONTROL_CHARACTERISTIC = "00010203-0405-0607-0809-0a0b0c0d2b11"
EFFECT_PARSE = re.compile("\[(\d+)/(\d+)/(\d+)/(\d+)]")

class CommandType(IntEnum):
    KEEP_ALIVE = [0xAA]
    SET_POWER = [0x33, 0x01]
    SET_BRIGHTNESS = [0x33, 0x04]
    SET_RGB = [0x33, 0x05, 0x02]
    SET_SCENE = [0x33, 0x05, 0x04]
    SET_RGBWW_SEGMENTS = [0x33, 0x05, 0x15, 0x01]
    SET_RELATIVE_BRIGHTNESS_SEGMENTS = [0x33, 0x05, 0x15, 0x02]
    SET_RGB_SEGMENTS = [0x33, 0x05, 0x0B]

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities
):
    light = hass.data[DOMAIN][config_entry.entry_id]
    ble_device = bluetooth.async_ble_device_from_address(
        hass, light.address.upper(), False
    )
    async_add_entities([GoveeBluetoothLight(light, ble_device, config_entry)])


class GoveeBluetoothLight(LightEntity):
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature(
        LightEntityFeature.EFFECT
        | LightEntityFeature.FLASH
        | LightEntityFeature.TRANSITION
    )

    def __init__(self, light, ble_device, config_entry: ConfigEntry) -> None:
        """Initialize an bluetooth light."""
        self._mac = light.address
        self._model = config_entry.data["model"]
        self._ble_device = ble_device
        self._state = None
        self._brightness = None
        self._data = json.loads(
            Path(Path(__file__).parent / "jsons" / (self._model + ".json")).read_text()
        )

    @property
    def effect_list(self) -> list[str] | None:
        effect_list = []
        for categoryIdx, category in enumerate(self._data["data"]["categories"]):
            for sceneIdx, scene in enumerate(category["scenes"]):
                for leffectIdx, lightEffect in enumerate(scene["lightEffects"]):
                    for seffectIxd, specialEffect in enumerate(
                        lightEffect["specialEffect"]
                    ):
                        # if 'supportSku' not in specialEffect or self._model in specialEffect['supportSku']:
                        # Workaround cause we need to store some metadata in effect (effect names not unique)
                        effect_list.append(
                            "%s - %s - %s [%s/%s/%s/%s]".format(
                                category["categoryName"],
                                scene["sceneName"],
                                lightEffect["scenceName"],
                                categoryIdx,
                                sceneIdx,
                                leffectIdx,
                                seffectIxd,
                            )
                        )

        return effect_list

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "GOVEE Light"

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._mac.replace(":", "")

    @property
    def brightness(self):
        return self._brightness

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._state

    async def async_turn_on(self, **kwargs) -> None:
        commands = [prepareSinglePacketData(CommandType.SET_POWER, [0x1])]

        self._state = True

        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            commands.append(
                prepareSinglePacketData(CommandType.SET_BRIGHTNESS, [brightness])
            )
            self._brightness = brightness

        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR)
            commands.append(
                prepareSinglePacketData(
                    CommandType.SET_RGB, [red, green, blue]
                )
            )

        if ATTR_EFFECT in kwargs:
            effect = kwargs.get(ATTR_EFFECT)
            if len(effect) > 0:
                search = EFFECT_PARSE.search(effect)

                # Parse effect indexes
                categoryIndex = int(search.group(1))
                sceneIndex = int(search.group(2))
                lightEffectIndex = int(search.group(3))
                specialEffectIndex = int(search.group(4))

                category = self._data["data"]["categories"][categoryIndex]
                scene = category["scenes"][sceneIndex]
                lightEffect = scene["lightEffects"][lightEffectIndex]
                specialEffect = lightEffect["specialEffect"][specialEffectIndex]

                # Prepare packets to send big payload in separated chunks
                for command in prepareMultiplePacketsData(
                    [*base64.b64decode(specialEffect["scenceParam"])],
                ):
                    commands.append(command)
                    # I think there needs to be the actual set_scene command here?

        for command in commands:
            await self._sendCommand(command)

    async def async_turn_off(self, **kwargs) -> None:
        await self._sendCommand(prepareSinglePacketData(CommandType.SET_POWER, [0x00]))
        self._state = False

    async def _sendCommand(self, command):
        client = await bleak_retry_connector.establish_connection(
            BleakClient, self._ble_device, self.unique_id
        )
        await client.write_gatt_char(UUID_CONTROL_CHARACTERISTIC, command, False)
