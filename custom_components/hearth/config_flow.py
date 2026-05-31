"""Config flow for Hearth Companion integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_URL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.service_info.mqtt import MqttServiceInfo

from .const import (
    CONF_DEFAULT_NOTIFICATION_TITLE,
    CONF_DEVICE_NAME,
    CONF_ORIGINAL_DEVICE_NAME,
    DEFAULT_NOTIFICATION_TITLE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class HearthConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hearth Companion."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._device_name: str | None = None
        self._serial_number: str | None = None
        self._device_info: dict = {}
        self._apis: dict = {}

    async def async_step_mqtt(
        self, discovery_info: MqttServiceInfo
    ) -> FlowResult:
        """Handle MQTT auto-discovery from hearth/devices/#."""
        assert discovery_info.subscribed_topic == "hearth/devices/#"

        try:
            payload = json.loads(discovery_info.payload)
        except (json.JSONDecodeError, TypeError):
            return self.async_abort(reason="invalid_discovery_payload")

        self._device_info = payload.get("device", {})
        self._serial_number = payload.get("serial_number")
        self._apis = payload.get("apis", {})
        self._device_name = self._device_info.get(
            "name", discovery_info.topic.rsplit("/", 1)[-1]
        )

        if not self._serial_number:
            return self.async_abort(reason="no_serial_number")

        await self.async_set_unique_id(self._serial_number)

        # If device already exists, update it and abort (raises AbortFlow)
        self._abort_if_unique_id_configured(
            updates={
                CONF_DEVICE_NAME: self._device_name,
                "device": self._device_info,
                "apis": self._apis,
            }
        )

        self.context["title_placeholders"] = {"name": self._device_name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm device addition."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._device_name or "Hearth Device",
                data={
                    CONF_DEVICE_NAME: self._device_name,
                    CONF_ORIGINAL_DEVICE_NAME: self._device_name,
                    "device": self._device_info,
                    "serial_number": self._serial_number,
                    "apis": self._apis,
                },
            )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"name": self._device_name or "Unknown"},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the setup menu with options."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["local_api", "mqtt_help"],
        )

    async def async_step_mqtt_help(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show MQTT troubleshooting help, then return to menu."""
        if user_input is not None:
            return await self.async_step_user()
        return self.async_show_form(step_id="mqtt_help")

    async def async_step_local_api(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle local API connection setup."""
        errors = {}

        if user_input is not None:
            host = user_input.get("host", "")
            port = user_input.get("port", 5115)
            use_ssl = user_input.get("ssl", False)
            scheme = "https" if use_ssl else "http"
            url = f"{scheme}://{host}:{port}"

            try:
                from aiohttp import ClientTimeout

                from homeassistant.helpers.aiohttp_client import (
                    async_get_clientsession,
                )

                session = async_get_clientsession(self.hass)
                async with session.get(
                    f"{url}/info", timeout=ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        errors["base"] = "cannot_connect"
                    else:
                        info = await resp.json()
                        device = info.get("device", {})
                        serial = info.get("serial_number", "")
                        device_name = device.get("name", host)

                        if serial:
                            await self.async_set_unique_id(serial)
                            self._abort_if_unique_id_configured()

                        return self.async_create_entry(
                            title=device_name,
                            data={
                                CONF_URL: url,
                                CONF_DEVICE_NAME: device_name,
                                CONF_ORIGINAL_DEVICE_NAME: device_name,
                                "device": device,
                                "serial_number": serial,
                            },
                        )
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="local_api",
            data_schema=vol.Schema(
                {
                    vol.Required("host"): str,
                    vol.Optional("port", default=5115): int,
                    vol.Optional("ssl", default=False): bool,
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow handler."""
        return HearthOptionsFlow()


class HearthOptionsFlow(OptionsFlow):
    """Handle options for the Hearth integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_title = self.config_entry.options.get(
            CONF_DEFAULT_NOTIFICATION_TITLE, DEFAULT_NOTIFICATION_TITLE
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DEFAULT_NOTIFICATION_TITLE,
                        default=current_title,
                    ): str,
                }
            ),
        )
