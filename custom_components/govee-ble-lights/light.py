from __future__ import annotations

import logging
import re
from datetime import timedelta

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

from .const import DOMAIN
from .device import Device

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

    _device: Device

    def __init__(self, ble_device, config_entry: ConfigEntry) -> None:
        self._entry_id = config_entry.entry_id
        self._mac = config_entry.unique_id or ""
        self._model = config_entry.data[CONF_MODEL]
        self._ble_device = ble_device
        self._state = None
        self._brightness = None
        self._device = Device(ble_device, self._model)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=f"Govee {self._model}",
            manufacturer="Govee",
            model=self._model,
        )

    @property
    def unique_id(self) -> str:
        return self._mac.replace(":", "")

    @property
    def brightness(self):
        return self._device._state.brightness

    @property
    def is_on(self) -> bool | None:
        return self._device._state.on

    async def async_update(self) -> None:
        pass
        # if self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get(CONF_KEEP_ALIVE, False):
        #     await self._send(PacketType.KEEP_ALIVE)

    async def async_turn_on(self, **kwargs) -> None:
        await self._device.set_power(True)

        if ATTR_BRIGHTNESS in kwargs:
            await self._device.set_brightness(kwargs.get(ATTR_BRIGHTNESS, 255))

        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR, [0, 0, 0])
            await self._device.set_color((red, green, blue))

        if ATTR_EFFECT in kwargs:
            pass

    async def async_turn_off(self) -> None:
        await self._device.set_power(False)
