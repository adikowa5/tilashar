# Образ бэкенда Тілашар. Запуск от непривилегированного пользователя.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MEDIA_ROOT=/data/media

WORKDIR /srv/app

# Сначала зависимости и код пакета — так слой с pip install кешируется
# между сборками, пока не менялся pyproject.toml.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

COPY alembic.ini ./
COPY alembic ./alembic

# Непривилегированный пользователь и каталог для родительских записей голоса.
RUN useradd --create-home --uid 10001 tilashar \
    && mkdir -p /data/media \
    && chown -R tilashar:tilashar /data /srv/app

USER tilashar

EXPOSE 8000

# Миграции накатываются отдельной командой (см. README), контейнер только обслуживает API.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
