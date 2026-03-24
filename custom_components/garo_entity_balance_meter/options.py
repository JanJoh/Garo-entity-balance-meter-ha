import voluptuous as vol
from homeassistant import config_entries


class GaroOptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = self.config_entry.data
        options = self.config_entry.options

        def get_value(key, default):
            return options.get(key, data.get(key, default))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("host", default=get_value("host", "")): str,
                    vol.Required("username", default=get_value("username", "")): str,
                    vol.Required("password", default=get_value("password", "")): str,
                    vol.Optional("scan_interval", default=get_value("scan_interval", 15)): int,
                    vol.Optional(
                        "ignore_tls_errors",
                        default=get_value("ignore_tls_errors", True),
                    ): bool,
                }
            ),
        )
