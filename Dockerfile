FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching.
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "anthropic>=0.40" \
    "elevenlabs>=1.0" \
    "fastapi>=0.110" \
    "uvicorn[standard]>=0.29" \
    "requests>=2.31" \
    "rapidfuzz>=3.6" \
    "pydantic>=2.6" \
    "pydantic-settings>=2.2" \
    "pylast>=5.3"

COPY app ./app

ENV DATA_DIR=/data APP_PORT=8099
EXPOSE 8099

# Healthcheck uses stdlib (no curl in slim image) so deploy-nas.sh can poll
# the container's Docker health status — same readiness signal pattern as shoppr.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8099/healthz')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099"]
