"""Implementation of a arcam media player entity"""

from homeassistant.components.media_player import PLATFORM_SCHEMA, MediaPlayerDevice
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_CHANNEL, SUPPORT_NEXT_TRACK,
    SUPPORT_PLAY_MEDIA, SUPPORT_PREVIOUS_TRACK, SUPPORT_SELECT_SOURCE,
    SUPPORT_TURN_OFF, SUPPORT_TURN_ON, SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_STEP, SUPPORT_VOLUME_SET, SUPPORT_SELECT_SOUND_MODE)

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_NAME, CONF_ZONE, STATE_ON, STATE_OFF
from arcam.fmj.client import Client
from arcam.fmj.state import State
from arcam.fmj import SourceCodes, IncomingAudioFormat, DecodeMode2CH, DecodeModeMCH

class ArcamFmj(MediaPlayerDevice):
    """Representation of a media device."""

    def __init__(self, config):
        """Initialize device."""
        super().__init__()
        self._client = Client(
            config[CONF_HOST],
            config[CONF_PORT])
        self._state = State(self._client, config[CONF_ZONE])
        self._name = config[CONF_NAME]
        self._support = (SUPPORT_SELECT_SOURCE |
                         SUPPORT_TURN_OFF |
                         SUPPORT_VOLUME_SET |
                         SUPPORT_SELECT_SOUND_MODE |
                         SUPPORT_VOLUME_MUTE |
                         SUPPORT_VOLUME_STEP)

        def _listen(packet):
            self.async_schedule_update_ha_state()

        self._client._listen.add(_listen)

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

    async def async_update(self):
        """Update state"""
        if not self._client.connected:
            if self._client.started:
                await self._state.stop()
                await self._client.stop()
            await self._client.start()
            await self._state.start()

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
