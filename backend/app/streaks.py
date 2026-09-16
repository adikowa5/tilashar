"""Расчёт серии (streak) занятий.

Правило продукта: пропуск одного дня серию не обнуляет («заморозка»),
два пропущенных дня подряд — обнуляют.

Модуль намеренно не зависит от БД: на вход подаётся список дат закрытых
уроков, на выход — число. Это позволяет тестировать логику без Postgres.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

# Максимальный разрыв между соседними активными днями, при котором серия жива.
# Разрыв в 1 день = занимались два дня подряд; разрыв в 2 дня = один пропуск (заморозка);
# разрыв в 3 и более = два пропущенных дня подряд, серия обрывается.
MAX_ALIVE_GAP_DAYS = 2


def compute_streak(days: Iterable[date], today: date) -> int:
    """Считает длину текущей серии на дату ``today``.

    ``days`` — даты, в которые ребёнок закрыл хотя бы один урок (порядок и
    дубликаты не важны, будущие даты игнорируются).

    Возвращает количество активных дней в непрерывной (с учётом заморозки)
    серии, примыкающей к сегодняшнему дню. Если последний активный день был
    более двух дней назад — серия уже обнулилась, возвращается 0.
    """
    unique_days = sorted({d for d in days if d <= today}, reverse=True)
    if not unique_days:
        return 0

    # Серия «дотягивается» до сегодня, только если последний активный день
    # не дальше, чем через один пропуск.
    if (today - unique_days[0]).days > MAX_ALIVE_GAP_DAYS:
        return 0

    streak = 1
    for newer, older in zip(unique_days, unique_days[1:]):
        if (newer - older).days <= MAX_ALIVE_GAP_DAYS:
            streak += 1
        else:
            break
    return streak


def is_frozen(days: Iterable[date], today: date) -> bool:
    """True, если серия жива, но сегодня и вчера занятий не было (состояние заморозки)."""
    unique_days = sorted({d for d in days if d <= today}, reverse=True)
    if not unique_days:
        return False
    gap = (today - unique_days[0]).days
    return 1 < gap <= MAX_ALIVE_GAP_DAYS
