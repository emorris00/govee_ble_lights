from __future__ import annotations

import base64
import json
import logging
import re
from datetime import timedelta
from pathlib import Path

import bleak_retry_connector
from bleak import BleakClient
from homeassistant.components import bluetooth
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MODEL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_KEEP_ALIVE, DOMAIN, CommandType
from .govee_utils import prepareMultiplePacketsData, prepareSinglePacketData

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=2)
UUID_CONTROL_CHARACTERISTIC = "00010203-0405-0607-0809-0a0b0c0d2b11"
EFFECT_PARSE = re.compile("\\[(\\d+)/(\\d+)/(\\d+)(?:/(\\d+))?]")


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    ble_device = bluetooth.async_ble_device_from_address(hass, config_entry.unique_id.upper(), False)
    async_add_entities([GoveeBluetoothLight(ble_device, config_entry)])


class GoveeBluetoothLight(LightEntity):
    _attr_has_entity_name = True
    _attr_name = None

    _attr_assumed_state = True
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature(
        LightEntityFeature.EFFECT | LightEntityFeature.FLASH | LightEntityFeature.TRANSITION
    )

    def __init__(self, ble_device, config_entry: ConfigEntry) -> None:
        self._entry_id = config_entry.entry_id
        self._mac = config_entry.unique_id
        self._model = config_entry.data[CONF_MODEL]
        self._ble_device = ble_device
        self._state = None
        self._brightness = None
        self._data = json.loads(Path(Path(__file__).parent / "jsons" / (self._model + ".json")).read_text("utf-8"))

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=f"Govee {self._model}",
            manufacturer="Govee",
            model=self._model,
        )

    @property
    def effect_list(self) -> list[str] | None:
        effect_list = []
        for category_index, category in enumerate(self._data["data"]["categories"]):
            for scene_index, scene in enumerate(category["scenes"]):
                for light_effect_index, light_effect in enumerate(scene["lightEffects"]):
                    found = False
                    if light_effect["specialEffect"]:
                        for special_effect_index, special_effect in enumerate(light_effect["specialEffect"]):
                            if not special_effect["supportSku"] or self._model in special_effect["supportSku"]:
                                found = True
                                effect_list.append(
                                    "{} - {} - {} [{}/{}/{}/{}]".format(
                                        category["categoryName"],
                                        scene["sceneName"],
                                        light_effect["scenceName"],
                                        category_index,
                                        scene_index,
                                        light_effect_index,
                                        special_effect_index,
                                    )
                                )
                                break
                    if not found:
                        effect_list.append(
                            "{} - {} - {} [{}/{}/{}]".format(
                                category["categoryName"],
                                scene["sceneName"],
                                light_effect["scenceName"],
                                category_index,
                                scene_index,
                                light_effect_index,
                            )
                        )

        return effect_list

    @property
    def unique_id(self) -> str:
        return self._mac.replace(":", "")

    @property
    def brightness(self):
        return self._brightness

    @property
    def is_on(self) -> bool | None:
        return self._state

    async def async_update(self) -> None:
        if self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get(CONF_KEEP_ALIVE, False):
            await self._send_command(prepareSinglePacketData(CommandType.KEEP_ALIVE))

    async def async_turn_on(self, **kwargs) -> None:
        commands = [prepareSinglePacketData(CommandType.SET_POWER, [0x1])]

        self._state = True

        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            commands.append(prepareSinglePacketData(CommandType.SET_BRIGHTNESS, [brightness]))
            self._brightness = brightness

        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR, [0, 0, 0])
            commands.append(prepareSinglePacketData(CommandType.SET_RGB, [red, green, blue]))

        if ATTR_EFFECT in kwargs:
            effect: str | None = kwargs.get(ATTR_EFFECT, None)
            if effect is not None:
                search = EFFECT_PARSE.search(effect)

                if search is not None:
                    # Parse effect indexes
                    category_index = int(search.group(1))
                    sceneIndex = int(search.group(2))
                    lightEffectIndex = int(search.group(3))

                    category = self._data["data"]["categories"][category_index]
                    scene = category["scenes"][sceneIndex]
                    lightEffect = scene["lightEffects"][lightEffectIndex]
                    sceneCode = int(lightEffect["sceneCode"])
                    scenceParam = lightEffect["scenceParam"]

                    if search.group(4) is not None:
                        specialEffectIndex = int(search.group(4))
                        specialEffect = lightEffect["specialEffect"][specialEffectIndex]
                        scenceParam = specialEffect["scenceParam"]

                    if scenceParam:
                        for command in prepareMultiplePacketsData(base64.b64decode(scenceParam)):
                            commands.append(command)

                    commands.append(prepareSinglePacketData(CommandType.SET_SCENE, sceneCode.to_bytes(2, "little")))

        for command in commands:
            await self._send_command(command)

    async def async_turn_off(self) -> None:
        await self._send_command(prepareSinglePacketData(CommandType.SET_POWER, [0x00]))
        self._state = False

    async def _send_command(self, command):
        client = await bleak_retry_connector.establish_connection(BleakClient, self._ble_device, self.unique_id)
        _LOGGER.debug("Sending command %s", command)
        await client.write_gatt_char(UUID_CONTROL_CHARACTERISTIC, command, False)
