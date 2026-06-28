"""Application configuration, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # AI
    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-opus-4-8", alias="ANTHROPIC_MODEL")

    # ElevenLabs
    elevenlabs_api_key: str = Field(alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field(alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = Field(
        default="eleven_multilingual_v2", alias="ELEVENLABS_MODEL_ID"
    )

    # Last.fm (optional — scrobbling is a no-op until all three are set)
    lastfm_api_key: str = Field(default="", alias="LASTFM_API_KEY")
    lastfm_api_secret: str = Field(default="", alias="LASTFM_API_SECRET")
    lastfm_session_key: str = Field(default="", alias="LASTFM_SESSION_KEY")
    default_track_seconds: int = Field(default=210, alias="DEFAULT_TRACK_SECONDS")

    # Discogs
    discogs_token: str = Field(alias="DISCOGS_TOKEN")
    discogs_username: str = Field(alias="DISCOGS_USERNAME")
    discogs_user_agent: str = Field(alias="DISCOGS_USER_AGENT")

    # Home Assistant
    ha_base_url: str = Field(alias="HA_BASE_URL")
    ha_token: str = Field(alias="HA_TOKEN")
    ha_camera_entity: str = Field(alias="HA_CAMERA_ENTITY")
    ha_media_player_entity: str = Field(alias="HA_MEDIA_PLAYER_ENTITY")
    # HA script that drives the WLED strip; called with an `action` of
    # flash / processing / done at each pipeline phase.
    ha_lights_script: str = Field(
        default="script.side_a_lights", alias="HA_LIGHTS_SCRIPT"
    )

    # App
    app_public_base_url: str = Field(alias="APP_PUBLIC_BASE_URL")
    app_port: int = Field(default=8099, alias="APP_PORT")
    flash_delay_seconds: float = Field(default=1.5, alias="FLASH_DELAY_SECONDS")
    data_dir: Path = Field(default=Path("./data"), alias="DATA_DIR")

    @property
    def lastfm_configured(self) -> bool:
        return bool(
            self.lastfm_api_key
            and self.lastfm_api_secret
            and self.lastfm_session_key
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "side-a.db"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.thumbnails_dir, self.media_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()  # type: ignore[call-arg]
    settings.ensure_dirs()
    return settings
