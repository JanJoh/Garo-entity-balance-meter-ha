import logging
import aiohttp
import async_timeout
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import aiohttp_client
import traceback
from homeassistant.helpers.entity import DeviceInfo

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
    _LOGGER.warning("GARO DEBUG: async_setup_entry called")

    options = entry.options
    data = entry.data

    host = options.get("host", data.get("host"))
    username = options.get("username", data.get("username"))
    password = options.get("password", data.get("password"))
    scan_interval = timedelta(seconds=options.get("scan_interval", data.get("scan_interval", 900)))
    ignore_tls = options.get("ignore_tls_errors", data.get("ignore_tls_errors", True))

    session = aiohttp_client.async_get_clientsession(hass)
    auth = aiohttp.BasicAuth(username, password)

    async def fetch_data():
        _LOGGER.warning("GARO DEBUG: fetch_data called")
        try:
            url = f"https://{host}/status/energy-meter"
            ssl_context = False if ignore_tls else None
            _LOGGER.warning("GARO DEBUG: Attempting request to %s", url)
            _LOGGER.warning("GARO DEBUG: SSL = %s", ssl_context)

            async with async_timeout.timeout(10):
                _LOGGER.warning("GARO DEBUG: Entering session.get()...")
                async with session.get(url, auth=auth, ssl=ssl_context) as response:
                    _LOGGER.warning("GARO DEBUG: Got response with status %s", response.status)

                    raw = await response.json()
                    _LOGGER.warning("GARO DEBUG: RAW JSON = %s", raw)

                    data = {}

                    if not isinstance(raw, list):
                        _LOGGER.error("GARO DEBUG: Unexpected type for raw JSON: %s", type(raw))
                        return {}

                    for idx, entry in enumerate(raw):
                        _LOGGER.warning("GARO DEBUG: Entry #%d = %s", idx, entry)
                        if not isinstance(entry, dict):
                            _LOGGER.warning("GARO DEBUG: Skipping non-dict entry: %s", entry)
                            continue

                        sampled = entry.get("sampledValue", [])
                        _LOGGER.warning("GARO DEBUG: sampledValue block = %s", sampled)
                        for item in sampled:
                            measurand = item.get("measurand")
                            phase = item.get("phase")
                            value = item.get("value")
                            _LOGGER.warning("GARO DEBUG: measurand=%s, phase=%s, value=%s", measurand, phase, value)

                            if value is None:
                                continue

                            try:
                                value = float(value)
                            except ValueError:
                                continue

                            if measurand == "Current.Import":
                                if phase == "L1":
                                    data["current_l1"] = value
                                elif phase == "L2":
                                    data["current_l2"] = value
                                elif phase == "L3":
                                    data["current_l3"] = value
                            elif measurand == "Voltage":
                                if phase == "L1-N":
                                    data["voltage_l1"] = value
                                elif phase == "L2-N":
                                    data["voltage_l2"] = value
                                elif phase == "L3-N":
                                    data["voltage_l3"] = value
                            elif measurand == "Energy.Active.Import.Register":
                                data["energy"] = value
                            elif measurand == "Power.Active.Import":
                                data["power"] = value

                    if not data:
                        _LOGGER.warning("GARO DEBUG: Parsed data dictionary is EMPTY")
                    else:
                        _LOGGER.warning("GARO DEBUG: Final parsed data = %s", data)

                    return data

        except Exception as err:
            _LOGGER.error("GARO DEBUG: Exception in fetch_data: %s", err)
            _LOGGER.warning("GARO DEBUG: Traceback:\n%s", traceback.format_exc())
            return {}

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Garo Entity Balance Meter",
        update_method=fetch_data,
        update_interval=scan_interval,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning("Initial data fetch failed: %s", e)

    entities = [GaroSensor(coordinator, sensor_type, entry) for sensor_type in SENSOR_TYPES]
    _LOGGER.warning("GARO DEBUG: Registered sensor types: %s", [e._sensor_type for e in entities])
    async_add_entities(entities)


class GaroSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, sensor_type, entry):
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._entry = entry
        self._attr_name = SENSOR_TYPES[sensor_type][0]
        self._attr_native_unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._attr_device_class = SENSOR_TYPES[sensor_type][2]
        self._attr_state_class = SENSOR_TYPES[sensor_type][3]

    @property
    def unique_id(self):
        return f"garo_{self._sensor_type}"


    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(self._entry.domain, self._entry.entry_id)},
            name="Garo Energy Meter",
            manufacturer="Garo",
            model="Entity Balance Meter",
            configuration_url=f"https://{self._entry.options['host']}"
        )


    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(self._entry.domain, self._entry.entry_id)},
            name="Garo Energy Meter",
            manufacturer="Garo",
            model="Entity Balance Meter",
            configuration_url=f"https://{self._entry.options['host']}"
        )

    @property
    def state(self):
        _LOGGER.warning("GARO DEBUG: state() called for %s", self._sensor_type)
        data = self.coordinator.data
        if isinstance(data, dict):
            value = data.get(self._sensor_type)
            _LOGGER.warning("GARO DEBUG: Sensor [%s] has value = %s", self._sensor_type, value)
            return value
        _LOGGER.warning("Unexpected data format: %s", type(data))
        return None

