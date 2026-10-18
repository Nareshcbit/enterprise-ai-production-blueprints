# Build stage: install dependencies into an isolated virtualenv and download
# the embedding model, so tasks never fetch it at startup.
FROM python:3.12-slim AS build
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
ENV FASTEMBED_CACHE_PATH=/opt/models
RUN /opt/venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

# Runtime stage: copy only the virtualenv, the model and the app, run as non-root.
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 router
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/models /opt/models
WORKDIR /app
COPY litellm_config.yaml .
COPY plugins/ plugins/
COPY prompts/ prompts/
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/opt/models \
    HF_HUB_OFFLINE=1
USER router
EXPOSE 4000
CMD ["litellm", "--config", "/app/litellm_config.yaml", "--port", "4000", "--host", "0.0.0.0"]
