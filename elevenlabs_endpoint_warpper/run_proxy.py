"""Entry point for the ElevenLabs-compatible TTS proxy server.

Can be run from the project root or directly from inside elevenlab_endpoint/:

    # From project root:
    python -m elevenlab_endpoint.run_proxy
    python elevenlab_endpoint/run_proxy.py

    # From inside elevenlab_endpoint/:
    python run_proxy.py

Environment variables (all optional):
    PROXY_HOST              Bind address (default: 0.0.0.0)
    PROXY_PORT              Listen port  (default: 8002)
    MIOTTS_BASE_URL         Upstream miotts_server URL (default: http://localhost:8001)
    PROXY_API_KEY           xi-api-key to validate; empty = no auth
    PROXY_TRANSCODE_MP3     Set to 'true' to enable WAV→MP3 transcoding (requires ffmpeg)
    PROXY_MIOTTS_TIMEOUT    HTTP timeout in seconds for miotts_server calls (default: 60)
    PROXY_LOG_LEVEL         Logging level (default: info)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root (parent of this file's directory) is on sys.path so
# that `elevenlab_endpoint` is importable regardless of the working directory.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


import argparse
import logging
import os


_UNSET = object()  # Sentinel to detect args not explicitly provided on CLI.


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ElevenLabs-compatible TTS proxy server")
    parser.add_argument(
        "--host",
        default=_UNSET,
        help="Host to bind. Overrides config.json 'host' and PROXY_HOST env var.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_UNSET,
        help="Port to listen on. Overrides config.json 'port' and PROXY_PORT env var.",
    )
    parser.add_argument(
        "--miotts-url",
        default=_UNSET,
        help="miotts_server base URL. Overrides config.json 'miotts_base_url' and MIOTTS_BASE_URL env var.",
    )
    parser.add_argument(
        "--log-level",
        default=_UNSET,
        help="Log level: debug, info, warning, error. Overrides PROXY_LOG_LEVEL env var.",
    )
    parser.add_argument(
        "--transcode-mp3",
        action="store_true",
        default=_UNSET,
        help="Enable WAV→MP3 transcoding (requires ffmpeg on PATH). Overrides config.json 'transcode_mp3'.",
    )
    return parser.parse_args()


def _set_env_if_provided(name: str, value: object, transform=str) -> None:
    """Write *value* to os.environ[name] only when it was explicitly provided.

    Args:
        name: Environment variable name.
        value: Parsed CLI value or _UNSET sentinel.
        transform: Callable to convert value to a string (default: str).
    """
    if value is not _UNSET:
        if isinstance(value, bool):
            os.environ[name] = "true" if value else "false"
        else:
            os.environ[name] = transform(value)


def main() -> None:
    """Parse CLI arguments, push explicit flags to env, then start uvicorn.

    Config priority (highest first):
      explicit CLI flag > environment variable > config.json > built-in default
    """
    args = _parse_args()

    # Determine log level: CLI > env > default
    log_level: str = (
        args.log_level if args.log_level is not _UNSET
        else os.getenv("PROXY_LOG_LEVEL", "info")
    )
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Only push explicitly-provided CLI values into the environment so that
    # config.json values are NOT silently overridden by argparse defaults.
    _set_env_if_provided("PROXY_HOST", args.host)
    _set_env_if_provided("PROXY_PORT", args.port)
    _set_env_if_provided("MIOTTS_BASE_URL", args.miotts_url)
    _set_env_if_provided("PROXY_TRANSCODE_MP3", args.transcode_mp3)

    import uvicorn

    from elevenlabs_endpoint_warpper.config import get_config
    from elevenlabs_endpoint_warpper.api import app

    # Log the effective config so the user can verify the settings being used.
    cfg = get_config()
    logger = logging.getLogger(__name__)
    logger.info("Proxy config: host=%s port=%d miotts_base_url=%s transcode_mp3=%s",
                cfg.host, cfg.port, cfg.miotts_base_url, cfg.transcode_mp3)

    uvicorn.run(
        app,
        host=cfg.host,
        port=cfg.port,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    main()
