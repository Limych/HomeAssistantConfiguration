"""Constants for Beward component."""
from datetime import timedelta
from typing import Dict

from beward.const import ALARM_MOTION, ALARM_SENSOR
from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_MOTION,
    DEVICE_CLASS_CONNECTIVITY,
)
from homeassistant.const import DEVICE_CLASS_TIMESTAMP

SUPPORT_LIB_URL = "https://github.com/Limych/py-beward/issues/new/choose"

CONF_EVENTS = "events"
CONF_RTSP_PORT = "rtsp_port"
CONF_STREAM = "stream"
CONF_FFMPEG_ARGUMENTS = "ffmpeg_arguments"
CONF_CAMERAS = "cameras"

EVENT_ONLINE = "online"
EVENT_MOTION = "motion"
EVENT_DING = "ding"

ALARMS_TO_EVENTS = {
    ALARM_MOTION: EVENT_MOTION,
    ALARM_SENSOR: EVENT_DING,
}

ATTR_DEVICE_ID = "device_id"

CAT_DOORBELL = "doorbell"
CAT_CAMERA = "camera"

DEVICE_CHECK_INTERVAL = timedelta(seconds=15)

CAMERA_LIVE = "live"
CAMERA_LAST_MOTION = "last_motion"
CAMERA_LAST_DING = "last_ding"

CAMERA_NAME_LIVE = "{} Live"
CAMERA_NAME_LAST_MOTION = "{} Last Motion"
CAMERA_NAME_LAST_DING = "{} Last Ding"

SENSOR_LAST_ACTIVITY = "last_activity"
SENSOR_LAST_MOTION = "last_motion"
SENSOR_LAST_DING = "last_ding"

# Camera types are defined like: name template, device class, device event
CAMERAS: Dict[str, list] = {
    CAMERA_LIVE: [CAMERA_NAME_LIVE, [CAT_DOORBELL, CAT_CAMERA], None],
    CAMERA_LAST_MOTION: [
        CAMERA_NAME_LAST_MOTION,
        [CAT_DOORBELL, CAT_CAMERA],
        EVENT_MOTION,
    ],
    CAMERA_LAST_DING: [CAMERA_NAME_LAST_DING, [CAT_DOORBELL], EVENT_DING],
}

# Sensor types: name, category, class
BINARY_SENSORS: Dict[str, list] = {
    EVENT_DING: ["Ding", [CAT_DOORBELL], None],
    EVENT_MOTION: ["Motion", [CAT_DOORBELL, CAT_CAMERA], DEVICE_CLASS_MOTION],
    EVENT_ONLINE: ["Online", [CAT_DOORBELL, CAT_CAMERA], DEVICE_CLASS_CONNECTIVITY],
}

# Sensor types: name, category, class, icon
SENSORS = {
    SENSOR_LAST_ACTIVITY: [
        "Last Activity",
        [CAT_DOORBELL, CAT_CAMERA],
        DEVICE_CLASS_TIMESTAMP,
        "history",
    ],
    SENSOR_LAST_MOTION: [
        "Last Motion",
        [CAT_DOORBELL, CAT_CAMERA],
        DEVICE_CLASS_TIMESTAMP,
        "history",
    ],
    SENSOR_LAST_DING: ["Last Ding", [CAT_DOORBELL], DEVICE_CLASS_TIMESTAMP, "history"],
}
