from __future__ import annotations
import logging, asyncio, aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import aiohttp_client, entity_registry as er
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import (
    DOMAIN, PLATFORMS, DATA_KEYS,
    CONF_HOST, CONF_USERNAME, CONF_PASSWORD,
    CONF_IGNORE_TLS_ERRORS, CONF_USE_HTTP,
    API_PATH,
)

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Bring an older config entry up to the current version.

    1.1 -> 1.2: move host and credentials out of entry.options into entry.data.
    Earlier versions of the options flow copied host/username/password into
    entry.options, which Home Assistant exposes unredacted (API, diagnostics).

    1.2 -> 1.3: entity unique IDs were "garo_<key>" for every device, so a second
    balancer got no entities. They are now "<entry_id>_<key>"; renaming them in
    the registry keeps entity IDs and history.
    """
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        data = dict(entry.data)
        options = dict(entry.options)
        for key in DATA_KEYS:
            if key in options:
                value = options.pop(key)
                if value and not data.get(key):
                    data[key] = value
        hass.config_entries.async_update_entry(entry, data=data, options=options, minor_version=2)
        _LOGGER.info("Migrated config entry %s: credentials moved from options to data", entry.entry_id)
    if entry.minor_version < 3:
        @callback
        def _entry_scoped(entity_entry: er.RegistryEntry) -> dict[str, str] | None:
            if entity_entry.unique_id.startswith("garo_"):
                return {"new_unique_id": f"{entry.entry_id}_{entity_entry.unique_id[len('garo_'):]}"}
            return None

        await er.async_migrate_entries(hass, entry.entry_id, _entry_scoped)
        hass.config_entries.async_update_entry(entry, minor_version=3)
        _LOGGER.info("Migrated config entry %s: entity unique IDs scoped to the entry", entry.entry_id)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    host = entry.data.get(CONF_HOST)
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    if not host:
        raise ConfigEntryNotReady("Host missing from config entry — use Reconfigure to enter it again")
    if not username or not password:
        raise ConfigEntryAuthFailed("Credentials missing from config entry")

    ignore_tls = entry.options.get(CONF_IGNORE_TLS_ERRORS, entry.data.get(CONF_IGNORE_TLS_ERRORS, True))
    use_http = entry.options.get(CONF_USE_HTTP, entry.data.get(CONF_USE_HTTP, False))
    scheme = "http" if use_http else "https"
    url = f"{scheme}://{host}{API_PATH}"

    session = aiohttp_client.async_get_clientsession(hass, verify_ssl=not ignore_tls)
    try:
        async with asyncio.timeout(15):
            async with session.get(url, auth=aiohttp.BasicAuth(username, password)) as resp:
                txt = await resp.text()
                if resp.status in (401, 403):
                    raise ConfigEntryAuthFailed(f"Authentication failed (status {resp.status})")
                if resp.status >= 400:
                    raise ConfigEntryNotReady(f"HTTP {resp.status}: {txt[:120]}")
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ConfigEntryNotReady(f"Connection error: {err}") from err

    hass.data[DOMAIN][entry.entry_id] = {
        CONF_HOST: host,
        "use_http": use_http,
        "session": session,
    }

    # One at a time: the update entity uses the coordinator the sensor platform creates.
    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, [platform])
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
