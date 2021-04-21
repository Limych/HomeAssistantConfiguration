"""
Component to integrate with Beward security devices.

For more details about this component, please refer to
https://github.com/Limych/ha-beward
"""

import logging
import os
import tempfile
from datetime import datetime
from typing import Dict

import beward
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
import voluptuous as vol
from beward.const import ALARM_MOTION, ALARM_SENSOR
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR
from homeassistant.components.camera import DOMAIN as CAMERA
from homeassistant.components.ffmpeg.camera import DEFAULT_ARGUMENTS
from homeassistant.components.sensor import DOMAIN as SENSOR
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_BINARY_SENSORS,
    CONF_SENSORS,
    ATTR_ATTRIBUTION,
)
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers import discovery
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.event import track_time_interval
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.util import slugify

from .const import (
    CONF_STREAM,
    ALARMS_TO_EVENTS,
    CONF_RTSP_PORT,
    CONF_CAMERAS,
    CONF_FFMPEG_ARGUMENTS,
    SUPPORT_LIB_URL,
    DEVICE_CHECK_INTERVAL,
    ATTR_DEVICE_ID,
    CAMERAS,
    BINARY_SENSORS,
    SENSORS,
)

_LOGGER = logging.getLogger(__name__)

# Base component constants
DOMAIN = "beward"
VERSION = "dev"
ISSUE_URL = "https://github.com/Limych/ha-beward/issues"
ATTRIBUTION = "Data provided by Beward device."

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_PORT, default=80): int,
        vol.Optional(CONF_RTSP_PORT): int,
        vol.Optional(CONF_STREAM, default=0): int,
        vol.Optional(CONF_FFMPEG_ARGUMENTS, default=DEFAULT_ARGUMENTS): cv.string,
        vol.Optional(CONF_CAMERAS, default=list(CAMERAS)): vol.All(
            cv.ensure_list, [vol.In(CAMERAS)]
        ),
        vol.Optional(CONF_BINARY_SENSORS): vol.All(
            cv.ensure_list, [vol.In(BINARY_SENSORS)]
        ),
        vol.Optional(CONF_SENSORS): vol.All(cv.ensure_list, [vol.In(SENSORS)]),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [DEVICE_SCHEMA])}, extra=vol.ALLOW_EXTRA
)


def setup(hass, config):
    """Set up component."""
    conf = config.get(DOMAIN)
    if conf is None:
        return True

    # Print startup message
    _LOGGER.info("Version %s", VERSION)
    _LOGGER.info(
        "If you have ANY issues with this, please report them here: %s", ISSUE_URL
    )

    hass.data.setdefault(DOMAIN, {})

    for index, device_config in enumerate(config[DOMAIN]):
        device_ip = device_config.get(CONF_HOST)
        name = device_config.get(CONF_NAME)
        username = device_config.get(CONF_USERNAME)
        password = device_config.get(CONF_PASSWORD)
        port = device_config.get(CONF_PORT)
        rtsp_port = device_config.get(CONF_RTSP_PORT)
        stream = device_config.get(CONF_STREAM)
        ffmpeg_arguments = config.get(CONF_FFMPEG_ARGUMENTS)
        cameras = device_config.get(CONF_CAMERAS)
        binary_sensors = device_config.get(CONF_BINARY_SENSORS)
        sensors = device_config.get(CONF_SENSORS)

        _LOGGER.debug("Connecting to device %s", device_ip)

        try:
            device = beward.Beward.factory(
                device_ip,
                username,
                password,
                port=port,
                rtsp_port=rtsp_port,
                stream=stream,
            )
        except ValueError as exc:
            _LOGGER.error(exc)
            if exc == 'Unknown device "None"':
                msg = (
                    "Device recognition error.<br />"
                    "Please try restarting Home Assistant — it usually helps."
                )
            else:
                msg = (
                    "Error: {}<br />"
                    'Please <a href="{}" target="_blank">contact the developers '
                    "of the Beward library</a> to solve this problem."
                    "".format(exc, SUPPORT_LIB_URL)
                )
            hass.components.persistent_notification.create(
                msg,
                title="Beward device Initialization Failure",
                notification_id="beward_connection_error",
            )
            raise PlatformNotReady from exc

        if device is None or not device.available:
            if device is None:
                err_msg = (
                    "Authorization rejected by Beward device for %s@%s" % username,
                    device_ip,
                )
            else:
                err_msg = (
                    "Could not connect to Beward device as %s@%s" % username,
                    device_ip,
                )

            _LOGGER.error(err_msg)
            hass.components.persistent_notification.create(
                "Error: {}<br />"
                "You will need to restart Home Assistant after fixing."
                "".format(err_msg),
                title="Beward device Configuration Failure",
                notification_id="beward_connection_error",
            )
            raise PlatformNotReady

        if name is None:
            name = "Beward %s" % device.system_info.get("DeviceID", "#%d" % (index + 1))
        if name in list(hass.data[DOMAIN]):
            _LOGGER.error('Duplicate name! Beward device "%s" is already exists.', name)
            continue

        controller = BewardController(hass, device, name)
        hass.data[DOMAIN][name] = controller
        _LOGGER.info(
            'Connected to Beward device "%s" as %s@%s',
            controller.name,
            username,
            device_ip,
        )

        if cameras:
            discovery.load_platform(
                hass,
                CAMERA,
                DOMAIN,
                {
                    CONF_NAME: name,
                    CONF_CAMERAS: cameras,
                    CONF_FFMPEG_ARGUMENTS: ffmpeg_arguments,
                },
                config,
            )

        if binary_sensors:
            discovery.load_platform(
                hass,
                BINARY_SENSOR,
                DOMAIN,
                {CONF_NAME: name, CONF_BINARY_SENSORS: binary_sensors},
                config,
            )

        if sensors:
            discovery.load_platform(
                hass, SENSOR, DOMAIN, {CONF_NAME: name, CONF_SENSORS: sensors}, config
            )

    if not hass.data[DOMAIN]:
        return False

    return True


class BewardController:
    """Beward device controller."""

    def __init__(self, hass, device: beward.BewardGeneric, name: str):
        """Initialize configured device."""
        self.hass = hass
        self._device = device
        self._name = name
        self._unique_id = self._device.system_info.get("DeviceID", self._device.host)

        self._available = True
        self.event_timestamp: Dict[str, datetime] = {}
        self.event_state: Dict[str, bool] = {}

        # Register callback to handle device alarms.
        self._device.add_alarms_handler(self._alarms_handler)
        self._device.listen_alarms(alarms=(ALARM_MOTION, ALARM_SENSOR))

        track_time_interval(hass, self._update_available, DEVICE_CHECK_INTERVAL)

    def service_signal(self, service):
        """Encode service and identifier into signal."""
        signal = "{}_{}_{}".format(DOMAIN, service, self.unique_id.replace(".", "_"))
        return signal

    @property
    def unique_id(self):
        """Return a device unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Get custom device name."""
        return self._name

    @property
    def device(self):
        """Get the configured device."""
        return self._device

    @property
    def available(self) -> bool:
        """Return True if device is available."""
        return self._available

    def _update_available(self, _=None):
        available = self._device.available
        if self._available != available:
            self._available = available
            _LOGGER.warning(
                'Device "%s" is %s',
                self._name,
                "reconnected" if available else "unavailable",
            )

            dispatcher_send(self.hass, self.service_signal("update"))

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            ATTR_DEVICE_ID: self.unique_id,
        }
        return attrs

    def history_image_path(self, event: str):
        """Return the path to saved image."""
        file_name = slugify(f"{self.name} last {event}") + ".jpg"
        return self.hass.config.path(STORAGE_DIR, DOMAIN, file_name)

    def set_event_state(self, timestamp: datetime, event: str, state: bool):
        """Call Beward to refresh information."""
        _LOGGER.debug("Updating Beward component")
        if state:
            self.event_timestamp[event] = timestamp
        self.event_state[event] = state

    def _cache_image(self, event: str, image):
        """Save image for event to cache."""
        image_path = self.history_image_path(event)
        tmp_filename = ""
        image_dir = os.path.split(image_path)[0]
        _LOGGER.debug("Save camera photo to %s", image_path)
        if not os.path.exists(image_dir):
            os.makedirs(image_dir, mode=0o755)
        try:
            # Modern versions of Python tempfile create
            # this file with mode 0o600
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=image_dir, delete=False
            ) as fdesc:
                fdesc.write(image)
                tmp_filename = fdesc.name
            os.chmod(tmp_filename, 0o644)
            os.replace(tmp_filename, image_path)
        except OSError as error:
            _LOGGER.exception("Saving image file failed: %s", image_path)
            raise error
        finally:
            if os.path.exists(tmp_filename):
                try:
                    os.remove(tmp_filename)
                except OSError as err:
                    # If we are cleaning up then something else
                    # went wrong, so we should suppress likely
                    # follow-on errors in the cleanup
                    _LOGGER.error("Image replacement cleanup failed: %s", err)

    def _alarms_handler(self, device, timestamp: datetime, alarm: str, state: bool):
        """Handle device's alarm events."""
        timestamp = dt_util.as_local(dt_util.as_utc(timestamp))
        _LOGGER.debug(
            'Handle alarm "%s". State %s at %s', alarm, state, timestamp.isoformat()
        )
        if alarm in (ALARM_MOTION, ALARM_SENSOR) and device == self._device:
            event = ALARMS_TO_EVENTS[alarm]
            self.event_state[event] = state
            if state:
                self.event_timestamp[event] = timestamp
                if isinstance(self._device, beward.BewardCamera):
                    self._cache_image(event, self._device.live_image)

            dispatcher_send(self.hass, self.service_signal("update"))
