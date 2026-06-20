from __future__ import annotations
import logging, asyncio, aiohttp
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import aiohttp_client
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfPower, UnitOfEnergy
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD,
    CONF_SCAN_INTERVAL, CONF_IGNORE_TLS_ERRORS, CONF_USE_HTTP,
    DEFAULT_SCAN_INTERVAL, MANUFACTURER, PRODUCT_NAME, API_PATH,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_MAP = {
    "power":      {"name": "Grid Power",          "device_class": SensorDeviceClass.POWER,   "unit": UnitOfPower.WATT,              "state_class": SensorStateClass.MEASUREMENT},
    "energy":     {"name": "Grid Energy",         "device_class": SensorDeviceClass.ENERGY,  "unit": UnitOfEnergy.WATT_HOUR,        "state_class": SensorStateClass.TOTAL_INCREASING},
    "current_l1": {"name": "Grid L1 Current",     "device_class": SensorDeviceClass.CURRENT, "unit": UnitOfElectricCurrent.AMPERE,  "state_class": SensorStateClass.MEASUREMENT},
    "current_l2": {"name": "Grid L2 Current",     "device_class": SensorDeviceClass.CURRENT, "unit": UnitOfElectricCurrent.AMPERE,  "state_class": SensorStateClass.MEASUREMENT},
    "current_l3": {"name": "Grid L3 Current",     "device_class": SensorDeviceClass.CURRENT, "unit": UnitOfElectricCurrent.AMPERE,  "state_class": SensorStateClass.MEASUREMENT},
    "voltage_l1": {"name": "Grid L1 Voltage",     "device_class": SensorDeviceClass.VOLTAGE, "unit": UnitOfElectricPotential.VOLT,  "state_class": SensorStateClass.MEASUREMENT},
    "voltage_l2": {"name": "Grid L2 Voltage",     "device_class": SensorDeviceClass.VOLTAGE, "unit": UnitOfElectricPotential.VOLT,  "state_class": SensorStateClass.MEASUREMENT},
    "voltage_l3": {"name": "Grid L3 Voltage",     "device_class": SensorDeviceClass.VOLTAGE, "unit": UnitOfElectricPotential.VOLT,  "state_class": SensorStateClass.MEASUREMENT},
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]

    def opt(key):
        return entry.options.get(key, entry.data.get(key))

    host = opt(CONF_HOST)
    username = opt(CONF_USERNAME)
    password = opt(CONF_PASSWORD)
    scan_interval = opt(CONF_SCAN_INTERVAL) or DEFAULT_SCAN_INTERVAL
    ignore_tls = opt(CONF_IGNORE_TLS_ERRORS)
    use_http = opt(CONF_USE_HTTP)

    scheme = "http" if use_http else "https"
    url = f"{scheme}://{host}{API_PATH}"
    session = data.get("session") or aiohttp_client.async_get_clientsession(hass, verify_ssl=not ignore_tls)

    async def _async_update_data():
        result = {}
        try:
            async with asyncio.timeout(15):
                async with session.get(url, auth=aiohttp.BasicAuth(username, password)) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        _LOGGER.warning("Status %s from %s: %s", resp.status, url, text[:120])
                        return result
                    try:
                        payload = await resp.json(content_type=None)
                    except Exception:
                        _LOGGER.error("JSON decode failed URL=%s raw=%s", url, text[:120])
                        return result

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
            _LOGGER.warning("Fetch failed: %s", e)

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
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, host, key):
        super().__init__(coordinator)
        self._key = key
        self._entry = entry
        self._host = host
        info = SENSOR_MAP[key]
        self._attr_name = info["name"]
        self._attr_unique_id = f"{host}_{key}"
        self._attr_device_class = info["device_class"]
        self._attr_native_unit_of_measurement = info["unit"]
        self._attr_state_class = info["state_class"]

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._key)

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.hass.data[DOMAIN][self._entry.entry_id]
        scheme = "http" if data.get("use_http") else "https"
        return DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            manufacturer=MANUFACTURER,
            name=PRODUCT_NAME,
            model="Entity Balance",
            configuration_url=f"{scheme}://{self._host}",
        )
