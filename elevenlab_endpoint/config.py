"""Configuration for the ElevenLabs-compatible TTS proxy server.

Settings are loaded in this priority order (highest wins):
  1. Environment variables
  2. config.json file  (path set via PROXY_CONFIG_FILE, default: elevenlab_endpoint/config.json)
  3. Hard-coded defaults

All JSON keys use snake_case and match the field names in ProxyConfig.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"


def _load_json_config(path: Path) -> dict:
    """Load a JSON config file and return its contents as a dict.

    Args:
        path: Filesystem path to the JSON config file.

    Returns:
        Parsed JSON dict, or an empty dict when the file does not exist.
    """
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            logger.warning("config.json root must be a JSON object — ignoring file.")
            return {}
        logger.info("Loaded config from %s", path)
        return data
    except Exception as exc:
        logger.warning("Failed to read config.json at %s: %s", path, exc)
        return {}


def _env(name: str, json_val, default: str) -> str:
    """Resolve a string config value: env var → json → default."""
    return os.getenv(name) or (str(json_val) if json_val is not None else default)


def _env_int(name: str, json_val, default: int) -> int:
    """Resolve an integer config value: env var → json → default."""
    raw = os.getenv(name)
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            pass
    if json_val is not None:
        try:
            return int(json_val)
        except (TypeError, ValueError):
            pass
    return default


def _env_float_opt(name: str, json_val) -> float | None:
    """Resolve an optional float config value: env var → json → None."""
    raw = os.getenv(name)
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            pass
    if json_val is not None:
        try:
            return float(json_val)
        except (TypeError, ValueError):
            pass
    return None


def _env_int_opt(name: str, json_val) -> int | None:
    """Resolve an optional integer config value: env var → json → None."""
    raw = os.getenv(name)
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            pass
    if json_val is not None:
        try:
            return int(json_val)
        except (TypeError, ValueError):
            pass
    return None


def _env_bool(name: str, json_val, default: bool) -> bool:
    """Resolve a boolean config value: env var → json → default."""
    raw = os.getenv(name)
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
    if json_val is not None:
        if isinstance(json_val, bool):
            return json_val
        return str(json_val).lower() in {"1", "true", "yes", "y", "on"}
    return default


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMDefaults:
    """Default LLM sampling parameters forwarded to miotts_server.

    All fields are optional. When ``None`` the miotts_server's own defaults
    are used for that parameter.
    """

    temperature: float | None = None
    """Sampling temperature (0.0–2.0). None = use miotts_server default."""

    top_p: float | None = None
    """Top-p nucleus sampling (0.0–1.0). None = use miotts_server default."""

    max_tokens: int | None = None
    """Maximum tokens to generate. None = use miotts_server default."""

    repetition_penalty: float | None = None
    """Repetition penalty (1.0–1.5). None = use miotts_server default."""

    presence_penalty: float | None = None
    """Presence penalty (0.0–1.0). None = use miotts_server default."""

    frequency_penalty: float | None = None
    """Frequency penalty (0.0–1.0). None = use miotts_server default."""


@dataclass(frozen=True)
class ProxyConfig:
    """Immutable configuration snapshot for the proxy server."""

    host: str
    """Host address the proxy binds to."""

    port: int
    """TCP port the proxy listens on."""

    miotts_base_url: str
    """Base URL of the upstream miotts_server."""

    api_key: str | None
    """
    When set, the ``xi-api-key`` request header is validated against this
    value. ``None`` = open access (suitable for local deployments).
    """

    transcode_mp3: bool
    """
    When ``True``, WAV audio from miotts_server is transcoded to MP3.
    Requires ``ffmpeg`` on PATH.
    """

    miotts_timeout: float
    """HTTP timeout (seconds) for requests to miotts_server."""

    default_voice_id: str
    """
    Fallback preset_id used when the requested voice_id is not found in the
    registry or on miotts_server. When empty, an unknown voice returns 404.
    """

    llm: LLMDefaults = field(default_factory=LLMDefaults)
    """Default LLM sampling parameters forwarded to miotts_server."""


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_config: ProxyConfig | None = None


def get_config() -> ProxyConfig:
    """Return the singleton proxy configuration, building it on first call.

    Config is merged from (highest precedence first):
    1. Environment variables
    2. config.json file (path from PROXY_CONFIG_FILE env var or default)
    3. Hard-coded defaults
    """
    global _config
    if _config is not None:
        return _config

    config_path = Path(os.getenv("PROXY_CONFIG_FILE", str(_DEFAULT_CONFIG_PATH)))
    j = _load_json_config(config_path)
    j_llm: dict = j.get("llm", {}) or {}

    raw_key = _env("PROXY_API_KEY", j.get("api_key"), "").strip()

    _config = ProxyConfig(
        host=_env("PROXY_HOST", j.get("host"), "0.0.0.0"),
        port=_env_int("PROXY_PORT", j.get("port"), 8002),
        miotts_base_url=_env("MIOTTS_BASE_URL", j.get("miotts_base_url"), "http://localhost:8001").rstrip("/"),
        api_key=raw_key if raw_key else None,
        transcode_mp3=_env_bool("PROXY_TRANSCODE_MP3", j.get("transcode_mp3"), False),
        default_voice_id=_env("PROXY_DEFAULT_VOICE_ID", j.get("default_voice_id"), "").strip(),
        miotts_timeout=float(_env("PROXY_MIOTTS_TIMEOUT", j.get("miotts_timeout"), "60")),
        llm=LLMDefaults(
            temperature=_env_float_opt("PROXY_LLM_TEMPERATURE", j_llm.get("temperature")),
            top_p=_env_float_opt("PROXY_LLM_TOP_P", j_llm.get("top_p")),
            max_tokens=_env_int_opt("PROXY_LLM_MAX_TOKENS", j_llm.get("max_tokens")),
            repetition_penalty=_env_float_opt("PROXY_LLM_REPETITION_PENALTY", j_llm.get("repetition_penalty")),
            presence_penalty=_env_float_opt("PROXY_LLM_PRESENCE_PENALTY", j_llm.get("presence_penalty")),
            frequency_penalty=_env_float_opt("PROXY_LLM_FREQUENCY_PENALTY", j_llm.get("frequency_penalty")),
        ),
    )
    return _config


def reset_config() -> None:
    """Reset cached config (useful in tests or to pick up file changes)."""
    global _config
    _config = None
