"""Sensor platform for Beward devices."""

import logging
from datetime import datetime
from os import path
from typing import Optional, Union, Dict, Any

import beward
import homeassistant.util.dt as dt_util
from homeassistant.const import (
    CONF_NAME,
    CONF_SENSORS,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from . import DOMAIN
from .const import (
    CAT_DOORBELL,
    CAT_CAMERA,
    EVENT_MOTION,
    EVENT_DING,
    SENSORS,
    SENSOR_LAST_MOTION,
    SENSOR_LAST_DING,
    SENSOR_LAST_ACTIVITY,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
) -> None:
    """Set up a binary sensors for a Beward device."""
    if discovery_info is None:
        return

    name = discovery_info[CONF_NAME]
    controller = hass.data[DOMAIN][name]
    category = None
    if isinstance(controller.device, beward.BewardCamera):
        category = CAT_CAMERA
    if isinstance(controller.device, beward.BewardDoorbell):
        category = CAT_DOORBELL

    sensors = []
    for sensor_type in discovery_info[CONF_SENSORS]:
        if category in SENSORS[sensor_type][1]:
            sensors.append(BewardSensor(controller, sensor_type))

    async_add_entities(sensors, True)


class BewardSensor(Entity):
    """A sensor implementation for Beward device."""

    def __init__(self, controller, sensor_type: str):
        """Initialize a sensor for Beward device."""
        super().__init__()

        self._unsub_dispatcher = None
        self._sensor_type = sensor_type
        self._controller = controller
        self._name = "{} {}".format(
            self._controller.name, SENSORS[self._sensor_type][0]
        )
        self._device_class = SENSORS[self._sensor_type][2]
        self._icon = "mdi:{}".format(SENSORS[self._sensor_type][3])
        self._state = None
        self._unique_id = f"{self._controller.unique_id}-{self._sensor_type}"

        self._update_callback(update_ha_state=False)

    @property
    def name(self) -> Optional[str]:
        """Return the name of the sensor."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._controller.available

    @property
    def state(self) -> Union[None, str, int, float]:
        """Return the state of the sensor."""
        return self._state

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return self._unique_id

    @property
    def device_class(self) -> Optional[str]:
        """Return the class of the sensor."""
        return self._device_class

    @property
    def device_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return the state attributes."""
        return self._controller.device_state_attributes

    @property
    def icon(self) -> Optional[str]:
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def should_poll(self) -> bool:
        """Return the polling state."""
        return False

    def _get_file_mtime(self, event) -> Optional[datetime]:
        image_path = self._controller.history_image_path(event)
        try:
            return dt_util.utc_from_timestamp(path.getmtime(image_path))
        except OSError:
            return None

    def _get_event_timestamp(self, event) -> Optional[datetime]:
        return self._controller.event_timestamp.get(event) or self._get_file_mtime(
            event
        )

    @callback
    def _update_callback(self, update_ha_state=True) -> None:
        """Get the latest data and updates the state."""
        event_ts = None
        if self._sensor_type == SENSOR_LAST_MOTION:
            event_ts = self._get_event_timestamp(EVENT_MOTION)

        elif self._sensor_type == SENSOR_LAST_DING:
            event_ts = self._get_event_timestamp(EVENT_DING)

        elif self._sensor_type == SENSOR_LAST_ACTIVITY:
            event_ts = self._get_event_timestamp(EVENT_MOTION)
            ding_ts = self._get_event_timestamp(EVENT_DING)
            if ding_ts is not None and event_ts is not None and ding_ts > event_ts:
                event_ts = ding_ts

        state = (
            dt_util.as_local(event_ts.replace(microsecond=0)).isoformat()
            if event_ts
            else None
        )
        if self._state != state:
            self._state = state
            _LOGGER.debug('%s sensor state changed to "%s"', self._name, self._state)
            if update_ha_state:
                self.async_schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self._unsub_dispatcher = async_dispatcher_connect(
            self.hass, self._controller.service_signal("update"), self._update_callback,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect from update signal."""
        if self._unsub_dispatcher is not None:
            self._unsub_dispatcher()
