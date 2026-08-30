"""Switch platform: the debug-logging toggle.

Lives on a service device for the account rather than on a hub, because
logging is account-wide -- one toggle, not one per awning.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SmartShadeDebugLoggingSwitch(coordinator, entry)])


class SmartShadeDebugLoggingSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Forces every poll to write a full payload report to the log.

    Setup already logs the authentication outcome unconditionally -- which pool
    answered, over which gateway. This switch covers the other half: what the
    cloud actually returns, and whether its shape matches what the entities are
    built to read. That only matters when someone is investigating, and it is
    genuinely noisy, so it is off by default and opt-in.

    State is restored across restarts: if you left it on to capture something
    intermittent, a restart should not quietly stop the capture.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "debug_logging"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bug-outline"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_debug_logging"

    @property
    def device_info(self) -> DeviceInfo:
        brand = self.coordinator.api.brand
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_account")},
            name="Smart Shade account",
            manufacturer="t2Fi",
            model=brand.name,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == "on":
            self.coordinator.debug_logging = True

    @property
    def is_on(self) -> bool:
        return self.coordinator.debug_logging

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.debug_logging = True
        self.async_write_ha_state()
        # Refresh straight away so the report appears now rather than at the
        # next scheduled poll -- someone who just flipped this wants output.
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.debug_logging = False
        self.async_write_ha_state()
