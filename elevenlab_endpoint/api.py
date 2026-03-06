"""FastAPI application for the ElevenLabs-compatible TTS proxy.

Exposes four routes that mirror the ElevenLabs v1 REST API:

    GET  /health
    GET  /v1/voices
    POST /v1/text-to-speech/{voice_id}
    POST /v1/text-to-speech/{voice_id}/stream

Every TTS request is translated into a MioTTS ``/v1/tts`` call, and the
resulting WAV audio is either returned directly or transcoded to MP3
depending on the ``PROXY_TRANSCODE_MP3`` config flag.
"""

from __future__ import annotations

import io
import logging

import httpx
from fastapi import FastAPI, Header, HTTPException, Path
from fastapi.responses import JSONResponse, StreamingResponse

from .config import get_config
from .schemas import ErrorDetail, TTSRequestBody, VoiceInfo, VoicesListResponse
from .voice_registry import list_voices, resolve_preset

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language code mapping
# ---------------------------------------------------------------------------

_LANGUAGE_PREFIX_MAP: dict[str, str] = {
    "ja": "ja",
    "en": "en",
}


def _map_language_code(language_code: str | None) -> str:
    """Map an ElevenLabs/IETF language code to a MioTTS language string.

    MioTTS accepts only ``"ja"``, ``"en"``, or ``"auto"``.
    The primary language subtag (e.g. ``"ja"`` from ``"ja-JP"``) is
    extracted and matched; anything unrecognised becomes ``"auto"``.

    Args:
        language_code: IETF language tag from the ElevenLabs request body,
            e.g. ``"ja"``, ``"ja-JP"``, ``"en-US"``.

    Returns:
        One of ``"ja"``, ``"en"``, or ``"auto"``.
    """
    if not language_code:
        return "auto"
    primary = language_code.strip().split("-")[0].lower()
    return _LANGUAGE_PREFIX_MAP.get(primary, "auto")

app = FastAPI(
    title="ElevenLabs-Compatible TTS Proxy",
    description=(
        "A thin proxy that accepts ElevenLabs v1 API calls and forwards them "
        "to a locally-running miotts_server instance."
    ),
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_api_key(xi_api_key: str | None) -> None:
    """Raise HTTP 401 if a key is configured and the request key does not match.

    Args:
        xi_api_key: Value of the ``xi-api-key`` request header (may be None).
    """
    config = get_config()
    if config.api_key is None:
        # No key configured — open access (suitable for local deployments).
        return
    if xi_api_key != config.api_key:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "Invalid or missing xi-api-key header."},
        )


async def _fetch_presets_from_miotts() -> list[str]:
    """Fetch the list of available preset IDs from miotts_server.

    Calls ``GET /v1/presets`` on the upstream server and returns the preset
    name list. Falls back to an empty list on any network or parse error so
    that the proxy stays healthy even when the server is temporarily
    unreachable.

    Returns:
        List of preset_id strings reported by miotts_server.
    """
    config = get_config()
    url = f"{config.miotts_base_url}/v1/presets"
    try:
        async with httpx.AsyncClient(timeout=config.miotts_timeout) as client:
            response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        return [str(p) for p in data.get("presets", [])]
    except Exception as exc:
        logger.warning("Could not fetch presets from miotts_server (%s): %s", url, exc)
        return []


async def _resolve_voice_or_404(voice_id: str) -> str:
    """Return the MioTTS preset_id for *voice_id* or raise HTTP 404.

    Resolution order:
    1. Local voice registry (supports custom aliases).
    2. Live preset list from miotts_server — any preset that exists on the
       server is accepted directly as a preset_id.

    Args:
        voice_id: The ElevenLabs voice identifier from the URL path.

    Returns:
        The corresponding MioTTS preset_id.

    Raises:
        HTTPException: HTTP 404 when *voice_id* is neither in the local
            registry nor present on miotts_server.
    """
    # 1. Check local registry (handles aliases and custom mappings).
    preset_id = resolve_preset(voice_id)
    if preset_id is not None:
        return preset_id

    # 2. Check if voice_id matches a preset that exists on the server.
    server_presets = await _fetch_presets_from_miotts()
    if voice_id in server_presets:
        logger.debug("voice_id %r not in local registry; using as preset_id directly.", voice_id)
        return voice_id

    # 3. Use the configured fallback voice, if any.
    config = get_config()
    if config.default_voice_id:
        logger.warning(
            "voice_id %r not found; falling back to default_voice_id %r.",
            voice_id,
            config.default_voice_id,
        )
        return config.default_voice_id

    raise HTTPException(
        status_code=404,
        detail={"status": "error", "message": f"Voice '{voice_id}' not found."},
    )


async def _fetch_wav_from_miotts(
    text: str,
    preset_id: str,
    language_code: str | None = None,
) -> bytes:
    """Forward a TTS request to miotts_server and return raw WAV bytes.

    Merges LLM defaults from :func:`~elevenlab_endpoint.config.get_config`
    into the request, and maps *language_code* to a MioTTS-compatible
    ``best_of_n.language`` hint.

    Args:
        text: The text to synthesise.
        preset_id: The MioTTS preset identifier for voice style.
        language_code: Optional IETF language tag from the client request
            (e.g. ``"ja-JP"``). Mapped to ``"ja"``, ``"en"``, or ``"auto"``
            and forwarded as the ``best_of_n.language`` hint.

    Returns:
        Raw WAV audio bytes.

    Raises:
        HTTPException: HTTP 502/504 when miotts_server is unreachable or
            returns an error.
    """
    config = get_config()

    # Build the LLM params block — only include fields that are explicitly set
    # in config so miotts_server can apply its own defaults for the rest.
    llm_params: dict = {}
    if config.llm.temperature is not None:
        llm_params["temperature"] = config.llm.temperature
    if config.llm.top_p is not None:
        llm_params["top_p"] = config.llm.top_p
    if config.llm.max_tokens is not None:
        llm_params["max_tokens"] = config.llm.max_tokens
    if config.llm.repetition_penalty is not None:
        llm_params["repetition_penalty"] = config.llm.repetition_penalty
    if config.llm.presence_penalty is not None:
        llm_params["presence_penalty"] = config.llm.presence_penalty
    if config.llm.frequency_penalty is not None:
        llm_params["frequency_penalty"] = config.llm.frequency_penalty

    # Map the ElevenLabs language_code to a MioTTS-compatible language hint.
    mio_language = _map_language_code(language_code)

    payload: dict = {
        "text": text,
        "reference": {"type": "preset", "preset_id": preset_id},
        "output": {"format": "wav"},
    }
    if llm_params:
        payload["llm"] = llm_params
    # Pass language as a best_of_n hint; miotts_server ignores it gracefully
    # when best_of_n is disabled on the server side.
    payload["best_of_n"] = {"language": mio_language}

    url = f"{config.miotts_base_url}/v1/tts"
    try:
        async with httpx.AsyncClient(timeout=config.miotts_timeout) as client:
            response = await client.post(url, json=payload)
    except httpx.ConnectError as exc:
        logger.error("Cannot connect to miotts_server at %s: %s", config.miotts_base_url, exc)
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "message": f"Cannot connect to miotts_server: {exc}",
            },
        ) from exc
    except httpx.TimeoutException as exc:
        logger.error("Timeout waiting for miotts_server: %s", exc)
        raise HTTPException(
            status_code=504,
            detail={"status": "error", "message": "miotts_server timed out."},
        ) from exc
    except httpx.RequestError as exc:
        logger.error("HTTP error communicating with miotts_server: %s", exc)
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": f"miotts_server request failed: {exc}"},
        ) from exc

    if response.status_code != 200:
        logger.error(
            "miotts_server returned HTTP %d: %s",
            response.status_code,
            response.text[:500],
        )
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "message": f"miotts_server error {response.status_code}: {response.text[:200]}",
            },
        )

    return response.content


def _transcode_wav_to_mp3(wav_bytes: bytes) -> bytes:
    """Transcode WAV audio to MP3 using pydub + ffmpeg.

    Args:
        wav_bytes: Raw WAV audio data.

    Returns:
        MP3-encoded audio bytes.

    Raises:
        HTTPException: HTTP 500 when pydub or ffmpeg are unavailable or fail.
    """
    try:
        from pydub import AudioSegment  # type: ignore[import-untyped]
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": "pydub is not installed. Install it or set PROXY_TRANSCODE_MP3=false.",
            },
        ) from exc

    try:
        segment = AudioSegment.from_wav(io.BytesIO(wav_bytes))
        mp3_buffer = io.BytesIO()
        segment.export(mp3_buffer, format="mp3")
        return mp3_buffer.getvalue()
    except Exception as exc:
        logger.exception("WAV→MP3 transcoding failed")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": f"Transcoding failed: {exc}. Ensure ffmpeg is on PATH.",
            },
        ) from exc


def _build_audio_response(
    wav_bytes: bytes,
    *,
    stream: bool,
    filename: str = "speech",
) -> StreamingResponse:
    """Build a StreamingResponse with WAV or MP3 bytes.

    Args:
        wav_bytes: Raw WAV audio from miotts_server.
        stream: When ``True``, sets headers appropriate for streaming.
        filename: Base filename used in the Content-Disposition header.

    Returns:
        A FastAPI ``StreamingResponse`` with the appropriate media type.
    """
    config = get_config()
    if config.transcode_mp3:
        audio_bytes = _transcode_wav_to_mp3(wav_bytes)
        media_type = "audio/mpeg"
        ext = "mp3"
    else:
        audio_bytes = wav_bytes
        media_type = "audio/wav"
        ext = "wav"

    headers: dict[str, str] = {}
    if not stream:
        headers["Content-Disposition"] = f'attachment; filename="{filename}.{ext}"'

    return StreamingResponse(io.BytesIO(audio_bytes), media_type=media_type, headers=headers)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", summary="Proxy liveness check")
async def health() -> dict[str, str]:
    """Return a simple liveness indicator for the proxy itself."""
    return {"status": "ok"}


@app.get(
    "/v1/voices",
    response_model=VoicesListResponse,
    summary="List available voices",
)
async def list_available_voices(
    xi_api_key: str | None = Header(default=None),
) -> VoicesListResponse:
    """Return all voices available on the upstream miotts_server.

    Fetches the live preset list from ``GET /v1/presets`` on miotts_server
    and merges it with the local voice registry. The result reflects the
    actual state of the server, so newly added presets appear automatically.

    Args:
        xi_api_key: Optional API key header for authentication.

    Returns:
        A ``VoicesListResponse`` containing all available voices.
    """
    _validate_api_key(xi_api_key)

    # Fetch the live preset list from miotts_server.
    server_presets = await _fetch_presets_from_miotts()

    # Merge: start with server presets, supplement with local-only aliases.
    seen: set[str] = set()
    voices: list[VoiceInfo] = []

    for preset_id in server_presets:
        seen.add(preset_id)
        voices.append(VoiceInfo(
            voice_id=preset_id,
            name=preset_id.replace("_", " ").title(),
            category="premade",
        ))

    # Include any local registry entries that are not already in the server list
    # (e.g. custom aliases that map to existing presets under a different name).
    for entry in list_voices():
        if entry["voice_id"] not in seen:
            voices.append(VoiceInfo(
                voice_id=entry["voice_id"],
                name=entry["voice_id"].replace("_", " ").title(),
                category="premade",
            ))

    return VoicesListResponse(voices=voices)


@app.post(
    "/v1/text-to-speech/{voice_id}",
    summary="Synthesise speech (full response)",
    responses={
        200: {"content": {"audio/wav": {}, "audio/mpeg": {}}},
        401: {"model": ErrorDetail},
        404: {"model": ErrorDetail},
        422: {"model": ErrorDetail},
        502: {"model": ErrorDetail},
        504: {"model": ErrorDetail},
    },
)
async def text_to_speech(
    voice_id: str = Path(..., description="ElevenLabs voice identifier."),
    body: TTSRequestBody = ...,
    xi_api_key: str | None = Header(default=None),
) -> StreamingResponse:
    """Synthesise text into speech and return the complete audio file.

    Translates the ElevenLabs request to a MioTTS ``/v1/tts`` call and
    returns the audio as a downloadable attachment.

    Args:
        voice_id: ElevenLabs voice ID, resolved to a MioTTS preset.
        body: ElevenLabs TTS request body.
        xi_api_key: Optional API key header for authentication.

    Returns:
        A ``StreamingResponse`` with audio/wav or audio/mpeg content.
    """
    _validate_api_key(xi_api_key)
    if not body.text or not body.text.strip():
        raise HTTPException(
            status_code=422,
            detail={"status": "error", "message": "text must not be empty."},
        )
    preset_id = await _resolve_voice_or_404(voice_id)
    logger.info(
        "TTS request: voice_id=%r → preset_id=%r text_len=%d",
        voice_id,
        preset_id,
        len(body.text),
    )
    wav_bytes = await _fetch_wav_from_miotts(body.text, preset_id, language_code=body.language_code)
    return _build_audio_response(wav_bytes, stream=False)


@app.post(
    "/v1/text-to-speech/{voice_id}/stream",
    summary="Synthesise speech (streaming response)",
    responses={
        200: {"content": {"audio/wav": {}, "audio/mpeg": {}}},
        401: {"model": ErrorDetail},
        404: {"model": ErrorDetail},
        422: {"model": ErrorDetail},
        502: {"model": ErrorDetail},
        504: {"model": ErrorDetail},
    },
)
async def text_to_speech_stream(
    voice_id: str = Path(..., description="ElevenLabs voice identifier."),
    body: TTSRequestBody = ...,
    xi_api_key: str | None = Header(default=None),
) -> StreamingResponse:
    """Synthesise text into speech and stream the audio back to the client.

    Functionally identical to ``text_to_speech`` but sets headers appropriate
    for streaming playback rather than file download.

    Args:
        voice_id: ElevenLabs voice ID, resolved to a MioTTS preset.
        body: ElevenLabs TTS request body.
        xi_api_key: Optional API key header for authentication.

    Returns:
        A ``StreamingResponse`` with audio/wav or audio/mpeg content.
    """
    _validate_api_key(xi_api_key)
    if not body.text or not body.text.strip():
        raise HTTPException(
            status_code=422,
            detail={"status": "error", "message": "text must not be empty."},
        )
    preset_id = await _resolve_voice_or_404(voice_id)
    logger.info(
        "TTS stream request: voice_id=%r → preset_id=%r text_len=%d",
        voice_id,
        preset_id,
        len(body.text),
    )
    wav_bytes = await _fetch_wav_from_miotts(body.text, preset_id, language_code=body.language_code)
    # miotts_server produces the full audio synchronously, so we stream it
    # as a single chunk. True chunk-by-chunk streaming would require changes
    # in miotts_server itself.
    return _build_audio_response(wav_bytes, stream=True)
