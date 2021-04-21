"""Binary sensor platform for Beward devices."""

import logging
from typing import Dict, Optional, Any

import beward

try:
    from homeassistant.components.binary_sensor import BinarySensorEntity
except ImportError:
    from homeassistant.components.binary_sensor import (
        BinarySensorDevice as BinarySensorEntity,
    )
from homeassistant.const import CONF_NAME, CONF_BINARY_SENSORS
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import DOMAIN
from .const import EVENT_ONLINE, CAT_DOORBELL, CAT_CAMERA, BINARY_SENSORS

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
    for sensor_type in discovery_info[CONF_BINARY_SENSORS]:
        if category in BINARY_SENSORS[sensor_type][1]:
            sensors.append(BewardBinarySensor(controller, sensor_type))

    async_add_entities(sensors, True)


class BewardBinarySensor(BinarySensorEntity):
    """A binary sensor implementation for Beward device."""

    def __init__(self, controller, sensor_type: str):
        """Initialize a sensor for Beward device."""
        super().__init__()

        self._unsub_dispatcher = None
        self._sensor_type = sensor_type
        self._controller = controller
        self._name = "{} {}".format(
            self._controller.name, BINARY_SENSORS[self._sensor_type][0]
        )
        self._device_class = BINARY_SENSORS[self._sensor_type][2]
        self._state = None
        self._unique_id = f"{self._controller.unique_id}-{self._sensor_type}"

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state."""
        return False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._sensor_type == EVENT_ONLINE or self._controller.available

    @property
    def is_on(self) -> Optional[bool]:
        """Return True if the binary sensor is on."""
        return self._state

    @property
    def device_class(self) -> Optional[str]:
        """Return the class of the binary sensor."""
        return self._device_class

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return self._unique_id

    @property
    def device_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return the state attributes."""
        return self._controller.device_state_attributes

    async def async_update(self) -> None:
        """Get the latest data and updates the state."""
        self._update_callback(update_ha_state=False)

    @callback
    def _update_callback(self, update_ha_state=True) -> None:
        """Get the latest data and updates the state."""
        state = (
            self._controller.available
            if self._sensor_type == EVENT_ONLINE
            else self._controller.event_state.get(self._sensor_type, False)
        )
        if self._state != state:
            self._state = state
            _LOGGER.debug(
                '%s binary sensor state changed to "%s"', self._name, self._state
            )
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
