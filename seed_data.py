"""Наповнює базу демонстраційними даними.
Запуск:  python seed_data.py   (на macOS: python3 seed_data.py)

Скрипт можна запускати повторно: якщо дані вже є, він їх не дублює.
Щоб почати «з чистого аркуша», видаліть файл db.sqlite і запустіть скрипт знову.
"""
from app import app
import models


def seed():
    models.init_db()

    if models.get_feedback():
        print('Відгуки вже є — пропускаю.')
        return
    models.add_feedback('Тестовий користувач', 'user@example.com',
                        'Підкажіть, будь ласка, чи є Škoda Octavia з автоматом?')
    print('Тестовий відгук додано.')


if __name__ == '__main__':
    with app.app_context():
        seed()
