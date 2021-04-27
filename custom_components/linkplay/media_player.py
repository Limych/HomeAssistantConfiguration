"""
Support for Linkplay based devices.

For more details about this platform, please refer to the documentation at
https://github.com/nagyrobi/home-assistant-custom-components-linkplay
"""

import binascii
import json
from json import loads, dumps
import upnpclient
import netdisco.ssdp
import logging
import urllib.request
import xml.etree.ElementTree as ET
import time
from datetime import timedelta
import socket
import requests
import string
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.util.dt import utcnow
from homeassistant.components import media_source
#from homeassistant.auth.models import RefreshToken
#from homeassistant.components.http.auth import async_sign_path
from homeassistant.util import Throttle
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_DEVICE_CLASS,
    CONF_HOST,
    CONF_NAME,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_IDLE,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
)
from homeassistant.components.media_player import (
    DEVICE_CLASS_SPEAKER, 
    BrowseMedia, 
    MediaPlayerEntity,
)
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_MUSIC,
    MEDIA_TYPE_URL,
    MEDIA_TYPE_TRACK,
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_MUSIC,
    SUPPORT_NEXT_TRACK,
    SUPPORT_PAUSE,
    SUPPORT_PLAY,
    SUPPORT_PLAY_MEDIA,
    SUPPORT_PREVIOUS_TRACK,
    SUPPORT_SEEK,
    SUPPORT_BROWSE_MEDIA,
    SUPPORT_SELECT_SOUND_MODE,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_SHUFFLE_SET,
    SUPPORT_REPEAT_SET,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
    SUPPORT_STOP,
    REPEAT_MODE_ALL,
    REPEAT_MODE_OFF,
    REPEAT_MODE_ONE,
)
from homeassistant.components.media_player.errors import BrowseError
from . import DOMAIN, ATTR_MASTER

_LOGGER = logging.getLogger(__name__)

ATTR_SLAVE = 'slave'
ATTR_LINKPLAY_GROUP = 'linkplay_group'
ATTR_FWVER = 'firmware'
ATTR_TRCNT = 'track_count'
ATTR_TRCRT = 'track_current'
ATTR_DEBUG = 'debug_info'

PARALLEL_UPDATES = 0

ICON_DEFAULT = 'mdi:speaker'
ICON_PLAYING = 'mdi:speaker-wireless'
ICON_MUTED = 'mdi:speaker-off'
ICON_MULTIROOM = 'mdi:speaker-multiple'
ICON_BLUETOOTH = 'mdi:speaker-bluetooth'
ICON_PUSHSTREAM = 'mdi:cast-audio'

CONF_NAME = 'name'
CONF_LASTFM_API_KEY = 'lastfm_api_key'
CONF_SOURCES = 'sources'
CONF_COMMONSOURCES = 'common_sources'
CONF_ICECAST_METADATA = 'icecast_metadata'
CONF_MULTIROOM_WIFIDIRECT = 'multiroom_wifidirect'
CONF_VOLUME_STEP = 'volume_step'

LASTFM_API_BASE = 'http://ws.audioscrobbler.com/2.0/?method='
MAX_VOL = 100
FW_MROOM_RTR_MIN = '4.2.8020'
UPNP_TIMEOUT = 2
TCPPORT = 8899
ICE_THROTTLE = timedelta(seconds=60)
UNA_THROTTLE = timedelta(seconds=120)
MROOM_UJWDIR = timedelta(seconds=20)
MROOM_UJWROU = timedelta(seconds=3)
ROOTDIR_USB = '/media/sda1/'

DEFAULT_ICECAST_UPDATE = 'StationName'
DEFAULT_MULTIROOM_WIFIDIRECT = False
DEFAULT_VOLUME_STEP = 5

PLATFORM_SCHEMA = vol.All(cv.PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_NAME): cv.string,
    vol.Optional(CONF_ICECAST_METADATA, default=DEFAULT_ICECAST_UPDATE): vol.In(['Off', 'StationName', 'StationNameSongTitle']),
    vol.Optional(CONF_MULTIROOM_WIFIDIRECT, default=DEFAULT_MULTIROOM_WIFIDIRECT): cv.boolean,
    vol.Optional(CONF_SOURCES): cv.ensure_list,
    vol.Optional(CONF_COMMONSOURCES): cv.ensure_list,
    vol.Optional(CONF_LASTFM_API_KEY): cv.string,
    vol.Optional(CONF_VOLUME_STEP, default=DEFAULT_VOLUME_STEP): vol.All(int, vol.Range(min=1, max=25)),
}))

SOUND_MODES = {'0': 'Normal', '1': 'Classic', '2': 'Pop', '3': 'Jazz', '4': 'Vocal'}

SOURCES = {'bluetooth': 'Bluetooth', 
           'line-in': 'Line-in', 
           'line-in2': 'Line-in 2', 
           'optical': 'Optical', 
           'co-axial': 'Coaxial', 
           'HDMI': 'HDMI', 
           'udisk': 'USB disk', 
           'TFcard': 'SD card', 
           'RCA': 'RCA', 
           'XLR': 'XLR', 
           'FM': 'FM', 
           'cd': 'CD'}

SOURCES_MAP = {'-1': 'Idle', 
               '0': 'Idle', 
               '1': 'Airplay', 
               '2': 'DLNA',
               '3': 'QPlay',
               '10': 'Network', 
               '11': 'udisk', 
               '16': 'TFcard',
               '20': 'API', 
               '21': 'udisk', 
               '30': 'Alarm', 
               '31': 'Spotify', 
               '40': 'line-in', 
               '41': 'bluetooth', 
               '43': 'optical',
               '44': 'RCA',
               '45': 'co-axial',
               '46': 'FM',
               '47': 'line-in2', 
               '48': 'XLR',
               '49': 'HDMI',
               '50': 'cd',
               '52': 'TFcard',
               '60': 'Talk',
               '99': 'Idle'}

SOURCES_LIVEIN = ['-1', '0', '40', '41', '43', '44', '45', '46', '47', '48', '49', '50', '99']
SOURCES_STREAM = ['1', '2', '3', '10', '30']
SOURCES_LOCALF = ['11', '16', '20', '21', '52', '60']

class LinkPlayData:
    """Storage class for platform global data."""
    def __init__(self):
        """Initialize the data."""
        self.entities = []

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Linkplay device."""

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = LinkPlayData()

    linkplay = LinkPlayDevice(config.get(CONF_HOST),
                              config.get(CONF_NAME),
                              config.get(CONF_SOURCES),
                              config.get(CONF_COMMONSOURCES),
                              config.get(CONF_ICECAST_METADATA),
                              config.get(CONF_MULTIROOM_WIFIDIRECT),
                              config.get(CONF_VOLUME_STEP),
                              config.get(CONF_LASTFM_API_KEY))

    add_entities([linkplay])

class LinkPlayDevice(MediaPlayerEntity):
    """Representation of a Linkplay device."""
    def __init__(self, 
                 host, 
                 name,
                 sources, 
                 common_sources, 
                 icecast_meta, 
                 multiroom_wifidirect, 
                 volume_step,
                 lfm_api_key=None
                 ):
        """Initialize the Linkplay device."""
        self._fw_ver = '1.0.0'
        self._uuid = ''
        self._features = None
        self._preset_key = 4
        self._name = name
        self._host = host
        self._icon = ICON_DEFAULT
        self._state = STATE_UNAVAILABLE
        self._volume = 0
        self._volume_step = volume_step
        self._fadevol = False
        self._source = None
        self._prev_source = None
        if sources is not None and sources != {}:
            self._source_list = loads(dumps(sources).strip('[]'))
        else:
            self._source_list = SOURCES.copy()
        if common_sources is not None and common_sources != {}:
            commonsources = loads(dumps(common_sources).strip('[]'))
            localsources = self._source_list
            self._source_list = {**localsources, **commonsources}
        self._sound_mode = None
        self._muted = False
        self._playhead_position = 0
        self._duration = 0
        self._position_updated_at = None
        self._shuffle = False
        self._repeat = REPEAT_MODE_OFF
        self._media_album = None
        self._media_artist = None
        self._media_prev_artist = None
        self._media_title = None
        self._media_prev_title = None
        self._lpapi = LinkPlayRestData(self._host)
        self._tcpapi = LinkPlayTcpUartData(self._host)
        self._media_image_url = None
        self._media_uri = None
        self._first_update = True
        if lfm_api_key is not None:
            self._lfmapi = LastFMRestData(lfm_api_key)
        else:
            self._lfmapi = None
        self._upnp_device = None
        self._slave_mode = False
        self._slave_ip = None
        self._trackq = []
        self._trackc = None
        self._master = None
        self._is_master = False
        self._wifi_channel = None
        self._ssid = None
        self._playing_localfile = True
        self._playing_stream = False
        self._playing_liveinput = False
        self._playing_spotify = False
        self._playing_webplaylist = False
        self._playing_tts = False
        self._slave_list = None
        self._multiroom_wifidirect = multiroom_wifidirect
        self._multiroom_group = []
        self._multiroom_prevsrc = None
        self._multiroom_unjoinat = None
        self._wait_for_mcu = 0
        self._new_song = True
        self._unav_throttle = False
        self._icecast_name = None
        self._icecast_meta = icecast_meta
        self._ice_skip_throt = False
        self._snapshot_active = False
        self._snap_source = None
        self._snap_state = STATE_UNKNOWN
        self._snap_volume = 0
        self._snap_spotify = False

    async def async_added_to_hass(self):
        """Record entity."""
        self.hass.data[DOMAIN].entities.append(self)

    @property
    def name(self):
        """Return the name of the device."""
        if self._slave_mode:
            for dev in self._multiroom_group:
                for device in self.hass.data[DOMAIN].entities:
                    if device._is_master:
                        return self._name + ' [' + device._name + ']'
        else:
            return self._name

    @property
    def icon(self):
        """Return the icon of the device."""
        if self._muted or self._state in [STATE_PAUSED, STATE_UNAVAILABLE]:
            return ICON_MUTED

        if self._slave_mode or self._is_master:
            return ICON_MULTIROOM

        if self._source == "Bluetooth":
            return ICON_BLUETOOTH

        if self._source == "DLNA" or self._source == "Airplay":
            return ICON_PUSHSTREAM

        if self._state == STATE_PLAYING:
            return ICON_PLAYING

        return ICON_DEFAULT

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return int(self._volume) / MAX_VOL

    @property
    def is_volume_muted(self):
        """Return boolean if volume is currently muted."""
        return self._muted

    @property
    def source(self):
        """Return the current input source."""
        if self._source not in ['Idle', 'Network']:
            return self._source
        else:
            return None

    @property
    def source_list(self):
        """Return the list of available input sources. If only one source exists, don't show it, as it's one and only one - WiFi shouldn't be listed."""
        source_list = self._source_list.copy()
        if 'wifi' in source_list:
            del source_list['wifi']

        if len(self._source_list) > 0:
            return list(source_list.values())
        else:
            return None

    @property
    def sound_mode(self):
        """Return the current sound mode."""
        return self._sound_mode

    @property
    def sound_mode_list(self):
        """Return the available sound modes."""
        return sorted(list(SOUND_MODES.values()))

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        if self._slave_mode and self._features:
            return self._features

        if self._playing_localfile or self._playing_spotify or self._playing_webplaylist:
            if self._state in [STATE_PLAYING, STATE_PAUSED]:
                self._features = \
                SUPPORT_SELECT_SOURCE | SUPPORT_SELECT_SOUND_MODE | SUPPORT_PLAY_MEDIA | \
                SUPPORT_VOLUME_SET | SUPPORT_VOLUME_STEP | SUPPORT_VOLUME_MUTE | \
                SUPPORT_STOP | SUPPORT_PLAY | SUPPORT_PAUSE | \
                SUPPORT_NEXT_TRACK | SUPPORT_PREVIOUS_TRACK | SUPPORT_SHUFFLE_SET | SUPPORT_REPEAT_SET | SUPPORT_SEEK
            else:
                self._features = \
                SUPPORT_SELECT_SOURCE | SUPPORT_SELECT_SOUND_MODE | SUPPORT_PLAY_MEDIA | \
                SUPPORT_VOLUME_SET | SUPPORT_VOLUME_STEP | SUPPORT_VOLUME_MUTE | \
                SUPPORT_STOP | SUPPORT_PLAY | SUPPORT_PAUSE | \
                SUPPORT_NEXT_TRACK | SUPPORT_PREVIOUS_TRACK | SUPPORT_SHUFFLE_SET | SUPPORT_REPEAT_SET

        elif self._playing_stream:
            self._features = \
            SUPPORT_SELECT_SOURCE | SUPPORT_SELECT_SOUND_MODE | SUPPORT_PLAY_MEDIA | \
            SUPPORT_VOLUME_SET | SUPPORT_VOLUME_STEP | SUPPORT_VOLUME_MUTE | \
            SUPPORT_STOP | SUPPORT_PLAY | SUPPORT_PAUSE

        elif self._playing_liveinput:
            self._features = \
            SUPPORT_SELECT_SOURCE | SUPPORT_SELECT_SOUND_MODE | SUPPORT_PLAY_MEDIA | \
            SUPPORT_VOLUME_SET | SUPPORT_VOLUME_STEP | SUPPORT_VOLUME_MUTE | \
            SUPPORT_STOP

        if "udisk" in self._source_list:
            self._features |= SUPPORT_BROWSE_MEDIA

        return self._features

    @property
    def media_position(self):
        """Time in seconds of current playback head position."""
        if self._playing_localfile or self._playing_spotify or self._slave_mode:
            return self._playhead_position
        else:
            return None

    @property
    def media_duration(self):
        """Time in seconds of current song duration."""
        if self._playing_localfile or self._playing_spotify or self._slave_mode:
            return self._duration
        else:
            return None

    @property
    def media_position_updated_at(self):
        """When the seek position was last updated."""
        if not self._playing_liveinput:
            return self._position_updated_at
        else:
            return None

    @property
    def shuffle(self):
        """Return True if shuffle mode is enabled."""
        return self._shuffle

    @property
    def repeat(self):
        """Return repeat mode."""
        return self._repeat

    @property
    def media_title(self):
        """Return title of the current track."""
        return self._media_title

    @property
    def media_artist(self):
        """Return name of the current track artist."""
        return self._media_artist

    @property
    def media_album_name(self):
        """Return name of the current track album."""
        return self._media_album

    @property
    def media_image_url(self):
        """Return name the image for the current track."""
        return self._media_image_url

    @property
    def media_content_type(self):
        """Content type of current playing media."""
        if self._playing_stream:
            return MEDIA_TYPE_URL
        else:
            return MEDIA_TYPE_MUSIC

    @property
    def ssid(self):
        """SSID to use for multiroom configuration."""
        return self._ssid

    @property
    def wifi_channel(self):
        """Wifi channel to use for multiroom configuration."""
        return self._wifi_channel

    @property
    def slave_ip(self):
        """Ip used in multiroom configuration."""
        return self._slave_ip

    @property
    def slave(self):
        """Return true if it is a slave."""
        return self._slave_mode

    @property
    def master(self):
        """master's entity id used in multiroom configuration."""
        return self._master

    @property
    def is_master(self):
        """Return true if it is a master."""
        return self._is_master

    @property
    def device_class(self):
        """Return the device class of this entity, if any."""
        return DEVICE_CLASS_SPEAKER

    @property
    def device_state_attributes(self):
        """List members in group and set master and slave state."""
        attributes = {}
        if self._multiroom_group is not None:
            attributes = {ATTR_LINKPLAY_GROUP: self._multiroom_group}

        attributes[ATTR_MASTER] = self._is_master
        attributes[ATTR_SLAVE] = self._slave_mode
        attributes[ATTR_FWVER] = self._fw_ver
        if len(self._trackq) > 0:
            attributes[ATTR_TRCNT] = len(self._trackq) - 1
            attributes[ATTR_TRCRT] = self._trackc

        if self._upnp_device is None:
            attributes[ATTR_DEBUG] = "UPnP not detected"
        else:
            attributes[ATTR_DEBUG] = "UPnP detected"

#        if self._playing_localfile:
#            attributes[ATTR_DEBUG] = "_playing_localfile"

#        elif self._playing_spotify:
#            attributes[ATTR_DEBUG] = "_playing_spotify"

#        elif self._playing_webplaylist:
#            attributes[ATTR_DEBUG] = "_playing_webplaylist"

#        elif self._playing_stream:
#            attributes[ATTR_DEBUG] = "_playing_stream"

#        elif self._playing_liveinput:
#            attributes[ATTR_DEBUG] = "_playing_liveinput"

        return attributes

    @property
    def host(self):
        """Self ip."""
        return self._host

    @property
    def track_count(self):
        """List of tracks present on the device."""
        if len(self._trackq) > 0:
            return len(self._trackq) - 1
        else:
            return 0

    @property
    def unique_id(self):
        """Return the unique id."""
        return "linkplay_media_" + self._host  # + self._uuid not available yet at start

    @property
    def fw_ver(self):
        """Return the firmware version number of the device."""
        return self._fw_ver

    @property
    def lpapi(self):
        """Device API."""
        return self._lpapi

    def set_volume_level(self, volume):
        """Set volume level, input range 0..1, linkplay device 0..100."""
        volume = str(round(int(volume * MAX_VOL)))
        if not (self._slave_mode and self._multiroom_wifidirect):

            if self._fadevol:
                voldiff = int(self._volume) - int(volume)
                steps = 1
                if voldiff < 33:
                    steps = 2
                elif voldiff >= 33 and voldiff < 66:
                    steps = 4
                elif voldiff > 66:
                    steps = 6
                volstep = int(round(voldiff / steps))
                voltemp = int(self._volume)
#                self._wait_for_mcu = 1  # set delay in update routine for the fade to finish
                for v in (range(0, steps - 1)):
                    voltemp = voltemp - volstep
                    self._lpapi.call('GET', 'setPlayerCmd:vol:{0}'.format(str(voltemp)))
                    time.sleep(0.6 / steps)

            if self._is_master:
                self._lpapi.call('GET', 'setPlayerCmd:slave_vol:{0}'.format(str(volume)))
            else:
                self._lpapi.call('GET', 'setPlayerCmd:vol:{0}'.format(str(volume)))
            value = self._lpapi.data

            if value == "OK":
                self._volume = volume
            else:
                _LOGGER.warning("Failed to set volume. Device: %s, Got response: %s", self.entity_id, value)
        else:
            if self._snapshot_active:
                return
            self._master.lpapi.call('GET', 'multiroom:SlaveVolume:{0}:{1}'.format(self._slave_ip, str(volume)))
            value = self._master.lpapi.data
            if value == "OK":
                self._volume = volume
            else:
                _LOGGER.warning("Failed to set volume. Device: %s, Got response: %s", self.entity_id, value)

    def volume_up(self):
        """Increase volume one step"""
        if int(self._volume) == 100 and not self._muted:
            return

        volume = int(self._volume) + int(self._volume_step)
        if volume > 100:
            volume = 100

        if not (self._slave_mode and self._multiroom_wifidirect):

            if self._is_master:
                self._lpapi.call('GET', 'setPlayerCmd:slave_vol:{0}'.format(str(volume)))
            else:
                self._lpapi.call('GET', 'setPlayerCmd:vol:{0}'.format(str(volume)))
            value = self._lpapi.data

            if value == "OK":
                self._volume = volume
            else:
                _LOGGER.warning("Failed to set volume_up. Device: %s, Got response: %s", self.entity_id, value)
        else:
            if self._snapshot_active:
                return
            self._master.lpapi.call('GET', 'multiroom:SlaveVolume:{0}:{1}'.format(self._slave_ip, str(volume)))
            value = self._master.lpapi.data
            if value == "OK":
                self._volume = volume
            else:
                _LOGGER.warning("Failed to set volume_up. Device: %s, Got response: %s", self.entity_id, value)

    def volume_down(self):
        """Decrease volume one step."""
        if int(self._volume) == 0:
            return

        volume = int(self._volume) - int(self._volume_step)
        if volume < 0:
            volume = 0

        if not (self._slave_mode and self._multiroom_wifidirect):

            if self._is_master:
                self._lpapi.call('GET', 'setPlayerCmd:slave_vol:{0}'.format(str(volume)))
            else:
                self._lpapi.call('GET', 'setPlayerCmd:vol:{0}'.format(str(volume)))
            value = self._lpapi.data

            if value == "OK":
                self._volume = volume
            else:
                _LOGGER.warning("Failed to set volume_down. Device: %s, Got response: %s", self.entity_id, value)
        else:
            if self._snapshot_active:
                return
            self._master.lpapi.call('GET', 'multiroom:SlaveVolume:{0}:{1}'.format(self._slave_ip, str(volume)))
            value = self._master.lpapi.data
            if value == "OK":
                self._volume = volume
            else:
                _LOGGER.warning("Failed to set volume_down. Device: %s, Got response: %s", self.entity_id, value)

    def mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
        if not (self._slave_mode and self._multiroom_wifidirect):
            if self._is_master:
                self._lpapi.call('GET', 'setPlayerCmd:slave_mute:{0}'.format(str(int(mute))))
            else:
                self._lpapi.call('GET', 'setPlayerCmd:mute:{0}'.format(str(int(mute))))
            value = self._lpapi.data
            if value == "OK":
                self._muted = bool(int(mute))
            else:
                _LOGGER.warning("Failed mute/unmute volume. Device: %s, Got response: %s", self.entity_id, value)
        else:
            self._master.lpapi.call('GET', 'multiroom:SlaveMute:{0}:{1}'.format(self._slave_ip, str(int(mute))))
            value = self._master.lpapi.data
            if value == "OK":
                self._muted = bool(int(mute))
            else:
                _LOGGER.warning("Failed mute/unmute volume. Device: %s, Got response: %s", self.entity_id, value)

    def media_play(self):
        """Send play command."""
        if not self._slave_mode:
            if self._state == STATE_PAUSED:
                self._lpapi.call('GET', 'setPlayerCmd:resume')
                value = self._lpapi.data

            elif self._prev_source != None:
                temp_source = next((k for k in self._source_list if self._source_list[k] == self._prev_source), None)
                if temp_source == None:
                    return

                if temp_source.find('http') == 0 or temp_source == 'udisk' or temp_source == 'TFcard':
                    self.select_source(self._prev_source)
                    if self._source != None:
                        self._source = None
                        value = "OK"
                else:
                    self._lpapi.call('GET', 'setPlayerCmd:play')
                    value = self._lpapi.data
            else:
                self._lpapi.call('GET', 'setPlayerCmd:play')
                value = self._lpapi.data

            if value == "OK":
                self._unav_throttle = False
                self._playing_tts = False
                self._state = STATE_PLAYING
                self._position_updated_at = utcnow()
                if self._slave_list is not None:
                    for slave in self._slave_list:
                        slave.set_state(self._state)
                        slave.set_position_updated_at(self.media_position_updated_at)
            else:
                _LOGGER.warning("Failed to start or resume playback. Device: %s, Got response: %s", self.entity_id, value)
        else:
            self._master.media_play()

    def media_pause(self):
        """Send pause command."""
        if not self._slave_mode:
            if self._playing_stream:
                # Pausing a live stream will cause a buffer overrun in hardware. Stop is the correct procedure in this case.
                # If the stream is configured as an input source, when pressing Play after this, it will be started again (using self._prev_source).
                self.media_stop()
                return

            self._lpapi.call('GET', 'setPlayerCmd:pause')
            value = self._lpapi.data
            if value == "OK":
                self._position_updated_at = utcnow()
                self._state = STATE_PAUSED
                if self._slave_list is not None:
                    for slave in self._slave_list:
                        slave.set_state(self._state)
                        slave.set_position_updated_at(self.media_position_updated_at)
            else:
                _LOGGER.warning("Failed to pause playback. Device: %s, Got response: %s", self.entity_id, value)
        else:
            self._master.media_pause()

    def media_stop(self):
        """Send stop command."""
        if not self._slave_mode:
            if self._playing_spotify or self._playing_liveinput:
                self._lpapi.call('GET', 'setPlayerCmd:switchmode:wifi')
                self._wait_for_mcu = 1.2

            self._lpapi.call('GET', 'setPlayerCmd:stop')
            value = self._lpapi.data
            if value == "OK":
                self._state = STATE_IDLE
                self._playhead_position = 0
                self._duration = 0
                self._media_title = None
                self._prev_source = self._source
                self._source = None
                self._media_artist = None
                self._media_album = None
                self._icecast_name = None
                self._media_uri = None
                self._trackc = None
                self._media_image_url = None
                self._position_updated_at = utcnow()
                self.schedule_update_ha_state(True)
                if self._slave_list is not None:
                    for slave in self._slave_list:
                        slave.set_state(self._state)
                        slave.set_position_updated_at(self.media_position_updated_at)
            else:
                _LOGGER.warning("Failed to stop playback. Device: %s, Got response: %s", self.entity_id, value)
        else:
            self._master.media_stop()

    def media_next_track(self):
        """Send next track command."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:next')
            value = self._lpapi.data
            self._playhead_position = 0
            self._duration = 0
            self._position_updated_at = utcnow()
            self._trackc = None
            self._wait_for_mcu = 2
            if value != "OK":
                _LOGGER.warning("Failed skip to next track. Device: %s, Got response: %s", self.entity_id, value)
        else:
            self._master.media_next_track()

    def media_previous_track(self):
        """Send previous track command."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:prev')
            value = self._lpapi.data
            self._playhead_position = 0
            self._duration = 0
            self._position_updated_at = utcnow()
            self._trackc = None
            self._wait_for_mcu = 2
            if value != "OK":
                _LOGGER.warning("Failed to skip to previous track." " Device: %s, Got response: %s", self.entity_id, value)
        else:
            self._master.media_previous_track()

    def media_seek(self, position):
        """Send media_seek command to media player."""
        if not self._slave_mode and position < self._duration:
            self._lpapi.call('GET', 'setPlayerCmd:seek:{0}'.format(str(position)))
            value = self._lpapi.data
            self._position_updated_at = utcnow()
            self._wait_for_mcu = 0.1
            if value != "OK":
                _LOGGER.warning("Failed to seek. Device: %s, Got response: %s", self.entity_id, value)
        else:
            self._master.media_seek(position)

    def clear_playlist(self):
        """Clear players playlist."""
        pass

    def play_media(self, media_type, media_id, **kwargs):
        """Play media from a URL or localfile."""
        _LOGGER.debug("Trying to play media. Device: %s, Media_type: %s, Media_id: %s", self.entity_id, media_type, media_id)
        if not self._slave_mode:
            if not media_type in [MEDIA_TYPE_MUSIC, MEDIA_TYPE_URL, MEDIA_TYPE_TRACK]:
                _LOGGER.warning("For %s Invalid media type %s. Only %s and %s is supported", self._name, media_type, MEDIA_TYPE_MUSIC, MEDIA_TYPE_URL)
                return

            if media_id.find('http') == 0:
                media_type = MEDIA_TYPE_URL

            if media_type == MEDIA_TYPE_URL:
                self._lpapi.call('GET', 'setPlayerCmd:play:{0}'.format(media_id))
                value = self._lpapi.data
                if value != "OK":
                    _LOGGER.warning("Failed to play media type URL. Device: %s, Got response: %s, Media_Id: %s", self.entity_id, value, media_id)
                    return False

            if media_type in [MEDIA_TYPE_MUSIC, MEDIA_TYPE_TRACK]:
                self._lpapi.call('GET', 'setPlayerCmd:playLocalList:{0}'.format(media_id))
                value = self._lpapi.data
                if value != "OK":
                    _LOGGER.warning("Failed to play media type music. Device: %s, Got response: %s, Media_Id: %s", self.entity_id, value, media_id)
                    return False

            if media_id.find('tts_proxy') != -1:
                self._playing_tts = True
            else:
                self._playing_tts = False
            self._state = STATE_PLAYING
            self._media_title = None
            self._media_artist = None
            self._media_album = None
            self._icecast_name = None
            self._playhead_position = 0
            self._duration = 0
            self._trackc = None
            self._position_updated_at = utcnow()
            self._media_image_url = None
            self._ice_skip_throt = True
            self._unav_throttle = False
            if media_type == MEDIA_TYPE_URL:
                self._media_uri = media_id
            elif media_type == MEDIA_TYPE_MUSIC:
                self._media_uri = None
                self._wait_for_mcu = 0.4
            return True

        else:
            if not self._snapshot_active:
                self._master.play_media(media_type, media_id)

    def select_source(self, source):
        """Select input source."""
        if not self._slave_mode:
            temp_source = next((k for k in self._source_list if self._source_list[k] == source), None)
            if temp_source == None:
                return

            if temp_source == "udisk":
                self._tracklist_via_upnp("USB")

            if len(self._source_list) > 0:
                prev_source = next((k for k in self._source_list if self._source_list[k] == self._source), None)

            if prev_source and prev_source.find('http') == 0 and temp_source in ['line-in', 'line-in2', 'optical', 'bluetooth', 'co-axial', 'HDMI', 'cd', 'udisk', 'RCA']:
                self._wait_for_mcu = 1

            self._unav_throttle = False
            if temp_source.find('http') == 0:
                self._lpapi.call('GET', 'setPlayerCmd:play:{0}'.format(temp_source))
                value = self._lpapi.data
                if value == "OK":
                    if prev_source and prev_source.find('http') == -1:
                        self._wait_for_mcu = 2  # switching from live to stream input -> time to report correct volume value at update
                    else:
                        self._wait_for_mcu = 0.5
                    self._playing_tts = False
                    self._source = source
                    self._media_uri = temp_source
                    self._state = STATE_PLAYING
                    self._playhead_position = 0
                    self._duration = 0
                    self._trackc = None
                    self._position_updated_at = utcnow()
                    self._media_title = None
                    self._media_artist = None
                    self._media_album = None
                    self._icecast_name = None
                    self._media_image_url = None
                    self._ice_skip_throt = True
                    if self._slave_list is not None:
                        for slave in self._slave_list:
                            slave.set_source(source)
                else:
                    _LOGGER.warning("Failed to select http source and play. Device: %s, Got response: %s", self.entity_id, value)
            else:
                self._lpapi.call('GET', 'setPlayerCmd:switchmode:{0}'.format(temp_source))
                value = self._lpapi.data
                if value == "OK":
                    if temp_source and temp_source in ['udisk', 'TFcard']:
                        self._wait_for_mcu = 2    # switching to locally stored files -> time to report correct volume value at update
                    else:
                        self._wait_for_mcu = 0.6  # switching to a physical input -> time to report correct volume value at update
                    self._source = source
                    self._media_uri = None
                    self._state = STATE_PLAYING
                    self._playhead_position = 0
                    self._duration = 0
                    self._trackc = None
                    if self._slave_list is not None:
                        for slave in self._slave_list:
                            slave.set_source(source)
                else:
                    _LOGGER.warning("Failed to select source. Device: %s, Got response: %s", self.entity_id, value)

            self.schedule_update_ha_state(True)
        else:
            self._master.select_source(source)

    def select_sound_mode(self, sound_mode):
        """Set Sound Mode for device."""
        if not self._slave_mode:
            mode = list(SOUND_MODES.keys())[list(
                SOUND_MODES.values()).index(sound_mode)]
            self._lpapi.call('GET', 'setPlayerCmd:equalizer:{0}'.format(mode))
            value = self._lpapi.data
            if value == "OK":
                self._sound_mode = sound_mode
                if self._slave_list is not None:
                    for slave in self._slave_list:
                        slave.set_sound_mode(sound_mode)
            else:
                _LOGGER.warning("Failed to set sound mode. Device: %s, Got response: %s", self.entity_id, value)
        else:
            self._master.select_sound_mode(sound_mode)

    def set_shuffle(self, shuffle):
        """Change the shuffle mode."""
        if not self._slave_mode:
            if shuffle:
                self._shuffle = shuffle
                mode = '2'
            else:
                if self._repeat == REPEAT_MODE_OFF:
                    mode = '0'
                elif self._repeat == REPEAT_MODE_ALL:
                    mode = '3'
                elif self._repeat == REPEAT_MODE_ONE:
                    mode = '1'
            self._lpapi.call('GET', 'setPlayerCmd:loopmode:{0}'.format(mode))
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to change shuffle mode. Device: %s, Got response: %s", self.entity_id, value)
        else:
            self._master.set_shuffle(shuffle)

    def set_repeat(self, repeat):
        """Change the repeat mode."""
        if not self._slave_mode:
            self._repeat = repeat
            if repeat == REPEAT_MODE_OFF:
                mode = '0'
            elif repeat == REPEAT_MODE_ALL:
                mode = '2' if self._shuffle else '3'
            elif repeat == REPEAT_MODE_ONE:
                mode = '1'
            self._lpapi.call('GET', 'setPlayerCmd:loopmode:{0}'.format(mode))
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to change repeat mode. Device: %s, Got response: %s", self.entity_id, value)
        else:
            self._master.set_repeat(repeat)

    def preset_button(self, preset):
        """Simulate pressing a physical preset button."""
        if self._preset_key != None and preset != None:
            if not self._slave_mode:
                if int(preset) > 0 and int(preset) <= self._preset_key:
                    self._lpapi.call('GET', 'MCUKeyShortClick:{0}'.format(str(preset)))
                    value = self._lpapi.data
                    self._wait_for_mcu = 2
                    self.schedule_update_ha_state(True)
                    if value != "OK":
                        _LOGGER.warning("Failed to recall preset %s. " "Device: %s, Got response: %s", self.entity_id, preset, value)
                else:
                    _LOGGER.warning("Wrong preset number %s. Device: %s, has to be integer between 1 and %s", self.entity_id, preset, self._preset_key)
            else:
                self._master.preset_button(preset)

    def join(self, slaves):
        """Add selected slaves to multiroom configuration."""
        if self._state == STATE_UNAVAILABLE:
            return

        if self.entity_id not in self._multiroom_group:
            self._multiroom_group.append(self.entity_id)
            self._is_master = True
            self._wait_for_mcu = 2

        for slave in slaves:
            if slave._is_master:
                _LOGGER.debug("Multiroom: slave has master flag set. Unjoining it from where it is. Master: %s, Slave: %s", self.entity_id, slave.entity_id)
                slave.unjoin_all()

            if slave.entity_id not in self._multiroom_group:
                if slave._slave_mode:
                    _LOGGER.debug("Multiroom: slave already has slave flag set. Unjoining it from where it is. Master: %s, Slave: %s", self.entity_id, slave.entity_id)
                    slave.unjoin_me()

                slave.set_previous_source(True)
                if self._multiroom_wifidirect:
                    _LOGGER.debug("Multiroom: Join in WiFi drect mode. Master: %s, Slave: %s", self.entity_id, slave.entity_id)
                    cmd = "ConnectMasterAp:ssid={0}:ch={1}:auth=OPEN:".format(self._ssid, self._wifi_channel) + "encry=NONE:pwd=:chext=0"
                else:
                    _LOGGER.debug("Multiroom: Join in multiroom mode. Master: %s, Slave: %s", self.entity_id, slave.entity_id)
                    cmd = 'ConnectMasterAp:JoinGroupMaster:eth{0}:wifi0.0.0.0'.format(self._host)

                slave._lpapi.call('GET', cmd)
                value = slave._lpapi.data
                _LOGGER.debug("Multiroom: command result: %s Master: %s, Slave: %s", value, self.entity_id, slave.entity_id)
                if value == "OK":
#                    slave.set_volume(self._volume)
#                    slave.set_volume_level(self._volume)
                    slave.set_master(self)
                    slave.set_is_master(False)
                    slave.set_slave_mode(True)
                    slave.set_media_title(self._media_title)
                    slave.set_media_artist(self._media_artist)
#                    slave.set_muted(self._muted)
                    slave.set_state(self.state)
                    slave.set_slave_ip(self._host)
                    slave.set_media_image_url(self._media_image_url)
                    slave.set_playhead_position(self.media_position)
                    slave.set_duration(self.media_duration)
                    slave.set_source(self._source)
                    slave.set_sound_mode(self._sound_mode)
                    slave.set_features(self._features)
                    self._multiroom_group.append(slave.entity_id)
                else:
                    slave.set_previous_source(False)
                    _LOGGER.warning("Failed to join multiroom. command result: %s Master: %s, Slave: %s", value, self.entity_id, slave.entity_id)

        for slave in slaves:
            if slave.entity_id in self._multiroom_group:
                slave.set_multiroom_group(self._multiroom_group)
##                slave.set_position_updated_at(utcnow())
##                slave.trigger_schedule_update(True)

        self._position_updated_at = utcnow()
        self.schedule_update_ha_state(True)

    def unjoin_all(self):
        """Disconnect everybody from the multiroom configuration because i'm the master."""
        if self._state == STATE_UNAVAILABLE:
            return

        cmd = "multiroom:Ungroup"
        self._lpapi.call('GET', cmd)
        value = self._lpapi.data
        if value == "OK":
            self._is_master = False
            for slave_id in self._multiroom_group:
                for device in self.hass.data[DOMAIN].entities:
                    if device.entity_id == slave_id and device.entity_id != self.entity_id:
                        device.set_slave_mode(False)
                        device.set_is_master(False)
                        device.set_slave_ip(None)
                        device.set_master(None)
                        device.set_multiroom_unjoinat(utcnow())
                        device.set_multiroom_group([])
                        device.trigger_schedule_update(True)
            self._multiroom_group = []
            self._position_updated_at = utcnow()
            self.schedule_update_ha_state(True)

        else:
            _LOGGER.warning("Failed to unjoin_all multiroom. " "Device: %s, Got response: %s", self.entity_id, value)

    def unjoin_me(self):
        """Disconnect myself from the multiroom configuration."""
        if self._multiroom_wifidirect:
            for dev in self._multiroom_group:
                for device in self.hass.data[DOMAIN].entities:
                    if device._is_master:
                        cmd = "multiroom:SlaveKickout:{0}".format(self._slave_ip)
                        self._master.lpapi_call('GET', cmd)
                        value = self._master.lpapi.data
                        self._master._position_updated_at = utcnow()

        else:
            cmd = "multiroom:Ungroup"
            self._lpapi.call('GET', cmd)
            value = self._lpapi.data

        if value == "OK":
            if self._master is not None:
                self._master.remove_from_group(self)
                self._master._wait_for_mcu = 1
                self._master.schedule_update_ha_state(True)
            self._multiroom_unjoinat = utcnow()
            self._master = None
            self._is_master = False
            self._slave_mode = False
            self._slave_ip = None
            self._multiroom_group = []
            self.schedule_update_ha_state(True)

        else:
            _LOGGER.warning("Failed to unjoin_me from multiroom. " "Device: %s, Got response: %s", self.entity_id, value)

    def remove_from_group(self, device):
        """Remove a certain device for multiroom lists."""
        if device.entity_id in self._multiroom_group:
            self._multiroom_group.remove(device.entity_id)
#            self.schedule_update_ha_state(True)

        if len(self._multiroom_group) <= 1:
            self._multiroom_group = []
            self._is_master = False
            self._slave_list = None

        for member in self._multiroom_group:
            for player in self.hass.data[DOMAIN].entities:
                if player.entity_id == member and player.entity_id != self.entity_id:
                    player.set_multiroom_group(self._multiroom_group)
#                    player.trigger_schedule_update(True)
#                    player.set_position_updated_at(utcnow())

    def execute_command(self, command, notif):
        """Execute desired command against the player using factory API."""
        if command.find('MCU') == 0:
            self._tcpapi.call(command)
            value = self._tcpapi.data
        elif command == 'Reboot':
            self._lpapi.call('GET', 'getStatus:ip:;reboot;')
            value = self._lpapi.data
        elif command == 'PromptEnable':
            self._lpapi.call('GET', 'PromptEnable')
            value = self._lpapi.data
        elif command == 'PromptDisable':
            self._lpapi.call('GET', 'PromptDisable')
            value = self._lpapi.data
        elif command == 'RouterMultiroomEnable':
            self._lpapi.call('GET', 'setMultiroomLogic:1')
            value = self._lpapi.data
        elif command == 'SetRandomWifiKey':
            from random import choice
            from string import ascii_letters
            newkey = (''.join(choice(ascii_letters) for i in range(16)))
            self._lpapi.call('GET', 'setNetwork:1:{0}'.format(newkey))
            value = self._lpapi.data
            if value == 'OK':
                value = self._lpapi.data + ", key: " + newkey
            else:
                value = "key: " + newkey
        elif command.find('SetApSSIDName:') == 0:
            ssidnam = command.replace('SetApSSIDName:', '').strip()
            if ssidnam != '':
                self._lpapi.call('GET', 'setSSID:{0}'.format(ssidnam))
                value = self._lpapi.data
                if value == 'OK':
                    value = self._lpapi.data + ", SoftAP SSID set to: " + ssidnam
            else:
                value == "SSID not specified correctly. You need 'SetApSSIDName: NewWifiName'"
        elif command.find('WriteDeviceNameToUnit:') == 0:
            devnam = command.replace('WriteDeviceNameToUnit:', '').strip()
            if devnam != '':
                self._lpapi.call('GET', 'setDeviceName:{0}'.format(devnam))
                value = self._lpapi.data
                if value == 'OK':
                    self._name = devnam
                    value = self._lpapi.data + ", name set to: " + self._name
            else:
                value == "Device name not specified correctly. You need 'WriteDeviceNameToUnit: My Device Name'"
        elif command == 'TimeSync':
            tme = time.strftime('%Y%m%d%H%M%S')
            self._lpapi.call('GET', 'timeSync:{0}'.format(tme))
            value = self._lpapi.data
            if value == 'OK':
                value = self._lpapi.data + ", time: " + tme
        elif command == 'Rescan':
            self._unav_throttle = False
            self._first_update = True
            self.schedule_update_ha_state(True)
            value = "OK"
        else:
            value = "No such command implemented."

        _LOGGER.warning("Player %s executed command: %s, result: %s", self.entity_id, command, value)

        if notif:
            self.hass.components.persistent_notification.async_create("<b>Executed command:</b><br>{0}<br><b>Result:</b><br>{1}".format(command, value), title=self.entity_id)

    def snapshot(self, switchinput):
        """Snapshot the current input source and the volume level of it """
        if self._state == STATE_UNAVAILABLE:
            return

        if not self._slave_mode:
            self._snapshot_active = True
            self._snap_source = self._source
            self._snap_state = self._state

            if self._playing_spotify:
                self._preset_snap_via_upnp(str(self._preset_key))
                self._snap_spotify = True
                self._snap_volume = int(self._volume)
                self._lpapi.call('GET', 'setPlayerCmd:stop')
                time.sleep(0.2)

            elif self._state == STATE_IDLE:
                self._snap_volume = int(self._volume)

            elif switchinput and not self._playing_stream:
                self._lpapi.call('GET', 'setPlayerCmd:switchmode:wifi')
                value = self._lpapi.data
                time.sleep(0.2)
                self._lpapi.call('GET', 'setPlayerCmd:stop')
                if value == "OK":
                    time.sleep(1.8)  # have to wait for the sound fade-in of the unit when physical source is changed, otherwise volume value will be incorrect
                    player_api_result = self._get_status('getPlayerStatus', no_throttle=True)
                    if player_api_result is not None:
                        try:
                            player_status = json.loads(player_api_result)
                            self._snap_volume = int(player_status['vol'])
                        except ValueError:
                            _LOGGER.warning("Erroneous JSON during snapshot volume reading: %s, %s", self.entity_id, self._name)
                            self._snap_volume = 0
                    else:
                        self._snap_volume = 0
                else:
                    self._snap_volume = 0
            else:
                self._snap_volume = int(self._volume)
                self._lpapi.call('GET', 'setPlayerCmd:stop')
        else:
            return
            #self._master.snapshot(switchinput)


    def restore(self):
        if self._state == STATE_UNAVAILABLE:
            return

        """Restore the current input source and the volume level of it """
        if not self._slave_mode:
            _LOGGER.warning("Player %s current source: %s, restoring volume: %s, and source to: %s", self.entity_id, self._source, self._snap_volume, self._snap_source)
            if self._snap_state != STATE_UNKNOWN:
                self._state = self._snap_state
                self._snap_state = STATE_UNKNOWN

            if self._snap_volume != 0:
                self._lpapi.call('GET', 'setPlayerCmd:vol:{0}'.format(str(self._snap_volume)))
                self._snap_volume = 0
                time.sleep(.6)

            if self._snap_spotify:
                self._snap_spotify = False
                self._lpapi.call('GET', 'MCUKeyShortClick:{0}'.format(str(self._preset_key)))
                time.sleep(1)
                self._snapshot_active = False
                self.schedule_update_ha_state(True)

            elif self._snap_source is not None:
                self._snapshot_active = False
                self.select_source(self._snap_source)
                self._snap_source = None
        else:
            return
            #self._master.restore()

    def set_multiroom_group(self, multiroom_group):
        """Set multiroom group info."""
        self._multiroom_group = multiroom_group

    def set_master(self, master):
        """Set master device for multiroom configuration."""
        self._master = master

    def set_is_master(self, is_master):
        """Set master device for multiroom configuration."""
        self._is_master = is_master

    def set_multiroom_unjoinat(self, tme):
        """The moment when unjoin has happened. Needs some time for the MCU to finish unjoining first"""
        self._multiroom_unjoinat = tme

    def set_slave_mode(self, slave_mode):
        """Set current device as slave in a multiroom configuration."""
        self._slave_mode = slave_mode
        self.schedule_update_ha_state(True)

    def set_previous_source(self, srcbool):
        """Memorize what was the previous source before entering multiroom."""
        if srcbool:
            self._multiroom_prevsrc = self._source
        else:
            self._multiroom_prevsrc = None

    def restore_previous_source(self):
        """Set to the last known source after exiting multiroom."""
        self.select_source(self._multiroom_prevsrc)
        self._multiroom_prevsrc = None

    def set_media_title(self, title):
        """Set the media title property."""
        self._media_title = title

    def set_media_artist(self, artist):
        """Set the media artist property."""
        self._media_artist = artist

    def set_volume(self, volume):
        """Set the volume property."""
        self._volume = volume

    def set_muted(self, mute):
        """Set the muted property."""
        self._muted = mute

    def set_state(self, state):
        """Set the state property."""
        self._state = state

    def set_slave_ip(self, slave_ip):
        """Set the slave ip property."""
        self._slave_ip = slave_ip

    def set_playhead_position(self, position):
        """Set the playhead position property."""
        self._playhead_position = position

    def set_duration(self, duration):
        """Set the duration property."""
        self._duration = duration

    def set_position_updated_at(self, time):
        """Set the position updated at property."""
        self._position_updated_at = time

    def set_source(self, source):
        """Set the source property."""
        self._source = source
        self.schedule_update_ha_state(True)

    def set_sound_mode(self, mode):
        """Set the sound mode property."""
        self._sound_mode = mode

    def set_media_image_url(self, url):
        """Set the media image URL property."""
        self._media_image_url = url

    def set_media_uri(self, uri):
        """Set the media URL property."""
        self.set_media_uri = uri

    def set_features(self, features):
        """Set the self features property."""
        self._features = features

    def set_wait_for_mcu(self, wait_for_mcu):
        """Set the wait for mcu processing duration property."""
        self._wait_for_mcu = wait_for_mcu

    def set_unav_throttle(self, unav_throttle):
        """Set update throttle property."""
        self._unav_throttle = unav_throttle

    def lpapi_call(self, method, cmd):
        """Set the media image URL property."""
        self._lpapi.call(method, cmd)
        value = self._lpapi.data
        if value == "OK":
            return True
        else:
            _LOGGER.warning("Failed to run on %s received command: %s, response %s", self.entity_id, cmd, value)

    def _is_playing_new_track(self):
        """Check if track is changed since last update."""
        if self._icecast_name != None:
            import unicodedata
            artmed = unicodedata.normalize('NFKD', str(self._media_artist) + str(self._media_title)).lower()
            artmedd = u"".join([c for c in artmed if not unicodedata.combining(c)])
            if artmedd.find(self._icecast_name.lower()) != -1 or artmedd.find(self._source.lower()) != -1:
                # don't trigger new track flag for icecast streams where track name contains station name or source name; save some energy by not quering last.fm with this
                self._media_image_url = None
                return False

        if self._media_artist != self._media_prev_artist or self._media_title != self._media_prev_title:
            return True
        else:
            return False

    def _fwvercheck(self, v):
        filled = []
        for point in v.split("."):
            filled.append(point.zfill(8))
        return tuple(filled)

    @Throttle(UNA_THROTTLE)
    def _get_status(self, status):
        #_LOGGER.debug('getting status for %s', self._name)
        self._lpapi.call('GET', status)
        if self._lpapi.data is None:
            _LOGGER.debug('Unable to connect to device: %s, %s', self.entity_id, self._name)
            self._unav_throttle = True
            self._wait_for_mcu = 0
            self._state = STATE_UNAVAILABLE
            self._playhead_position = None
            self._duration = None
            self._position_updated_at = None
            self._media_title = None
            self._media_artist = None
            self._media_album = None
            self._media_image_url = None
            self._media_uri = None
            self._icecast_name = None
            self._source = None
            self._upnp_device = None
            self._first_update = True
            self._slave_mode = False
            self._is_master = False

        return self._lpapi.data

    def _update_via_upnp(self):
        """Update track info via UPNP."""
        import validators
        radio = False

        if self._upnp_device is None:
            return

        try:
            media_info = self._upnp_device.AVTransport.GetMediaInfo(InstanceID=0)
            media_info = media_info.get('CurrentURIMetaData')
        except:
            _LOGGER.warning("GetMediaInfo UPNP error: %s", self.entity_id)
            return

        if media_info is None:
            return

        self._media_title = None
        self._media_album = None
        self._media_artist = None
        self._media_image_url = None

        xml_tree = ET.fromstring(media_info)

        xml_path = "{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item/"
        title_xml_path = "{http://purl.org/dc/elements/1.1/}title"
        artist_xml_path = "{urn:schemas-upnp-org:metadata-1-0/upnp/}artist"
        album_xml_path = "{urn:schemas-upnp-org:metadata-1-0/upnp/}album"
        image_xml_path = "{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI"
        radiosub_xml_path = "{http://purl.org/dc/elements/1.1/}subtitle"

        if radio:
            title = xml_tree.find("{0}{1}".format(xml_path, radiosub_xml_path)).text
            if title.find(' - ') != -1:
                titles = title.split(' - ')
                self._media_artist = string.capwords(titles[0].strip())
                self._media_title = string.capwords(titles[1].strip())
            else:
                self._media_title = string.capwords(title.strip())
        else:
            self._media_title = xml_tree.find("{0}{1}".format(xml_path, title_xml_path)).text
            self._media_artist = xml_tree.find("{0}{1}".format(xml_path, artist_xml_path)).text
            self._media_album = xml_tree.find("{0}{1}".format(xml_path, album_xml_path)).text
 
        self._media_image_url = xml_tree.find("{0}{1}".format(xml_path, image_xml_path)).text

        if not validators.url(self._media_image_url):
            self._media_image_url = None

    def _preset_snap_via_upnp(self, presetnum):
        """Retrieve tracks list queue via UPNP."""
        if self._upnp_device is None or not self._playing_spotify:
            return

        try:
            result = self._upnp_device.PlayQueue.SetSpotifyPreset(KeyIndex=presetnum)
        except:
            _LOGGER.debug("SetSpotifyPreset UPNP error: %s, %s", self.entity_id, presetnum)
            return

        result = str(result.get('Result'))

        try:
            preset_map = self._upnp_device.PlayQueue.GetKeyMapping()
            preset_map = preset_map.get('QueueContext')
        except:
            _LOGGER.debug("GetKeyMapping UPNP error: %s", self.entity_id)
            return

        xml_tree = ET.fromstring(preset_map)

        try:
            xml_tree.find('Key'+presetnum+'/Name').text = "Snapshot set by Home Assistant ("+result+")"
        except:
            data=xml_tree.find('Key'+presetnum)
            snap=ET.SubElement(data,'Name')
            snap.text = "Snapshot set by Home Assistant ("+result+")"

        try:
            xml_tree.find('Key'+presetnum+'/Source').text = "SPOTIFY"
        except:
            data=xml_tree.find('Key'+presetnum)
            snap=ET.SubElement(data,'Source')
            snap.text = "SPOTIFY"

        try:
            xml_tree.find('Key'+presetnum+'/PicUrl').text = "https://brands.home-assistant.io/_/media_player/icon.png"
        except:
            data=xml_tree.find('Key'+presetnum)
            snap=ET.SubElement(data,'PicUrl')
            snap.text = "https://brands.home-assistant.io/_/media_player/icon.png"

        preset_map = ET.tostring(xml_tree, encoding='unicode')

        try:
            setmap = self._upnp_device.PlayQueue.SetKeyMapping(QueueContext=preset_map)
        except:
            _LOGGER.debug("SetKeyMapping UPNP error: %s, %s", self.entity_id, preset_map)
            return

    def _tracklist_via_upnp(self, media):
        """Retrieve tracks list queue via UPNP."""
        if self._upnp_device is None:
            return

        if media == 'USB':
            queuename = 'USBDiskQueue'  # 'CurrentQueue'  # 'USBDiskQueue'
            rootdir = ROOTDIR_USB
        else:
            _LOGGER.debug("Tracklist retrieval: %s, %s is not supported. You can use only 'USB' for now.", self.entity_id, media_info)
            self._trackq = []
            return

        try:
            media_info = self._upnp_device.PlayQueue.BrowseQueue(QueueName=queuename)
        except:
            _LOGGER.debug("Tracklist get error, media not present?: %s, %s", self.entity_id, media)
            self._trackq = []
            return

        media_info = media_info.get('QueueContext')
        if media_info is None:
            return

        xml_tree = ET.fromstring(media_info)

        trackq = []
        for playlist in xml_tree:
           for tracks in playlist:
               for track in tracks:
                   if track.tag == 'URL':
                       if rootdir in track.text:
                           tracku = track.text.replace(rootdir, '')
                           trackq.append(tracku)

        if len(trackq) > 0:
            self._trackq = trackq

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        """Implement the websocket media browsing helper."""
        if media_content_id not in (None, "root"):
            raise BrowseError(
                f"Media not found: {media_content_type} / {media_content_id}"
            )

        source_media_name = self._source_list.get("udisk", "USB Disk")

        if len(self._trackq) > 0:
            radio = [
                BrowseMedia(
                    title = preset,
                    media_class = MEDIA_CLASS_MUSIC,
                    media_content_id = index,
                    media_content_type = MEDIA_TYPE_MUSIC,
                    can_play = True,
                    can_expand = False,
                )
                for index, preset in enumerate(self._trackq, start=1)
            ]

            root = BrowseMedia(
                title=self._name + " " + source_media_name,
                media_class = MEDIA_CLASS_DIRECTORY,
                media_content_id = "root",
                media_content_type = "listing",
                can_play = False,
                can_expand = True,
                children = radio,
            )

        else:
            root = BrowseMedia(
                title=self._name + " " + source_media_name,
                media_class = MEDIA_CLASS_DIRECTORY,
                media_content_id = "root",
                media_content_type = "listing",
                can_play = False,
                can_expand = False,
            )

        return root

    def fill_input_select(self, in_slct, trk_src):
        """Fill the specified input select with tracks list."""
        self._tracklist_via_upnp(trk_src)
        if len(self._trackq) > 0:
            service_data = {'entity_id': in_slct, 'options': self._trackq}
            self.hass.services.call('input_select', 'set_options', service_data)
            return
        else:
            _LOGGER.debug("Retrieved tracklist empty: %s, tracklist: %s", self.entity_id, self._trackq)

    def play_track(self, track):
        """Play media track by name found in the tracks list."""
        if not len(self._trackq) > 0 or track is None:
            return

        track.hass = self.hass   # render template
        trackn = track.async_render()

        if not self._slave_mode:
            try:
                index = [idx for idx, s in enumerate(self._trackq) if trackn in s][0]
            except (IndexError):
                return

            if not index > 0:
                return

            self._lpapi.call('GET', 'setPlayerCmd:playLocalList:{0}'.format(index))
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to play media track by name. Device: %s, Got response: %s", self.entity_id, value)
                return False
            else:
                self._state = STATE_PLAYING
                self._playing_tts = False
                self._wait_for_mcu = 0.4
                self._media_title = None
                self._media_artist = None
                self._media_album = None
                self._trackc = None
                self._icecast_name = None
                self._playhead_position = 0
                self._duration = 0
                self._position_updated_at = utcnow()
                self._media_image_url = None
                self._media_uri = None
                self._ice_skip_throt = False
                self._unav_throttle = False
                self.schedule_update_ha_state(True)
                return True
        else:
            self._master.play_track(track)


    @Throttle(ICE_THROTTLE)
    def _update_from_icecast(self):
        """Update track info from icecast stream."""
        if self._icecast_meta == 'Off':
            return True
        #_LOGGER.debug('Looking for IceCast metadata: %s', self._name)

#        def NiceToICY(self):
#            class InterceptedHTTPResponse():
#                pass
#            import io
#            line = self.fp.readline().replace(b"ICY 200 OK\r\n", b"HTTP/1.0 200 OK\r\n")
#            InterceptedSelf = InterceptedHTTPResponse()
#            InterceptedSelf.fp = io.BufferedReader(io.BytesIO(line))
#            InterceptedSelf.debuglevel = self.debuglevel
#            InterceptedSelf._close_conn = self._close_conn
#            return ORIGINAL_HTTP_CLIENT_READ_STATUS(InterceptedSelf)

#        ORIGINAL_HTTP_CLIENT_READ_STATUS = urllib.request.http.client.HTTPResponse._read_status
#        urllib.request.http.client.HTTPResponse._read_status = NiceToICY

        try:
            request = urllib.request.Request(self._media_uri, headers={'Icy-MetaData': 1})  # request metadata
            response = urllib.request.urlopen(request)
        except:  # (urllib.error.HTTPError)
            self._media_title = None
            self._media_artist = None
            self._icecast_name = None
            self._media_image_url = None
            return True

        icy_name = response.headers['icy-name']
        if icy_name is not None and icy_name != 'no name' and icy_name != 'Unspecified name' and icy_name != '-':
            try:  # 'latin1' # default: iso-8859-1 for mp3 and utf-8 for ogg streams
                self._icecast_name = icy_name.encode('latin1').decode('utf-8')
            except (UnicodeDecodeError):
                self._icecast_name = icy_name

            #_LOGGER.debug('For: %s found icy_name: %s', self._name, '"' + icy_name + '"')

        else:
            self._icecast_name = None

        if self._icecast_meta == 'StationName':
            self._media_title = self._icecast_name
            self._media_artist = None
            self._media_image_url = None
            return True

        import re
        import struct
        import chardet
        icy_metaint_header = response.headers['icy-metaint']
        if icy_metaint_header is not None:
            metaint = int(icy_metaint_header)
            for _ in range(10):  # title may be empty initially, try several times
                response.read(metaint)  # skip to metadata
                metadata_length = struct.unpack('B', response.read(1))[0] * 16  # length byte
                metadata = response.read(metadata_length).rstrip(b'\0')
                #_LOGGER.debug('For: %s found metadata: %s', self._name, metadata)

                # extract title from the metadata
                # m = re.search(br"StreamTitle='([^']*)';", metadata)
                m = re.search(br"StreamTitle='(.*)';", metadata)
                #_LOGGER.debug('For: %s found m: %s', self._name, m)
                if m:
                    title = m.group(0)
                    #_LOGGER.debug('For: %s found title: %s', self._name, title)

                    if title:
                        code_detect = chardet.detect(title)['encoding']
                        title = title.decode(code_detect, errors='ignore')
                        titlek = title.split("';")
                        title = titlek[0]
                        titlem = title.split("='")
                        title = titlem[1]
                        #_LOGGER.debug('For: %s found decoded title: %s', self._name, title)

                        title = re.sub(r'\[.*?\]\ *', '', title)  #  "\s*\[.*?\]\s*"," ",title)
                        if title.find('~~~~~') != -1:  # for United Music Subasio servers
                            titles = title.split('~')
                            self._media_artist = string.capwords(titles[0].strip().strip('-'))
                            self._media_title = string.capwords(titles[1].strip().strip('-'))
                        elif title.find(' - ') != -1:  # for ordinary Icecast servers
                            titles = title.split(' - ')
                            self._media_artist = string.capwords(titles[0].strip().strip('-'))
                            self._media_title = string.capwords(titles[1].strip().strip('-'))
                        else:
                            if self._icecast_name is not None:
                                self._media_artist = '[' + self._icecast_name + ']'
                            else:
                                self._media_artist = None
                            self._media_title = string.capwords(title)

                        if self._media_artist == '-':
                            self._media_artist = None
                        if self._media_title == '-':
                            self._media_title = None

                        if self._media_artist is not None:
                            self._media_artist.replace('/', ' / ')
                            self._media_artist.replace('  ', ' ')

                        if self._media_title is not None:
                            self._media_title.replace('/', ' / ')
                            self._media_title.replace('  ', ' ')

                        break
                else:
                    if self._icecast_name is not None:
                        self._media_title = self._icecast_name
                    else:
                        self._media_title = None
                    self._media_artist = None
                    self._media_image_url = None

        else:
            if self._icecast_name is not None:
                self._media_title = self._icecast_name
            else:
                self._media_title = None
            self._media_artist = None
            self._media_image_url = None

        #_LOGGER.debug('For: %s stated media_title: %s', self._name, self._media_title)
        #_LOGGER.debug('For: %s stated media_artist: %s', self._name, self._media_artist)

    def _get_playerstatus_metadata(self, plr_stat):
        try:
            if plr_stat['uri'] != "":
                rootdir = ROOTDIR_USB
                try:
                    self._trackc = str(bytearray.fromhex(plr_stat['uri']).decode('utf-8')).replace(rootdir, '')
                except ValueError:
                    self._trackc = plr_stat['uri'].replace(rootdir, '')
        except KeyError:
            pass
        if plr_stat['Title'] != '':
            try:
                title = str(bytearray.fromhex(plr_stat['Title']).decode('utf-8'))
            except ValueError:
                title = plr_stat['Title']
            if title.lower() != 'unknown':
                self._media_title = string.capwords(title)
                if self._trackc == None:
                    self._trackc = self._media_title
            else:
                self._media_title = None
        if plr_stat['Artist'] != '':
            try:
                artist = str(bytearray.fromhex(plr_stat['Artist']).decode('utf-8'))
            except ValueError:
                artist = plr_stat['Artist']
            if artist.lower() != 'unknown':
                self._media_artist = string.capwords(artist)
            else:
                self._media_artist = None
        if plr_stat['Album'] != '':
            try:
                album = str(bytearray.fromhex(plr_stat['Album']).decode('utf-8'))
            except ValueError:
                album = plr_stat['Album']
            if album.lower() != 'unknown':
                self._media_album = string.capwords(album)
            else:
                self._media_album = None

        if self._media_title is not None and self._media_artist is not None:
            return True
        else:
            return False

    def _get_lastfm_coverart(self):
        """Get cover art from last.fm."""
        if self._media_title is None or self._media_artist is None:
            self._media_image_url = None
            return

        self._lfmapi.call('GET', 'track.getInfo', "artist={0}&track={1}".format(self._media_artist, self._media_title))
        lfmdata = json.loads(self._lfmapi.data)
        try:
            self._media_image_url = lfmdata['track']['album']['image'][3]['#text']
        except (ValueError, KeyError):
            self._media_image_url = None

        if self._media_image_url == '':
            self._media_image_url = None

    def upnp_discover(self, timeout=5):
        devices = {}
        for entry in netdisco.ssdp.scan(timeout):
            if entry.location in devices:
                continue
            try:
                devices[entry.location] = upnpclient.Device(entry.location)
            except Exception as exc:
                _LOGGER.debug('Error \'%s\' for %s', exc, entry.location)
        return list(devices.values())

    def trigger_schedule_update(self, before):
        self.schedule_update_ha_state(before)

    def update(self):
        """Get the latest player details from the device."""
        if self._master is None:
            self._slave_mode = False

        if self._slave_mode or self._snapshot_active:
            return True

        if self._multiroom_unjoinat is not None:
            if self._multiroom_wifidirect:
                waittim = MROOM_UJWDIR
            else:
                waittim = MROOM_UJWROU

            if utcnow() <= (self._multiroom_unjoinat + waittim):
                self._source = None
                self._media_title = None
                self._media_artist = None
                self._media_uri = None
                self._media_image_url = None
                self._state = STATE_IDLE
                return True
            else:
                self._multiroom_unjoinat = None
                self._playhead_position = 0
                self._duration = 0
                self._position_updated_at = utcnow()
#                self.restore_previous_source()
                self.select_source(self._multiroom_prevsrc)
                self._multiroom_prevsrc = None
                return True

        if self._wait_for_mcu > 0:  # have wait for the hardware unit to finish processing command, otherwise some reported status values will be incorrect
            time.sleep(self._wait_for_mcu)
            self._wait_for_mcu = 0

        if self._unav_throttle:
            player_api_result = self._get_status('getPlayerStatus')
        else:
            player_api_result = self._get_status('getPlayerStatus', no_throttle=True)

        if player_api_result is None:
            _LOGGER.debug("No response from api: %s, %s", self.entity_id, player_api_result)
            return

        try:
            player_status = json.loads(player_api_result)
        except ValueError:
            _LOGGER.warning("Erroneous JSON during update player_status: %s, %s", self.entity_id, self._name)
            return

        if isinstance(player_status, dict):
            self._unav_throttle = False
            if self._first_update or (self._state == STATE_UNAVAILABLE or self._multiroom_wifidirect):
                self._lpapi.call('GET', 'getStatus')
                device_api_result = self._lpapi.data
                if device_api_result is not None:
                    try:
                        device_status = json.loads(device_api_result)
                    except ValueError:
                        _LOGGER.debug("Erroneous JSON during first update: %s, %s", self.entity_id, device_api_result)
                        device_status = None
                    if isinstance(device_status, dict):
                        if self._state == STATE_UNAVAILABLE:
                            self._state = STATE_IDLE
                        self._wifi_channel = device_status['WifiChannel']
                        self._ssid = binascii.hexlify(device_status['ssid'].encode('utf-8'))
                        self._ssid = self._ssid.decode()
                        try:
                            self._name = device_status['DeviceName']
                        except KeyError:
                            pass

                        try:
                            self._fw_ver = device_status['firmware']
                        except KeyError:
                            fw_ver = '1.0.0'

                        try:
                            self._preset_key = int(device_status['preset_key'])
                        except KeyError:
                            preset_key = 4

                        try:
                            self._uuid = device_status['uuid']  # FF31F09E - Arylic
                        except KeyError:
                            self._uuid = self._host

                        if not self._multiroom_wifidirect and self._fw_ver:
                            if self._fwvercheck(self._fw_ver) < self._fwvercheck(FW_MROOM_RTR_MIN):
                                self._multiroom_wifidirect = True

                        if self._upnp_device is None and self._name is not None:
                            for entry in self.upnp_discover(UPNP_TIMEOUT):
                                if entry.friendly_name == self._name:
                                    self._upnp_device = upnpclient.Device(entry.location)
                                    break

                        if self._first_update:
                            self._position_updated_at = utcnow()
                            self._duration = 0
                            self._playhead_position = 0
                            if "udisk" in self._source_list:
                                self._tracklist_via_upnp("USB")
                            self._first_update = False

            if self._multiroom_group == []:
                self._slave_mode = False
                self._is_master = False
                self._master = None

            if not self._is_master:
                self._master = None
                self._multiroom_group = []

            self._volume = player_status['vol']
            self._muted = bool(int(player_status['mute'])) 
            self._sound_mode = SOUND_MODES.get(player_status['eq'])

            self._shuffle = {
                '2': True,
            }.get(player_status['loop'], False)

            self._repeat = {
                '2': REPEAT_MODE_ALL,
                '3': REPEAT_MODE_ALL,
                '1': REPEAT_MODE_ONE,
            }.get(player_status['loop'], REPEAT_MODE_OFF)

            self._state = {
                'stop': STATE_IDLE,
                'load': STATE_PLAYING,
                'play': STATE_PLAYING,
                'pause': STATE_PAUSED,
            }.get(player_status['status'], STATE_IDLE)

            if self._state in [STATE_PLAYING, STATE_PAUSED]:
                self._position_updated_at = utcnow()
                self._duration = int(int(player_status['totlen']) / 1000)
                self._playhead_position = int(int(player_status['curpos']) / 1000)
            else:
                self._duration = 0
                self._playhead_position = 0

            self._playing_spotify = bool(player_status['mode'] == '31')
            self._playing_liveinput = player_status['mode'] in SOURCES_LIVEIN
            self._playing_stream = player_status['mode'] in SOURCES_STREAM
            self._playing_localfile = player_status['mode'] in SOURCES_LOCALF

            if bool(player_status['mode'] != '10'):
                self._playing_tts = False

            if not (self._playing_liveinput or self._playing_stream or self._playing_spotify):
                self._playing_localfile = True

            try:
                if self._playing_stream and player_status['uri'] != "":
                    try:
                        self._media_uri = str(bytearray.fromhex(player_status['uri']).decode('utf-8'))
                    except ValueError:
                        self._media_uri = player_status['uri']
            except KeyError:
                pass

            if self._media_uri:
                # Detect web music service by their CDN subdomains in the URL
                # Tidal, Deezer
                self._playing_webplaylist = \
                    bool(self._media_uri.find('audio.tidal.') != -1) or \
                    bool(self._media_uri.find('.dzcdn.') != -1) or \
                    bool(self._media_uri.find('.deezer.') != -1)

            if not self._playing_webplaylist:
                source_t = SOURCES_MAP.get(player_status['mode'], 'Network')
                source_n = None
                if source_t == 'Network':
                    if self._media_uri:
                        source_n = self._source_list.get(self._media_uri, 'Network')
                else:
                    source_n = self._source_list.get(source_t, None)

                if source_n != None:
                    self._source = source_n
                else:
                    self._source = source_t
            else:
                self._source = 'Web playlist'

            if self._source != 'Network' and not (self._playing_stream or self._playing_localfile):
                if self._source == 'Idle':
                    self._media_title = None
                    self._state = STATE_IDLE
                else:
                    self._media_title = self._source
                    self._state = STATE_PLAYING

                self._media_artist = None
                self._media_album = None
                self._media_image_url = None
                self._icecast_name = None

            if player_status['mode'] in ['1', '2', '3']:
                self._state = STATE_PLAYING
                self._media_title = self._source

            if player_status['mode'] in ['11', '16'] and len(self._trackq) <= 0:
                if int(player_status['curpos']) > 6000 and self._state == STATE_PLAYING:
                    self._tracklist_via_upnp("USB")

            if self._playing_spotify:
                self._update_via_upnp()

            elif self._playing_webplaylist:
                self._update_via_upnp()

            else:
                if self._state not in [STATE_PLAYING, STATE_PAUSED]:
                    self._media_title = None
                    self._media_artist = None
                    self._media_album = None
                    self._media_image_url = None
                    self._icecast_name = None
                    self._playing_tts = False

                if self._playing_localfile and self._state in [STATE_PLAYING, STATE_PAUSED] and not self._playing_tts:
                    self._get_playerstatus_metadata(player_status)

                    if self._media_title is not None and self._media_artist is None:
                        cutext = ['mp3', 'mp2', 'm2a', 'mpg', 'wav', 'aac', 'flac', 'flc', 'm4a', 'ape', 'wma', 'ac3', 'ogg']
                        querywords = self._media_title.split('.')
                        resultwords  = [word for word in querywords if word.lower() not in cutext]
                        title = ' '.join(resultwords)
                        title.replace('_', ' ')
                        if title.find(' - ') != -1:
                            titles = title.split(' - ')
                            self._media_artist = string.capwords(titles[0].strip().strip('-'))
                            self._media_title = string.capwords(titles[1].strip().strip('-'))
                        else:
                            self._media_title = string.capwords(title.strip().strip('-'))
                    else:
                        self._media_title = self._source

                elif self._state == STATE_PLAYING and self._media_uri and int(player_status['totlen']) > 0 and not self._snapshot_active and not self._playing_tts:
                    self._get_playerstatus_metadata(player_status)

                elif self._state == STATE_PLAYING and self._media_uri and int(player_status['totlen']) <= 0 and not self._snapshot_active and not self._playing_tts:
                    if self._ice_skip_throt:
                        self._update_from_icecast(no_throttle=True)
                        self._ice_skip_throt = False
                    else:
                        self._update_from_icecast()

                self._new_song = self._is_playing_new_track()
                if self._lfmapi is not None and self._new_song:
                    self._get_lastfm_coverart()

            self._media_prev_artist = self._media_artist
            self._media_prev_title = self._media_title

        else:
            _LOGGER.warning("Erroneous JSON during update and process player_status: %s, %s", self.entity_id, self._name)

        # Get multiroom slave information #
        self._lpapi.call('GET', 'multiroom:getSlaveList')
        slave_list = self._lpapi.data
        if slave_list is None:
            self._is_master = False
            self._slave_list = None
            self._multiroom_group = []
            return True

        try:
            slave_list = json.loads(slave_list)
        except ValueError:
            _LOGGER.debug("Erroneous JSON during slave list parsing: %s, %s", self.entity_id, self._name)
            slave_list = None
            self._slave_list = None
            self._multiroom_group = []

        self._slave_list = []
        self._multiroom_group = []
        if isinstance(slave_list, dict):
            if int(slave_list['slaves']) > 0:
                self._multiroom_group.append(self.entity_id)
                self._is_master = True
                for slave in slave_list['slave_list']:
                    for device in self.hass.data[DOMAIN].entities:
                        if device._name == slave['name']:
                            self._multiroom_group.append(device.entity_id)
                            device.set_master(self)
                            device.set_is_master(False)
                            device.set_slave_mode(True)
                            device.set_media_title(self._media_title)
                            device.set_media_artist(self._media_artist)
                            device.set_volume(slave['volume'])
                            #device.set_muted(slave['mute'])
                            device.set_state(self.state)
                            device.set_slave_ip(slave['ip'])
                            device.set_media_image_url(self._media_image_url)
                            device.set_playhead_position(self.media_position)
                            device.set_duration(self.media_duration)
                            device.set_position_updated_at(self.media_position_updated_at)
                            device.set_source(self._source)
                            device.set_sound_mode(self._sound_mode)
                            device.set_features(self._features)

                    for slave in slave_list['slave_list']:
                        for device in self.hass.data[DOMAIN].entities:
                            if device.entity_id in self._multiroom_group:
                                device.set_multiroom_group(self._multiroom_group)

        else:
            _LOGGER.debug("Erroneous JSON during slave list parsing and processing: %s, %s", self.entity_id, self._name)

        return True

class LinkPlayRestData:
    """Class for handling the data retrieval from the Linkplay device."""
    def __init__(self, host):
        """Initialize the data object."""
        self.data = None
        self._request = None
        self._host = host

    def call(self, method, cmd):
        """Get the latest data from REST service."""
        self.data = None
        self._request = None
        resource = "http://{0}/httpapi.asp?command={1}".format(self._host, cmd)
        self._request = requests.Request(method, resource).prepare()
#        _LOGGER.debug("Updating LinkPlayRestData from %s", self._request.url)
        try:
            with requests.Session() as sess:
                response = sess.send(
                    self._request, timeout=5)
#            self.data = response.text
            self.data = str(response.content, 'utf-8', errors='replace')

        except requests.exceptions.RequestException as ex:
            _LOGGER.debug("Error fetching data: %s from %s failed with %s", self._request, self._request.url, ex)
            self.data = None

class LinkPlayTcpUartData:
    """Class for handling the data retrieval from the Linkplay device."""
    def __init__(self, host):
        """Initialize the data object."""
        self.data = None
        self._host = host

    def call(self, cmd):
        """Get the latest data from TCP service."""
        HEAD = '18 96 18 20 0b 00 00 00 c1 02 00 00 00 00 00 00 00 00 00 00 '
        CMHX = ' '.join(hex(ord(c))[2:] for c in cmd)
        self.data = None
#        _LOGGER.debug("Sending to %s TCP command: %s", self._host, cmd)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self._host, TCPPORT))
                s.send(bytes.fromhex(HEAD + CMHX))
                data = str(repr(s.recv(1024))).encode().decode("unicode-escape")

            pos = data.find("AXX")
            if pos == -1:
                pos = data.find("MCU")

            self.data = data[pos:(len(data)-2)]
#            _LOGGER.debug("Received from %s TCP command result: %s", self._host, self.data)
            try:
                s.close()
            except:
                pass

        except socket.error as ex:
            _LOGGER.debug("Error sending TCP command: %s with %s", cmd, ex)
            self.data = None

class LastFMRestData:
    """Class for handling the data retrieval from the Linkplay device."""
    def __init__(self, api_key):
        """Initialize the data object."""
        self.data = None
        self._request = None
        self._api_key = api_key

    def call(self, method, cmd, params):
        """Get the latest data from REST service."""
        self.data = None
        self._request = None
        resource = "{0}{1}&{2}&api_key={3}&format=json".format(
            LASTFM_API_BASE, cmd, params, self._api_key)
        self._request = requests.Request(method, resource).prepare()
#        _LOGGER.debug("Updating LastFMRestData from %s", self._request.url)
        try:
            with requests.Session() as sess:
                response = sess.send(
                    self._request, timeout=10)
            self.data = response.text

        except requests.exceptions.RequestException as ex:
            _LOGGER.debug("Error fetching data: %s from %s failed with %s", self._request, self._request.url, ex)
            self.data = None
# END
