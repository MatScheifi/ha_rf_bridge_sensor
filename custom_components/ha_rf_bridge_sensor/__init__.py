"""The RF Bridge Sensor integration."""
from homeassistant.helpers import device_registry as dr
from .const import DOMAIN

PLATFORMS = ["sensor"]

async def async_setup_entry(hass, entry):
    """Set up RF Bridge Sensor from a config entry."""
    hass.data.setdefault(DOMAIN, {})

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

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    # Forward the unload to the sensor platform.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
