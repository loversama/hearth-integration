"""Hearth Companion — Home Assistant integration for the Hearth desktop companion app.

Discovers Hearth devices via MQTT (hearth/devices/#), creates notification
and media player entities.
"""

from __future__ import annotations

import json
import logging

from homeassistant.components import mqtt
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_NAME, CONF_URL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    device_registry as dr,
    discovery,
    entity_registry as er,
)

from .const import (
    CONF_DEVICE_NAME,
    CONF_ORIGINAL_DEVICE_NAME,
    DOMAIN,
    MQTT_DEVICES_TOPIC,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Hearth integration (global, once per HA instance)."""
    hass.data.setdefault(DOMAIN, {})
    hass.http.register_view(MediaPlayerThumbnailView())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Hearth device from a config entry."""
    hass.data[DOMAIN][entry.entry_id] = {
        "internal_mqtt": {},
        "apis": {},
        "thumbnail": None,
        "loaded": {"media_player": False, "notifications": False},
    }

    device_name = entry.data.get(CONF_DEVICE_NAME, entry.title)
    url = entry.data.get(CONF_URL)

    if url is not None:
        # Local API mode — notifications only
        apis = {"notifications": True, "media_player": False}
        hass.data[DOMAIN][entry.entry_id]["apis"] = apis
        await _update_device_info(hass, entry, entry.data.get("device", {}))
        await _handle_apis_changed(hass, entry, apis)
    else:
        # MQTT mode — full-featured, subscribe to device updates
        topic = f"{MQTT_DEVICES_TOPIC}/{device_name}"

        # Load platforms immediately from stored config entry data so we don't
        # have to wait for the next MQTT announce (the discovery message that
        # triggered the config flow is already consumed).
        stored_apis = entry.data.get("apis", {})
        if stored_apis:
            hass.data[DOMAIN][entry.entry_id]["apis"] = stored_apis
            await _update_device_info(hass, entry, entry.data.get("device", {}))
            await _handle_apis_changed(hass, entry, stored_apis)

        @callback
        def _device_message_received(msg):
            try:
                payload = json.loads(msg.payload)
            except (json.JSONDecodeError, TypeError):
                _LOGGER.warning("Invalid JSON in device announce from %s", device_name)
                return

            device_info = payload.get("device", {})
            new_apis = payload.get("apis", {})

            hass.async_create_task(_update_device_info(hass, entry, device_info))

            cached_apis = hass.data[DOMAIN][entry.entry_id].get("apis", {})
            if new_apis != cached_apis:
                hass.data[DOMAIN][entry.entry_id]["apis"] = new_apis
                hass.async_create_task(_handle_apis_changed(hass, entry, new_apis))

        unsub = await mqtt.async_subscribe(hass, topic, _device_message_received, 0)
        hass.data[DOMAIN][entry.entry_id]["internal_mqtt"]["device_unsub"] = unsub

    return True


async def _update_device_info(
    hass: HomeAssistant, entry: ConfigEntry, device_info: dict
) -> None:
    """Update the HA device registry with device metadata."""
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id)},
        name=device_info.get("name", entry.title),
        manufacturer=device_info.get("manufacturer", "Hearth"),
        model=device_info.get("model", "Desktop Companion"),
        sw_version=device_info.get("sw_version"),
    )


async def _handle_apis_changed(
    hass: HomeAssistant, entry: ConfigEntry, apis: dict
) -> None:
    """Load/unload platforms based on what the device advertises."""
    loaded = hass.data[DOMAIN][entry.entry_id]["loaded"]
    device_name = entry.data.get(CONF_DEVICE_NAME, entry.title)
    original_name = entry.data.get(CONF_ORIGINAL_DEVICE_NAME, device_name)

    if apis.get("media_player") and not loaded["media_player"]:
        await hass.config_entries.async_forward_entry_setups(
            entry, [Platform.MEDIA_PLAYER]
        )
        loaded["media_player"] = True

    if apis.get("notifications") and not loaded["notifications"]:
        await discovery.async_load_platform(
            hass,
            Platform.NOTIFY,
            DOMAIN,
            {
                CONF_ID: entry.entry_id,
                CONF_NAME: original_name,
                CONF_DEVICE_NAME: device_name,
            },
            {},
        )
        loaded["notifications"] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Hearth config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id, {})

    # Unsubscribe MQTT topics
    for unsub in data.get("internal_mqtt", {}).values():
        if callable(unsub):
            unsub()

    # Unload media player platform if loaded
    loaded = data.get("loaded", {})
    if loaded.get("media_player"):
        await hass.config_entries.async_unload_platforms(
            entry, [Platform.MEDIA_PLAYER]
        )

    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


class MediaPlayerThumbnailView(HomeAssistantView):
    """Serve media player thumbnail images."""

    url = f"/api/{DOMAIN}/{{media_player}}/thumbnail.png"
    name = f"api:{DOMAIN}:thumbnail"
    requires_auth = False

    async def get(self, request, media_player):
        """Return the thumbnail for a media player entity."""
        from aiohttp import web

        hass = request.app["hass"]
        entity_reg = er.async_get(hass)
        entity = entity_reg.async_get(media_player)

        if entity is None:
            return web.Response(status=404, text="Entity not found")

        entry_id = entity.config_entry_id
        data = hass.data.get(DOMAIN, {}).get(entry_id, {})
        thumbnail = data.get("thumbnail")

        if thumbnail is None:
            return web.Response(status=500, text="No thumbnail available")

        return web.Response(body=thumbnail, content_type="image/png")
