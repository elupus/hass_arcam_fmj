"""Arcam media player"""
import asyncio
import logging

from arcam.fmj import (
    ConnectionFailed,
    DecodeMode2CH,
    DecodeModeMCH,
    IncomingAudioFormat,
    SourceCodes
)
from arcam.fmj.client import Client
from arcam.fmj.state import State
import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerDevice
)
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_MUSIC,
    SUPPORT_SELECT_SOUND_MODE,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_TURN_ON,
    SUPPORT_TURN_OFF,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_ZONE,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import HomeAssistantType, ConfigType
from homeassistant.helpers.service import async_call_from_config

from .const import (
    SIGNAL_CLIENT_DATA,
    SIGNAL_CLIENT_STARTED,
    SIGNAL_CLIENT_STOPPED
)

DEFAULT_PORT = 50000
DEFAULT_NAME = 'Arcam FMJ'

ZONE_SCHEMA = vol.Schema({
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(SERVICE_TURN_ON): cv.SERVICE_SCHEMA
})

def _optional_zone(value):
    if value:
        return ZONE_SCHEMA(value)
    return ZONE_SCHEMA({})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.positive_int,
    vol.Optional(CONF_ZONE): {
        vol.In([1, 2]): _optional_zone
    },
    vol.Optional(CONF_SCAN_INTERVAL, default=5): cv.positive_int,
})

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass: HomeAssistantType,
                               config: ConfigType,
                               async_add_devices,
                               discovery_info=None):
    """Setup platform."""
    client = Client(
        config[CONF_HOST],
        config[CONF_PORT])

    asyncio.ensure_future(_run_client(hass, client, config[CONF_SCAN_INTERVAL]))

    async_add_devices([
        ArcamFmj(client,
                 zone_config.get(CONF_NAME, '{} - {}'.format(DEFAULT_NAME, zone)),
                 zone,
                 zone_config.get(SERVICE_TURN_ON))
        for zone, zone_config in config[CONF_ZONE].items()
    ])

async def _run_client(hass, client, interval):
    task = asyncio.Task.current_task()
    run = True
    async def _stop(_):
        nonlocal run
        run = False
        task.cancel()
        await task

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)

    def _listen(_):
        hass.helpers.dispatcher.async_dispatcher_send(
            SIGNAL_CLIENT_DATA, client.host)

    while run:
        try:
            await asyncio.wait_for(client.start(), timeout=interval)

            _LOGGER.info("Client connected %s", client.host)
            hass.helpers.dispatcher.async_dispatcher_send(
                SIGNAL_CLIENT_STARTED, client.host)

            try:
                with client.listen(_listen):
                    await client.process()
            finally:
                await client.stop()

                _LOGGER.info("Client disconnected %s", client.host)
                hass.helpers.dispatcher.async_dispatcher_send(
                    SIGNAL_CLIENT_STOPPED, client.host)

        except ConnectionFailed:
            await asyncio.sleep(interval)
        except asyncio.TimeoutError:
            continue


class ArcamFmj(MediaPlayerDevice):
    """Representation of a media device."""

    def __init__(self,
                 client: Client,
                 name: str,
                 zone: int,
                 turn_on: ConfigType):
        """Initialize device."""
        super().__init__()
        self._client = client
        self._state = State(client, zone)
        self._name = name
        self._turn_on = turn_on
        self._support = (SUPPORT_SELECT_SOURCE |
                         SUPPORT_VOLUME_SET |
                         SUPPORT_VOLUME_MUTE |
                         SUPPORT_VOLUME_STEP |
                         SUPPORT_TURN_OFF)
        if zone == 1:
            self._support |= SUPPORT_SELECT_SOUND_MODE

    def _get_2ch(self):
        """Return if source is 2 channel or not"""
        audio_format, _ = self._state.get_incoming_audio_format()
        return bool(
            audio_format in (
                IncomingAudioFormat.PCM,
                IncomingAudioFormat.ANALOGUE_DIRECT,
                None)
        )

    @property
    def should_poll(self) -> bool:
        """No need to poll."""
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
        return STATE_OFF

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        support = self._support
        if (self._state.get_power() is not None or
                self._turn_on):
            support |= SUPPORT_TURN_ON
        return support

    async def async_added_to_hass(self):
        """Once registed add listener for events."""

        await self._state.start()

        def _data(host):
            if host == self._client.host:
                self.async_schedule_update_ha_state()

        def _started(host):
            if host == self._client.host:
                self.async_schedule_update_ha_state(force_refresh=True)

        def _stopped(host):
            if host == self._client.host:
                self.async_schedule_update_ha_state(force_refresh=True)

        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_CLIENT_DATA, _data)

        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_CLIENT_STARTED, _started)

        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_CLIENT_STOPPED, _stopped)

    async def async_update(self):
        """Force update state"""
        _LOGGER.info("Update state %s", self.name)
        await self._state.update()

    async def async_mute_volume(self, mute):
        """Send mute command."""
        await self._state.set_mute(mute)
        self.async_schedule_update_ha_state()

    async def async_select_source(self, source):
        """Select a specific source."""
        value = SourceCodes[source]
        await self._state.set_source(value)
        self.async_schedule_update_ha_state()


    async def async_select_sound_mode(self, sound_mode):
        """Select a specific source."""
        if self._get_2ch():
            await self._state.set_decode_mode_2ch(
                DecodeMode2CH[sound_mode])
        else:
            await self._state.set_decode_mode_mch(
                DecodeModeMCH[sound_mode])
        self.async_schedule_update_ha_state()

    async def async_set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        await self._state.set_volume(round(volume * 99.0))
        self.async_schedule_update_ha_state()

    async def async_volume_up(self):
        """Turn volume up for media player."""
        await self._state.inc_volume()
        self.async_schedule_update_ha_state()

    async def async_volume_down(self):
        """Turn volume up for media player."""
        await self._state.dec_volume()
        self.async_schedule_update_ha_state()

    async def async_turn_on(self):
        """Turn the media player on."""
        if self._state.get_power() is not None:
            _LOGGER.info("Turning on device using connection")
            await self._state.set_power(True)
        elif self._turn_on:
            _LOGGER.info("Turning on device using service call")
            await async_call_from_config(
                self.hass, self._turn_on,
                variables=None, blocking=True,
                validate_config=False)
        else:
            _LOGGER.error("Unable to turn on")

    async def async_turn_off(self):
        """Turn the media player off."""
        await self._state.set_power(False)

    @property
    def source(self):
        """Return the current input source."""
        value = self._state.get_source()
        if value is None:
            return None
        return value.name

    @property
    def source_list(self):
        """List of available input sources."""
        return [x.name for x in self._state.get_source_list()]

    @property
    def sound_mode(self):
        """Name of the current sound mode."""
        if self._state.zn != 1:
            return None

        if self._get_2ch():
            value = self._state.get_decode_mode_2ch()
        else:
            value = self._state.get_decode_mode_mch()
        if value:
            return value.name
        return None

    @property
    def sound_mode_list(self):
        """List of available sound modes."""
        if self._state.zn != 1:
            return None

        if self._get_2ch():
            return [x.name for x in DecodeMode2CH]
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
        return None

    @property
    def media_content_type(self):
        """Content type of current playing media."""
        source = self._state.get_source()
        if source == SourceCodes.DAB:
            value = MEDIA_TYPE_MUSIC
        elif source == SourceCodes.FM:
            value = MEDIA_TYPE_MUSIC
        else:
            value = None
        return value

    @property
    def media_channel(self):
        """Channel currently playing."""
        source = self._state.get_source()
        if source == SourceCodes.DAB:
            value = self._state.get_dab_station()
        elif source == SourceCodes.FM:
            value = self._state.get_rds_information()
        else:
            value = None
        return value

    @property
    def media_artist(self):
        """Artist of current playing media, music track only."""
        source = self._state.get_source()
        if source == SourceCodes.DAB:
            value = self._state.get_dls_pdt()
        else:
            value = None
        return value

    @property
    def media_title(self):
        """Title of current playing media."""
        source = self._state.get_source()
        if source is None:
            return None

        channel = self.media_channel

        if channel:
            value = "{} - {}".format(source.name, channel)
        else:
            value = source.name
        return value
