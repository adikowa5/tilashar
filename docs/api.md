# Tilashar API v1 — контракт этапа 1

Базовый путь: `/api/v1`. Формат — JSON, UTF-8. Все идентификаторы — UUID-строки.
Ошибки: `{"detail": "<code>"}` + HTTP-код. Коды ошибок ниже перечислены явно.

## Аутентификация

JWT: access (30 мин) и refresh (30 дней) в теле ответа, клиент хранит их сам.
Заголовок: `Authorization: Bearer <access>`.

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| POST | `/auth/code` | `{"phone": "+77011234567"}` | `{"sent": true, "dev_code": "000000"\|null, "retry_after": 60}` |
| POST | `/auth/token` | `{"phone": "...", "code": "123456"}` | `TokenPair` |
| POST | `/auth/refresh` | `{"refresh_token": "..."}` | `TokenPair` |
| POST | `/auth/guest` | — | `TokenPair` (создаёт гостевую семью) |
| POST | `/auth/claim` | `{"phone": "...", "code": "..."}` | `TokenPair` — превращает гостевую семью в обычную, сохраняя детей и прогресс |
| POST | `/auth/logout` | `{"refresh_token": "..."}` | `204` |

`TokenPair` = `{"access_token": str, "refresh_token": str, "token_type": "bearer", "expires_in": 1800}`

Коды ошибок: `code_not_found`, `code_expired`, `code_invalid`, `too_many_attempts`, `phone_invalid`, `token_invalid`, `already_claimed`.

В dev-режиме (`SMS_PROVIDER=console`) код всегда `000000` и возвращается в `dev_code`.
Лимит: 5 запросов кода на телефон в час, 5 попыток ввода на код.

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
| GET | `/content/topics` | `[Topic]` — встроенные темы + темы семьи |
| GET | `/content/topics/{slug}` | `Topic` с полем `words` |
| POST | `/content/topics` | своя тема (из AI-генерации): `{"title_kk","title_ru","pic","words":[Word]}` |

`Topic` = `{"id","slug","title_kk","title_ru","pic","kind":"builtin"|"family","word_count"}`
`Word` = `{"id","text_kk","text_ru","syllables","pic","audio_key"}`

`audio_key` — ключ записи в паке озвучки (`w:алма`); фронт сам решает, брать ли запись родителя.

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

## Голос родителя

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/voices` | — | `[{"key","url","duration_ms","updated_at"}]` |
| PUT | `/voices` | multipart: `key`, `file` (audio/wav, ≤2 МБ) | запись |
| DELETE | `/voices/{key}` | — | `204` |

Ключ — `w:<слово>` или `p:<фраза>`, проверяется по регулярке `^[wp]:.{1,64}$`.
Файлы кладутся в `MEDIA_ROOT/<family_id>/<sha256>.wav`, отдаются по `/media/...`.

## Прочее

`GET /health` → `{"status":"ok","db":"ok"}`.
`GET /api/v1/config` → `{"sms_provider","dev_mode","max_children","version"}`.

## Правила авторизации

* Любой `/children/{id}/...` проверяет, что ребёнок принадлежит семье вызывающего — иначе `404` (не `403`, чтобы не раскрывать существование).
* Гостевая семья живёт 30 дней, потом чистится задачей; при `claim` привязывается к телефону.
* Голос ребёнка на сервере не хранится вообще: распознавание идёт в браузере, на сервер приходят только `stars` и распознанный текст.
