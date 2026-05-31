"""Media player platform for Hearth Companion."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_DEVICE_NAME, DOMAIN, MQTT_MEDIA_PLAYER_TOPIC

_LOGGER = logging.getLogger(__name__)

SUPPORT_HEARTH = (
    MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.SEEK
    | MediaPlayerEntityFeature.VOLUME_SET
)

STATE_MAP = {
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "idle": MediaPlayerState.IDLE,
    "off": MediaPlayerState.OFF,
}

AVAILABILITY_TIMEOUT = 5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Hearth media player from a config entry."""
    device_name = entry.data.get(CONF_DEVICE_NAME, entry.title)

    registry = dr.async_get(hass)
    device = registry.async_get_device(identifiers={(DOMAIN, entry.unique_id)})

    entity = HearthMediaPlayer(hass, entry, device_name, device)
    async_add_entities([entity])


class HearthMediaPlayer(MediaPlayerEntity):
    """A media player entity backed by a Hearth companion device."""

    _attr_has_entity_name = True
    _attr_supported_features = SUPPORT_HEARTH
    _attr_available = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_name: str,
        device: dr.DeviceEntry | None,
    ) -> None:
        """Initialize the media player."""
        self.hass = hass
        self._entry = entry
        self._device_name = device_name
        self._attr_unique_id = f"{entry.unique_id}_media_player"
        self._attr_name = "Media Player"

        if device:
            self._attr_device_info = {
                "identifiers": {(DOMAIN, entry.unique_id)},
                "name": device_name,
            }

        self._attr_state = MediaPlayerState.OFF
        self._volume: float = 0.0
        self._muted: bool = False
        self._artist: str | None = None
        self._title: str | None = None
        self._album: str | None = None
        self._duration: float | None = None
        self._position: float | None = None
        self._position_updated: Any = None
        self._unsubs: list = []

    async def async_added_to_hass(self) -> None:
        """Subscribe to MQTT topics when added to HA."""
        state_topic = f"{MQTT_MEDIA_PLAYER_TOPIC}/{self._device_name}/state"
        thumb_topic = f"{MQTT_MEDIA_PLAYER_TOPIC}/{self._device_name}/thumbnail"
        _LOGGER.info("Hearth media player subscribing to: %s", state_topic)

        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass, state_topic, self._state_received, 0
            )
        )
        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass,
                thumb_topic,
                self._thumbnail_received,
                0,
                encoding=None,
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from MQTT topics."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def _state_received(self, msg) -> None:
        """Handle a state update from the device."""
        try:
            data = json.loads(msg.payload)
        except (json.JSONDecodeError, TypeError):
            _LOGGER.warning("Hearth media player: invalid state payload")
            return

        _LOGGER.debug("Hearth media player state received: %s", data.get("state"))
        state_str = data.get("state", "off")
        self._attr_state = STATE_MAP.get(state_str, MediaPlayerState.OFF)

        self._volume = data.get("volume", 0) / 100.0
        self._muted = data.get("muted", False)
        self._artist = data.get("artist") or data.get("albumartist")
        self._title = data.get("title")
        self._album = data.get("albumtitle")
        self._duration = data.get("duration")
        self._position = data.get("currentposition")
        self._position_updated = dt_util.utcnow()

        self.async_write_ha_state()

    @callback
    def _thumbnail_received(self, msg) -> None:
        """Handle a thumbnail update (raw PNG bytes)."""
        self.hass.data[DOMAIN][self._entry.entry_id]["thumbnail"] = msg.payload

    # -- Properties --

    @property
    def volume_level(self) -> float:
        return self._volume

    @property
    def is_volume_muted(self) -> bool:
        return self._muted

    @property
    def media_title(self) -> str | None:
        return self._title

    @property
    def media_artist(self) -> str | None:
        return self._artist

    @property
    def media_album_name(self) -> str | None:
        return self._album

    @property
    def media_duration(self) -> float | None:
        return self._duration

    @property
    def media_position(self) -> float | None:
        return self._position

    @property
    def media_position_updated_at(self) -> Any:
        return self._position_updated

    @property
    def media_image_url(self) -> str | None:
        if self.hass.data[DOMAIN].get(self._entry.entry_id, {}).get("thumbnail"):
            return f"/api/{DOMAIN}/{self.entity_id}/thumbnail.png"
        return None

    # -- Commands --

    async def _send_command(self, command: str, data: Any = None) -> None:
        """Publish a command to the device."""
        topic = f"{MQTT_MEDIA_PLAYER_TOPIC}/{self._device_name}/cmd"
        payload = {"command": command}
        if data is not None:
            payload["data"] = data
        _LOGGER.info("Hearth media: sending %s to %s", command, topic)
        await mqtt.async_publish(
            self.hass, topic, json.dumps(payload), qos=1, retain=False
        )

    async def async_media_play(self) -> None:
        await self._send_command("play")

    async def async_media_pause(self) -> None:
        await self._send_command("pause")

    async def async_media_stop(self) -> None:
        await self._send_command("stop")

    async def async_media_next_track(self) -> None:
        await self._send_command("next")

    async def async_media_previous_track(self) -> None:
        await self._send_command("previous")

    async def async_set_volume_level(self, volume: float) -> None:
        await self._send_command("setvolume", int(volume * 100))

    async def async_volume_up(self) -> None:
        await self._send_command("volumeup")

    async def async_volume_down(self) -> None:
        await self._send_command("volumedown")

    async def async_mute_volume(self, mute: bool) -> None:
        await self._send_command("mute", mute)

    async def async_media_seek(self, position: float) -> None:
        await self._send_command("seek", position)

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play media from a URL or media source."""
        if media_id.startswith("media-source://"):
            from homeassistant.components.media_source import async_resolve_media

            resolved = await async_resolve_media(self.hass, media_id, self.entity_id)
            media_id = resolved.url

        # Resolve relative URLs (e.g. /api/tts_proxy/xxx.mp3) to full URLs
        if media_id.startswith("/"):
            base = self.hass.config.internal_url or self.hass.config.external_url or ""
            if base:
                media_id = f"{base.rstrip('/')}{media_id}"
            else:
                _LOGGER.warning("Cannot resolve relative URL %s — no HA base URL configured", media_id)

        await self._send_command("playmedia", media_id)
