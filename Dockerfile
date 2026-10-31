FROM python:3.13-slim-bookworm
COPY --from=denoland/deno:bin-2.9.8 /deno /usr/local/bin/deno

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FFMPEG_LOCATION=/usr/bin/ffmpeg
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appuser app.py calendario.py descargador.py ./
COPY --chown=appuser:appuser templates ./templates
COPY --chown=appuser:appuser static ./static
RUN mkdir -p descarga && chown appuser:appuser /app /app/descarga
USER appuser
EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 2 --timeout 900 --access-logfile - --error-logfile - app:app"]
