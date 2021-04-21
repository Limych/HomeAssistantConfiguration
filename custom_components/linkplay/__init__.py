"""
Support for LinkPlay based devices.

For more details about this platform, please refer to the documentation at
https://github.com/nagyrobi/home-assistant-custom-components-linkplay
"""
import logging
import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import config_validation as cv

DOMAIN = 'linkplay'

SERVICE_JOIN = 'join'
SERVICE_UNJOIN = 'unjoin'
SERVICE_PRESET = 'preset'
SERVICE_CMD = 'command'
SERVICE_SNAP = 'snapshot'
SERVICE_REST = 'restore'
SERVICE_LIST = 'get_tracks'
SERVICE_PLAY = 'play_track'

ATTR_MASTER = 'master'
ATTR_PRESET = 'preset'
ATTR_CMD = 'command'
ATTR_NOTIF = 'notify'
ATTR_SNAP = 'switchinput'
ATTR_SELECT = 'input_select'
ATTR_SOURCE = 'source'
ATTR_TRACK = 'track'

SERVICE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids
})

JOIN_SERVICE_SCHEMA = SERVICE_SCHEMA.extend({
    vol.Required(ATTR_MASTER): cv.entity_id
})

PRESET_BUTTON_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.comp_entity_ids,
    vol.Required(ATTR_PRESET): cv.positive_int
})

CMND_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.comp_entity_ids,
    vol.Required(ATTR_CMD): cv.string,
    vol.Optional(ATTR_NOTIF, default=True): cv.boolean
})

REST_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.comp_entity_ids
})

SNAP_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.comp_entity_ids,
    vol.Optional(ATTR_SNAP, default=True): cv.boolean
})

GETTRK_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required(ATTR_SELECT): cv.entity_id,
    vol.Optional(ATTR_SOURCE, default='USB'): cv.string
})

PLYTRK_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required(ATTR_TRACK): cv.template
})

_LOGGER = logging.getLogger(__name__)

def setup(hass, config):
    """Handle service configuration."""

    def service_handle(service):
        """Handle services."""
        _LOGGER.debug("service_handle from id: %s",
                      service.data.get(ATTR_ENTITY_ID))
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        entities = hass.data[DOMAIN].entities

        if entity_ids:
            if entity_ids == 'all':
                entity_ids = [e.entity_id for e in entities]
            entities = [e for e in entities if e.entity_id in entity_ids]

        if service.service == SERVICE_JOIN:
            master = [e for e in hass.data[DOMAIN].entities
                      if e.entity_id == service.data[ATTR_MASTER]]
            if master:
                client_entities = [e for e in entities
                                   if e.entity_id != master[0].entity_id]
                _LOGGER.debug("**JOIN** set clients %s for master %s",
                              [e.entity_id for e in client_entities],
                              master[0].entity_id)
                master[0].join(client_entities)

        elif service.service == SERVICE_UNJOIN:
            _LOGGER.debug("**UNJOIN** entities: %s", entities)
            masters = [entities for entities in entities
                       if entities.is_master]
            if masters:
                for master in masters:
                    master.unjoin_all()
            else:
                for entity in entities:
                    entity.unjoin_me()

        elif service.service == SERVICE_PRESET:
            preset = service.data.get(ATTR_PRESET)
            for device in entities:
                if device.entity_id in entity_ids:
                    _LOGGER.debug("**PRESET** entity: %s; preset: %s", device.entity_id, preset)
                    device.preset_button(preset)

        elif service.service == SERVICE_CMD:
            command = service.data.get(ATTR_CMD)
            notify = service.data.get(ATTR_NOTIF)
            for device in entities:
                if device.entity_id in entity_ids:
                    _LOGGER.debug("**COMMAND** entity: %s; command: %s", device.entity_id, command)
                    device.execute_command(command, notify)

        elif service.service == SERVICE_SNAP:
            switchinput = service.data.get(ATTR_SNAP)
            for device in entities:
                if device.entity_id in entity_ids:
                    _LOGGER.debug("**SNAPSHOT** entity: %s;", device.entity_id)
                    device.snapshot(switchinput)

        elif service.service == SERVICE_REST:
            for device in entities:
                if device.entity_id in entity_ids:
                    _LOGGER.debug("**RESTORE** entity: %s;", device.entity_id)
                    device.restore()

        elif service.service == SERVICE_LIST:
            in_slct = service.data.get(ATTR_SELECT)
            trk_src = service.data.get(ATTR_SOURCE)
            for device in entities:
                if device.entity_id in entity_ids:
                    _LOGGER.debug("**GET TRACKS** entity: %s; source: %s; to: %s", device.entity_id, trk_src, in_slct)
                    device.fill_input_select(in_slct, trk_src)

        elif service.service == SERVICE_PLAY:
            track = service.data.get(ATTR_TRACK)
            for device in entities:
                if device.entity_id in entity_ids:
                    _LOGGER.debug("**PLAY TRACK** entity: %s; track: %s", device.entity_id, track)
                    device.play_track(track)


    hass.services.register(
        DOMAIN, SERVICE_JOIN, service_handle, schema=JOIN_SERVICE_SCHEMA)
    hass.services.register(
        DOMAIN, SERVICE_UNJOIN, service_handle, schema=SERVICE_SCHEMA)
    hass.services.register(
        DOMAIN, SERVICE_PRESET, service_handle, schema=PRESET_BUTTON_SCHEMA)
    hass.services.register(
        DOMAIN, SERVICE_CMD, service_handle, schema=CMND_SERVICE_SCHEMA)
    hass.services.register(
        DOMAIN, SERVICE_SNAP, service_handle, schema=SNAP_SERVICE_SCHEMA)
    hass.services.register(
        DOMAIN, SERVICE_REST, service_handle, schema=REST_SERVICE_SCHEMA)
    hass.services.register(
        DOMAIN, SERVICE_LIST, service_handle, schema=GETTRK_SERVICE_SCHEMA)
    hass.services.register(
        DOMAIN, SERVICE_PLAY, service_handle, schema=PLYTRK_SERVICE_SCHEMA)


    return True
