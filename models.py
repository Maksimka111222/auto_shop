"""Робота з базою даних SQLite для MOTOREX.

Що тут є:
- SCHEMA — SQL-опис усіх таблиць (CREATE TABLE IF NOT EXISTS);
- get_db() / close_db() — одне з'єднання на один HTTP-запит;
- init_db() — створення таблиць (безпечно викликати повторно);
- функції CRUD для кожної таблиці.

Правила, яких дотримуємось у всьому файлі:
1. Усі значення передаються в SQL через `?` (параметризовані запити),
   тому SQL-ін'єкція неможлива.
2. Зміни даних виконуються всередині `with db:` — це транзакція:
   при успіху автоматично виконується commit(), при помилці — rollback().
3. Одразу після підключення вмикаємо `PRAGMA foreign_keys = ON`,
   бо SQLite за замовчуванням НЕ перевіряє зовнішні ключі.
"""
import sqlite3
from datetime import datetime

from flask import current_app, g


SCHEMA = """
-- Відгуки з форми «Зворотний зв'язок»
CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL,
    message    TEXT NOT NULL,
    -- 0 = нове, 1 = опрацьоване менеджером (операція UPDATE в адмінці)
    is_processed INTEGER NOT NULL DEFAULT 0 CHECK (is_processed IN (0, 1)),
    created_at TEXT NOT NULL
);
"""


def now():
    """Поточні дата й час у форматі, який зручно сортувати: 2026-11-16 14:05:00."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ---------------------------------------------------------------- з'єднання

def get_db():
    """Повертає з'єднання для поточного запиту (створює, якщо його ще немає)."""
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row            # рядки читаються як row['name']
        g.db.execute('PRAGMA foreign_keys = ON')  # вмикаємо перевірку FOREIGN KEY
    return g.db


def close_db(exception=None):
    """Закриває з'єднання наприкінці запиту (реєструється в app.py)."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Створює таблиці, яких ще немає. Наявні дані не зачіпає."""
    db = get_db()
    db.executescript(SCHEMA)


# ------------------------------------------------------------------ відгуки

def add_feedback(name, email, message):
    """CREATE: зберігає новий відгук."""
    db = get_db()
    with db:
        db.execute(
            'INSERT INTO feedback (name, email, message, created_at) VALUES (?, ?, ?, ?)',
            (name, email, message, now()),
        )


def get_feedback():
    """READ: усі відгуки — спочатку неопрацьовані, потім нові зверху."""
    return get_db().execute('SELECT * FROM feedback ORDER BY is_processed, id DESC').fetchall()


def toggle_feedback(feedback_id):
    """UPDATE: перемикає позначку «опрацьовано» (0 -> 1, 1 -> 0)."""
    db = get_db()
    with db:
        db.execute('UPDATE feedback SET is_processed = 1 - is_processed WHERE id = ?', (feedback_id,))


def delete_feedback(feedback_id):
    """DELETE: видаляє відгук за id."""
    db = get_db()
    with db:
        db.execute('DELETE FROM feedback WHERE id = ?', (feedback_id,))


def count_rows(table):
    """Кількість рядків у таблиці (для статистики на головній сторінці адмінки).
    Назва таблиці підставляється в SQL, тому дозволяємо лише відомі назви."""
    allowed = {'feedback', 'cars', 'orders', 'test_drives', 'users'}
    if table not in allowed:
        raise ValueError(f'Невідома таблиця: {table}')
    try:
        return get_db().execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    except sqlite3.OperationalError:
        # Таблиці ще немає (наступні етапи роботи)
        return 0
