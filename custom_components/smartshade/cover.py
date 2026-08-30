"""Cover (awning) platform for Smart-Shade."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_CLOSE, ACTION_OPEN, ACTION_STOP, DOMAIN
from .entity import SmartShadeEntity

_LOGGER = logging.getLogger(__name__)

# Commands are sequenced by a CID read from the device shadow and
# incremented, so two overlapping presses would claim the same id.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        SmartShadeCover(coordinator, entry, serial)
        for serial in (coordinator.data or {})
    ]
    async_add_entities(entities)


class SmartShadeCover(SmartShadeEntity, CoverEntity):
    """An awning driven through the Smart-Shade RF hub."""

    _attr_device_class = CoverDeviceClass.AWNING
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )
    # The hub is a one-way RF bridge with no position sensing, so this reflects
    # the last command in the device shadow rather than a measured position.
    _attr_assumed_state = True
    _attr_name = None

    def __init__(self, coordinator, entry, serial: str) -> None:
        super().__init__(coordinator, entry, serial)
        self._attr_unique_id = f"{serial}_awning"
        self._optimistic: bool | None = None

    @property
    def is_closed(self) -> bool | None:
        """Infer from the last command recorded in the cloud shadow.

        This is not a measured position -- the hub has no position sensing. The
        shadow records commands that went through the cloud (from Home Assistant
        or the official app), so state survives restarts, but a press of the
        handheld remote or a wind-sensor auto-retract is invisible here and will
        leave this stale until the next cloud command. A STOP leaves the
        position genuinely unknown, so we report None rather than guessing.
        """
        action = self.last_action
        if action == ACTION_OPEN:
            return False
        if action == ACTION_CLOSE:
            return True
        if action == ACTION_STOP:
            return None
        return self._optimistic

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the command this state was inferred from, and its blind spot.

        Surfacing both makes it obvious why the state can be stale: it is the
        last cloud command, not a measured position.
        """
        return {
            "last_cloud_command": self.last_action_name,
            "state_source": "last command sent via Home Assistant or the "
            "official app; physical remotes and wind-sensor auto-retract are "
            "not detected",
        }

    async def async_open_cover(self, **kwargs: Any) -> None:
        self._optimistic = False
        await self._send(ACTION_OPEN)

    async def async_close_cover(self, **kwargs: Any) -> None:
        self._optimistic = True
        await self._send(ACTION_CLOSE)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        self._optimistic = None
        await self._send(ACTION_STOP)
