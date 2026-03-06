"""Voice registry: maps ElevenLabs voice_id strings to MioTTS preset_id strings.

The ElevenLabs API identifies voices by opaque ID strings. This module
maintains a bidirectional registry so the proxy can translate any incoming
voice_id to the correct MioTTS preset.

Built-in entries mirror the preset files shipped with miotts_server:
  - jp_female, jp_male, en_female, en_male

Additional custom mappings can be registered at runtime via
``register_voice()``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in voice → preset map
# Keys are ElevenLabs voice IDs; values are MioTTS preset IDs.
# ---------------------------------------------------------------------------
_BUILTIN_VOICES: dict[str, str] = {
    "jp_female": "jp_female",
    "jp_male": "jp_male",
    "en_female": "en_female",
    "en_male": "en_male",
}

# Runtime registry (starts with a copy of the built-ins).
_registry: dict[str, str] = dict(_BUILTIN_VOICES)


def resolve_preset(voice_id: str) -> str | None:
    """Return the MioTTS preset_id for *voice_id*, or ``None`` if not found.

    Args:
        voice_id: The ElevenLabs voice identifier from the client request.

    Returns:
        The corresponding MioTTS preset_id, or ``None`` when the voice_id is
        not registered.
    """
    if not voice_id:
        return None
    preset = _registry.get(voice_id)
    if preset is None:
        logger.warning("Unknown voice_id %r — no matching preset found.", voice_id)
    return preset


def register_voice(voice_id: str, preset_id: str) -> None:
    """Register a custom voice_id → preset_id mapping.

    Args:
        voice_id: The ElevenLabs voice identifier to register.
        preset_id: The MioTTS preset_id it should resolve to.
    """
    if not voice_id:
        raise ValueError("voice_id must not be empty")
    if not preset_id:
        raise ValueError("preset_id must not be empty")
    _registry[voice_id] = preset_id
    logger.debug("Registered voice %r → preset %r", voice_id, preset_id)


def list_voices() -> list[dict[str, str]]:
    """Return all registered voices as a list of ``{voice_id, preset_id}`` dicts.

    Returns:
        List of dicts, each containing ``voice_id`` and ``preset_id``.
    """
    return [{"voice_id": vid, "preset_id": pid} for vid, pid in _registry.items()]


def reset_registry() -> None:
    """Restore the registry to its built-in defaults (useful in tests)."""
    global _registry
    _registry = dict(_BUILTIN_VOICES)
