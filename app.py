"""Точка входа для Vercel.

Python-рантайм Vercel ищет в корне файл app.py (или index.py/main.py) с переменной
`app` и поднимает его как ASGI-функцию. Локально всё запускается как раньше —
через docker compose и uvicorn app.main:app внутри backend/.
"""

from backend.app.main import app

__all__ = ["app"]
