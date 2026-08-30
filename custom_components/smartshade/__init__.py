"""Smart Shade PRO awning integration (Spettmann Smart-Shade RF hubs)."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SmartShadeApi, SmartShadeApiError, SmartShadeAuthError
from .report import build_report, render
from .const import (
    BRANDS,
    CONF_APP_NAME,
    CONF_BRAND,
    CONF_POOL_USERNAME,
    CONF_REFRESH_TOKEN,
    DEFAULT_BRAND,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HUB_SERIAL_PREFIXES,
    NON_HUB_SERIAL_PREFIXES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.COVER,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]


def is_controllable_hub(serial: str) -> bool:
    """Whether this account device is an RF hub we can send awning commands to.

    get-grill-list returns everything registered to the account -- not just
    awning hubs, but paired RF accessories and any other t2Fi product the same
    login owns. Classification follows the app's own serial-prefix map, which is
    identical across both brand pools.

    Only an explicitly recognised hub is accepted. Anything the app recognises
    as something else is rejected outright, including devices that do have a
    cloud shadow: a Light Bug or an RGB controller would otherwise survive the
    shadow fetch and appear as an awning with buttons that do nothing.

    An unrecognised prefix falls through to the shadow fetch, so a hub model
    newer than this map still works rather than being silently dropped.
    """
    if serial.startswith(HUB_SERIAL_PREFIXES):
        return True
    if serial.startswith(NON_HUB_SERIAL_PREFIXES):
        return False
    return True


class SmartShadeCoordinator(DataUpdateCoordinator):
    """Polls the hub list and each hub's reported state."""

    def __init__(self, hass: HomeAssistant, api: SmartShadeApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self._logged_state_once: set[str] = set()
        # Flipped by the "Debug logging" switch. While on, every poll writes a
        # full payload report at warning level -- deliberately noisy, because
        # the point is to capture what an unconfirmed brand actually returns.
        self.debug_logging = False
        # The unfiltered device list, kept so a debug report can show what was
        # skipped as well as what was kept.
        self.raw_devices: list[dict] = []

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            hubs = await self.api.get_grill_list()
        except SmartShadeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SmartShadeApiError as err:
            raise UpdateFailed(str(err)) from err

        self.raw_devices = hubs
        result: dict[str, dict] = {}
        for hub in hubs:
            serial = hub.get("GrillNumber")
            if not serial:
                continue
            if not is_controllable_hub(serial):
                _LOGGER.debug("skipping %s: recognised as a non-hub device", serial)
                continue
            try:
                state = await self.api.get_state(serial)
            except SmartShadeApiError as err:
                # Backstop for devices whose prefix we do not recognise: an
                # accessory has no shadow of its own and answers 400.
                _LOGGER.debug("skipping %s: no shadow (%s)", serial, err)
                continue
            if serial not in self._logged_state_once:
                self._logged_state_once.add(serial)
                _LOGGER.debug("shadow for %s: %s", serial, state)
            result[serial] = {"hub": hub, "state": state}

        if self.debug_logging:
            self._log_payload_report(result)
        return result

    def _log_payload_report(self, result: dict[str, dict]) -> None:
        """Dump what the cloud returned this poll, loudly and PII-free."""
        brand = self.api.brand
        first = next(iter(result.values()), None)
        report = build_report(
            brand_key=brand.key,
            brand_name=brand.name,
            selected_brand=brand.key,
            gateway=brand.api_base,
            new_api=brand.new_api,
            app_name=self.api.app_name,
            auth_attempts=[
                {
                    "brand": brand.key,
                    "result": "in use",
                    "app_name": self.api.app_name,
                    "detail": None,
                }
            ],
            devices=self.raw_devices,
            shadow=(first or {}).get("state"),
            brand_verified=brand.hardware_confirmed,
        )
        _LOGGER.warning(
            "Smart Shade debug logging is ON -- payload report follows. It "
            "contains no personal data; paste it into a GitHub issue, then "
            "turn the switch off.\n%s",
            render(report),
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart-Shade from a config entry."""
    session = async_get_clientsession(hass)
    # Entries created before brand support carry no brand key; they were all
    # Smart Shade PRO, which is the default.
    brand = BRANDS.get(entry.data.get(CONF_BRAND, DEFAULT_BRAND), BRANDS[DEFAULT_BRAND])
    api = SmartShadeApi(
        session,
        entry.data[CONF_USERNAME],
        brand=brand,
        app_name=entry.data.get(CONF_APP_NAME),
        pool_username=entry.data.get(CONF_POOL_USERNAME),
    )
    api.set_refresh_token(entry.data.get(CONF_REFRESH_TOKEN))

    try:
        if entry.data.get(CONF_REFRESH_TOKEN):
            await api.refresh()
        else:
            await api.authenticate(entry.data[CONF_PASSWORD])
    except SmartShadeAuthError as err:
        # A stored refresh token can go stale; fall back to a full login.
        password = entry.data.get(CONF_PASSWORD)
        if not password:
            raise ConfigEntryAuthFailed(str(err)) from err
        try:
            await api.authenticate(password)
        except SmartShadeAuthError as err2:
            # A stored login that stops working is worth saying out loud, with
            # the brand named -- the same failure a fresh setup would report.
            _LOGGER.warning(
                "Smart Shade sign-in failed for brand %s (%s). If this brand "
                "is one of the untested ones, please run Add Integration -> "
                "Smart Shade PRO -> Compatibility report and open an issue.",
                brand.key,
                type(err2).__name__,
            )
            raise ConfigEntryAuthFailed(str(err2)) from err2

    # Persist whatever the login learned. The pool username matters as much as
    # the token: without it the token cannot be used on the next cold start.
    fresh = {
        CONF_REFRESH_TOKEN: api.refresh_token,
        CONF_POOL_USERNAME: api.pool_username,
    }
    if any(entry.data.get(k) != v for k, v in fresh.items() if v):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, **{k: v for k, v in fresh.items() if v}}
        )

    coordinator = SmartShadeCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options (remote descriptor) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
