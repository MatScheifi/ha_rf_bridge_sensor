"""The RF Bridge Sensor integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from .const import DOMAIN

PLATFORMS = ["sensor"]
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry):
    """Set up RF Bridge Sensor from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.info("Setting up RF Bridge Sensor entry: %s", entry.entry_id)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="RF Bridge",
        manufacturer="RF Bridge Sensor",
    )
    
    # Forward the setup to the sensor platform.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.info("Options update listener in __init__.py triggered, reloading entry: %s", entry.entry_id)
    # This reloads the integration, causing sensor.py to run again with the new list
    await hass.config_entries.async_reload(entry.entry_id)
    
async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    _LOGGER.info("Unloading RF Bridge Sensor entry: %s", entry.entry_id)
    # Forward the unload to the sensor platform.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
