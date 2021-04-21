*Please :star: this repo if you find it useful*

# My Home Assistant Configuration

This [Home Assistant](https://www.home-assistant.io/) configuration is based on [configuration by Isabella Gross Alström](https://isabellaalstrom.github.io/).

*Описание проекта будет вестись полностью на английском, но я готов помогать и русскоязычным пользователям Home Assistant. Буду рад, если смогу быть полезен в настройке вашего умного дома.*

![](https://img.shields.io/maintenance/yes/2021.svg?style=popout)
[![](https://img.shields.io/github/last-commit/Limych/HomeAssistantConfiguration.svg?style=popout)](https://github.com/Limych/HomeAssistantConfiguration/commits/master)

![Project Maintenance](https://img.shields.io/badge/maintainer-Andrey%20Khrolenok%20%40Limych-blue.svg?style=popout)

Like the Isabella I'm using the GitHub [issues](https://github.com/Limych/HomeAssistantConfiguration/issues) and [project](https://github.com/Limych/HomeAssistantConfiguration/projects/1) to keep track of bugs in my configuration and new features I want to make/use.

## Organizing the configuration

This configuration is broken down into [packages](https://www.home-assistant.io/docs/configuration/packages/), sort of mini configuration-files. This makes it easy to see everything pertaining to a specific implementation.

But while using packages you can no longer reload your config with the buttons in the ui.

> **_Note_**:\
> In this configuration, I've use several custom components. Those of them that I wrote myself, you can find in a [separate repositories](https://github.com/search?q=user%3ALimych+ha-).

## Ecosystem

<details>
    <p><summary>Now I have very few devices in the system. But I plan to gradually add new ones. Click to expand and read more.</summary></p>

I am running Hass.io on [Raspberry Pi 3 Model B+](https://www.raspberrypi.org/products/raspberry-pi-3-model-b-plus/) with Raspbian, in Docker. To run Hass.io this way, [install manually in Docker](https://github.com/home-assistant/hassio-installer).

* **Personal gadgets:**
    1. Android devices (Phones and Tablets);
* **Media:**
    1. [FreeNAS](https://freenas.org/) File Server;
    1. [Emby](https://emby.media/) Media Server;
    1. [Plex](https://www.plex.tv/) Media Server;
    1. Two [LinkPlay-driven](https://github.com/Limych/media_player.linkplay) Wireless Speakers;
    1. Smart TV driven by Android TV;
* **Network:**
    1. [Transmission](https://transmissionbt.com/) BitTorrent Client;
    1. [Sonarr](https://sonarr.tv/) TV-series Monitoring Server;
    1. [Radarr](https://radarr.video/) Movies Monitoring Server;
    1. [Lidarr](https://lidarr.audio/) Music Monitoring Server;
    1. [Syncthing](https://syncthing.net/) Sync Client;
* **Security:**
    1. [OPNsense-driven](https://opnsense.org/) Network Firewall;
    1. [Beward DS06M](https://www.beward.ru/katalog/ip-videodomofony/vyzyvnye-paneli/vyzyvnaya-panel-ds06m/) Doorbell;
    1. Home made security sensor (PIR & front door opening) direct wired to Home Assistant Raspberry PI;
    1. Home made ESP32-based [ESPHome-driven](https://esphome.io/) climate (outdoor <s>Humidity, Temperature</s> & Illuminance and indoor Pressure, <s>Humidity,</s> Temperature, CO2 & tVOC) & security (PIR) sensor;
* **Climate:**
    1. Home made ESP32-based [ESPHome-driven](https://esphome.io/) climate (outdoor <s>Humidity, Temperature</s> & Illuminance and indoor Pressure, <s>Humidity,</s> Temperature, CO2 & tVOC) & security (PIR) sensor;
    1. Sonoff TH10 [ESPHome-driven](https://esphome.io/) bathroom climate sensor (Humidity & Temperature) & fan controller;
    1. [JQ-300 Indoor Air Quality Meter](https://community.home-assistant.io/t/jq-300-200-100-indoor-air-quality-meter/189098);
* **Misc:**
    1. Android tablet based [WallPanel-driven](https://thanksmister.com/wallpanel-android/) Home Assistant dashboard;

</details>

## Lovelace

I'm using [YAML mode](https://www.home-assistant.io/lovelace/yaml-mode/). Single file splitted to several ones via [includes](https://www.home-assistant.io/docs/configuration/splitting_configuration/).

My main Lovelace-file is found [here](https://github.com/Limych/HomeAssistantConfiguration/blob/master/ui-lovelace.yaml), and my folder with includes [here](https://github.com/Limych/HomeAssistantConfiguration/tree/master/lovelace). This is very much still a work in progress, so files might not correspond exactly to screenshots.

<p align="center">* * *</p>
I put a lot of work into making this repo and component available and updated to inspire and help others! I will be glad to receive thanks from you — it will give me new strength and add enthusiasm:
<p align="center"><br>
<a href="https://www.patreon.com/join/limych?" target="_blank"><img src="http://khrolenok.ru/support_patreon.png" alt="Patreon" width="250" height="48"></a>
<br>or&nbsp;support via Bitcoin or Etherium:<br>
<a href="https://sochain.com/a/mjz640g" target="_blank"><img src="http://khrolenok.ru/support_bitcoin.png" alt="Bitcoin" width="150"><br>
16yfCfz9dZ8y8yuSwBFVfiAa3CNYdMh7Ts</a>
</p>

### Examples from my Lovelace GUI

I have tried to make a GUI that is [mobile first](https://medium.com/@Vincentxia77/what-is-mobile-first-design-why-its-important-how-to-make-it-7d3cf2e29d00), since that's how I most often look at it.

Click on the images to get to the corresponding YAML-file.

#### Mobile

<details>
    <p><summary>Click to expand!</summary></p>

Home view

[![](https://raw.githubusercontent.com/Limych/HomeAssistantConfiguration/master/docs/images/mobile_home.jpg)](https://github.com/Limych/HomeAssistantConfiguration/blob/master/lovelace/00_home_view.yaml)

Home info

[![](https://raw.githubusercontent.com/Limych/HomeAssistantConfiguration/master/docs/images/mobile_home_info.jpg)](https://github.com/Limych/HomeAssistantConfiguration/blob/master/lovelace/10_home_info_view.yaml)

System info

[![](https://raw.githubusercontent.com/Limych/HomeAssistantConfiguration/master/docs/images/mobile_system_info.jpg)](https://github.com/Limych/HomeAssistantConfiguration/blob/master/lovelace/30_system_info_view.yaml)

Automations view

[![](https://raw.githubusercontent.com/Limych/HomeAssistantConfiguration/master/docs/images/mobile_automations.jpg)](https://github.com/Limych/HomeAssistantConfiguration/blob/master/lovelace/00_automations_view.yaml)

</details>

#### Desktop

<details>
    <p><summary>Click to expand!</summary></p>

Home view

[![](https://raw.githubusercontent.com/Limych/HomeAssistantConfiguration/master/docs/images/desktop_home.jpg)](https://github.com/Limych/HomeAssistantConfiguration/blob/master/lovelace/00_home_view.yaml)

Home info

[![](https://raw.githubusercontent.com/Limych/HomeAssistantConfiguration/master/docs/images/desktop_home_info.jpg)](https://github.com/Limych/HomeAssistantConfiguration/blob/master/lovelace/10_home_info_view.yaml)

System info

[![](https://raw.githubusercontent.com/Limych/HomeAssistantConfiguration/master/docs/images/desktop_system_info.jpg)](https://github.com/Limych/HomeAssistantConfiguration/blob/master/lovelace/30_system_info_view.yaml)

Automations view

[![](https://raw.githubusercontent.com/Limych/HomeAssistantConfiguration/master/docs/images/desktop_automations.jpg)](https://github.com/Limych/HomeAssistantConfiguration/blob/master/lovelace/00_automations_view.yaml)

</details>

## Add-ons

* [Backup Hass.io to Google Drive](https://github.com/samccauley/addon-hassiogooglebackup#readme);
* [HACS](https://github.com/custom-components/hacs);
* [IDE](https://github.com/hassio-addons/addon-ide/blob/master/README.md);
* [Log Viewer](https://github.com/hassio-addons/addon-log-viewer);
* [MariaDB](https://www.home-assistant.io/addons/mariadb/) — official addon;
* [Mosquitto MQTT broker](https://www.home-assistant.io/addons/mosquitto/) — official addon;
* [Presence Monitor](https://github.com/Limych/addon-presence-monitor);
* [Samba Share](https://www.home-assistant.io/addons/samba/) — official addon;

# Get in contact

[E-mail](mailto:andrey@khrolenok.ru)
