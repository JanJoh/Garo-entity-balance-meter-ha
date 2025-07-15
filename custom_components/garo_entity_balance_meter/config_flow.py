import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

DOMAIN = "garo_entity_balance_meter"

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("username"): str,
        vol.Required("password"): str,
        vol.Optional("scan_interval", default=15): cv.positive_int,
    }
)

class GaroMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="Garo Entity Balance Meter", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )
