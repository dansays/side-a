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

    # NOTE (roadmap): these will become a WLED sequence — a bright "flash" preset
    # for the snapshot, a "loading" animation during identify+TTS, then revert to
    # the neutral setting at playback. Replace light_on/light_off with
    # flash()/loading()/restore() (WLED presets via light.turn_on / select / effect
    # or the WLED JSON API) and re-sequence in pipeline.run_trigger. See README Roadmap.
    def light_on(self) -> None:
        self._service(
            "light", "turn_on", {"entity_id": self.settings.ha_light_entity}
        )

    def light_off(self) -> None:
        self._service(
            "light", "turn_off", {"entity_id": self.settings.ha_light_entity}
        )

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
