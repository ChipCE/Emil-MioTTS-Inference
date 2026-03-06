# ElevenLabs-Compatible TTS Proxy (`elevenlab_endpoint`)

A lightweight Python/FastAPI middleware that exposes the **ElevenLabs v1 TTS REST API** surface and relays every request to the locally-running **MioTTS server** (`miotts_server`). Any client that supports ElevenLabs (Home Assistant Talk mode, the `elevenlabs` Python SDK, etc.) works without modification.

---

## Architecture

```
ElevenLabs client
        │  POST /v1/text-to-speech/{voice_id}
        ▼
elevenlab_endpoint  (this proxy · default port 8002)
        │  voice_id ──► preset_id  (voice_registry)
        │  language_code ──► best_of_n.language
        │  LLM params ──► config.json / env vars
        │  POST /v1/tts
        ▼
miotts_server  (default port 8001)
        │  returns WAV
        ▼
elevenlab_endpoint  ──► optional WAV→MP3 transcode ──► client
```

---

## Quick Start

> [!IMPORTANT]
> All commands must be run from the **project root** (`c:\Data\Code\Emil-MioTTS-Inference`), not from inside `elevenlab_endpoint/`. Python needs to see the `elevenlab_endpoint/` folder as a package in the current directory.

```bash
# Navigate to project root first
cd c:\Data\Code\Emil-MioTTS-Inference

# 1. Make sure miotts_server is already running on port 8001
python run_server.py --port 8001

# 2. Edit elevenlab_endpoint/config.json  (optional)

# 3. Start the proxy (default port 8002) — either form works
python -m elevenlab_endpoint.run_proxy
# or
python elevenlab_endpoint/run_proxy.py
```

---

## Configuration

Settings are merged in this priority order (highest wins):

```
Environment variable  >  config.json  >  built-in default
```

### `config.json`

Located at `elevenlab_endpoint/config.json` by default. Override the path with the `PROXY_CONFIG_FILE` environment variable.

```json
{
  "host": "0.0.0.0",
  "port": 8002,
  "miotts_base_url": "http://localhost:8001",
  "miotts_timeout": 60,
  "api_key": "",
  "transcode_mp3": false,
  "llm": {
    "temperature": null,
    "top_p": null,
    "max_tokens": null,
    "repetition_penalty": null,
    "presence_penalty": null,
    "frequency_penalty": null
  }
}
```

> Set any `llm` field to `null` to use miotts_server's own defaults for that parameter.

### Environment Variables

Every setting can also be overridden with an env var (takes precedence over `config.json`):

| Environment Variable | `config.json` key | Default | Description |
|---|---|---|---|
| `PROXY_CONFIG_FILE` | — | `elevenlab_endpoint/config.json` | Path to the JSON config file |
| `PROXY_HOST` | `host` | `0.0.0.0` | Bind address |
| `PROXY_PORT` | `port` | `8002` | Listen port |
| `MIOTTS_BASE_URL` | `miotts_base_url` | `http://localhost:8001` | Upstream miotts_server URL |
| `PROXY_MIOTTS_TIMEOUT` | `miotts_timeout` | `60` | HTTP timeout (seconds) |
| `PROXY_API_KEY` | `api_key` | *(empty)* | Validates `xi-api-key` header. Leave empty for open access. |
| `PROXY_TRANSCODE_MP3` | `transcode_mp3` | `false` | Transcode WAV→MP3 (requires `ffmpeg`) |
| `PROXY_LOG_LEVEL` | — | `info` | Log level (`debug`, `info`, `warning`, `error`) |
| `PROXY_LLM_TEMPERATURE` | `llm.temperature` | `null` | LLM sampling temperature (0.0–2.0) |
| `PROXY_LLM_TOP_P` | `llm.top_p` | `null` | Top-p nucleus sampling (0.0–1.0) |
| `PROXY_LLM_MAX_TOKENS` | `llm.max_tokens` | `null` | Max tokens to generate |
| `PROXY_LLM_REPETITION_PENALTY` | `llm.repetition_penalty` | `null` | Repetition penalty (1.0–1.5) |
| `PROXY_LLM_PRESENCE_PENALTY` | `llm.presence_penalty` | `null` | Presence penalty (0.0–1.0) |
| `PROXY_LLM_FREQUENCY_PENALTY` | `llm.frequency_penalty` | `null` | Frequency penalty (0.0–1.0) |

---

## API Reference

### `GET /health`

Proxy liveness check.

**Response `200 OK`**
```json
{ "status": "ok" }
```

---

### `GET /v1/voices`

Returns all voices registered in the voice registry.

**Headers (optional)**

| Header | Description |
|---|---|
| `xi-api-key` | Required only when `PROXY_API_KEY` / `api_key` is set |

**Response `200 OK`**
```json
{
  "voices": [
    { "voice_id": "jp_female", "name": "Jp Female", "category": "premade" },
    { "voice_id": "jp_male",   "name": "Jp Male",   "category": "premade" },
    { "voice_id": "en_female", "name": "En Female", "category": "premade" },
    { "voice_id": "en_male",   "name": "En Male",   "category": "premade" }
  ]
}
```

---

### `POST /v1/text-to-speech/{voice_id}`

Synthesise text to speech and return the complete audio file as a download attachment.

**Path Parameters**

| Parameter | Type | Description |
|---|---|---|
| `voice_id` | `string` | ElevenLabs voice identifier. Must exist in the voice registry. |

**Headers**

| Header | Required | Description |
|---|---|---|
| `Content-Type` | Yes | `application/json` |
| `xi-api-key` | Conditional | Required when `api_key` is configured |

**Request Body**

```json
{
  "text": "こんにちは、世界！",
  "model_id": "miotts",
  "language_code": "ja",
  "voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.75
  }
}
```

| Field | Type | Required | Forwarded to miotts | Description |
|---|---|---|---|---|
| `text` | `string` | **Yes** | ✅ | Text to synthesise |
| `model_id` | `string` | No | ❌ | Accepted for compatibility; ignored |
| `language_code` | `string` | No | ✅ | IETF tag (`"ja"`, `"ja-JP"`, `"en-US"`, …). Mapped to miotts `best_of_n.language` |
| `voice_settings` | `object` | No | ❌ | Accepted for compatibility; ignored |
| `output_format` | `string` | No | ❌ | Use `transcode_mp3` config instead |
| `optimize_streaming_latency` | `int` | No | ❌ | Accepted for compatibility; ignored |

#### Language Code Mapping

| ElevenLabs `language_code` | MioTTS `best_of_n.language` |
|---|---|
| `"ja"`, `"ja-JP"`, `"ja-*"` | `"ja"` |
| `"en"`, `"en-US"`, `"en-*"` | `"en"` |
| anything else / omitted | `"auto"` |

**Response `200 OK`**

Raw audio bytes:
- `Content-Type: audio/wav` — when `transcode_mp3` is `false`
- `Content-Type: audio/mpeg` — when `transcode_mp3` is `true`

**Error Responses**

| Status | Condition |
|---|---|
| `401 Unauthorized` | `xi-api-key` header wrong or missing while `api_key` is configured |
| `404 Not Found` | `voice_id` is not in the voice registry |
| `422 Unprocessable Entity` | `text` is empty |
| `502 Bad Gateway` | miotts_server returned an error or is unreachable |
| `504 Gateway Timeout` | miotts_server did not respond within `miotts_timeout` seconds |

---

### `POST /v1/text-to-speech/{voice_id}/stream`

Identical to the endpoint above but returns the audio as an inline stream (no `Content-Disposition: attachment` header), suitable for clients that play audio directly.

> **Note:** miotts_server generates audio synchronously, so both endpoints return the full audio in a single chunk. True incremental streaming would require changes in miotts_server.

---

## Voice Registry

Built-in voice entries map directly to the preset files in the `presets/` directory:

| `voice_id` | MioTTS preset | Notes |
|---|---|---|
| `jp_female` | `jp_female` | Japanese female |
| `jp_male` | `jp_male` | Japanese male |
| `en_female` | `en_female` | English female |
| `en_male` | `en_male` | English male |

**Unknown `voice_id` → HTTP 404.**

Custom mappings can be added at runtime via `voice_registry.register_voice()`.

---

## Audio Output

| `transcode_mp3` | `Content-Type` | Requirement |
|---|---|---|
| `false` *(default)* | `audio/wav` | — |
| `true` | `audio/mpeg` | `ffmpeg` on system PATH |

```bash
# Install ffmpeg (Windows)
winget install ffmpeg
```

---

## Example curl Commands

```bash
# List voices
curl http://localhost:8002/v1/voices

# Japanese TTS → WAV
curl -X POST http://localhost:8002/v1/text-to-speech/jp_female \
  -H "Content-Type: application/json" \
  -d '{"text": "こんにちは、世界！", "language_code": "ja"}' \
  --output speech.wav

# English TTS (streaming endpoint)
curl -X POST http://localhost:8002/v1/text-to-speech/en_female/stream \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, world!", "language_code": "en"}' \
  --output speech.wav

# With API key
curl -X POST http://localhost:8002/v1/text-to-speech/jp_male \
  -H "Content-Type: application/json" \
  -H "xi-api-key: my-secret-key" \
  -d '{"text": "テスト", "language_code": "ja-JP"}' \
  --output speech.wav

# Unknown voice → HTTP 404
curl -X POST http://localhost:8002/v1/text-to-speech/unknown_voice \
  -H "Content-Type: application/json" \
  -d '{"text": "test"}' -v
```

---

## File Structure

```
elevenlab_endpoint/
├── __init__.py          # Package marker
├── api.py               # FastAPI app — routes, language mapping, request forwarding
├── config.py            # Three-tier config loader (env > config.json > defaults)
├── config.json          # User-editable config file
├── schemas.py           # Pydantic models (ElevenLabs-compatible request/response)
├── voice_registry.py    # voice_id → preset_id mapping registry
├── run_proxy.py         # Entry point (CLI + uvicorn launcher)
└── tests/
    ├── __init__.py
    ├── test_voice_registry.py
    └── test_schemas.py
```

---

## Interactive API Docs (auto-generated by FastAPI)

| URL | Description |
|---|---|
| http://localhost:8002/docs | Swagger UI |
| http://localhost:8002/redoc | ReDoc |
| http://localhost:8002/openapi.json | Raw OpenAPI schema |
