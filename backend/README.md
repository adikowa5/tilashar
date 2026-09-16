# Tilashar backend

Бэкенд приложения **Тілашар** — изучение казахских слов детьми 6–9 лет.
FastAPI + SQLAlchemy 2.0 (синхронный) + Alembic + Postgres (SQLite в тестах).

Контракт API: [`../docs/api.md`](../docs/api.md). Базовый путь — `/api/v1`.

## Быстрый старт

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export DATABASE_URL="postgresql+psycopg://tilashar:tilashar@localhost:5432/tilashar"
export JWT_SECRET="сменить-в-проде"

alembic upgrade head                      # схема
python -m app.seed ../../tilashar/words.js  # встроенный контент
uvicorn app.main:app --reload
```

Документация Swagger — `http://localhost:8000/docs`, проверка живости — `GET /health`.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://tilashar:tilashar@localhost:5432/tilashar` | Подключение к БД. В тестах — `sqlite://` |
| `JWT_SECRET` | `dev-secret-change-me` | Подпись JWT и HMAC-хеш SMS-кодов. **Обязательно менять в проде**, длина от 32 байт |
| `ACCESS_TTL_MIN` | `30` | Время жизни access-токена, минуты |
| `REFRESH_TTL_DAYS` | `30` | Время жизни refresh-токена, дни |
| `SMS_PROVIDER` | `console` | `console` — код в лог и в `dev_code`; `mobizon` — реальная отправка |
| `MOBIZON_API_KEY` | пусто | Ключ Mobizon, нужен только при `SMS_PROVIDER=mobizon` |
| `MEDIA_ROOT` | `/data/media` | Каталог родительских записей, отдаётся по `/media/...` |
| `MAX_CHILDREN` | `4` | Лимит активных детей в семье |
| `CORS_ORIGINS` | `*` | Список источников через запятую либо `*` |

Дополнительно (есть значения по умолчанию, обычно менять не нужно):
`CODE_TTL_SEC=300`, `CODE_RETRY_AFTER_SEC=60`, `CODE_REQUESTS_PER_HOUR=5`,
`CODE_MAX_ATTEMPTS=5`, `LESSON_SIZE=8`, `MAX_VOICE_BYTES=2097152`,
`JWT_ALGORITHM=HS256`, `MOBIZON_BASE_URL=https://api.mobizon.kz`.

Настройки читаются и из файла `.env` в каталоге запуска.

## Миграции

```bash
alembic upgrade head            # накатить
alembic downgrade -1            # откатить один шаг
alembic revision -m "описание"  # новая ревизия (правится руками)
alembic revision --autogenerate -m "описание"  # черновик по моделям
```

URL берётся из `DATABASE_URL`: в `alembic.ini` он намеренно пустой.
Стартовая ревизия — `alembic/versions/0001_initial.py`, написана вручную и
использует только портируемые типы (`String`, `Integer`, `Boolean`, `DateTime`,
`Date`, `Text`), чтобы одинаково ложиться на Postgres и SQLite. UUID хранятся
строками длиной 36.

## Сидинг контента

Источник — `words.js` фронтенда (`window.TILASHAR_TOPICS=[...]`, каждое слово —
массив `[текст, картинка/цвет/цифра, слоги]`). Русские переводы и русские
названия тем лежат словарями в `app/seed.py`.

```bash
python -m app.seed                 # ищет words.js в нескольких типичных местах
python -m app.seed /путь/words.js  # явный путь
SEED_WORDS_JS=/путь/words.js python -m app.seed
```

Операция идемпотентна: повторный запуск обновляет темы и слова по `slug`
и `text_kk`, а слова, исчезнувшие из `words.js`, удаляет.
Темы: `animals`, `fruits`, `colors`, `numbers`, `home`, `nature` — 50 слов.

## Тесты

```bash
pytest -q
```

Тесты идут на SQLite в памяти (`StaticPool`), схема поднимается через
`Base.metadata.create_all` — alembic в тестах не участвует. Внешних сервисов не
требуется: SMS-отправитель в тестах консольный, код всегда `000000`.

## Docker

```bash
docker build -t tilashar-backend .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL="postgresql+psycopg://tilashar:tilashar@host.docker.internal:5432/tilashar" \
  -e JWT_SECRET="..." \
  -v tilashar-media:/data/media \
  tilashar-backend
```

Миграции накатываются отдельной командой:
`docker run --rm -e DATABASE_URL=... tilashar-backend alembic upgrade head`.

## Как всё устроено

```
app/
  main.py      сборка FastAPI, CORS, /health, /api/v1/config, статика /media
  config.py    настройки из окружения (pydantic-settings)
  db.py        движок, фабрика сессий, Base
  models.py    ORM-модели
  schemas.py   Pydantic-схемы запросов и ответов
  security.py  HMAC-хеш кода, выпуск и проверка JWT, ротация refresh
  deps.py      get_db, current_user, current_family, owned_child + хелперы
  sms.py       SmsSender: ConsoleSender и MobizonSender
  streaks.py   чистый расчёт серии по датам
  seed.py      разбор words.js и наполнение БД
  routers/     auth, me, children, content, lesson, voice
```

Ключевые правила:

* **Серия.** Считается по дням, в которые ребёнок закрыл урок. Пропуск одного
  дня замораживает серию, два подряд — обнуляют. Логика в `app/streaks.py`
  и не зависит от БД.
* **Урок дня.** До 8 слов: сначала новые слова первой незакрытой темы (тема
  закрыта, когда все её слова набрали ≥ 2 звёзд), затем повторы слов с 0–1
  звездой. Состав фиксируется при первом обращении к `/today` и хранится в
  `lesson_days.plan`, поэтому в течение дня не меняется. Выбор повторов
  детерминирован: ГПСЧ засевается `child_id` и датой.
* **Даты.** «День» везде считается по UTC — и `day` попытки, и «сегодня» урока.
* **Чужой ребёнок** всегда даёт `404`, а не `403`.
* **Голос ребёнка** на сервер не попадает: приходят только звёзды и
  распознанный браузером текст.
