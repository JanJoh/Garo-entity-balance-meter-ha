import logging
import aiohttp
import async_timeout

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    "power": ("Power Consumption", "W"),
    "energy": ("Energy Total", "Wh"),
    "current_l1": ("Current L1", "A"),
    "current_l2": ("Current L2", "A"),
    "current_l3": ("Current L3", "A"),
    "voltage_l1": ("Voltage L1", "V"),
    "voltage_l2": ("Voltage L2", "V"),
    "voltage_l3": ("Voltage L3", "V"),
}

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    host = config.get("host")
    username = config.get("username")
    password = config.get("password")
    scan_interval = config.get("scan_interval", 900)

    session = aiohttp.ClientSession()
    auth = aiohttp.BasicAuth(username, password)

    async def fetch_data():
        try:
            async with async_timeout.timeout(10):
                url = f"https://{host}/status/energy-meter"
                async with session.get(url, auth=auth, ssl=False) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"HTTP error {response.status}")
                    return await response.json()
        except Exception as e:
            _LOGGER.error("Failed to fetch data: %s", e)
            raise UpdateFailed(f"Error: {e}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Garo Entity Balance Meter",
        update_method=fetch_data,
        update_interval=scan_interval
    )

    await coordinator.async_refresh()

    sensors = [GaroSensor(coordinator, key) for key in SENSOR_TYPES]
    async_add_entities(sensors, True)


class GaroSensor(SensorEntity):
    def __init__(self, coordinator, sensor_type):
        self.coordinator = coordinator
        self.type = sensor_type
        self._attr_name = SENSOR_TYPES[sensor_type][0]
        self._attr_native_unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._attr_device_class = self._get_device_class(sensor_type)
        self._attr_unique_id = f"garo_entity_balance_meter_{sensor_type}"

        if sensor_type == "energy":
            self._attr_state_class = "total_increasing"
        else:
            self._attr_state_class = "measurement"

        self._attr_device_info = {
            "identifiers": {("garo_entity_balance_meter", "main_meter")},
            "name": "Garo Entity Balance Meter",
            "manufacturer": "Garo",
            "model": "DLB Energy Meter",
            "sw_version": "1.0"
        }

    def _get_device_class(self, sensor_type):
        if sensor_type.startswith("current"):
            return "current"
        if sensor_type.startswith("voltage"):
            return "voltage"
        if sensor_type == "power":
            return "power"
        if sensor_type == "energy":
            return "energy"
        return None

    @property
    def native_value(self):
        data = self.coordinator.data
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

    @property
    def available(self):
        return self.coordinator.last_update_success

    async def async_update(self):
        await self.coordinator.async_request_refresh()