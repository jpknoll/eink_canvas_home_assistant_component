"""The BLOOMIN8 E-Ink Canvas integration."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import voluptuous as vol
from datetime import datetime
import random
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.config_validation as cv

from .api_client import EinkCanvasApiClient
from .const import DOMAIN, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class RuntimeData:
    """Runtime data for BLOOMIN8 E-Ink Canvas integration."""

    api_client: EinkCanvasApiClient
    device_info: dict[str, Any] | None = None
    logs: list[dict[str, Any]] = field(default_factory=list)


# Extend ConfigEntry to type hint runtime_data
type EinkCanvasConfigEntry = ConfigEntry[RuntimeData]


# Supported platforms
PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.TEXT,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the BLOOMIN8 E-Ink Canvas component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EinkCanvasConfigEntry) -> bool:
    """Set up BLOOMIN8 E-Ink Canvas from a config entry."""
    host = entry.data[CONF_HOST]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    # Create API client
    api_client = EinkCanvasApiClient(hass, host)

    # Store runtime data
    entry.runtime_data = RuntimeData(api_client=api_client)

    # Create device registration
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, host)},
        name=name,
        manufacturer="BLOOMIN8",
        model="E-Ink Canvas",
    )

    # Register services
    await _register_services(hass, entry)

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _register_services(hass: HomeAssistant, entry: EinkCanvasConfigEntry) -> None:
    """Register device control services."""
    runtime_data = entry.runtime_data
    api_client = runtime_data.api_client

    def add_log(message: str, level: str = "info") -> None:
        """Add log entry (synchronous)."""
        log_entry = {
            "timestamp": datetime.now(),
            "level": level,
            "message": message,
        }

        runtime_data.logs.append(log_entry)
        # Keep only the latest 50 logs
        if len(runtime_data.logs) > 50:
            runtime_data.logs.pop(0)

    async def handle_show_next(call: ServiceCall) -> None:
        """Handle show next image service."""
        success = await api_client.show_next()
        if success:
            add_log("Successfully switched to next image")
        else:
            add_log("Failed to switch to next image", "error")

    async def handle_sleep(call: ServiceCall) -> None:
        """Handle device sleep service."""
        success = await api_client.sleep()
        if success:
            add_log("Device entered sleep mode")
        else:
            add_log("Device sleep failed", "error")

    async def handle_reboot(call: ServiceCall) -> None:
        """Handle device reboot service."""
        success = await api_client.reboot()
        if success:
            add_log("Device reboot command sent")
        else:
            add_log("Device reboot failed", "error")

    async def handle_clear_screen(call: ServiceCall) -> None:
        """Handle clear screen service."""
        success = await api_client.clear_screen()
        if success:
            add_log("Screen cleared")
        else:
            add_log("Clear screen failed", "error")

    async def handle_whistle(call: ServiceCall) -> None:
        """Handle keep alive service."""
        success = await api_client.whistle()
        if success:
            add_log("Keep alive signal sent")
        else:
            add_log("Keep alive failed", "error")

    async def handle_update_settings(call: ServiceCall) -> None:
        """Handle update device settings service."""
        settings_data = {}

        if "name" in call.data:
            settings_data["name"] = call.data["name"]
        if "sleep_duration" in call.data:
            settings_data["sleep_duration"] = call.data["sleep_duration"]
        if "max_idle" in call.data:
            settings_data["max_idle"] = call.data["max_idle"]
        if "idx_wake_sens" in call.data:
            settings_data["idx_wake_sens"] = call.data["idx_wake_sens"]

        if not settings_data:
            add_log("No settings parameters provided", "warning")
            return

        success = await api_client.update_settings(settings_data)
        if success:
            settings_str = ", ".join([f"{k}: {v}" for k, v in settings_data.items()])
            add_log(f"Device settings updated: {settings_str}")
        else:
            add_log("Settings update failed", "error")

    async def handle_refresh_device_info(call: ServiceCall) -> None:
        """Handle refresh device info service."""
        device_info = await api_client.get_device_info()
        if device_info:
            runtime_data.device_info = device_info
            add_log("Device info refreshed")
        else:
            add_log("Failed to refresh device info", "error")

    async def handle_sync_photos(call: ServiceCall) -> None:
        """Handle sync photos from media source service."""
        media_source_id = call.data.get("media_source_id")
        target_gallery = call.data.get("target_gallery", "default")
        max_photos = call.data.get("max_photos", 50)
        overwrite_existing = call.data.get("overwrite_existing", False)

        if not media_source_id:
            add_log("No media source ID provided for photo sync", "error")
            return

        add_log(f"Starting photo sync from {media_source_id} to gallery {target_gallery}")
        
        result = await api_client.sync_photos_from_media_source(
            media_source_id=media_source_id,
            target_gallery=target_gallery,
            max_photos=max_photos,
            overwrite_existing=overwrite_existing
        )

        if result["success"]:
            add_log(f"Photo sync completed successfully - Synced: {result['synced_count']}, "
                   f"Skipped: {result['skipped_count']}, Failed: {result['failed_count']}")
        else:
            add_log(f"Photo sync failed - Errors: {len(result['errors'])}, "
                   f"Synced: {result['synced_count']}, Failed: {result['failed_count']}", "error")
            
            # Log individual errors
            for error in result["errors"][:5]:  # Limit to first 5 errors
                add_log(f"Sync error: {error}", "error")

    async def handle_push_random_item(call: ServiceCall) -> None:
        """Handle push random item from media source service."""
        media_source_id = call.data.get("media_source_id")

        if not media_source_id:
            add_log("No media source ID provided for push random item", "error")
            return

        add_log(f"Getting random photo from {media_source_id}")
        
        try:
            # Browse the media source to get photos (limit to 100 for random selection)
            photos = await api_client._browse_media_source_photos(media_source_id, 100)
            
            if not photos:
                add_log("No photos found in media source", "error")
                return
            
            # Pick a random photo
            random_photo = random.choice(photos)
            add_log(f"Selected random photo: {random_photo.get('title', 'Unknown')}")
            
            # Push the photo to the e-ink media player
            # We need to use the media player to display the photo
            # Get the media_content_id for the selected photo
            media_content_id = random_photo.get('media_content_id')
            if not media_content_id:
                add_log("Selected photo has no media_content_id", "error")
                return
            
            # Play the selected photo on all e-ink media players
            from homeassistant.components.media_player import DOMAIN as MEDIA_DOMAIN
            
            # Find all e-ink canvas media players
            entity_ids = [
                entity_id for entity_id in hass.states.async_entity_ids(MEDIA_DOMAIN)
                if hass.states.get(entity_id).attributes.get("device_info", {}).get("manufacturer") == "BLOOMIN8"
            ]
            
            if not entity_ids:
                add_log("No BLOOMIN8 E-Ink Canvas media players found", "error")
                return
            
            # Play the photo on all found media players
            for entity_id in entity_ids:
                await hass.services.async_call(
                    MEDIA_DOMAIN,
                    "play_media",
                    {
                        "entity_id": entity_id,
                        "media_content_id": media_content_id,
                        "media_content_type": random_photo.get('media_content_type', 'image/jpeg')
                    },
                    blocking=True
                )
            
            add_log(f"Successfully pushed random photo to {len(entity_ids)} media player(s)")
            
        except Exception as err:
            add_log(f"Error pushing random item: {err}", "error")

    # Register all services
    services = [
        ("show_next", handle_show_next, {}),
        ("sleep", handle_sleep, {}),
        ("reboot", handle_reboot, {}),
        ("clear_screen", handle_clear_screen, {}),
        ("whistle", handle_whistle, {}),
        ("refresh_device_info", handle_refresh_device_info, {}),
        ("update_settings", handle_update_settings, {
            vol.Optional("name"): str,
            vol.Optional("sleep_duration"): int,
            vol.Optional("max_idle"): int,
            vol.Optional("idx_wake_sens"): int,
        }),
        ("sync_photos", handle_sync_photos, {
            vol.Required("media_source_id"): str,
            vol.Optional("target_gallery", default="default"): str,
            vol.Optional("max_photos", default=50): int,
            vol.Optional("overwrite_existing", default=False): bool,
        }),
        ("push_random_item", handle_push_random_item, {
            vol.Required("media_source_id"): str,
        }),
    ]

    for service_name, handler, schema in services:
        hass.services.async_register(
            DOMAIN,
            service_name,
            handler,
            schema=vol.Schema(schema)
        )


async def async_unload_entry(hass: HomeAssistant, entry: EinkCanvasConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Remove services
        services_to_remove = [
            "show_next", "sleep", "reboot", "clear_screen",
            "whistle", "refresh_device_info", "update_settings", "sync_photos", "push_random_item"
        ]
        for service in services_to_remove:
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)

    return unload_ok
