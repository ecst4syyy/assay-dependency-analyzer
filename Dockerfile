FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FLASK_APP=app:create_app

WORKDIR /srv/assay

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 10001 assay
COPY --chown=assay:assay app ./app
COPY --chown=assay:assay migrations ./migrations
COPY --chown=assay:assay data ./data
COPY --chown=assay:assay docker/entrypoint.sh ./entrypoint.sh
RUN mkdir -p instance && chown assay:assay instance

USER assay
EXPOSE 5000
ENTRYPOINT ["./entrypoint.sh"]
