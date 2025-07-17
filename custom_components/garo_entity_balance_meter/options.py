from homeassistant import config_entries
import voluptuous as vol

from .const import DOMAIN

class GaroOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("scan_interval", default=options.get("scan_interval", data.get("scan_interval", 15))): int,
                vol.Optional("ignore_tls_errors", default=options.get("ignore_tls_errors", data.get("ignore_tls_errors", False))): bool,
                vol.Optional("username", default=options.get("username", data.get("username", ""))): str,
                vol.Optional("password", default=options.get("password", data.get("password", ""))): str,
            })
        )

