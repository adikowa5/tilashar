"""Точка входа для Vercel.

Python-рантайм Vercel ищет в корне файл с переменной `app` — asgi.py подходит.
Имя намеренно не app.py: внутри бэкенда импорты идут как `from app.config import ...`,
и корневой модуль с тем же именем перекрывал бы пакет backend/app.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402  — импорт только после правки sys.path

__all__ = ["app"]
