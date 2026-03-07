"""Unit tests for elevenlab_endpoint.voice_registry.

Verifies that voice_id → preset_id resolution works correctly and that
unknown voice IDs return None (so the API layer can raise HTTP 404).
"""

from __future__ import annotations

import pytest

from elevenlab_endpoint.voice_registry import (
    list_voices,
    register_voice,
    reset_registry,
    resolve_preset,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    """Restore the built-in registry after every test."""
    yield
    reset_registry()


class TestResolvePreset:
    def test_known_voices_resolve_to_correct_preset(self):
        """All built-in voice IDs should map to themselves (same preset name)."""
        built_ins = ["jp_female", "jp_male", "en_female", "en_male"]
        for voice_id in built_ins:
            result = resolve_preset(voice_id)
            assert result == voice_id, f"Expected {voice_id!r}, got {result!r}"

    def test_unknown_voice_id_returns_none(self):
        """An unregistered voice_id must return None so the caller can raise 404."""
        result = resolve_preset("totally_unknown_voice")
        assert result is None

    def test_empty_voice_id_returns_none(self):
        """An empty string should return None without raising."""
        assert resolve_preset("") is None

    def test_case_sensitive_lookup(self):
        """Voice IDs are case-sensitive; 'JP_Female' is not the same as 'jp_female'."""
        assert resolve_preset("JP_Female") is None


class TestRegisterVoice:
    def test_custom_voice_resolves_after_registration(self):
        """Registering a custom mapping should make it resolvable."""
        register_voice("custom_voice", "en_female")
        assert resolve_preset("custom_voice") == "en_female"

    def test_register_overrides_existing_entry(self):
        """Re-registering a built-in voice_id should update its preset."""
        register_voice("jp_female", "en_male")
        assert resolve_preset("jp_female") == "en_male"

    def test_register_empty_voice_id_raises(self):
        """Registering with an empty voice_id must raise ValueError."""
        with pytest.raises(ValueError, match="voice_id"):
            register_voice("", "en_female")

    def test_register_empty_preset_id_raises(self):
        """Registering with an empty preset_id must raise ValueError."""
        with pytest.raises(ValueError, match="preset_id"):
            register_voice("some_voice", "")


class TestListVoices:
    def test_list_contains_all_built_ins(self):
        """list_voices() must include all four built-in entries."""
        voices = list_voices()
        voice_ids = {v["voice_id"] for v in voices}
        assert {"jp_female", "jp_male", "en_female", "en_male"}.issubset(voice_ids)

    def test_list_contains_registered_custom_voice(self):
        """A newly registered voice should appear in list_voices()."""
        register_voice("custom_x", "en_male")
        voices = list_voices()
        ids = [v["voice_id"] for v in voices]
        assert "custom_x" in ids

    def test_list_entries_have_required_keys(self):
        """Every entry must have both 'voice_id' and 'preset_id' keys."""
        for entry in list_voices():
            assert "voice_id" in entry
            assert "preset_id" in entry


class TestResetRegistry:
    def test_reset_removes_custom_registrations(self):
        """After reset, custom registrations should be gone."""
        register_voice("temp_voice", "en_female")
        assert resolve_preset("temp_voice") == "en_female"
        reset_registry()
        assert resolve_preset("temp_voice") is None

    def test_reset_restores_built_ins(self):
        """After reset, all built-in voices should resolve correctly."""
        register_voice("jp_female", "en_male")  # override a built-in
        reset_registry()
        assert resolve_preset("jp_female") == "jp_female"
