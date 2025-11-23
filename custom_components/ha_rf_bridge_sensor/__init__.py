"""The RF Bridge Sensor integration."""
from .const import DOMAIN

PLATFORMS = ["sensor"]

async def async_setup_entry(hass, entry):
    """Set up RF Bridge Sensor from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Forward the setup to the sensor platform.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    # Forward the unload to the sensor platform.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
