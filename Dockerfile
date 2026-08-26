FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime libs Pillow's wheel needs for JPEG support.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DEBUG defaults True and SECRET_KEY has a dev fallback at import time, so
# this runs fine at build time with no TESTGEN_* env vars set.
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Invoked via `sh` rather than executed directly, so the file's exec bit
# (unreliable coming from a Windows checkout) doesn't matter.
CMD ["sh", "deploy/entrypoint.sh"]
