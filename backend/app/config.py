from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WAR_ROOM_", env_file=ROOT / ".env", extra="ignore", populate_by_name=True
    )
    database_path: Path = Path("data/war_room.db")
    storage_mode: Literal["browser", "local_sqlite"] = "browser"
    serve_frontend: bool = False
    public_url: str = Field(
        default="", validation_alias=AliasChoices("WAR_ROOM_PUBLIC_URL", "RENDER_EXTERNAL_URL")
    )
    access_password: SecretStr = SecretStr("")
    llm_provider: Literal["disabled", "gemini", "openai"] = Field(
        default="gemini", validation_alias=AliasChoices("LLM_PROVIDER", "WAR_ROOM_LLM_PROVIDER")
    )
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="", validation_alias="GEMINI_MODEL")
    openai_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="", validation_alias="OPENAI_MODEL")

    @model_validator(mode="after")
    def public_configuration(self):
        if self.public_url:
            parsed = urlsplit(self.public_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError("Public URL must be an HTTPS origin")
            self.public_url = self.public_url.rstrip("/")
            if self.storage_mode != "browser":
                raise ValueError("Public hosting requires browser storage")
            if len(self.access_password.get_secret_value()) < 16:
                raise ValueError(
                    "Public hosting requires an access password of at least 16 characters"
                )
        return self

    @property
    def resolved_database_path(self) -> Path:
        return self.database_path if self.database_path.is_absolute() else ROOT / self.database_path

    @property
    def content_path(self) -> Path:
        return ROOT / "content"
