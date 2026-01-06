"""API Client for BLOOMIN8 E-Ink Canvas.

This client implements the official Bloomin8 E-Ink Canvas API as documented in openapi.yaml.
The device returns some responses with incorrect content-types (e.g., text/json, text/javascript
instead of application/json), so we handle JSON parsing manually where needed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components import media_source
from homeassistant.components.media_player.browse_media import async_process_play_media_url
from homeassistant.components.media_player import BrowseMedia, MediaClass

from .const import (
    ENDPOINT_SHOW,
    ENDPOINT_SHOW_NEXT,
    ENDPOINT_SLEEP,
    ENDPOINT_REBOOT,
    ENDPOINT_CLEAR_SCREEN,
    ENDPOINT_SETTINGS,
    ENDPOINT_WHISTLE,
    ENDPOINT_DEVICE_INFO,
    ENDPOINT_UPLOAD,
    ENDPOINT_STATUS,
)

_LOGGER = logging.getLogger(__name__)


class EinkCanvasApiClient:
    """API client for BLOOMIN8 E-Ink Canvas device."""

    def __init__(self, hass: HomeAssistant, host: str) -> None:
        """Initialize the API client."""
        self._hass = hass
        self._host = host
        self._session = async_get_clientsession(hass)

    @property
    def host(self) -> str:
        """Return the device host."""
        return self._host

    async def get_status(self) -> dict[str, Any] | None:
        """Get device status."""
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(
                    f"http://{self._host}{ENDPOINT_STATUS}"
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except Exception as err:
            _LOGGER.debug("Error getting status: %s", err)
            return None

    async def get_device_info(self) -> dict[str, Any] | None:
        """Get device information from /deviceInfo endpoint.

        Returns device status including name, version, battery, screen resolution,
        current image, network info, etc. See openapi.yaml for full response schema.
        """
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(
                    f"http://{self._host}{ENDPOINT_DEVICE_INFO}"
                ) as response:
                    if response.status == 200:
                        text_response = await response.text()
                        # Device may return incorrect content-type, parse JSON manually
                        try:
                            return json.loads(text_response)
                        except json.JSONDecodeError:
                            # Try to extract JSON from malformed response
                            start = text_response.find("{")
                            end = text_response.rfind("}") + 1
                            if start >= 0 and end > start:
                                return json.loads(text_response[start:end])
                            _LOGGER.warning("Invalid JSON in device info response")
                    return None
        except Exception as err:
            _LOGGER.debug("Error getting device info: %s", err)
            return None

    async def show_next(self) -> bool:
        """Show next image."""
        try:
            async with async_timeout.timeout(10):
                async with self._session.post(
                    f"http://{self._host}{ENDPOINT_SHOW_NEXT}"
                ) as response:
                    if response.status == 200:
                        _LOGGER.info("Successfully sent showNext command")
                        return True
                    _LOGGER.error("ShowNext failed with status %s", response.status)
                    return False
        except Exception as err:
            _LOGGER.error("Error in showNext: %s", err)
            return False

    async def sleep(self) -> bool:
        """Put device to sleep."""
        try:
            async with async_timeout.timeout(10):
                async with self._session.post(
                    f"http://{self._host}{ENDPOINT_SLEEP}"
                ) as response:
                    if response.status == 200:
                        _LOGGER.info("Device sleep command sent successfully")
                        return True
                    _LOGGER.error("Sleep failed with status %s", response.status)
                    return False
        except Exception as err:
            _LOGGER.error("Error in sleep: %s", err)
            return False

    async def reboot(self) -> bool:
        """Reboot device."""
        try:
            async with async_timeout.timeout(10):
                async with self._session.post(
                    f"http://{self._host}{ENDPOINT_REBOOT}"
                ) as response:
                    if response.status == 200:
                        _LOGGER.info("Device reboot command sent successfully")
                        return True
                    _LOGGER.error("Reboot failed with status %s", response.status)
                    return False
        except Exception as err:
            _LOGGER.error("Error in reboot: %s", err)
            return False

    async def clear_screen(self) -> bool:
        """Clear the screen."""
        try:
            async with async_timeout.timeout(10):
                async with self._session.post(
                    f"http://{self._host}{ENDPOINT_CLEAR_SCREEN}"
                ) as response:
                    if response.status == 200:
                        _LOGGER.info("Screen cleared successfully")
                        return True
                    _LOGGER.error("Clear screen failed with status %s", response.status)
                    return False
        except Exception as err:
            _LOGGER.error("Error in clear screen: %s", err)
            return False

    async def whistle(self) -> bool:
        """Send keep-alive signal."""
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(
                    f"http://{self._host}{ENDPOINT_WHISTLE}"
                ) as response:
                    if response.status == 200:
                        _LOGGER.info("Whistle command sent successfully")
                        return True
                    _LOGGER.error("Whistle failed with status %s", response.status)
                    return False
        except Exception as err:
            _LOGGER.error("Error in whistle: %s", err)
            return False

    async def update_settings(self, settings: dict[str, Any]) -> bool:
        """Update device settings."""
        if not settings:
            _LOGGER.warning("No settings parameters provided")
            return False

        try:
            async with async_timeout.timeout(10):
                async with self._session.post(
                    f"http://{self._host}{ENDPOINT_SETTINGS}",
                    json=settings,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        _LOGGER.info("Settings updated successfully: %s", settings)
                        return True
                    _LOGGER.error("Settings update failed with status %s", response.status)
                    return False
        except Exception as err:
            _LOGGER.error("Error in update settings: %s", err)
            return False

    async def show_image(
        self,
        image_path: str,
        play_type: int = 0,
        dither: int | None = None,
        duration: int = 99999
    ) -> bool:
        """Show image using /show API with full path.

        Args:
            image_path: Path to image (e.g., "/gallerys/default/image.jpg")
            play_type: 0=single image, 1=gallery slideshow, 2=playlist
            dither: Optional dithering algorithm (0=Floyd-Steinberg, 1=JJN)
            duration: Display duration in seconds (default: 99999)
        """
        try:
            # Parse image_path to extract gallery and filename
            # Format: "/gallerys/{gallery}/{filename}"
            parts = image_path.strip("/").split("/")
            if len(parts) >= 3 and parts[0] == "gallerys":
                gallery = parts[1]
                filename = parts[2]
            else:
                # Fallback for unexpected format
                gallery = "default"
                filename = image_path.split("/")[-1]

            return await self.show_image_by_name(filename, gallery, play_type, dither, duration)
        except Exception as err:
            _LOGGER.error("Error showing image: %s", err)
            return False

    async def show_image_by_name(
        self,
        filename: str,
        gallery: str = "default",
        play_type: int = 0,
        dither: int | None = None,
        duration: int = 99999
    ) -> bool:
        """Show image using /show API with separate filename and gallery.

        Args:
            filename: Image filename (e.g., "image.jpg")
            gallery: Gallery name (default: "default")
            play_type: 0=single image, 1=gallery slideshow, 2=playlist
            dither: Optional dithering algorithm (0=Floyd-Steinberg, 1=JJN)
            duration: Display duration in seconds (default: 99999)
        """
        try:
            show_data = {
                "play_type": play_type
            }

            if play_type == 0:
                # Single image mode: requires full path
                show_data["image"] = f"/gallerys/{gallery}/{filename}"
            elif play_type == 1:
                # Gallery slideshow mode: requires gallery, duration, and filename only
                show_data["image"] = filename
                show_data["gallery"] = gallery
                show_data["duration"] = duration
            elif play_type == 2:
                # Playlist mode: would need playlist parameter
                show_data["image"] = f"/gallerys/{gallery}/{filename}"

            if dither is not None:
                show_data["dither"] = dither

            _LOGGER.info("Showing image - gallery: %s, filename: %s, data: %s", gallery, filename, show_data)

            async with self._session.post(
                f"http://{self._host}{ENDPOINT_SHOW}",
                json=show_data
            ) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully displayed image: %s/%s", gallery, filename)
                    return True
                response_text = await response.text()
                _LOGGER.error(
                    "Failed to show image: %s - %s",
                    response.status,
                    response_text
                )
                return False
        except Exception as err:
            _LOGGER.error("Error showing image: %s", err)
            return False

    async def upload_image(
        self,
        image_data: bytes,
        filename: str,
        gallery: str = "default",
        show_now: bool = False,
        max_retries: int = 3
    ) -> str | None:
        """Upload image to device via /upload endpoint.

        Args:
            image_data: JPEG image bytes
            filename: Filename to save as
            gallery: Gallery name (default: "default")
            show_now: Display immediately after upload (1) or not (0)
            max_retries: Number of retry attempts

        Returns:
            Full image path (e.g., "/gallerys/default/image.jpg") or None on failure

        Note:
            The device returns {"status":100, "path":"/gallerys/default/"} with
            content-type text/javascript. We must append the filename to get the full path.
        """
        for attempt in range(max_retries):
            try:
                form = aiohttp.FormData()
                form.add_field(
                    "image",
                    image_data,
                    filename=filename,
                    content_type="image/jpeg"
                )

                # Build URL with query parameters as per original working code
                upload_url = f"http://{self._host}{ENDPOINT_UPLOAD}?filename={filename}&gallery={gallery}&show_now={'1' if show_now else '0'}"

                async with async_timeout.timeout(30):
                    async with self._session.post(
                        upload_url,
                        data=form
                    ) as response:
                        if response.status == 200:
                            response_text = await response.text()

                            try:
                                result = json.loads(response_text)
                                _LOGGER.info("Upload response: %s", result)
                                # Response contains directory path only, append filename
                                base_path = result.get("path", f"/gallerys/{gallery}/")
                                if not base_path.endswith("/"):
                                    base_path += "/"
                                image_path = f"{base_path}{filename}"
                                _LOGGER.info("Constructed path: %s (base: %s, filename: %s)",
                                           image_path, base_path, filename)
                                return image_path
                            except json.JSONDecodeError as e:
                                # Fallback to default path construction
                                _LOGGER.warning("Failed to parse upload response: %s", e)
                                image_path = f"/gallerys/{gallery}/{filename}"
                                _LOGGER.info("Using default path: %s", image_path)
                                return image_path

                        response_text = await response.text()
                        _LOGGER.error("Upload failed: %s - %s", response.status, response_text)
                        return None

            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as err:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    _LOGGER.warning(
                        "Upload attempt %d/%d failed: %s. Retrying in %ds...",
                        attempt + 1, max_retries, err, wait_time
                    )
                    await asyncio.sleep(wait_time)
                else:
                    _LOGGER.error("Upload failed after %d attempts: %s", max_retries, err)
                    return None
            except Exception as err:
                _LOGGER.error("Unexpected upload error: %s", err)
                return None

        return None

    async def get_galleries(self) -> list[dict[str, Any]]:
        """Get list of all galleries via /gallery/list endpoint.

        Returns:
            List of gallery objects with 'name' field, e.g., [{"name": "default"}]

        Note:
            Device returns content-type text/json instead of application/json.
        """
        try:
            async with self._session.get(
                f"http://{self._host}/gallery/list"
            ) as response:
                if response.status == 200:
                    text_response = await response.text()
                    try:
                        return json.loads(text_response)
                    except json.JSONDecodeError as err:
                        _LOGGER.error("Failed to parse galleries response: %s", err)
                return []
        except Exception as err:
            _LOGGER.error("Error getting galleries: %s", err)
            return []

    async def get_gallery_images(
        self,
        gallery_name: str,
        offset: int = 0,
        limit: int = 100
    ) -> dict[str, Any]:
        """Get paginated list of images from a gallery via /gallery endpoint.

        Args:
            gallery_name: Gallery name to query
            offset: Starting index for pagination
            limit: Number of items per page

        Returns:
            Dict with 'data' (list of images), 'total', 'offset', 'limit'
            Each image has 'name', 'size', 'time' fields.
        """
        try:
            params = {
                "gallery_name": gallery_name,
                "offset": offset,
                "limit": limit
            }
            async with self._session.get(
                f"http://{self._host}/gallery",
                params=params
            ) as response:
                if response.status == 200:
                    text_response = await response.text()
                    try:
                        return json.loads(text_response)
                    except json.JSONDecodeError as err:
                        _LOGGER.error("Failed to parse gallery images response: %s", err)
                return {"data": []}
        except Exception as err:
            _LOGGER.error("Error getting gallery images: %s", err)
            return {"data": []}

    async def sync_photos_from_media_source(
        self,
        media_source_id: str,
        target_gallery: str = "default",
        max_photos: int = 50,
        overwrite_existing: bool = False
    ) -> dict[str, Any]:
        """Sync photos from a Home Assistant media source to a device gallery.

        Args:
            media_source_id: Media source identifier (e.g., "media_source://local/photos/vacation")
            target_gallery: Target gallery name on device (default: "default")
            max_photos: Maximum number of photos to sync (default: 50)
            overwrite_existing: Whether to overwrite existing photos with same name (default: False)

        Returns:
            Dict with sync results:
            - success: bool - Overall success status
            - synced_count: int - Number of photos successfully synced
            - skipped_count: int - Number of photos skipped
            - failed_count: int - Number of photos that failed to sync
            - errors: list[str] - List of error messages
            - synced_photos: list[str] - List of synced photo paths

        Raises:
            ValueError: If media_source_id is invalid
            Exception: For network or device errors
        """
        result = {
            "success": False,
            "synced_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "errors": [],
            "synced_photos": []
        }

        try:
            # Validate media source ID
            if not media_source.is_media_source_id(media_source_id):
                raise ValueError(f"Invalid media source ID: {media_source_id}")

            _LOGGER.info("Starting photo sync from %s to gallery %s", media_source_id, target_gallery)

            # Browse the media source to get all photos
            photos = await self._browse_media_source_photos(media_source_id, max_photos)
            if not photos:
                _LOGGER.warning("No photos found in media source: %s", media_source_id)
                result["success"] = True
                return result

            _LOGGER.info("Found %d photos to sync", len(photos))

            # Get existing photos in target gallery if overwrite_existing is False
            existing_photos = set()
            if not overwrite_existing:
                gallery_info = await self.get_gallery_images(target_gallery, offset=0, limit=1000)
                existing_photos = {photo["name"] for photo in gallery_info.get("data", [])}
                _LOGGER.info("Found %d existing photos in gallery %s", len(existing_photos), target_gallery)

            # Sync each photo
            for photo_info in photos:
                try:
                    photo_name = photo_info["name"]
                    photo_url = photo_info["url"]

                    # Check if photo already exists
                    if not overwrite_existing and photo_name in existing_photos:
                        _LOGGER.debug("Skipping existing photo: %s", photo_name)
                        result["skipped_count"] += 1
                        continue

                    # Download photo data
                    photo_data = await self._download_photo_data(photo_url)
                    if not photo_data:
                        result["errors"].append(f"Failed to download photo: {photo_name}")
                        result["failed_count"] += 1
                        continue

                    # Upload to device
                    uploaded_path = await self.upload_image(
                        photo_data,
                        photo_name,
                        gallery=target_gallery,
                        show_now=False
                    )

                    if uploaded_path:
                        result["synced_photos"].append(uploaded_path)
                        result["synced_count"] += 1
                        _LOGGER.info("Successfully synced photo: %s -> %s", photo_name, uploaded_path)
                    else:
                        result["errors"].append(f"Failed to upload photo: {photo_name}")
                        result["failed_count"] += 1

                except Exception as err:
                    error_msg = f"Error syncing photo {photo_info.get('name', 'unknown')}: {str(err)}"
                    _LOGGER.error(error_msg)
                    result["errors"].append(error_msg)
                    result["failed_count"] += 1

            # Determine overall success
            result["success"] = result["failed_count"] == 0 and result["synced_count"] > 0

            _LOGGER.info(
                "Photo sync completed - Success: %s, Synced: %d, Skipped: %d, Failed: %d",
                result["success"], result["synced_count"], result["skipped_count"], result["failed_count"]
            )

            return result

        except Exception as err:
            error_msg = f"Photo sync failed: {str(err)}"
            _LOGGER.error(error_msg)
            result["errors"].append(error_msg)
            return result

    async def _browse_media_source_photos(self, media_source_id: str, max_photos: int) -> list[dict[str, str]]:
        """Browse media source and return list of photos.

        Args:
            media_source_id: Media source identifier
            max_photos: Maximum number of photos to return

        Returns:
            List of photo info dicts with 'name' and 'url' keys
        """
        photos = []

        try:
            # Resolve media source and browse recursively
            media_item = await media_source.async_browse_media(
                self._hass,
                media_source_id,
                content_type_filter="image/*"
            )

            # Extract photos from media item (recursive)
            photos = await self._extract_photos_from_media_item(media_item, max_photos)

            # Limit results
            if len(photos) > max_photos:
                photos = photos[:max_photos]
                _LOGGER.info("Limited photo sync to %d photos", max_photos)

        except Exception as err:
            _LOGGER.error("Error browsing media source %s: %s", media_source_id, err)

        return photos

    async def _extract_photos_from_media_item(
        self,
        media_item,
        max_photos: int,
        photos: list | None = None
    ) -> list[dict[str, str]]:
        """Recursively extract photos from media item.

        Args:
            media_item: BrowseMedia item
            max_photos: Maximum photos to collect
            photos: Existing photos list (for recursion)

        Returns:
            List of photo info dicts
        """
        if photos is None:
            photos = []

        # Stop if we've reached max photos
        if len(photos) >= max_photos:
            return photos

        # If this is a playable media item (photo), add it
        if (media_item.media_class in [MediaClass.IMAGE, MediaClass.PHOTO] and
            media_item.can_play and
            hasattr(media_item, 'media_content_type') and
            media_item.media_content_type and
            media_item.media_content_type.startswith("image/")):
            
            photo_info = {
                "name": media_item.title,
                "url": media_item.media_content_id
            }
            photos.append(photo_info)
            _LOGGER.debug("Found photo: %s", media_item.title)

        # If this has children, recurse
        if (hasattr(media_item, 'children') and
            media_item.children and
            len(photos) < max_photos):
            
            for child in media_item.children:
                photos = await self._extract_photos_from_media_item(child, max_photos, photos)
                if len(photos) >= max_photos:
                    break

        return photos

    async def _download_photo_data(self, photo_url: str) -> bytes | None:
        """Download photo data from URL.

        Args:
            photo_url: URL to download photo from

        Returns:
            Photo data as bytes or None on failure
        """
        try:
            # Process media URL if it's a media source
            if media_source.is_media_source_id(photo_url):
                play_item = await media_source.async_resolve_media(
                    self._hass, photo_url, "eink_canvas.sync"
                )
                photo_url = async_process_play_media_url(self._hass, play_item.url)

            async with async_timeout.timeout(30):
                async with self._session.get(photo_url) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        _LOGGER.error("Failed to download photo from %s: status %d", photo_url, response.status)
                        return None

        except Exception as err:
            _LOGGER.error("Error downloading photo from %s: %s", photo_url, err)
            return None
