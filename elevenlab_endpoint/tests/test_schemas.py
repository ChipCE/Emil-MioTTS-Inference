"""Unit tests for elevenlab_endpoint.schemas.

Verifies that TTSRequestBody and related models parse correctly, enforce
required fields, and accept optional ElevenLabs-specific fields for
API compatibility.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from elevenlab_endpoint.schemas import (
    TTSRequestBody,
    VoiceInfo,
    VoicesListResponse,
)


class TestTTSRequestBody:
    def test_minimal_body_with_text_only(self):
        """A body with just 'text' should be valid."""
        body = TTSRequestBody(text="Hello world")
        assert body.text == "Hello world"
        assert body.model_id is None
        assert body.voice_settings is None

    def test_full_body_with_all_fields(self):
        """All optional fields should parse without error."""
        body = TTSRequestBody(
            text="Test",
            model_id="miotts",
            voice_settings={
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.1,
                "use_speaker_boost": True,
            },
            output_format="mp3_44100_128",
            optimize_streaming_latency=1,
            language_code="ja",
        )
        assert body.text == "Test"
        assert body.model_id == "miotts"
        assert body.voice_settings is not None
        assert body.voice_settings.stability == 0.5

    def test_missing_text_raises_validation_error(self):
        """Omitting 'text' must raise a ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TTSRequestBody()  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("text",) for e in errors)

    def test_voice_settings_stability_out_of_range(self):
        """stability must be between 0.0 and 1.0."""
        with pytest.raises(ValidationError):
            TTSRequestBody(
                text="Hi",
                voice_settings={"stability": 1.5},
            )

    def test_voice_settings_similarity_boost_out_of_range(self):
        """similarity_boost must be between 0.0 and 1.0."""
        with pytest.raises(ValidationError):
            TTSRequestBody(
                text="Hi",
                voice_settings={"similarity_boost": -0.1},
            )

    def test_extra_fields_are_ignored(self):
        """Unknown fields from ElevenLabs clients should not raise errors."""
        # Pydantic v2 ignores extra fields by default for BaseModel
        body = TTSRequestBody.model_validate(
            {
                "text": "Hello",
                "some_future_field": "value",
                "another_unknown": 42,
            }
        )
        assert body.text == "Hello"


class TestVoiceInfo:
    def test_required_fields(self):
        """voice_id and name are required; category defaults to 'premade'."""
        info = VoiceInfo(voice_id="jp_female", name="Jp Female")
        assert info.voice_id == "jp_female"
        assert info.name == "Jp Female"
        assert info.category == "premade"
        assert info.description is None

    def test_custom_category(self):
        """Category can be overridden."""
        info = VoiceInfo(voice_id="custom", name="Custom Voice", category="cloned")
        assert info.category == "cloned"


class TestVoicesListResponse:
    def test_empty_voices_list(self):
        """An empty list is valid."""
        resp = VoicesListResponse(voices=[])
        assert resp.voices == []

    def test_voices_list_with_entries(self):
        """A list with multiple VoiceInfo entries should round-trip correctly."""
        resp = VoicesListResponse(
            voices=[
                VoiceInfo(voice_id="jp_female", name="Jp Female"),
                VoiceInfo(voice_id="en_male", name="En Male"),
            ]
        )
        assert len(resp.voices) == 2
        assert resp.voices[0].voice_id == "jp_female"
