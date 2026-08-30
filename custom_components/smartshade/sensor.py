"""Sensor platform: the last command the cloud has a record of."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_NAMES, DOMAIN
from .entity import SmartShadeEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SmartShadeLastCommandSensor(coordinator, entry, serial)
        for serial in (coordinator.data or {})
    )


class SmartShadeLastCommandSensor(SmartShadeEntity, SensorEntity):
    """The last command recorded in the hub's cloud shadow.

    This is the raw signal the cover's open/closed state is inferred from,
    surfaced on its own so the inference is auditable. It only ever reflects
    commands that went through the cloud -- Home Assistant or the official app.
    A handheld remote talks straight to the receiver and a wind sensor retracts
    the awning on its own, and neither reaches the cloud, so this can be stale.
    """

    _attr_translation_key = "last_cloud_command"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = sorted(ACTION_NAMES.values())
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-arrow-down-outline"

    def __init__(self, coordinator, entry, serial: str) -> None:
        super().__init__(coordinator, entry, serial)
        self._attr_unique_id = f"{serial}_last_cloud_command"

    @property
    def native_value(self) -> str | None:
        return self.last_action_name
