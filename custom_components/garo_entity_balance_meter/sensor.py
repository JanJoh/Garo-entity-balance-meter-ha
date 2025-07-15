import logging
import aiohttp
import async_timeout
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed, CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    "power": ("Power Consumption", "W", "power", "measurement"),
    "energy": ("Energy Total", "Wh", "energy", "total_increasing"),
    "current_l1": ("Current L1", "A", "current", "measurement"),
    "current_l2": ("Current L2", "A", "current", "measurement"),
    "current_l3": ("Current L3", "A", "current", "measurement"),
    "voltage_l1": ("Voltage L1", "V", "voltage", "measurement"),
    "voltage_l2": ("Voltage L2", "V", "voltage", "measurement"),
    "voltage_l3": ("Voltage L3", "V", "voltage", "measurement"),
}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    _LOGGER.debug("Setting up Garo Entity Balance Meter sensors from config entry")

    session = aiohttp.ClientSession()
    auth = aiohttp.BasicAuth(entry.data["username"], entry.data["password"])
    host = entry.data["host"]
    scan_interval = timedelta(seconds=entry.data.get("scan_interval", 900))
    ignore_tls = entry.data.get("ignore_tls_errors", True)


    async def fetch_data():
        try:
            async with async_timeout.timeout(10):
                url = f"https://{host}/status/energy-meter"
                _LOGGER.debug("Requesting data from %s", url)
                async with session.get(url, auth=auth, ssl=not ignore_tls) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"HTTP error {response.status}")
                    result = await response.json()
                    _LOGGER.debug("Received data: %s", result)
                    return result
        except Exception as e:
            _LOGGER.error("Failed to fetch data: %s", e)
            raise UpdateFailed(f"Error fetching data: {e}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Garo Entity Balance Meter",
        update_method=fetch_data,
        update_interval=scan_interval,
    )

    await coordinator.async_refresh()

    sensors = [GaroSensor(coordinator, key) for key in SENSOR_TYPES]
    async_add_entities(sensors)


class GaroSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, sensor_type):
        super().__init__(coordinator)
        self.type = sensor_type
        name, unit, device_class, state_class = SENSOR_TYPES[sensor_type]
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_unique_id = f"garo_entity_balance_meter_{sensor_type}"
        self._attr_device_info = {
            "identifiers": {("garo_entity_balance_meter", "main_meter")},
            "name": "Garo Entity Balance Meter",
            "manufacturer": "Garo",
            "model": "DLB Energy Meter",
            "sw_version": "1.0"
        }

    @property
    def native_value(self):
        data = self.coordinator.data or []
        for item in data:
            for val in item.get("sampledValue", []):
                measurand = val.get("measurand")
                phase = val.get("phase", "")

                if self.type == "power" and measurand == "Power.Active.Import":
                    return float(val["value"])
                if self.type == "energy" and measurand == "Energy.Active.Import.Register":
                    return float(val["value"])
                if self.type.startswith("current") and measurand == "Current.Import":
                    phase_map = {"current_l1": "L1", "current_l2": "L2", "current_l3": "L3"}
                    if phase == phase_map[self.type]:
                        return float(val["value"])
                if self.type.startswith("voltage") and measurand == "Voltage":
                    phase_map = {"voltage_l1": "L1-N", "voltage_l2": "L2-N", "voltage_l3": "L3-N"}
                    if phase == phase_map[self.type]:
                        return float(val["value"])
        return None
