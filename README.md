# Hearth Companion — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Home Assistant custom integration for [Hearth](https://github.com/loversama/hearth) — the cross-platform desktop companion app.

Hearth turns your PC into a Home Assistant device with sensors, commands, notifications, and media player control. This integration auto-discovers your Hearth devices via MQTT and creates the corresponding entities in Home Assistant.

## Features

- **Auto-discovery** — Hearth devices are automatically discovered when they connect to your MQTT broker
- **Notifications** — Send rich notifications to your desktop with action buttons, images, and sticky toasts via `notify.{device_name}`
- **Media Player** — Control media playback on your PC (play, pause, next, volume, etc.) via `media_player.{device_name}`
- **Device Triggers** — Create automations triggered by notification action button presses
- **Local API** — Optional direct HTTP connection for notifications (no MQTT required)

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/loversama/hearth-integration` as an **Integration**
4. Search for "Hearth Companion" and install
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/hearth/` directory to your HA `config/custom_components/hearth/`
2. Restart Home Assistant

## Setup

### Automatic (MQTT)

1. Ensure both Home Assistant and Hearth are connected to the same MQTT broker
2. Open Hearth and enable the companion mode in Settings
3. Home Assistant will automatically discover your device and prompt you to add it

### Manual (Local API)

1. In Home Assistant, go to **Settings → Devices & Services → Add Integration**
2. Search for "Hearth Companion"
3. Enter your PC's IP address and port (default: 5115)

## Entities Created

| Entity | Type | Description |
|--------|------|-------------|
| `notify.{device_name}` | Notification | Send desktop notifications with action buttons |
| `media_player.{device_name}` | Media Player | Control media playback, volume, see now-playing |
| `sensor.{device_name}_*` | Sensors | CPU, GPU, memory, disk, network, battery, and more |
| `button/switch/number/select.*` | Commands | Lock, sleep, shutdown, media keys, custom scripts |

Sensors and commands are published via standard MQTT auto-discovery — they appear automatically when configured in Hearth's companion settings.

## Notification Examples

```yaml
# Simple notification
service: notify.my_desktop
data:
  title: "Home Assistant"
  message: "Motion detected in the garden!"

# With action buttons
service: notify.my_desktop
data:
  title: "Security Alert"
  message: "Camera detected movement"
  data:
    image: "/api/camera_proxy/camera.garden"
    sticky: true
    importance: "high"
    actions:
      - action: "ACK"
        title: "Acknowledge"
      - action: "VIEW"
        title: "View Camera"
        uri: "http://your-ha:8123/lovelace/cameras"

# Clear a notification by tag
service: notify.my_desktop
data:
  message: "clear_notification"
  data:
    tag: "security_alert"
```

## Media Player

Control your PC's media playback from Home Assistant:

```yaml
# Pause media
service: media_player.media_pause
target:
  entity_id: media_player.my_desktop

# Set volume to 50%
service: media_player.volume_set
target:
  entity_id: media_player.my_desktop
data:
  volume_level: 0.5
```

## MQTT Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `hearth/devices/{name}` | Device → HA | Device discovery + API announcements |
| `hearth/notifications/{name}` | HA → Device | Send notifications |
| `hearth/notifications/{name}/actions` | Device → HA | Notification action callbacks |
| `hearth/media_player/{name}/state` | Device → HA | Now-playing state |
| `hearth/media_player/{name}/thumbnail` | Device → HA | Album art (raw PNG) |
| `hearth/media_player/{name}/cmd` | HA → Device | Media player commands |

## Requirements

- Home Assistant 2024.1.0 or newer
- MQTT broker (Mosquitto recommended)
- [Hearth](https://github.com/loversama/hearth) desktop app

## License

MIT
