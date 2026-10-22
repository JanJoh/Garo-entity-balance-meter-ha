from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = runtime.get("coordinator")
    follower = runtime.get("dlm_follower")
    return {
        "entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "coordinator_data": coordinator.data if coordinator else None,
        "dlm": None if follower is None else {
            "offset": follower.offset,
            "changes": follower.changes,
            "latest": None if follower.latest is None else {
                "timestamp": follower.latest.timestamp.isoformat(),
                "charger": follower.latest.charger,
                "raw": follower.latest.raw,
                "filtered": follower.latest.filtered,
            },
        },
    }
