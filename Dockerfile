FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# uid 1000 matches the default `ubuntu` user on EC2, so the bind-mounted
# media folder is writable by the container and readable by Nginx.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Static files are baked into the image and served by WhiteNoise. The dummy
# key only exists for this build step; the real one comes from .env at runtime.
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && mkdir -p /app/media /app/logs \
    && chown -R app:app /app/media /app/logs

USER app
EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--worker-class", "gthread", "--workers", "2", "--threads", "4", \
     "--timeout", "30", \
     "--access-logfile", "-", "--error-logfile", "-"]
