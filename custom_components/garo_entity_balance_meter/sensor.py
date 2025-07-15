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

    # Pull from options if available, fallback to data
    options = entry.options
    data = entry.data

    host = options.get("host", data.get("host"))
    username = options.get("username", data.get("username"))
    password = options.get("password", data.get("password"))
    scan_interval = timedelta(seconds=options.get("scan_interval", data.get("scan_interval", 900)))
    ignore_tls = options.get("ignore_tls_errors", data.get("ignore_tls_errors", True))

    session = aiohttp.ClientSession()
    auth = aiohttp.BasicAuth(username, password)

    async def fetch_data():
        try:
            url = f"https://{host}/meter_data.json"
            ssl_context = False if ignore_tls else None

            async with async_timeout.timeout(10):
                async with session.get(url, auth=auth, ssl=ssl_context) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"HTTP error {response.status}")
                    return await response.json()

        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Garo Entity Balance Meter",
        update_method=fetch_data,
        update_interval=scan_interval,
    )

    await coordinator.async_config_entry_first_refresh()

    entities = [
        GaroSensor(coordinator, sensor_type)
        for sensor_type in SENSOR_TYPES
    ]
    async_add_entities(entities)


class GaroSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, sensor_type):
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_name = SENSOR_TYPES[sensor_type][0]
        self._attr_unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._attr_device_class = SENSOR_TYPES[sensor_type][2]
        self._attr_state_class = SENSOR_TYPES[sensor_type][3]

    @property
    def unique_id(self):
        return f"garo_{self._sensor_type}"

    @property
    def state(self):
        return self.coordinator.data.get(self._sensor_type)
