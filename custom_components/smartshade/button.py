"""Button platform: the awning's light command."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_LIGHT, DOMAIN
from .entity import SmartShadeEntity

# Commands are sequenced by a CID read from the device shadow and
# incremented, so two overlapping presses would claim the same id.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SmartShadeLightButton(coordinator, entry, serial)
        for serial in (coordinator.data or {})
    )


class SmartShadeLightButton(SmartShadeEntity, ButtonEntity):
    """Sends the LIGHT command (RF action 5), as on the physical remote."""

    _attr_translation_key = "light"
    _attr_icon = "mdi:lightbulb"

    def __init__(self, coordinator, entry, serial: str) -> None:
        super().__init__(coordinator, entry, serial)
        self._attr_unique_id = f"{serial}_light"

    async def async_press(self) -> None:
        await self._send(ACTION_LIGHT)
