FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 clipforge \
    && useradd --uid 10001 --gid clipforge --create-home --shell /usr/sbin/nologin clipforge \
    && mkdir -p /var/lib/clipforge/media /var/lib/clipforge/outputs /var/lib/clipforge/models \
    && chown -R clipforge:clipforge /var/lib/clipforge \
    && chmod 0700 /var/lib/clipforge /var/lib/clipforge/media /var/lib/clipforge/outputs /var/lib/clipforge/models

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY --chown=clipforge:clipforge app ./app
COPY --chown=clipforge:clipforge alembic ./alembic
COPY --chown=clipforge:clipforge alembic.ini ./alembic.ini

USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "app.server"]
