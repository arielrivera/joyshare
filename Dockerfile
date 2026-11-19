FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JOYSHARE_DATA=/data

# ffmpeg does the converting (DejaVu is the font of the optional visible credit). deno lets yt-dlp solve YouTube's JavaScript challenges.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data /srv \
    && chown app:app /data /srv

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app app app
COPY --chown=app:app web web
COPY --chown=app:app tests tests

USER app
VOLUME /data
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
