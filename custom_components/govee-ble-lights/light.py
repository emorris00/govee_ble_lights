from __future__ import annotations

import json
import logging
import re
from array import array
from collections.abc import Iterable
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

from .const import CONF_KEEP_ALIVE, DOMAIN, PacketType
from .govee_utils import prepare_packet, prepare_scene_data_packets

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=2)
UUID_CONTROL_CHARACTERISTIC = "00010203-0405-0607-0809-0a0b0c0d2b11"
EFFECT_PARSE = re.compile("\\[(\\d+)/(\\d+)/(\\d+)(?:/(\\d+))?]")


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    unique_id = config_entry.unique_id or ""
    ble_device = bluetooth.async_ble_device_from_address(hass, unique_id.upper(), True)
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
        self._mac = config_entry.unique_id or ""
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
            await self._send(PacketType.KEEP_ALIVE)

    async def async_turn_on(self, **kwargs) -> None:
        packets: list[array[int]] = [prepare_packet(PacketType.SET_POWER, [0x01])]

        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            packets.append(prepare_packet(PacketType.SET_BRIGHTNESS, [brightness]))
            self._brightness = brightness

        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR, [0, 0, 0])
            packets.append(prepare_packet(PacketType.SET_RGB, [red, green, blue]))

        if ATTR_EFFECT in kwargs:
            effect: str | None = kwargs.get(ATTR_EFFECT, None)
            if effect is not None:
                search = EFFECT_PARSE.search(effect)

                if search is not None:
                    # Parse effect indexes
                    category_index = int(search.group(1))
                    scene_index = int(search.group(2))
                    light_effect_index = int(search.group(3))

                    category = self._data["data"]["categories"][category_index]
                    scene = category["scenes"][scene_index]
                    light_effect = scene["lightEffects"][light_effect_index]
                    scene_code = int(light_effect["sceneCode"])
                    scence_param = light_effect["scenceParam"]

                    if search.group(4) is not None:
                        special_effect_index = int(search.group(4))
                        special_effect = light_effect["specialEffect"][special_effect_index]
                        scence_param = special_effect["scenceParam"]

                    if scence_param:
                        packets += prepare_scene_data_packets(scence_param)

                    packets.append(prepare_packet(PacketType.SET_SCENE, scene_code.to_bytes(2, "little")))

        for packet in packets:
            await self._send_packet(packet)

        self._state = True

    async def async_turn_off(self) -> None:
        await self._send(PacketType.SET_POWER, 0x00)
        self._state = False

    async def _send(self, *args: PacketType | int | Iterable[int] | None):
        await self._send_packet(prepare_packet(*args))

    async def _send_packet(self, packet: array[int]):
        client = await bleak_retry_connector.establish_connection(BleakClient, self._ble_device, self.unique_id)
        _LOGGER.debug("Sending command %s", packet)
        return await client.write_gatt_char(UUID_CONTROL_CHARACTERISTIC, packet)
