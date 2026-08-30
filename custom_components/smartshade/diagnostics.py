"""Diagnostics for a configured Smart Shade PRO entry.

Available from the integration page once setup has succeeded. For the case that
matters most to compatibility work -- setup that never succeeds -- see the
"Compatibility report" option in the config flow, which produces the same
report without needing an entry.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .report import build_report


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api
    brand = api.brand
    data = coordinator.data or {}
    first = next(iter(data.values()), None)

    return build_report(
        brand_key=brand.key,
        brand_name=brand.name,
        selected_brand=brand.key,
        gateway=brand.api_base,
        new_api=brand.new_api,
        app_name=api.app_name,
        # The entry is already set up, so the pool it uses is settled; there is
        # no probe history to report.
        auth_attempts=[
            {
                "brand": brand.key,
                "result": "in use",
                "app_name": api.app_name,
                "detail": None,
            }
        ],
        devices=[entry["hub"] for entry in data.values()],
        shadow=(first or {}).get("state"),
        brand_verified=brand.hardware_confirmed,
    )
