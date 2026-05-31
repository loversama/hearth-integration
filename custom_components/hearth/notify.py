"""Notification platform for Hearth Companion."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components.notify import BaseNotificationService
from homeassistant.const import CONF_ID, CONF_NAME, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    CONF_DEFAULT_NOTIFICATION_TITLE,
    CONF_DEVICE_NAME,
    DEFAULT_NOTIFICATION_TITLE,
    DOMAIN,
    MQTT_NOTIFICATIONS_TOPIC,
)

_LOGGER = logging.getLogger(__name__)


async def async_get_service(
    hass: HomeAssistant,
    config: ConfigType,
    discovery_info: DiscoveryInfoType | None = None,
) -> HearthNotificationService | None:
    """Get the notification service."""
    if discovery_info is None:
        return None

    entry_id = discovery_info.get(CONF_ID)
    device_name = discovery_info.get(CONF_DEVICE_NAME)

    if not entry_id or not device_name:
        _LOGGER.error("Missing entry_id or device_name in discovery_info")
        return None

    return HearthNotificationService(hass, entry_id, device_name)


# Legacy alias for older HA versions
get_service = async_get_service


class HearthNotificationService(BaseNotificationService):
    """Send notifications to a Hearth companion device."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, device_name: str
    ) -> None:
        """Initialize the service."""
        self.hass = hass
        self._entry_id = entry_id
        self._device_name = device_name

    async def async_send_message(self, message: str = "", **kwargs: Any) -> None:
        """Send a notification to the device."""
        title = kwargs.get("title")
        data = kwargs.get("data", {}) or {}

        # Default title from integration options
        if not title:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry:
                title = entry.options.get(
                    CONF_DEFAULT_NOTIFICATION_TITLE, DEFAULT_NOTIFICATION_TITLE
                )
            else:
                title = DEFAULT_NOTIFICATION_TITLE

        # Resolve relative image paths to full external URLs
        if "image" in data and data["image"]:
            image = data["image"]
            if image.startswith("/api/"):
                external_url = self.hass.config.external_url or ""
                if external_url:
                    data["image"] = f"{external_url}{image}"

        payload = {"message": message, "title": title, "data": data}

        # Check if this is a local API entry or MQTT entry
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        url = entry.data.get(CONF_URL) if entry else None

        if url:
            await self._send_via_local_api(url, payload)
        else:
            await self._send_via_mqtt(payload)

    async def _send_via_mqtt(self, payload: dict) -> None:
        """Send notification via MQTT."""
        from homeassistant.components import mqtt

        topic = f"{MQTT_NOTIFICATIONS_TOPIC}/{self._device_name}"
        await mqtt.async_publish(
            self.hass, topic, json.dumps(payload), qos=1, retain=False
        )

    async def _send_via_local_api(self, url: str, payload: dict) -> None:
        """Send notification via the local HTTP API."""
        from aiohttp import ClientTimeout

        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        try:
            session = async_get_clientsession(self.hass)
            async with session.post(
                f"{url}/notify",
                json=payload,
                timeout=ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error(
                        "Hearth local API notify failed: %s %s",
                        resp.status,
                        await resp.text(),
                    )
        except Exception as err:
            _LOGGER.error("Failed to send notification via local API: %s", err)
