# Tilashar API v1 — контракт

Базовый путь: `/api/v1`. Формат — JSON, UTF-8. Все идентификаторы — UUID-строки.
Ошибки: `{"detail": "<code>"}` + HTTP-код. Коды ошибок ниже перечислены явно.

## Вход без регистрации

Семья не регистрируется. Первое устройство создаёт семью (`/auth/guest`), остальные подключаются
по коду семьи (`/auth/join`). Телефонов, почты и паролей у семей нет.

JWT: access (30 мин) и refresh (400 дней, продлевается при каждом обновлении) в теле ответа.
Заголовок: `Authorization: Bearer <access>`.

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| POST | `/auth/guest` | — | `TokenPair` — новая семья на этом устройстве |
| POST | `/auth/join` | `{"code": "ABCD-2345"}` | `TokenPair` — устройство в существующей семье |
| GET | `/family/code` | — | `{"code": "ABCD-2345"}` — создаётся при первом запросе |
| POST | `/family/code` | — | `{"code": "..."}` — новый код, старый перестаёт работать |
| POST | `/auth/refresh` | `{"refresh_token": "..."}` | `TokenPair` |
| POST | `/auth/logout` | `{"refresh_token": "..."}` | `204` |

`TokenPair` = `{"access_token": str, "refresh_token": str, "token_type": "bearer", "expires_in": 1800}`

Код семьи — 8 символов без похожих (`0/O`, `1/I/L`); регистр, пробелы и дефис при вводе не важны.
Ссылка-приглашение: `https://<сайт>/?join=<код>`.

Ограничения на IP: `GUEST_PER_HOUR` (20) новых семей в час, `JOIN_ATTEMPTS_PER_HOUR` (12) неверных кодов в час.
Коды ошибок: `code_invalid` (404), `too_many_attempts` (429), `token_invalid` (401).

## Я и семья

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/me` | `{"user": {...}, "family": {...}, "children": [Child]}` |
| PATCH | `/me` | `{"locale": "ru"}` → user |
| PATCH | `/family` | `{"model_voice": true}` → family |

`Family` = `{"id", "is_guest": bool, "model_voice": bool, "created_at"}`

## Дети

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/children` | — | `[Child]` |
| POST | `/children` | `{"name", "age": 7, "avatar": "fox", "locale": "kk"}` | `Child` (201) |
| PATCH | `/children/{id}` | любое подмножество полей | `Child` |
| DELETE | `/children/{id}` | — | `204` (мягкое удаление) |

`Child` = `{"id", "name", "age", "avatar", "locale", "stars_total", "streak", "created_at"}`
Возраст 6–9; вне диапазона — `age_out_of_range`. Максимум 4 активных ребёнка — `too_many_children`.

## Контент

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/content/catalog` | весь опубликованный материал одним ответом, **без токена**; `ETag` = версия |
| GET | `/media/{sha256}.{ext}` | файл (голос или картинка), без токена, кешируется навсегда |
| GET | `/content/topics`, `/content/topics/{slug}` | старый формат по темам (оставлен для совместимости) |

```
Catalog = {"version", "topics": [CTopic], "phrases": [CPhrase]}
CTopic  = {"id","slug","title_kk","title_ru","pic","image_url","is_published","order_index","words":[CWord]}
CWord   = {"id","text_kk","text_ru","syllables","pic","image_url","audio_url","model_audio_url"}
CPhrase = {"key","text_kk","text_ru","audio_url","model_audio_url"}
```

Какой голос звучит: для слова — `audio_url` (автор), иначе `model_audio_url` (модель), иначе синтез браузера.
Для фразы похвалы — запись семьи (`/voices`), иначе автор, иначе модель.
`pic` — эмодзи, цвет `#RRGGBB` или цифра; показывается, если нет `image_url`.

## Редактор автора

Вход по паролю `ADMIN_PASSWORD`. Токен автора — в заголовке `X-Admin-Token`, живёт `ADMIN_TTL_HOURS` (12).
Смена пароля делает старые токены недействительными. Пустой `ADMIN_PASSWORD` → `503 admin_disabled`.

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| POST | `/admin/login` | `{"password"}` | `{"token","expires_in"}`; 10 неверных попыток в час с IP |
| GET | `/admin/catalog` | — | `Catalog` вместе с неопубликованным |
| GET | `/admin/stats` | — | семьи, активные за 7 дней, дети, попытки, слова с голосом, объём файлов |
| POST | `/admin/topics` | `{"title_kk","title_ru","pic","is_published"}` | `CTopic` (по умолчанию черновик) |
| PATCH | `/admin/topics/{id}` | любые из полей выше | `CTopic` |
| DELETE | `/admin/topics/{id}` | — | `204` (слова и прогресс по ним удаляются) |
| POST | `/admin/topics/order` | `{"ids": [...]}` | `Catalog` |
| PUT / DELETE | `/admin/topics/{id}/image` | multipart `file` | `CTopic` |
| POST | `/admin/topics/{id}/words` | `{"text_kk","text_ru","syllables","pic"}` | `CWord` |
| POST | `/admin/topics/{id}/words/bulk` | `{"words": [...]}` (до 200, дубли пропускаются) | `CTopic` |
| POST | `/admin/topics/{id}/words/order` | `{"ids": [...]}` | `CTopic` |
| PATCH | `/admin/words/{id}` | поля слова, `topic_id` — перенос в другую категорию | `CWord` |
| DELETE | `/admin/words/{id}` | — | `204` |
| PUT / DELETE | `/admin/words/{id}/audio` | multipart `file` (WAV ≤ 2 МБ) | `CWord` |
| PUT / DELETE | `/admin/words/{id}/image` | multipart `file` (PNG/JPG/WebP/GIF ≤ 1 МБ; SVG нельзя) | `CWord` |
| PATCH | `/admin/phrases/{key}` | `{"text_kk","text_ru"}` | `CPhrase` |
| PUT / DELETE | `/admin/phrases/{key}/audio` | multipart `file` | `CPhrase` |

Тип файла проверяется по содержимому, а не по заголовку. Одинаковые файлы хранятся один раз.

## Урок дня

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/children/{id}/today` | `{"date","streak","done","total","items":[TodayItem]}` |
| POST | `/children/{id}/attempts` | массив попыток → `{"stars_total","streak","day_done": bool}` |
| GET | `/children/{id}/progress` | `{"<word_id>": {"stars": 3, "attempts": 5}}` |

`TodayItem` = `{"kind":"word","word_id","topic_slug","status":"new"|"review"|"done"}`
Состав дня на этапе 1: до 8 слов — новые слова текущей темы плюс слова с 0–1 звездой на повтор.

`Attempt` (в массиве) = `{"word_id","stars":0..3,"heard": str|null,"mode":"asr"|"manual","at": ISO-8601}`
Массив до 50 элементов, идемпотентен по `(child_id, word_id, at)`.

Серия (`streak`): считается по дням, в которых ребёнок закрыл хотя бы один урок; пропуск одного дня серию не обнуляет («заморозка»), два подряд — обнуляет.

## Похвала голосом родителя

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/voices` | — | `[{"key","url","duration_ms","updated_at"}]` |
| PUT | `/voices` | multipart: `key`, `file` (WAV, ≤2 МБ) | запись |
| DELETE | `/voices/{key}` | — | `204` |

Ключ — только фраза похвалы: `^p:[a-z_]{1,32}$` (`p:great`, `p:good` …). Слова уроков озвучивает автор.
Файл лежит в БД и отдаётся по `/api/v1/voices/audio/<sha256>.wav` без токена.

## Прочее

`GET /health` → `{"status":"ok","db":"ok"}`; при ошибке базы — ещё `reason` (без логина и пароля).
`GET /api/v1/config` → `{"max_children","version"}`.
`GET /api/v1/internal/cleanup` — ежедневная уборка, только с заголовком `Authorization: Bearer <CRON_SECRET>`.

## Правила авторизации и хранения

* Любой `/children/{id}/...` проверяет, что ребёнок принадлежит семье вызывающего — иначе `404` (не `403`, чтобы не раскрывать существование).
* Личных данных родителя нет. О ребёнке — имя (можно прозвище), возраст, аватар.
* Уборка удаляет семьи без единой попытки через `INACTIVE_EMPTY_DAYS` (60) дней без визитов и любые семьи через `INACTIVE_DAYS` (400).
* Голос ребёнка на сервере не хранится вообще: распознавание идёт в браузере, на сервер приходят только `stars` и распознанный текст.
