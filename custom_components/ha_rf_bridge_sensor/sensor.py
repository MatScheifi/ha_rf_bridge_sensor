import json
import logging
import os
import importlib.util
import time
import uuid

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_send, async_dispatcher_connect
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from .const import DOMAIN, CONF_TOPIC

_LOGGER = logging.getLogger(__name__)

# Signal for the coordinator to send updates to sensors
SIGNAL_UPDATE_SENSOR = "rf_bridge_update_{}"

def load_parsers():
    """Loads all parser modules from the 'parsers' directory."""
    parsers_dir = os.path.join(os.path.dirname(__file__), "parsers")
    parser_files = [f for f in os.listdir(parsers_dir) if f.endswith(".py") and not f.startswith("__")]
    
    loaded_parsers = {}
    for f in parser_files:
        module_name = f[:-3]
        try:
            spec = importlib.util.spec_from_file_location(
                f"parsers.{module_name}", os.path.join(parsers_dir, f)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "parse"):
                loaded_parsers[module_name] = module.parse
                _LOGGER.info(f"Successfully loaded RF parser: {module_name}")
            else:
                _LOGGER.warning(f"RF Parser '{module_name}' does not have a 'parse' function.")
        except Exception as e:
            _LOGGER.error(f"Failed to load RF parser '{module_name}': {e}")
    return loaded_parsers

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    # Migrate options if they are in the old format
    devices = config_entry.options.get("devices", [])
    if devices and isinstance(devices[0], str):
        _LOGGER.info("Migrating RF Bridge Sensor device configuration to new format")
        new_devices = []
        for device_id in devices:
            new_devices.append({
                "internal_id": str(uuid.uuid4()),
                "name": f"RF Device {device_id}",
                "rf_id": device_id
            })
        new_options = config_entry.options.copy()
        new_options["devices"] = new_devices
        hass.config_entries.async_update_entry(config_entry, options=new_options)

    coordinator = RFBridgeCoordinator(hass, config_entry)
    coordinator.set_async_add_entities(async_add_entities)
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator
    
    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    
    coordinator.load_configured_devices()
    await coordinator.async_subscribe()

async def update_listener(hass, entry):
    """Handle options update."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.load_configured_devices()

class RFBridgeCoordinator:
    """Handles MQTT messages and sensor discovery."""
    def __init__(self, hass, config_entry):
        self.hass = hass
        self.config_entry = config_entry
        self.async_add_entities = None
        self.topic = config_entry.data.get(CONF_TOPIC)
        self.parsers = load_parsers()
        self.created_sensors = set()
        self.configured_devices = []
        self._rf_id_map = {}
        self._discovered_devices = {}

    def set_async_add_entities(self, async_add_entities):
        self.async_add_entities = async_add_entities

    def load_configured_devices(self):
        """Load configured devices from config entry options."""
        self.configured_devices = self.config_entry.options.get("devices", [])
        self._rf_id_map = {dev["rf_id"]: dev for dev in self.configured_devices}
        _LOGGER.debug(f"Loaded configured devices: {self.configured_devices}")

    @property
    def discovered_devices(self):
        """Return recently discovered devices."""
        now = time.time()
        # Keep devices for 24 hours (86400 seconds)
        recent_devices = {
            dev_id: info
            for dev_id, info in self._discovered_devices.items()
            if now - info["last_seen"] < 86400
        }
        return recent_devices

    async def async_subscribe(self):
        """Subscribe to the MQTT topic."""
        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            try:
                payload = json.loads(message.payload)
                
                rf_data = None
                if "RfReceived" in payload and isinstance(payload.get("RfReceived"), dict):
                    rf_data = payload["RfReceived"].get("Data")
                elif "RfRaw" in payload and isinstance(payload.get("RfRaw"), dict):
                    rf_data = payload["RfRaw"].get("Data")

                if not rf_data:
                    return

                self.hass.async_create_task(self.async_process_rf_data(rf_data))

            except Exception as e:
                _LOGGER.debug(f"Error processing MQTT payload: {e}")

        await mqtt.async_subscribe(self.hass, self.topic, message_received)

    async def async_process_rf_data(self, rf_data):
        """Test RF data against all available parsers."""
        for parser_name, parse_func in self.parsers.items():
            try:
                parsed_data = parse_func(rf_data)
                if parsed_data and "id" in parsed_data:
                    _LOGGER.debug(f"Parser '{parser_name}' matched data: {parsed_data}")
                    rf_id = parsed_data["id"]
                    
                    device_config = self._rf_id_map.get(rf_id)
                    if device_config:
                        internal_id = device_config["internal_id"]
                        if internal_id not in self.created_sensors:
                            self.async_add_new_sensors(device_config, parsed_data)
                            self.created_sensors.add(internal_id)
                        
                        async_dispatcher_send(self.hass, SIGNAL_UPDATE_SENSOR.format(internal_id), parsed_data)
                    else:
                        # Don't add to discovered if it's already configured
                        if rf_id not in self._rf_id_map:
                            self._discovered_devices[rf_id] = {
                                "data": parsed_data,
                                "last_seen": time.time()
                            }
                    return
            except Exception as e:
                _LOGGER.error(f"Error in parser '{parser_name}': {e}")

    def async_add_new_sensors(self, device_config, parsed_data):
        """Add new sensor entities for a newly discovered device."""
        if not self.async_add_entities:
            _LOGGER.error("Cannot add entities because async_add_entities is not set.")
            return

        new_sensors = []
        internal_id = device_config["internal_id"]
        device_name = device_config["name"]

        if "temperature" in parsed_data:
            new_sensors.append(RFBridgeSensor(self.hass, self.config_entry, internal_id, device_name, "Temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE))
        if "humidity" in parsed_data:
            new_sensors.append(RFBridgeSensor(self.hass, self.config_entry, internal_id, device_name, "Humidity", PERCENTAGE, SensorDeviceClass.HUMIDITY))
        
        if new_sensors:
            _LOGGER.info(f"Creating sensors for configured RF device '{device_name}'.")
            self.async_add_entities(new_sensors)

class RFBridgeSensor(SensorEntity):
    """Representation of a sensor that is updated by the coordinator."""
    def __init__(self, hass, config_entry, internal_id, device_name, sensor_type, unit, device_class):
        self._hass = hass
        self._internal_id = internal_id
        self._sensor_type = sensor_type
        
        self._attr_name = f"{device_name} {sensor_type}"
        self._attr_unique_id = f"{config_entry.entry_id}_{internal_id}_{sensor_type.lower()}"
        self.entity_id = f"sensor.{device_name.lower().replace(' ', '_')}_{sensor_type.lower()}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_should_poll = False

    async def async_added_to_hass(self):
        """Register for updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self._hass,
                SIGNAL_UPDATE_SENSOR.format(self._internal_id),
                self._async_update_state,
            )
        )

    @callback
    def _async_update_state(self, data):
        """Update the sensor's state."""
        value = data.get(self._sensor_type.lower())
        if value is not None:
            self._attr_native_value = value
            self.async_write_ha_state()
new_string:
import json
import logging
import os
import importlib.util
import time
import uuid

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_send, async_dispatcher_connect
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from .const import DOMAIN, CONF_TOPIC

_LOGGER = logging.getLogger(__name__)

# Signal for the coordinator to send updates to sensors
SIGNAL_UPDATE_SENSOR = "rf_bridge_update_{}"

def load_parsers():
    """Loads all parser modules from the 'parsers' directory."""
    parsers_dir = os.path.join(os.path.dirname(__file__), "parsers")
    parser_files = [f for f in os.listdir(parsers_dir) if f.endswith(".py") and not f.startswith("__")]
    
    loaded_parsers = {}
    for f in parser_files:
        module_name = f[:-3]
        try:
            spec = importlib.util.spec_from_file_location(
                f"parsers.{module_name}", os.path.join(parsers_dir, f)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "parse"):
                loaded_parsers[module_name] = module.parse
                _LOGGER.info(f"Successfully loaded RF parser: {module_name}")
            else:
                _LOGGER.warning(f"RF Parser '{module_name}' does not have a 'parse' function.")
        except Exception as e:
            _LOGGER.error(f"Failed to load RF parser '{module_name}': {e}")
    return loaded_parsers

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    # Migrate options if they are in the old format
    devices = config_entry.options.get("devices", [])
    if devices and isinstance(devices[0], str):
        _LOGGER.info("Migrating RF Bridge Sensor device configuration to new format")
        new_devices = []
        for device_id in devices:
            new_devices.append({
                "internal_id": str(uuid.uuid4()),
                "name": f"RF Device {device_id}",
                "rf_id": device_id
            })
        new_options = config_entry.options.copy()
        new_options["devices"] = new_devices
        hass.config_entries.async_update_entry(config_entry, options=new_options)

    coordinator = RFBridgeCoordinator(hass, config_entry)
    coordinator.set_async_add_entities(async_add_entities)
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator
    
    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    
    coordinator.load_configured_devices()
    await coordinator.async_subscribe()

async def update_listener(hass, entry):
    """Handle options update."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.load_configured_devices()

class RFBridgeCoordinator:
    """Handles MQTT messages and sensor discovery."""
    def __init__(self, hass, config_entry):
        self.hass = hass
        self.config_entry = config_entry
        self.async_add_entities = None
        self.topic = config_entry.data.get(CONF_TOPIC)
        self.parsers = load_parsers()
        self.created_sensors = set()
        self.configured_devices = []
        self._rf_id_map = {}
        self._discovered_devices = {}

    def set_async_add_entities(self, async_add_entities):
        self.async_add_entities = async_add_entities

    def load_configured_devices(self):
        """Load configured devices from config entry options."""
        self.configured_devices = self.config_entry.options.get("devices", [])
        self._rf_id_map = {dev["rf_id"]: dev for dev in self.configured_devices}
        _LOGGER.debug(f"Loaded configured devices: {self.configured_devices}")

    @property
    def discovered_devices(self):
        """Return recently discovered devices."""
        now = time.time()
        # Keep devices for 24 hours (86400 seconds)
        recent_devices = {
            dev_id: info
            for dev_id, info in self._discovered_devices.items()
            if now - info["last_seen"] < 86400
        }
        return recent_devices

    async def async_subscribe(self):
        """Subscribe to the MQTT topic."""
        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            try:
                payload = json.loads(message.payload)
                
                rf_data = None
                if "RfReceived" in payload and isinstance(payload.get("RfReceived"), dict):
                    rf_data = payload["RfReceived"].get("Data")
                elif "RfRaw" in payload and isinstance(payload.get("RfRaw"), dict):
                    rf_data = payload["RfRaw"].get("Data")

                if not rf_data:
                    return

                self.hass.async_create_task(self.async_process_rf_data(rf_data))

            except Exception as e:
                _LOGGER.debug(f"Error processing MQTT payload: {e}")

        await mqtt.async_subscribe(self.hass, self.topic, message_received)

    async def async_process_rf_data(self, rf_data):
        """Test RF data against all available parsers."""
        for parser_name, parse_func in self.parsers.items():
            try:
                parsed_data = parse_func(rf_data)
                if parsed_data and "id" in parsed_data:
                    _LOGGER.debug(f"Parser '{parser_name}' matched data: {parsed_data}")
                    rf_id = parsed_data["id"]
                    
                    device_config = self._rf_id_map.get(rf_id)
                    if device_config:
                        internal_id = device_config["internal_id"]
                        if internal_id not in self.created_sensors:
                            self.async_add_new_sensors(device_config, parsed_data)
                            self.created_sensors.add(internal_id)
                        
                        async_dispatcher_send(self.hass, SIGNAL_UPDATE_SENSOR.format(internal_id), parsed_data)
                    else:
                        # Don't add to discovered if it's already configured
                        if rf_id not in self._rf_id_map:
                            self._discovered_devices[rf_id] = {
                                "data": parsed_data,
                                "last_seen": time.time()
                            }
                    return
            except Exception as e:
                _LOGGER.error(f"Error in parser '{parser_name}': {e}")

    def async_add_new_sensors(self, device_config, parsed_data):
        """Add new sensor entities for a newly discovered device."""
        if not self.async_add_entities:
            _LOGGER.error("Cannot add entities because async_add_entities is not set.")
            return

        new_sensors = []
        internal_id = device_config["internal_id"]
        device_name = device_config["name"]

        if "temperature" in parsed_data:
            new_sensors.append(RFBridgeSensor(self.hass, self.config_entry, internal_id, device_name, "Temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE))
        if "humidity" in parsed_data:
            new_sensors.append(RFBridgeSensor(self.hass, self.config_entry, internal_id, device_name, "Humidity", PERCENTAGE, SensorDeviceClass.HUMIDITY))
        
        if new_sensors:
            _LOGGER.info(f"Creating sensors for configured RF device '{device_name}'.")
            self.async_add_entities(new_sensors)

class RFBridgeSensor(SensorEntity):
    """Representation of a sensor that is updated by the coordinator."""
    def __init__(self, hass, config_entry, internal_id, device_name, sensor_type, unit, device_class):
        self._hass = hass
        self._internal_id = internal_id
        self._sensor_type = sensor_type
        
        self._attr_name = f"{device_name} {sensor_type}"
        self._attr_unique_id = f"{config_entry.entry_id}_{internal_id}_{sensor_type.lower()}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_should_poll = False

    async def async_added_to_hass(self):
        """Register for updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self._hass,
                SIGNAL_UPDATE_SENSOR.format(self._internal_id),
                self._async_update_state,
            )
        )

    @callback
    def _async_update_state(self, data):
        """Update the sensor's state."""
        value = data.get(self._sensor_type.lower())
        if value is not None:
            self._attr_native_value = value
            self.async_write_ha_state()
old_string:
import json
import logging
import os
import importlib.util
import time
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_send, async_dispatcher_connect
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from .const import DOMAIN, CONF_TOPIC

_LOGGER = logging.getLogger(__name__)

# Signal for the coordinator to send updates to sensors
SIGNAL_UPDATE_SENSOR = "rf_bridge_update_{}"

def load_parsers():
    """Loads all parser modules from the 'parsers' directory."""
    parsers_dir = os.path.join(os.path.dirname(__file__), "parsers")
    parser_files = [f for f in os.listdir(parsers_dir) if f.endswith(".py") and not f.startswith("__")]
    
    loaded_parsers = {}
    for f in parser_files:
        module_name = f[:-3]
        try:
            spec = importlib.util.spec_from_file_location(
                f"parsers.{module_name}", os.path.join(parsers_dir, f)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "parse"):
                loaded_parsers[module_name] = module.parse
                _LOGGER.info(f"Successfully loaded RF parser: {module_name}")
            else:
                _LOGGER.warning(f"RF Parser '{module_name}' does not have a 'parse' function.")
        except Exception as e:
            _LOGGER.error(f"Failed to load RF parser '{module_name}': {e}")
    return loaded_parsers

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    coordinator = RFBridgeCoordinator(hass, config_entry)
    coordinator.set_async_add_entities(async_add_entities)
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator
    
    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    
    coordinator.load_configured_devices()
    await coordinator.async_subscribe()

async def update_listener(hass, entry):
    """Handle options update."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.load_configured_devices()

class RFBridgeCoordinator:
    """Handles MQTT messages and sensor discovery."""
    def __init__(self, hass, config_entry):
        self.hass = hass
        self.config_entry = config_entry
        self.async_add_entities = None
        self.topic = config_entry.data.get(CONF_TOPIC)
        self.parsers = load_parsers()
        self.created_sensors = set()
        self.configured_devices = set()
        self._discovered_devices = {}

    def set_async_add_entities(self, async_add_entities):
        self.async_add_entities = async_add_entities

    def load_configured_devices(self):
        """Load configured devices from config entry options."""
        self.configured_devices = set(self.config_entry.options.get("devices", []))
        _LOGGER.debug(f"Loaded configured devices: {self.configured_devices}")

    @property
    def discovered_devices(self):
        """Return recently discovered devices."""
        now = time.time()
        # Keep devices for 24 hours (86400 seconds)
        recent_devices = {
            dev_id: info
            for dev_id, info in self._discovered_devices.items()
            if now - info["last_seen"] < 86400
        }
        return recent_devices

    async def async_subscribe(self):
        """Subscribe to the MQTT topic."""
        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            try:
                payload = json.loads(message.payload)
                
                rf_data = None
                if "RfReceived" in payload and isinstance(payload.get("RfReceived"), dict):
                    rf_data = payload["RfReceived"].get("Data")
                elif "RfRaw" in payload and isinstance(payload.get("RfRaw"), dict):
                    rf_data = payload["RfRaw"].get("Data")

                if not rf_data:
                    return

                self.hass.async_create_task(self.async_process_rf_data(rf_data))

            except Exception as e:
                _LOGGER.debug(f"Error processing MQTT payload: {e}")

        await mqtt.async_subscribe(self.hass, self.topic, message_received)

    async def async_process_rf_data(self, rf_data):
        """Test RF data against all available parsers."""
        for parser_name, parse_func in self.parsers.items():
            try:
                parsed_data = parse_func(rf_data)
                if parsed_data and "id" in parsed_data:
                    _LOGGER.debug(f"Parser '{parser_name}' matched data: {parsed_data}")
                    device_id = parsed_data["id"]
                    
                    if device_id in self.configured_devices:
                        if device_id not in self.created_sensors:
                            self.async_add_new_sensors(device_id, parsed_data)
                            self.created_sensors.add(device_id)
                        
                        async_dispatcher_send(self.hass, SIGNAL_UPDATE_SENSOR.format(device_id), parsed_data)
                    else:
                        self._discovered_devices[device_id] = {
                            "data": parsed_data,
                            "last_seen": time.time()
                        }
                    return
            except Exception as e:
                _LOGGER.error(f"Error in parser '{parser_name}': {e}")

    def async_add_new_sensors(self, device_id, parsed_data):
        """Add new sensor entities for a newly discovered device."""
        if not self.async_add_entities:
            _LOGGER.error("Cannot add entities because async_add_entities is not set.")
            return

        new_sensors = []
        base_name = f"RF {device_id}"

        if "temperature" in parsed_data:
            new_sensors.append(RFBridgeSensor(self.hass, self.config_entry, device_id, "Temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE))
        if "humidity" in parsed_data:
            new_sensors.append(RFBridgeSensor(self.hass, self.config_entry, device_id, "Humidity", PERCENTAGE, SensorDeviceClass.HUMIDITY))
        
        if new_sensors:
            _LOGGER.info(f"Creating sensors for configured RF device '{device_id}'.")
            self.async_add_entities(new_sensors)

class RFBridgeSensor(SensorEntity):
    """Representation of a sensor that is updated by the coordinator."""
    def __init__(self, hass, config_entry, device_id, sensor_type, unit, device_class):
        self._hass = hass
        self._device_id = device_id
        self._sensor_type = sensor_type
        
        self._attr_name = f"RF {device_id} {sensor_type}"
        self._attr_unique_id = f"{config_entry.entry_id}_{device_id}_{sensor_type.lower()}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_should_poll = False

    async def async_added_to_hass(self):
        """Register for updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self._hass,
                SIGNAL_UPDATE_SENSOR.format(self._device_id),
                self._async_update_state,
            )
        )

    @callback
    def _async_update_state(self, data):
        """Update the sensor's state."""
        value = data.get(self._sensor_type.lower())
        if value is not None:
            self._attr_native_value = value
            self.async_write_ha_state()