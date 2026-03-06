"""Pydantic models for the ElevenLabs-compatible TTS proxy API.

These schemas mirror the ElevenLabs v1 REST API surface that client
applications typically interact with. Only the fields relevant to our
proxy are included; unknown fields sent by clients are silently ignored
thanks to Pydantic's default behaviour.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class VoiceSettings(BaseModel):
    """Optional voice quality knobs forwarded from the ElevenLabs client.

    These are accepted for API compatibility but are not forwarded to
    miotts_server (which does not have equivalent parameters).
    """

    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    similarity_boost: float | None = Field(default=None, ge=0.0, le=1.0)
    style: float | None = Field(default=None, ge=0.0, le=1.0)
    use_speaker_boost: bool | None = None


class TTSRequestBody(BaseModel):
    """Request body accepted on ``POST /v1/text-to-speech/{voice_id}``."""

    text: str = Field(..., description="Text to synthesise into speech.")
    model_id: str | None = Field(
        default=None,
        description="Model identifier. Accepted for compatibility; ignored by the proxy.",
    )
    voice_settings: VoiceSettings | None = None

    # ElevenLabs SDK also sends these; accept and ignore them.
    output_format: str | None = None
    optimize_streaming_latency: int | None = None
    language_code: str | None = None


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------


class VoiceInfo(BaseModel):
    """A single voice entry in the /v1/voices response."""

    voice_id: str
    name: str
    category: str = "premade"
    description: str | None = None


class VoicesListResponse(BaseModel):
    """Response body for ``GET /v1/voices``."""

    voices: list[VoiceInfo]


class ErrorDetail(BaseModel):
    """Standard error response body."""

    status: str
    message: str
