# ─────────────────────────────────────────────────────────────────────────────
# Base: CUDA 12.4 + cuDNN + Ubuntu 22.04
# Matches recent PyTorch / flash-attn requirements.
# Using the "runtime" image; change to "devel" only if you need to compile
# CUDA extensions inside the container (flash-attn is compiled on first run
# via its own wheel, so "runtime" is sufficient).
# ─────────────────────────────────────────────────────────────────────────────
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

# ── System packages ───────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python build deps
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    # Build tools needed for pyopenjtalk / ninja / etc.
    build-essential \
    cmake \
    git \
    curl \
    # Audio libraries required by soundfile / pyopenjtalk
    libsndfile1 \
    libportaudio2 \
    # Misc
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Make python3.12 the default "python" / "python3"
RUN update-alternatives --install /usr/bin/python  python  /usr/bin/python3.12 1 \
 && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# ── uv (fast Python package manager) ─────────────────────────────────────────
# Pin the version so builds stay reproducible.
ENV UV_VERSION=0.6.2
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies via uv ───────────────────────────────────────
# Copy lock file and project metadata first for better layer caching.
COPY pyproject.toml uv.lock ./

# Sync dependencies from lock file (no editable install yet).
# --no-install-project: installs deps only, not the project package itself.
RUN uv sync --frozen --no-install-project

# ── Copy application source ───────────────────────────────────────────────────
COPY miotts_server/ ./miotts_server/
COPY run_server.py run_gradio.py ./
COPY scripts/ ./scripts/

# Copy default presets (can be overridden by a host volume at runtime).
COPY presets/ ./presets/

# ── Runtime environment defaults ──────────────────────────────────────────────
# These can all be overridden in docker-compose or at `docker run` time.
ENV PYTHONUNBUFFERED=1 \
    MIOTTS_HOST=0.0.0.0 \
    MIOTTS_PORT=8001 \
    MIOTTS_DEVICE=cuda \
    MIOTTS_PRESETS_DIR=/app/presets

# Expose the API port
EXPOSE 8001

# ── Entrypoint ────────────────────────────────────────────────────────────────
# ENTRYPOINT activates the venv; CMD picks which script to run.
# docker-compose services can override CMD to switch between
# run_server.py (default) and run_gradio.py.
ENTRYPOINT ["uv", "run", "python"]
CMD ["run_server.py"]
