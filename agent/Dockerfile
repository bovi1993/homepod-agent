FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Stage 1: install system dependencies.
# (Split into a separate stage so the runtime image stays slim.)
FROM python:3.11-slim AS base

WORKDIR /app

# Install the project package and its runtime deps.
# We deliberately use non-editable install (`pip install .`) rather than `pip install -e .`
# so the package lives in site-packages and isn't tied to /app at runtime.
COPY pyproject.toml README.md ./
COPY agent ./agent
RUN python -m pip install --no-cache-dir .

EXPOSE 8000 8001 8765 51827

# Default to running the LLM agent; user can override with docker-compose.
CMD ["python", "-m", "uvicorn", "llm.main:app", "--host", "0.0.0.0", "--port", "8000"]