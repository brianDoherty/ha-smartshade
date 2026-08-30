"""Shared base entity + RF command-key construction for Smart-Shade."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ACTION_NAMES,
    CONF_CHANNEL,
    CONF_RECEIVER_MODEL,
    CONF_REMOTE_NUMBER,
    CONF_REMOTE_TYPE,
    DEFAULT_CHANNEL,
    DEFAULT_RECEIVER_MODEL,
    DEFAULT_REMOTE_NUMBER,
    DEFAULT_REMOTE_TYPE,
    DOMAIN,
)


def build_command_key(options, action: int) -> str:
    """Build the RF descriptor the hub expects.

    Format (from RFHRemoteControlViewModel):
        "<remoteType>:<action>:<remoteNumber>:<channel><receiverModel>"
    """
    remote_type = options.get(CONF_REMOTE_TYPE, DEFAULT_REMOTE_TYPE)
    remote_number = options.get(CONF_REMOTE_NUMBER, DEFAULT_REMOTE_NUMBER)
    channel = options.get(CONF_CHANNEL, DEFAULT_CHANNEL)
    receiver = options.get(CONF_RECEIVER_MODEL, DEFAULT_RECEIVER_MODEL) or ""
    return f"{remote_type}:{action}:{remote_number}:{channel}{receiver}"


class SmartShadeEntity(CoordinatorEntity):
    """Base entity bound to one hub (GrillNumber)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, serial: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._serial = serial

    @property
    def _hub(self) -> dict:
        data = self.coordinator.data or {}
        return (data.get(self._serial) or {}).get("hub") or {}

    @property
    def _nickname(self) -> str:
        return self._hub.get("NickName") or self._serial

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            name=self._nickname,
            manufacturer="Spettmann / Marygrove",
            model=self._hub.get("Model") or "Smart-Shade Hub",
            serial_number=self._serial,
        )

    @property
    def _shadow(self) -> dict:
        """The AWS IoT device shadow body for this hub."""
        data = self.coordinator.data or {}
        state = (data.get(self._serial) or {}).get("state") or {}
        return (state.get("data") or {}).get("state") or {}

    @property
    def last_action(self) -> int | None:
        """Action code of the most recent command recorded in the shadow.

        The hub is a one-way RF bridge and reports no awning position, but the
        desired shadow retains the last command it was asked to send -- including
        ones issued from the phone app -- so it survives HA restarts.
        """
        desired = self._shadow.get("desired") or {}
        steps = (desired.get("CMD_LST") or {}).get("CMD_steps") or []
        if not steps:
            return None
        parts = str(steps[0].get("C", "")).split(":")
        if len(parts) < 2:
            return None
        try:
            return int(parts[1])
        except ValueError:
            return None

    @property
    def last_action_name(self) -> str | None:
        """The last recorded command as a word: open / close / stop / light.

        Only commands that travelled through the cloud are recorded here -- ones
        sent from Home Assistant or the official app. The hub is a one-way RF
        transmitter: it never hears the handheld remote, and the wind sensor
        retracts the awning by talking to the receiver directly, so neither
        shows up. Treat this as "last command we know about", not as position.
        """
        return ACTION_NAMES.get(self.last_action)

    def _next_cid(self) -> int:
        """Next command id. The hub echoes the executed one as reported.LastCID."""
        desired = self._shadow.get("desired") or {}
        try:
            return int(desired.get("CID", 0)) + 1
        except (TypeError, ValueError):
            return 1

    async def _send(self, action: int) -> None:
        key = build_command_key(self._entry.options, action)
        await self.coordinator.api.send_command(
            self._serial, key, 0.2, self._next_cid()
        )
        await self.coordinator.async_request_refresh()
