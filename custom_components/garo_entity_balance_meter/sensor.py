from __future__ import annotations
import logging, asyncio, aiohttp
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers import aiohttp_client, device_registry as dr
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfPower, UnitOfEnergy, UnitOfTemperature
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD,
    CONF_SCAN_INTERVAL, CONF_SLOW_SCAN_INTERVAL,
    CONF_IGNORE_TLS_ERRORS, CONF_USE_HTTP,
    DEFAULT_SCAN_INTERVAL, DEFAULT_SLOW_SCAN_INTERVAL,
    MANUFACTURER, PRODUCT_NAME, API_PATH,
)

_LOGGER = logging.getLogger(__name__)

API_PATH_TEMPS               = "/status/temperatures"
API_PATH_FIRMWARE_VERSION    = "/config/firmware-version"
API_PATH_DEVICE_ID           = "/config/device-id"
API_PATH_UNIT_ID             = "/config/unit-id"
API_PATH_NETWORK_INTERFACE   = "/netconf/network-interface"
API_PATH_CONNECTION_STATUS   = "/netconf/connection-status"
API_PATH_CSMS_STATUS         = "/netconf/csms-connection-status"

SENSOR_MAP = {
    # --- Fast (energy meter) — names kept identical to original to preserve entity IDs and LTS ---
    "power":      {"name": "Power Consumption", "device_class": SensorDeviceClass.POWER,   "unit": UnitOfPower.WATT,             "state_class": SensorStateClass.MEASUREMENT},
    "energy":     {"name": "Energy Total",      "device_class": SensorDeviceClass.ENERGY,  "unit": UnitOfEnergy.WATT_HOUR,       "state_class": SensorStateClass.TOTAL_INCREASING},
    "current_l1": {"name": "Current L1",        "device_class": SensorDeviceClass.CURRENT, "unit": UnitOfElectricCurrent.AMPERE, "state_class": SensorStateClass.MEASUREMENT},
    "current_l2": {"name": "Current L2",        "device_class": SensorDeviceClass.CURRENT, "unit": UnitOfElectricCurrent.AMPERE, "state_class": SensorStateClass.MEASUREMENT},
    "current_l3": {"name": "Current L3",        "device_class": SensorDeviceClass.CURRENT, "unit": UnitOfElectricCurrent.AMPERE, "state_class": SensorStateClass.MEASUREMENT},
    "voltage_l1": {"name": "Voltage L1",        "device_class": SensorDeviceClass.VOLTAGE, "unit": UnitOfElectricPotential.VOLT, "state_class": SensorStateClass.MEASUREMENT},
    "voltage_l2": {"name": "Voltage L2",        "device_class": SensorDeviceClass.VOLTAGE, "unit": UnitOfElectricPotential.VOLT, "state_class": SensorStateClass.MEASUREMENT},
    "voltage_l3": {"name": "Voltage L3",        "device_class": SensorDeviceClass.VOLTAGE, "unit": UnitOfElectricPotential.VOLT, "state_class": SensorStateClass.MEASUREMENT},
    # --- Slow (diagnostics, disabled by default) ---
    "cpu_temperature":    {"name": "CPU Temperature",    "device_class": SensorDeviceClass.TEMPERATURE, "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT, "entity_category": EntityCategory.DIAGNOSTIC, "enabled_default": False},
    "board_temperature":  {"name": "Board Temperature",  "device_class": SensorDeviceClass.TEMPERATURE, "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT, "entity_category": EntityCategory.DIAGNOSTIC, "enabled_default": False},
    "firmware_version":   {"name": "Firmware Version",   "device_class": None, "unit": None, "state_class": None, "entity_category": EntityCategory.DIAGNOSTIC, "enabled_default": False},
    "device_id":          {"name": "Device ID",          "device_class": None, "unit": None, "state_class": None, "entity_category": EntityCategory.DIAGNOSTIC, "enabled_default": False},
    "unit_id":            {"name": "Unit ID",            "device_class": None, "unit": None, "state_class": None, "entity_category": EntityCategory.DIAGNOSTIC, "enabled_default": False},
    "network_interface":  {"name": "Network Interface",  "device_class": None, "unit": None, "state_class": None, "entity_category": EntityCategory.DIAGNOSTIC, "enabled_default": False},
    "ip_address":         {"name": "IP Address",         "device_class": None, "unit": None, "state_class": None, "entity_category": EntityCategory.DIAGNOSTIC, "enabled_default": False},
    "wifi_ssid":          {"name": "Wi-Fi SSID",         "device_class": None, "unit": None, "state_class": None, "entity_category": EntityCategory.DIAGNOSTIC, "enabled_default": False},
    "wifi_signal":        {"name": "Wi-Fi Signal",       "device_class": SensorDeviceClass.SIGNAL_STRENGTH, "unit": "dBm", "state_class": SensorStateClass.MEASUREMENT, "entity_category": EntityCategory.DIAGNOSTIC, "enabled_default": False},
    "csms_status":        {"name": "CSMS Connection",    "device_class": None, "unit": None, "state_class": None, "entity_category": EntityCategory.DIAGNOSTIC, "enabled_default": False},
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]

    def opt(key):
        return entry.options.get(key, entry.data.get(key))

    host = opt(CONF_HOST)
    username = opt(CONF_USERNAME)
    password = opt(CONF_PASSWORD)
    scan_interval = opt(CONF_SCAN_INTERVAL) or DEFAULT_SCAN_INTERVAL
    slow_scan_interval = opt(CONF_SLOW_SCAN_INTERVAL) or DEFAULT_SLOW_SCAN_INTERVAL
    ignore_tls = opt(CONF_IGNORE_TLS_ERRORS)
    use_http = opt(CONF_USE_HTTP)

    scheme = "http" if use_http else "https"
    base_url         = f"{scheme}://{host}{API_PATH}"
    temp_url         = f"{scheme}://{host}{API_PATH_TEMPS}"
    firmware_url     = f"{scheme}://{host}{API_PATH_FIRMWARE_VERSION}"
    device_id_url    = f"{scheme}://{host}{API_PATH_DEVICE_ID}"
    unit_id_url      = f"{scheme}://{host}{API_PATH_UNIT_ID}"
    net_iface_url    = f"{scheme}://{host}{API_PATH_NETWORK_INTERFACE}"
    conn_status_url  = f"{scheme}://{host}{API_PATH_CONNECTION_STATUS}"
    csms_url         = f"{scheme}://{host}{API_PATH_CSMS_STATUS}"

    session = data.get("session") or aiohttp_client.async_get_clientsession(hass, verify_ssl=not ignore_tls)

    def _extract_simple(payload):
        if isinstance(payload, dict):
            return next(iter(payload.values()), None)
        return payload

    _slow_modulo = max(1, round(slow_scan_interval / scan_interval))
    _LOGGER.info(
        "Poll intervals: fast=%ds slow=%ds (slow fires every %d fast ticks)",
        scan_interval, slow_scan_interval, _slow_modulo,
    )
    _slow_cache: dict = {}
    _slow_counter = [_slow_modulo - 1]

    async def _async_update_data():
        _slow_counter[0] += 1
        if _slow_counter[0] >= _slow_modulo:
            _slow_counter[0] = 0

            # --- Temperatures ---
            try:
                async with asyncio.timeout(10):
                    async with session.get(temp_url, auth=aiohttp.BasicAuth(username, password)) as resp:
                        if resp.status == 200:
                            try:
                                temps = await resp.json(content_type=None)
                            except Exception:
                                _LOGGER.warning("Temp JSON decode failed")
                            else:
                                _LOGGER.debug("Temperatures raw=%r", temps)
                                if isinstance(temps, dict):
                                    cpu = temps.get("cpu")
                                    board = (
                                        temps.get("base_board") or temps.get("board")
                                        or temps.get("baseboard") or temps.get("pcb")
                                    )
                                    if isinstance(cpu, (int, float)):
                                        _slow_cache["cpu_temperature"] = float(cpu)
                                    if isinstance(board, (int, float)):
                                        _slow_cache["board_temperature"] = float(board)
            except Exception as e:
                _LOGGER.debug("Temperature fetch failed: %s", e)

            # --- Firmware version, device ID, unit ID ---
            for label, url, key in (
                ("firmware_version", firmware_url, "firmware_version"),
                ("device_id",        device_id_url, "device_id"),
                ("unit_id",          unit_id_url,   "unit_id"),
            ):
                try:
                    async with asyncio.timeout(10):
                        async with session.get(url, auth=aiohttp.BasicAuth(username, password)) as resp:
                            if resp.status == 200:
                                try:
                                    raw = await resp.json(content_type=None)
                                except Exception:
                                    raw = await resp.text()
                                val = _extract_simple(raw)
                                if val is not None:
                                    _slow_cache[key] = str(val)
                            else:
                                _LOGGER.debug("%s endpoint status %s", label, resp.status)
                except Exception as e:
                    _LOGGER.debug("%s fetch failed: %s", label, e)

            # --- Network interface ---
            try:
                async with asyncio.timeout(10):
                    async with session.get(net_iface_url, auth=aiohttp.BasicAuth(username, password)) as resp:
                        if resp.status == 200:
                            try:
                                raw = await resp.json(content_type=None)
                            except Exception:
                                raw = await resp.text()
                            val = _extract_simple(raw)
                            if val is not None:
                                _slow_cache["network_interface"] = str(val)
            except Exception as e:
                _LOGGER.debug("network_interface fetch failed: %s", e)

            # --- Connection status (IP, WiFi) ---
            try:
                async with asyncio.timeout(10):
                    async with session.get(conn_status_url, auth=aiohttp.BasicAuth(username, password)) as resp:
                        if resp.status == 200:
                            try:
                                raw = await resp.json(content_type=None)
                            except Exception:
                                pass
                            else:
                                if isinstance(raw, dict):
                                    for k in ("ip_address", "ip", "address", "ipv4"):
                                        if k in raw:
                                            _slow_cache["ip_address"] = str(raw[k])
                                            break
                                    for k in ("ssid", "SSID", "wifi_ssid"):
                                        if k in raw:
                                            _slow_cache["wifi_ssid"] = str(raw[k])
                                            break
                                    for k in ("rssi", "RSSI", "signal", "signal_strength"):
                                        if k in raw:
                                            try:
                                                _slow_cache["wifi_signal"] = float(raw[k])
                                            except (ValueError, TypeError):
                                                pass
                                            break
            except Exception as e:
                _LOGGER.debug("connection_status fetch failed: %s", e)

            # --- CSMS connection status ---
            try:
                async with asyncio.timeout(10):
                    async with session.get(csms_url, auth=aiohttp.BasicAuth(username, password)) as resp:
                        if resp.status == 200:
                            try:
                                raw = await resp.json(content_type=None)
                            except Exception:
                                raw = await resp.text()
                            _LOGGER.debug("csms_status raw=%r", raw)
                            if isinstance(raw, dict):
                                status = raw.get("status") or raw.get("connected") or raw.get("state")
                                if status is not None:
                                    _slow_cache["csms_status"] = str(status)
                            elif raw is not None:
                                _slow_cache["csms_status"] = str(_extract_simple(raw) or raw)
            except Exception as e:
                _LOGGER.debug("csms_status fetch failed: %s", e)

        # Merge slow cache then fetch fast data
        result = dict(_slow_cache)

        # --- Energy meter ---
        try:
            async with asyncio.timeout(15):
                async with session.get(base_url, auth=aiohttp.BasicAuth(username, password)) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        _LOGGER.warning("Status %s from %s: %s", resp.status, base_url, text[:120])
                    else:
                        try:
                            payload = await resp.json(content_type=None)
                        except Exception:
                            _LOGGER.error("JSON decode failed URL=%s raw=%s", base_url, text[:120])
                        else:
                            for block in payload:
                                for sv in block.get("sampledValue", []):
                                    meas = sv.get("measurand")
                                    phase = sv.get("phase")
                                    raw = sv.get("value")
                                    if raw is None:
                                        continue
                                    try:
                                        val = float(raw)
                                    except (ValueError, TypeError):
                                        continue
                                    if meas == "Current.Import":
                                        if phase == "L1": result["current_l1"] = val
                                        elif phase == "L2": result["current_l2"] = val
                                        elif phase == "L3": result["current_l3"] = val
                                    elif meas == "Voltage":
                                        if phase == "L1-N": result["voltage_l1"] = val
                                        elif phase == "L2-N": result["voltage_l2"] = val
                                        elif phase == "L3-N": result["voltage_l3"] = val
                                    elif meas == "Energy.Active.Import.Register":
                                        prev = (coordinator.data or {}).get("energy")
                                        if prev is not None and val < prev:
                                            _LOGGER.warning("Energy counter decreased (%.1f -> %.1f), keeping previous", prev, val)
                                            val = prev
                                        result["energy"] = val
                                    elif meas == "Power.Active.Import":
                                        result["power"] = val
        except Exception as e:
            _LOGGER.warning("Energy meter fetch failed: %s", e)

        return result

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="garo_entity_balance_meter",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )
    data["coordinator"] = coordinator
    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        GaroBalanceSensor(coordinator, entry, host, key)
        for key in SENSOR_MAP
    )


class GaroBalanceSensor(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator, entry, host, key):
        super().__init__(coordinator)
        self._key = key
        self._entry = entry
        self._host = host
        info = SENSOR_MAP[key]
        self._attr_name = info["name"]
        self._attr_unique_id = f"garo_{key}"
        self._attr_device_class = info.get("device_class")
        self._attr_native_unit_of_measurement = info.get("unit")
        self._attr_state_class = info.get("state_class")
        self._attr_entity_category = info.get("entity_category")
        self._attr_entity_registry_enabled_default = info.get("enabled_default", True)

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._key)

    @property
    def device_info(self) -> DeviceInfo:
        entry_data = self.coordinator.hass.data[DOMAIN][self._entry.entry_id]
        scheme = "http" if entry_data.get("use_http") else "https"
        coord_data = self.coordinator.data or {}
        device_id = coord_data.get("device_id")
        unit_id = coord_data.get("unit_id")
        fw = coord_data.get("firmware_version")

        connections: set = set()
        if unit_id and "-" in unit_id:
            mac_raw = unit_id.split("-")[-1]
            if len(mac_raw) == 12 and all(c in "0123456789ABCDEFabcdef" for c in mac_raw):
                mac = ":".join(mac_raw[i:i+2] for i in range(0, 12, 2))
                connections.add((dr.CONNECTION_NETWORK_MAC, mac.upper()))

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            connections=connections,
            manufacturer=MANUFACTURER,
            name=PRODUCT_NAME,
            model="Entity Balance",
            serial_number=device_id,
            sw_version=fw,
            configuration_url=f"{scheme}://{self._host}",
        )
