"""Arcam media player"""
import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_NAME, CONF_ZONE
from homeassistant.components.media_player import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

DEFAULT_PORT=50000
DEFAULT_NAME='Arcam FMJ'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.positive_int,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_ZONE, default=1): cv.positive_int,
})

async def async_setup_platform(hass,
                               config,
                               async_add_devices,
                               discovery_info=None):


    from .entities.media_player import setup
    await setup(hass,
                config,
                async_add_devices,
                discovery_info=discovery_info)
