"""
Application configuration.

Loads settings from environment variables (via .env file) and exposes
them as a typed Settings dataclass. Fails fast if required keys are missing.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env file (if present) into os.environ
load_dotenv()


@dataclass
class Settings:
    """Central configuration for the voice survey agent."""

    # --- Required ---
    google_api_key: str = field(default_factory=lambda: os.environ.get("GOOGLE_API_KEY", ""))
    openai_api_key: str | None = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", None))

    # --- Voice engine selection ---
    # Supported values: "gemini" (default), "openai" (TODO), "cascade" (TODO)
    voice_engine: str = field(default_factory=lambda: os.environ.get("VOICE_ENGINE", "gemini"))

    # --- Server ---
    host: str = field(default_factory=lambda: os.environ.get("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("PORT", "8765")))

    # --- Model ---
    gemini_model: str = field(
        default_factory=lambda: os.environ.get(
            "GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025"
        )
    )

    def __post_init__(self) -> None:
        if not self.google_api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. "
                "Copy .env.example to .env and add your key from https://aistudio.google.com/"
            )


def get_settings() -> Settings:
    """Create and validate a Settings instance."""
    return Settings()
