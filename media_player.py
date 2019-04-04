"""Arcam media player"""
import asyncio
import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from arcam.fmj import (
    DecodeMode2CH,
    DecodeModeMCH,
    IncomingAudioFormat,
    SourceCodes
)
from arcam.fmj.client import Client
from arcam.fmj.state import State
from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerDevice
)
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_CHANNEL,
    SUPPORT_NEXT_TRACK,
    SUPPORT_PLAY_MEDIA,
    SUPPORT_PREVIOUS_TRACK,
    SUPPORT_SELECT_SOUND_MODE,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_ZONE,
    STATE_OFF,
    STATE_ON
)

from .const import (
    SIGNAL_CLIENT_DATA,
    SIGNAL_CLIENT_STARTED,
    SIGNAL_CLIENT_STOPPED
)

DEFAULT_PORT=50000
DEFAULT_NAME='Arcam FMJ'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.positive_int,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_ZONE, default=1): cv.positive_int,
})

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass,
                               config,
                               async_add_devices,
                               discovery_info=None):

    client = Client(
        config[CONF_HOST],
        config[CONF_PORT])

    #hass.async_add_job(run_client(hass, client))
    asyncio.ensure_future(run_client(hass, client))

    async_add_devices([
        ArcamFmj(client,
                 config[CONF_NAME],
                 config[CONF_ZONE])])

async def run_client(hass, client):
    def _listen(packet):
        hass.helpers.dispatcher.async_dispatcher_send(
            SIGNAL_CLIENT_DATA, client._host)

    while True:
        try:
            await client.start()

            hass.helpers.dispatcher.async_dispatcher_send(
                SIGNAL_CLIENT_STARTED, client._host)

            with client.listen(_listen):
                await client.process()

            hass.helpers.dispatcher.async_dispatcher_send(
                SIGNAL_CLIENT_STOPPED, client._host)
        except (ConnectionError, OSError):
            await asyncio.sleep(1.0)
            pass
        finally:
            await client.stop()



class ArcamFmj(MediaPlayerDevice):
    """Representation of a media device."""

    def __init__(self, client: Client, name: str, zone: int):
        """Initialize device."""
        super().__init__()
        self._client = client
        self._state = State(client, zone)
        self._name = name
        self._support = (SUPPORT_SELECT_SOURCE |
                         SUPPORT_TURN_OFF |
                         SUPPORT_VOLUME_SET |
                         SUPPORT_SELECT_SOUND_MODE |
                         SUPPORT_VOLUME_MUTE |
                         SUPPORT_VOLUME_STEP)

    def _get_2ch(self):
        """Return if source is 2 channel or not"""
        f, _ = self._state.get_incoming_audio_format()
        if (f == IncomingAudioFormat.PCM or
            f == IncomingAudioFormat.ANALOGUE_DIRECT or
            f == None):
            return True
        else:
            return False


    @property
    def name(self):
        """Return the name of the controlled device."""
        return self._name            

    @property
    def state(self):
        """Return the state of the device."""
        if self._state.get_power():
            return STATE_ON
        else:
            return STATE_OFF

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return self._support

    async def async_added_to_hass(self):
        """Once registed add listener for events."""

        def _data(host):
            if host == self._client._host:
                self.async_schedule_update_ha_state()

        async def _update():
            await self._state.update()
            self.async_schedule_update_ha_state()

        def _started(host):
            if host == self._client._host:
                self.hass.async_add_job(_update())

        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_CLIENT_DATA, _data)

        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_CLIENT_STARTED, _started)

    async def async_update(self):
        """Update state"""
        pass

    async def async_mute_volume(self, mute):
        """Send mute command."""
        await self._state.set_mute(mute)

    async def async_select_source(self, source):
        """Select a specific source."""
        value = SourceCodes[source]
        await self._state.set_source(value)

    async def async_select_sound_mode(self, sound_mode):
        """Select a specific source."""
        if self._get_2ch():
            await self._state.set_decode_mode_2ch(
                DecodeMode2CH[sound_mode])
        else:
            await self._state.set_decode_mode_mch(
                DecodeModeMCH[sound_mode])

    async def async_set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        await self._state.set_volume(round(volume * 99.0))

    async def async_volume_up(self):
        """Turn volume up for media player."""
        await self._state.inc_volume()

    async def async_volume_down(self):
        """Turn volume up for media player."""
        await self._state.dec_volume()

    @property
    def source(self):
        """Return the current input source."""
        value = self._state.get_source()
        if value:
            return value.name
        else:
            return None

    @property
    def source_list(self):
        """List of available input sources."""
        return [x.name for x in SourceCodes]

    @property
    def sound_mode(self):
        """Name of the current sound mode."""
        if self._get_2ch():
            value = self._state.get_decode_mode_2ch()
        else:
            value = self._state.get_decode_mode_mch()
        if value:
            return value.name
        else:
            return None

    @property
    def sound_mode_list(self):
        """List of available sound modes."""
        if self._get_2ch():
            return [x.name for x in DecodeMode2CH]
        else:
            return [x.name for x in DecodeModeMCH]

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        value = self._state.get_mute()
        if value is None:
            return None
        return value

    @property
    def volume_level(self):
        value = self._state.get_volume()
        if value:
            return value / 99.0
        else:
            return None

    @property
    def media_title(self):
        """Title of current playing media."""
        value = self._state.get_source()
        if value:
            return value.name
        else:
            return None
