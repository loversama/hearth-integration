"""Device triggers for Hearth Companion."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.mqtt import trigger as mqtt_trigger
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import CONF_ACTION, CONF_DEVICE_NAME, DOMAIN, MQTT_NOTIFICATIONS_TOPIC

TRIGGER_TYPES = {"notifications_mqtt", "notifications_event"}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        vol.Required(CONF_ACTION): str,
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """Return available triggers for a device."""
    triggers = []
    for trigger_type in TRIGGER_TYPES:
        triggers.append(
            {
                CONF_PLATFORM: "device",
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: trigger_type,
            }
        )
    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    trigger_type = config[CONF_TYPE]
    trigger_action = config[CONF_ACTION]

    registry = dr.async_get(hass)
    device = registry.async_get(config[CONF_DEVICE_ID])
    if not device:
        return lambda: None

    # Find the device name from the config entry
    device_name = None
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN:
            device_name = entry.data.get(CONF_DEVICE_NAME, entry.title)
            break

    if not device_name:
        return lambda: None

    if trigger_type == "notifications_mqtt":
        topic = f"{MQTT_NOTIFICATIONS_TOPIC}/{device_name}/actions"
        return await mqtt_trigger.async_attach_trigger(
            hass,
            mqtt_trigger.TRIGGER_SCHEMA(
                {
                    "platform": "mqtt",
                    "topic": topic,
                    "value_template": "{{ value_json.action }}",
                    "payload": trigger_action,
                }
            ),
            action,
            trigger_info,
        )

    if trigger_type == "notifications_event":
        return await event_trigger.async_attach_trigger(
            hass,
            event_trigger.TRIGGER_SCHEMA(
                {
                    "platform": "event",
                    "event_type": "hearth_notifications",
                    "event_data": {
                        "device_name": device_name,
                        "action": trigger_action,
                    },
                }
            ),
            action,
            trigger_info,
        )

    return lambda: None
