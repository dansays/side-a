"""Thin Home Assistant REST client.

HA owns all physical I/O for this project: the camera (snapshot source), the
'flash' light, and the HomePod (playback). The app drives them over HA's REST API
with a long-lived access token.
"""

from __future__ import annotations

import requests

from .config import Settings, get_settings


class HomeAssistant:
    def __init__(self, settings: Settings):
        self.base = settings.ha_base_url.rstrip("/")
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {settings.ha_token}",
                "Content-Type": "application/json",
            }
        )

    def _service(self, domain: str, service: str, data: dict) -> None:
        resp = self.session.post(
            f"{self.base}/api/services/{domain}/{service}", json=data, timeout=30
        )
        resp.raise_for_status()

    def camera_snapshot(self) -> bytes:
        """Fetch a still JPEG from the configured HA camera entity."""
        resp = self.session.get(
            f"{self.base}/api/camera_proxy/{self.settings.ha_camera_entity}",
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content

    def lights(self, action: str) -> None:
        """Drive the WLED strip via the HA script.

        `action` is one of: 'flash' (bright, for the snapshot), 'processing'
        (loading animation during ID/script/TTS), 'done' (revert to neutral as
        the audio fires). The script entity is called as a service, passing
        `action` as a script variable.
        """
        domain, _, object_id = self.settings.ha_lights_script.partition(".")
        self._service(domain, object_id, {"action": action})

    def play_media(self, url: str) -> None:
        self._service(
            "media_player",
            "play_media",
            {
                "entity_id": self.settings.ha_media_player_entity,
                "media_content_id": url,
                "media_content_type": "music",
            },
        )


def get_ha() -> HomeAssistant:
    return HomeAssistant(get_settings())
