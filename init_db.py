"""Створює таблиці в db.sqlite (якщо їх ще немає).
Запуск із папки проєкту:  python init_db.py   (на macOS: python3 init_db.py)
"""
from app import app
import models

if __name__ == '__main__':
    with app.app_context():
        models.init_db()
    print(f"База даних готова: {app.config['DATABASE']}")
