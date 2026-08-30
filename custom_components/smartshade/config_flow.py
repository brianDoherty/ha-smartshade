"""Config flow for Smart Shade PRO."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import SmartShadeApiError, SmartShadeAuthError, validate_brand
from .report import build_report, render, render_login
from .const import (
    CONF_APP_NAME,
    CONF_BRAND,
    CONF_POOL_USERNAME,
    BRANDS,
    CONF_CHANNEL,
    CONF_RECEIVER_MODEL,
    CONF_REFRESH_TOKEN,
    CONF_REMOTE_NUMBER,
    CONF_REMOTE_TYPE,
    DEFAULT_BRAND,
    DEFAULT_CHANNEL,
    DEFAULT_RECEIVER_MODEL,
    DEFAULT_REMOTE_NUMBER,
    DEFAULT_REMOTE_TYPE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

def _brand_selector() -> SelectSelector:
    """Pick the app you sign into. Confirmed ones are listed first.

    We ask rather than probe. The brands sit in two different Cognito pools,
    and trying them in turn would offer one brand's credentials to another
    brand's pool -- a failed login on an account that does not exist there, and
    two lockout attempts per typo. The question is also an easy one: it is the
    app on their phone, not something they have to look up.
    """
    # Confirmed hardware first, then apps sharing its login, then the rest.
    ordered = sorted(
        BRANDS.values(),
        key=lambda b: (not b.hardware_confirmed, not b.credentials_confirmed, b.name),
    )
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=b.key, label=f"{b.name}  ({b.status})")
                for b in ordered
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _credentials_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_BRAND, default=DEFAULT_BRAND): _brand_selector(),
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


class SmartShadeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Smart-Shade config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer normal setup, or a report for when setup will not work.

        The compatibility report exists because Home Assistant's diagnostics
        need a config entry, and the accounts we most need reports from are the
        ones that never get that far.
        """
        return self.async_show_menu(step_id="user", menu_options=["login", "report"])

    async def _probe(
        self, brand_key: str, username: str, password: str, *, fetch_shadow: bool
    ) -> tuple[Any, list[dict] | None, dict, str | None]:
        """Run brand detection and build the compatibility report for it.

        Shared by both entry points so a failed sign-in produces exactly the
        report the user would have got by asking for one -- which is the whole
        point: nobody thinks to run diagnostics before they have a problem.

        Returns (api, devices, report, error_code); api is None on failure and
        error_code is the translation key to show the user.
        """
        session = async_get_clientsession(self.hass)
        brand = BRANDS[brand_key]
        attempts: list[dict] = []
        api = hubs = shadow = None
        error: str | None = None
        error_code: str | None = None
        try:
            api, hubs = await validate_brand(
                session, username, password, brand, attempts=attempts
            )
        except SmartShadeAuthError as err:
            # Cognito distinguishes "no such user in this pool" from "wrong
            # password", and the difference matters: the first usually means a
            # typo'd email or the wrong app picked, not a bad password.
            error = f"{type(err).__name__}: {err}"[:300]
            error_code = (
                "user_not_found"
                if "user does not exist" in str(err).lower()
                else "invalid_auth"
            )
        except SmartShadeApiError as err:
            # Authenticated but no device list -- the signature of an
            # unconfirmed brand rather than a bad password.
            error, error_code = f"{type(err).__name__}: {err}"[:300], "cannot_connect"

        if fetch_shadow and api is not None and hubs:
            first = next(
                (h for h in hubs if isinstance(h.get("GrillNumber"), str)), None
            )
            if first:
                try:
                    shadow = await api.get_state(first["GrillNumber"])
                except SmartShadeApiError as err:
                    error = f"device list OK, shadow fetch failed: {err}"[:300]

        report = build_report(
            # matched -> only when sign-in actually worked
            brand_key=api.brand.key if api else None,
            brand_name=api.brand.name if api else None,
            selected_brand=brand.key,
            gateway=brand.api_base,
            new_api=brand.new_api,
            app_name=brand.app_name,
            auth_attempts=attempts,
            devices=hubs,
            shadow=shadow,
            error=error,
            brand_verified=brand.hardware_confirmed,
        )
        return api, hubs, report, error_code

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            brand_key = user_input[CONF_BRAND]
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            api, hubs, report, error_code = await self._probe(
                brand_key, username, password, fetch_shadow=True
            )
            if error_code is not None:
                # Every failed sign-in logs the full report, unprompted. A user
                # who cannot get in has no config entry and therefore no
                # diagnostics, so this is the only artefact they can hand us --
                # and warning level means it is there without anyone having
                # thought to turn on debug logging beforehand.
                _LOGGER.warning(
                    "Smart Shade sign-in failed. The report below is free of "
                    "personal data -- please include it when reporting a "
                    "brand as unsupported:\n%s",
                    render(report),
                )
                errors["base"] = error_code
            else:
                # Auth outcome always goes to the log: one line, once, and
                # the first thing anyone needs when a brand misbehaves. The
                # payload shapes stay behind the debug-logging switch so a
                # working install does not dump walls of text.
                _LOGGER.info("Smart Shade signed in -- %s", render_login(report))
                if report["findings"]:
                    _LOGGER.warning(
                        "Smart Shade set up, but %d thing(s) need a look: %s. "
                        "Turn on the 'Debug logging' switch under the Smart "
                        "Shade account device for the full payload report.",
                        len(report["findings"]),
                        "; ".join(report["findings"]),
                    )
                # An account exists in exactly one pool, so the email alone
                # identifies it -- and keeping the bare form means entries
                # created before brand detection still match.
                # The same email can exist in both pools, so identity is the
                # account *and* the brand. The default brand keeps the bare
                # form so entries made before this field still match.
                unique_id = username.lower()
                if brand_key != DEFAULT_BRAND:
                    unique_id = f"{brand_key}:{unique_id}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                _LOGGER.info(
                    "%s: discovered %d hub(s)", api.brand.name, len(hubs)
                )
                return self.async_create_entry(
                    title=username,
                    data={
                        # Store what the probe resolved so it never runs again.
                        CONF_BRAND: brand_key,
                        CONF_APP_NAME: api.app_name,
                        CONF_POOL_USERNAME: api.pool_username,
                        # Whatever spelling actually authenticated.
                        CONF_USERNAME: api.username,
                        CONF_PASSWORD: password,
                        CONF_REFRESH_TOKEN: api.refresh_token,
                    },
                )

        return self.async_show_form(
            step_id="login", data_schema=_credentials_schema(), errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """A stored login stopped working -- ask for the password again.

        Without this, the ConfigEntryAuthFailed raised at startup leaves the
        entry broken with no way back except deleting and re-adding it.
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors: dict[str, str] = {}
        if user_input is not None and entry is not None:
            username = entry.data[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            api, _hubs, report, error_code = await self._probe(
                entry.data.get(CONF_BRAND, DEFAULT_BRAND),
                username,
                password,
                fetch_shadow=False,
            )
            if error_code is not None:
                _LOGGER.warning(
                    "Smart Shade re-authentication failed:\n%s", render(report)
                )
                errors["base"] = error_code
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    # The brand is not re-asked here: it is a property of the
                    # account, and only the password can have changed.
                    data={
                        **entry.data,
                        CONF_APP_NAME: api.app_name,
                        CONF_POOL_USERNAME: api.pool_username,
                        CONF_PASSWORD: password,
                        CONF_REFRESH_TOKEN: api.refresh_token,
                    },
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={
                "username": entry.data[CONF_USERNAME] if entry else ""
            },
        )

    async def async_step_report(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run the brand probe and show a PII-free report of what happened."""
        if user_input is None:
            return self.async_show_form(step_id="report", data_schema=_credentials_schema())

        _api, _hubs, report, _code = await self._probe(
            user_input[CONF_BRAND],
            user_input[CONF_USERNAME].strip(),
            user_input[CONF_PASSWORD],
            fetch_shadow=True,
        )
        text = render(report)
        # Also emit it at warning level: the log survives closing the dialog,
        # and users are used to copying from there.
        _LOGGER.warning("Smart Shade compatibility report:\n%s", text)
        return self.async_abort(
            reason="report", description_placeholders={"report": text}
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return SmartShadeOptionsFlow(entry)


class SmartShadeOptionsFlow(OptionsFlow):
    """Tune the paired-remote descriptor used to build RF command keys."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_REMOTE_TYPE,
                    default=opts.get(CONF_REMOTE_TYPE, DEFAULT_REMOTE_TYPE),
                ): vol.All(int, vol.Range(min=1, max=3)),
                vol.Required(
                    CONF_REMOTE_NUMBER,
                    default=opts.get(CONF_REMOTE_NUMBER, DEFAULT_REMOTE_NUMBER),
                ): vol.All(int, vol.Range(min=0, max=99)),
                vol.Required(
                    CONF_CHANNEL,
                    default=opts.get(CONF_CHANNEL, DEFAULT_CHANNEL),
                ): vol.All(int, vol.Range(min=0, max=99)),
                vol.Optional(
                    CONF_RECEIVER_MODEL,
                    default=opts.get(CONF_RECEIVER_MODEL, DEFAULT_RECEIVER_MODEL),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
