import voluptuous as vol
import uuid
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN, CONF_TOPIC

# Schema for setting up the integration
DATA_SCHEMA = vol.Schema({
    vol.Required("name", default="RF Bridge Sensors"): str,
    vol.Required(CONF_TOPIC, default="tele/RF_Bridge/RESULT"): str,
})

class RFBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RF Bridge Sensor."""
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return RFBridgeOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title=user_input["name"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA
        )

class RFBridgeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handles CRUD operations for RF Bridge devices."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)
        self.coordinator = None
        self.device_info = {}

    async def async_step_init(self, user_input=None):
        """Main menu."""
        self.coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        
        return self.async_show_menu(
            step_id="init",
            menu_options=["add", "edit", "delete"],
        )

    async def async_step_add(self, user_input=None):
        """Add menu."""
        return self.async_show_menu(
            step_id="add",
            menu_options=["add_manual", "add_from_discovered"]
        )

    async def async_step_add_manual(self, user_input=None):
        """Form to add a device manually."""
        if user_input is not None:
            devices = self.options.get("devices", [])
            new_device = {
                "internal_id": str(uuid.uuid4()),
                "name": user_input["name"],
                "rf_id": user_input["rf_id"],
            }
            devices.append(new_device)
            self.options["devices"] = devices
            return self.async_create_entry(title="", data=self.options)

        return self.async_show_form(
            step_id="add_manual",
            data_schema=vol.Schema({
                vol.Required("name"): str,
                vol.Required("rf_id"): str,
            })
        )

    async def async_step_add_from_discovered(self, user_input=None):
        """Form to add a device from the discovered list."""
        discovered = self.coordinator.discovered_devices
        if not discovered:
            return self.async_abort(reason="no_discovered_devices")
        
        if user_input is not None:
            self.device_info['rf_id'] = user_input['rf_id']
            return await self.async_step_name_discovered()

        discovered_map = {
            dev_id: f"{dev_id} (seen: {dt_util.as_local(dt_util.utc_from_timestamp(info['last_seen'])).strftime('%d-%b %H:%M')})"
            for dev_id, info in discovered.items()
        }
        
        return self.async_show_form(
            step_id="add_from_discovered",
            data_schema=vol.Schema({
                vol.Required("rf_id"): vol.In(discovered_map)
            })
        )

    async def async_step_name_discovered(self, user_input=None):
        """Form to give a name to a discovered device."""
        if user_input is not None:
            devices = self.options.get("devices", [])
            new_device = {
                "internal_id": str(uuid.uuid4()),
                "name": user_input["name"],
                "rf_id": self.device_info["rf_id"],
            }
            devices.append(new_device)
            self.options["devices"] = devices
            return self.async_create_entry(title="", data=self.options)

        return self.async_show_form(
            step_id="name_discovered",
            data_schema=vol.Schema({vol.Required("name"): str}),
            description_placeholders={"rf_id": self.device_info["rf_id"]}
        )

    async def async_step_edit(self, user_input=None):
        """Form to select a device to edit."""
        configured_devices = self.options.get("devices", [])
        if not configured_devices:
            return self.async_abort(reason="no_devices_to_edit")

        if user_input is not None:
            self.device_info['internal_id'] = user_input['internal_id']
            return await self.async_step_edit_form()

        device_map = {
            dev["internal_id"]: f"{dev['name']} ({dev['rf_id']})" for dev in configured_devices
        }

        return self.async_show_form(
            step_id="edit",
            data_schema=vol.Schema({
                vol.Required("internal_id"): vol.In(device_map)
            })
        )

    async def async_step_edit_form(self, user_input=None):
        """Form to edit device name and RF ID."""
        if user_input is not None:
            devices = self.options.get("devices", [])
            for i, dev in enumerate(devices):
                if dev["internal_id"] == self.device_info["internal_id"]:
                    devices[i]["name"] = user_input["name"]
                    devices[i]["rf_id"] = user_input["rf_id"]
                    break
            self.options["devices"] = devices
            return self.async_create_entry(title="", data=self.options)

        device_to_edit = next(
            dev for dev in self.options.get("devices", []) 
            if dev["internal_id"] == self.device_info["internal_id"]
        )

        return self.async_show_form(
            step_id="edit_form",
            data_schema=vol.Schema({
                vol.Required("name", default=device_to_edit["name"]): str,
                vol.Required("rf_id", default=device_to_edit["rf_id"]): str,
            })
        )

    async def async_step_delete(self, user_input=None):
        """Form to delete devices."""
        configured_devices = self.options.get("devices", [])
        if not configured_devices:
            return self.async_abort(reason="no_devices_to_delete")

        if user_input is not None:
            to_delete = user_input["internal_ids"]
            devices = [
                dev for dev in configured_devices if dev["internal_id"] not in to_delete
            ]
            self.options["devices"] = devices
            return self.async_create_entry(title="", data=self.options)
        
        device_map = {
            dev["internal_id"]: f"{dev['name']} ({dev['rf_id']})" for dev in configured_devices
        }

        return self.async_show_form(
            step_id="delete",
            data_schema=vol.Schema({
                vol.Required("internal_ids"): cv.multi_select(device_map)
            })
        )