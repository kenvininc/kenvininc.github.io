FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN chmod +x /app/deploy/entrypoint.sh

ENV STATIC_ROOT=/app/staticfiles MEDIA_ROOT=/app/media
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
