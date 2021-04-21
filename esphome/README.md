# ESPHome firmwares

This directory are store my custom firmwares for some devices.

## Bathroom

Bathroom sensor and exhaust fan controller on Sonoff TH10 + SI7021 temperature & humidity sensor.

Features:
- Can work autonomously;
- If connected to Home Assistant, automatically once a minute publish current temperature and humidity.
- Automatically turning on fan then humidity above setted threshold and turning off it otherwise;
- You can manually turn on fan for 5 minutes pressing button on sensor body. Each button press reset switch off timer to 5 minutes;
- Via API (through service in Home Assistant) you can set non default humidity threshold permanently or for some time;
- Via API (through service in Home Assistant) you can manually control fan at any time. You can turn on fan permanently or for some time;

## Kitchen

Kitchen sensor and cooling fan controller on Sonoff TH10 + SI7021 temperature & humidity sensor.

Features:
- Can work autonomously;
- If connected to Home Assistant, automatically once a minute publish current temperature and humidity.
- You can manually turn on fan for 5 minutes pressing button on sensor body. If fun already turning on, button pressing turn it off;
- Via API (through service in Home Assistant) you can manually control fan at any time. You can turn on fan permanently or for some time;

## Kitchen_old

Old version of kitchen sensor. 
