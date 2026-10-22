from __future__ import annotations
import logging, asyncio, aiohttp, voluptuous as vol
from typing import Any
from homeassistant import config_entries
from homeassistant.core import callback, HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    CONF_HOST, CONF_USERNAME, CONF_PASSWORD,
    CONF_SCAN_INTERVAL, CONF_SLOW_SCAN_INTERVAL,
    CONF_IGNORE_TLS_ERRORS, CONF_USE_HTTP, CONF_ENABLE_DLM, DATA_KEYS,
    DEFAULT_SCAN_INTERVAL, DEFAULT_SLOW_SCAN_INTERVAL, DEFAULT_ENABLE_DLM, API_PATH,
)

_LOGGER = logging.getLogger(__name__)

class CannotConnect(Exception): pass
class InvalidAuth(Exception): pass


async def _async_validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    host = data[CONF_HOST]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]
    ignore_tls = data.get(CONF_IGNORE_TLS_ERRORS, True)
    use_http = data.get(CONF_USE_HTTP, False)
    scheme = "http" if use_http else "https"
    session = aiohttp_client.async_get_clientsession(hass, verify_ssl=not ignore_tls)
    try:
        async with asyncio.timeout(10):
            async with session.get(
                f"{scheme}://{host}{API_PATH}",
                auth=aiohttp.BasicAuth(username, password),
            ) as resp:
                if resp.status in (401, 403):
                    raise InvalidAuth
                if resp.status >= 400:
                    raise CannotConnect(f"HTTP {resp.status}")
    except InvalidAuth:
        raise
    except Exception as err:
        raise CannotConnect(err) from err


class GaroBalanceMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 2  # 1.2: credentials live only in entry.data (see async_migrate_entry)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return GaroBalanceMeterOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            scan = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            slow = user_input.get(CONF_SLOW_SCAN_INTERVAL, DEFAULT_SLOW_SCAN_INTERVAL)
            if slow < scan:
                errors[CONF_SLOW_SCAN_INTERVAL] = "slow_must_be_gte_fast"
            else:
                try:
                    await self.async_set_unique_id(user_input[CONF_HOST])
                    self._abort_if_unique_id_configured()
                    await _async_validate_input(self.hass, user_input)
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error validating input")
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(
                        title=f"GARO Balance @ {user_input[CONF_HOST]}",
                        data=user_input,
                    )

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
            vol.Required(CONF_USERNAME, default=(user_input or {}).get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=(user_input or {}).get(CONF_PASSWORD, "")): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=5)),
            vol.Optional(CONF_SLOW_SCAN_INTERVAL, default=DEFAULT_SLOW_SCAN_INTERVAL): vol.All(int, vol.Range(min=5)),
            vol.Optional(CONF_IGNORE_TLS_ERRORS, default=True): bool,
            vol.Optional(CONF_USE_HTTP, default=False): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Change host or credentials. They are stored in entry.data only."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors = {}
        if user_input is not None:
            settings = {**entry.data, **entry.options}
            try:
                await _async_validate_input(self.hass, {**settings, **user_input})
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating input")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    title=f"GARO Balance @ {user_input[CONF_HOST]}",
                    data={**entry.data, **user_input},
                    reason="reconfigure_successful",
                )

        current = {**entry.data, **(user_input or {})}
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=current.get(CONF_HOST, "")): str,
            vol.Required(CONF_USERNAME, default=current.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)


class GaroBalanceMeterOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            scan = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            slow = user_input.get(CONF_SLOW_SCAN_INTERVAL, DEFAULT_SLOW_SCAN_INTERVAL)
            if slow < scan:
                errors[CONF_SLOW_SCAN_INTERVAL] = "slow_must_be_gte_fast"
            else:
                # Options hold polling/TLS settings only. Host and credentials stay in
                # entry.data, which Home Assistant redacts; options are exposed as-is.
                options = {k: v for k, v in user_input.items() if k not in DATA_KEYS}
                return self.async_create_entry(title="Options updated", data=options)

        data = {**self._entry.data, **self._entry.options}
        schema = vol.Schema({
            vol.Optional(CONF_SCAN_INTERVAL, default=data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(int, vol.Range(min=5)),
            vol.Optional(CONF_SLOW_SCAN_INTERVAL, default=data.get(CONF_SLOW_SCAN_INTERVAL, DEFAULT_SLOW_SCAN_INTERVAL)): vol.All(int, vol.Range(min=5)),
            vol.Optional(CONF_IGNORE_TLS_ERRORS, default=data.get(CONF_IGNORE_TLS_ERRORS, True)): bool,
            vol.Optional(CONF_USE_HTTP, default=data.get(CONF_USE_HTTP, False)): bool,
            vol.Optional(CONF_ENABLE_DLM, default=data.get(CONF_ENABLE_DLM, DEFAULT_ENABLE_DLM)): bool,
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
