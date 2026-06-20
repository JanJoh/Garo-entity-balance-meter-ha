from __future__ import annotations
import logging, asyncio, aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import aiohttp_client
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN, PLATFORMS,
    CONF_HOST, CONF_USERNAME, CONF_PASSWORD,
    CONF_IGNORE_TLS_ERRORS, CONF_USE_HTTP,
    API_PATH,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    def opt(key, default=None):
        return entry.options.get(key, entry.data.get(key, default))

    host = opt(CONF_HOST)
    username = opt(CONF_USERNAME)
    password = opt(CONF_PASSWORD)
    ignore_tls = opt(CONF_IGNORE_TLS_ERRORS, True)
    use_http = opt(CONF_USE_HTTP, False)
    scheme = "http" if use_http else "https"
    url = f"{scheme}://{host}{API_PATH}"

    session = aiohttp_client.async_get_clientsession(hass, verify_ssl=not ignore_tls)
    try:
        async with asyncio.timeout(15):
            async with session.get(url, auth=aiohttp.BasicAuth(username, password)) as resp:
                txt = await resp.text()
                if resp.status in (401, 403):
                    raise ConfigEntryNotReady(f"Authentication failed (status {resp.status})")
                if resp.status >= 400:
                    raise ConfigEntryNotReady(f"HTTP {resp.status}: {txt[:120]}")
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ConfigEntryNotReady(f"Connection error: {err}") from err

    hass.data[DOMAIN][entry.entry_id] = {
        CONF_HOST: host,
        "use_http": use_http,
        "session": session,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
