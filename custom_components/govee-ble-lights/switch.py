from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_MODEL,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_KEEP_ALIVE, DOMAIN


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    async_add_entities([KeepAliveSwitch(config_entry)])


class KeepAliveSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Keep Alive"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._mac = config_entry.unique_id or ""
        self._model = config_entry.data[CONF_MODEL]
        self._entry_id = config_entry.entry_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name="Govee {}".format(self._model),
            manufacturer="Govee",
            model=self._model,
        )

    @property
    def unique_id(self) -> str:
        return self._mac.replace(":", "")

    @property
    def is_on(self, **kwargs):
        return self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get(CONF_KEEP_ALIVE, False)

    def turn_on(self, **kwargs):
        self.hass.data.setdefault(DOMAIN, {}).setdefault(self._entry_id, {})[CONF_KEEP_ALIVE] = True

    def turn_off(self, **kwargs):
        self.hass.data.setdefault(DOMAIN, {}).setdefault(self._entry_id, {})[CONF_KEEP_ALIVE] = False
