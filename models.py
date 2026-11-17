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
from datetime import date

from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash

# Допустимі статуси замовлення. Перший присвоюється новому замовленню.
ORDER_STATUSES = ['Нове', 'В обробці', 'Підтверджене', 'Виконане', 'Скасоване']

# Значення для фільтрів каталогу (також використовуються у формі адмінки).
BODY_TYPES = ['Седан', 'Хетчбек', 'Ліфтбек', 'Купе', 'Кросовер', 'Універсал']
FUEL_TYPES = ['Бензин', 'Дизель', 'Гібрид', 'Електро']
TRANSMISSIONS = ['Автомат', 'Механіка']

# Дозволені варіанти сортування. Ключ приходить з браузера, а значення
# підставляється в SQL. Тому в SQL може потрапити ЛИШЕ рядок із цього словника.
SORT_OPTIONS = {
    'new': ('Спочатку новіші', 'year DESC, id DESC'),
    'price_asc': ('Ціна: від дешевших', 'price ASC'),
    'price_desc': ('Ціна: від дорожчих', 'price DESC'),
    'name': ('За назвою (А-Я)', 'brand ASC, name ASC'),
}

# Статуси заявки на тест-драйв.
TEST_DRIVE_STATUSES = ['Нова', 'Підтверджена', 'Проведена', 'Скасована']

# Ролі користувачів.
ROLES = ['client', 'admin']
ROLE_NAMES = {'client': 'Клієнт', 'admin': 'Адміністратор'}

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

-- Автомобілі (товари магазину)
CREATE TABLE IF NOT EXISTS cars (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    brand        TEXT    NOT NULL,
    name         TEXT    NOT NULL,
    body_type    TEXT    NOT NULL,
    fuel         TEXT    NOT NULL,
    transmission TEXT    NOT NULL,
    year         INTEGER NOT NULL CHECK (year BETWEEN 1950 AND 2100),
    price        REAL    NOT NULL CHECK (price >= 0),
    image        TEXT,
    description  TEXT
);

-- Замовлення (шапка): хто замовив, загальна сума, статус
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    email         TEXT NOT NULL,
    phone         TEXT NOT NULL,
    comment       TEXT,
    total_price   REAL NOT NULL,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

-- Проміжна таблиця «багато-до-багатьох»: одне замовлення містить багато авто,
-- одне авто може бути в багатьох замовленнях.
-- unit_price — ціна на момент замовлення (історія не зміниться, якщо ціну змінять).
-- ON DELETE CASCADE: видалили замовлення -> його позиції видаляються автоматично.
-- ON DELETE RESTRICT: не можна видалити авто, яке є хоча б в одному замовленні.
CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    car_id     INTEGER NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL    NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
    FOREIGN KEY (car_id)   REFERENCES cars (id)   ON DELETE RESTRICT
);

-- Заявки на тест-драйв (додаткова таблиця, Рівень 2).
-- Зв'язок «один-до-багатьох»: одне авто — багато заявок.
CREATE TABLE IF NOT EXISTS test_drives (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id         INTEGER NOT NULL,
    customer_name  TEXT NOT NULL,
    phone          TEXT NOT NULL,
    email          TEXT NOT NULL,
    preferred_date TEXT NOT NULL,
    comment        TEXT,
    status         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (car_id) REFERENCES cars (id) ON DELETE CASCADE
);

-- Користувачі з ролями (Рівень 3). Пароль НІКОЛИ не зберігаємо відкрито —
-- лише його хеш. COLLATE NOCASE: Test@Mail.com і test@mail.com — один email.
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'client' CHECK (role IN ('client', 'admin')),
    created_at    TEXT NOT NULL
);
"""

# Колонки, які додаються до ВЖЕ існуючих таблиць (міграція).
# CREATE TABLE IF NOT EXISTS не змінює наявну таблицю, тому нові колонки
# додаємо через ALTER TABLE, якщо їх ще немає.
# ON DELETE SET NULL: якщо користувача видалили, його замовлення залишаються.
MIGRATIONS = [
    ('orders', 'user_id', 'INTEGER REFERENCES users (id) ON DELETE SET NULL'),
    ('test_drives', 'user_id', 'INTEGER REFERENCES users (id) ON DELETE SET NULL'),
]


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
    for table, column, definition in MIGRATIONS:
        # PRAGMA table_info повертає список колонок таблиці
        columns = [row['name'] for row in db.execute(f'PRAGMA table_info({table})')]
        if column not in columns:
            # Назви таблиць/колонок беруться лише з нашого списку MIGRATIONS, не від користувача
            db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
    db.commit()


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


# --------------------------------------------------------------- автомобілі

def search_cars(q='', brand='', body_type='', fuel='', transmission='',
                price_min=None, price_max=None, sort='new'):
    """Пошук і фільтрація авто (Рівень 3).

    WHERE будується з частин лише для тих фільтрів, які заповнені.
    Самі значення фільтрів ідуть окремим списком params -> через `?`.
    """
    conditions = []
    params = []

    if q:
        # Шукаємо і в марці, і в моделі, і в описі
        conditions.append("(brand || ' ' || name LIKE ? OR description LIKE ?)")
        params += [f'%{q}%', f'%{q}%']
    if brand:
        conditions.append('brand = ?')
        params.append(brand)
    if body_type:
        conditions.append('body_type = ?')
        params.append(body_type)
    if fuel:
        conditions.append('fuel = ?')
        params.append(fuel)
    if transmission:
        conditions.append('transmission = ?')
        params.append(transmission)
    if price_min is not None:
        conditions.append('price >= ?')
        params.append(price_min)
    if price_max is not None:
        conditions.append('price <= ?')
        params.append(price_max)

    sql = 'SELECT * FROM cars'
    if conditions:
        sql += ' WHERE ' + ' AND '.join(conditions)
    # Сортування — тільки з білого списку SORT_OPTIONS
    sql += ' ORDER BY ' + SORT_OPTIONS.get(sort, SORT_OPTIONS['new'])[1]
    return get_db().execute(sql, params).fetchall()


def get_brands():
    """Список марок для випадного списку фільтра."""
    rows = get_db().execute('SELECT DISTINCT brand FROM cars ORDER BY brand').fetchall()
    return [row['brand'] for row in rows]


def get_cars():
    return get_db().execute('SELECT * FROM cars ORDER BY brand, name').fetchall()


def get_car(car_id):
    return get_db().execute('SELECT * FROM cars WHERE id = ?', (car_id,)).fetchone()


def get_cars_by_ids(ids):
    """Авто за списком id. Кількість `?` залежить від довжини списку, значення — параметри."""
    ids = list(ids)
    if not ids:
        return []
    placeholders = ','.join('?' * len(ids))
    return get_db().execute(
        f'SELECT * FROM cars WHERE id IN ({placeholders}) ORDER BY id', ids
    ).fetchall()


# --------------------------------------------------------------- замовлення

def create_order(customer_name, email, phone, comment, cart, user_id=None):
    """Створює замовлення з кошика {id авто: кількість}.

    Ціни беруться з БД, а не з браузера. Замовлення і його позиції
    записуються ОДНІЄЮ транзакцією: або все, або нічого.
    Повертає id нового замовлення.
    """
    cars = get_cars_by_ids(cart.keys())
    if not cars:
        raise ValueError('Кошик порожній')

    total = round(sum(car['price'] * cart[car['id']] for car in cars), 2)
    db = get_db()
    with db:
        cur = db.execute(
            'INSERT INTO orders (customer_name, email, phone, comment, total_price, status, created_at, user_id) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (customer_name, email, phone, comment, total, ORDER_STATUSES[0], now(), user_id),
        )
        order_id = cur.lastrowid
        db.executemany(
            'INSERT INTO order_items (order_id, car_id, quantity, unit_price) VALUES (?, ?, ?, ?)',
            [(order_id, car['id'], cart[car['id']], car['price']) for car in cars],
        )
    return order_id


# -------------------------------------------- автомобілі: керування в адмінці

def add_car(data):
    """CREATE: data — словник з полями форми (див. routes/admin.py)."""
    db = get_db()
    with db:
        cur = db.execute(
            'INSERT INTO cars (brand, name, body_type, fuel, transmission, year, price, image, description) '
            'VALUES (:brand, :name, :body_type, :fuel, :transmission, :year, :price, :image, :description)',
            data,
        )
    return cur.lastrowid


def update_car(car_id, data):
    """UPDATE: оновлює всі поля авто."""
    db = get_db()
    with db:
        db.execute(
            'UPDATE cars SET brand = :brand, name = :name, body_type = :body_type, fuel = :fuel, '
            'transmission = :transmission, year = :year, price = :price, image = :image, '
            'description = :description WHERE id = :id',
            {**data, 'id': car_id},
        )


def delete_car(car_id):
    """DELETE: якщо авто є в замовленні, SQLite кине sqlite3.IntegrityError
    (ON DELETE RESTRICT). Заявки на тест-драйв видаляться автоматично (CASCADE)."""
    db = get_db()
    with db:
        db.execute('DELETE FROM cars WHERE id = ?', (car_id,))


def get_latest_cars(limit=3):
    """Найновіші авто для блоку «Популярне в каталозі» на головній."""
    return get_db().execute('SELECT * FROM cars ORDER BY year DESC, id DESC LIMIT ?', (limit,)).fetchall()


# ---------------------------------------------- замовлення: керування в адмінці

def get_orders(status=''):
    """Список замовлень (можна відфільтрувати за статусом) з кількістю авто в кожному."""
    sql = ('SELECT o.*, COALESCE(SUM(oi.quantity), 0) AS items_count '
           'FROM orders o LEFT JOIN order_items oi ON oi.order_id = o.id')
    params = []
    if status:
        sql += ' WHERE o.status = ?'
        params.append(status)
    sql += ' GROUP BY o.id ORDER BY o.id DESC'
    return get_db().execute(sql, params).fetchall()


def get_order_details(order_id):
    """Замовлення та його позиції (JOIN order_items з cars)."""
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    items = db.execute(
        'SELECT c.id AS car_id, c.brand, c.name, c.image, oi.quantity, oi.unit_price, '
        '       oi.quantity * oi.unit_price AS subtotal '
        'FROM order_items oi JOIN cars c ON oi.car_id = c.id '
        'WHERE oi.order_id = ? ORDER BY oi.id',
        (order_id,),
    ).fetchall()
    return order, items


def update_order_status(order_id, status):
    if status not in ORDER_STATUSES:
        raise ValueError(f'Невідомий статус: {status}')
    db = get_db()
    with db:
        db.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))


def delete_order(order_id):
    """Позиції замовлення видаляє сама база (ON DELETE CASCADE)."""
    db = get_db()
    with db:
        db.execute('DELETE FROM orders WHERE id = ?', (order_id,))


# ----------------------------------------------------- тест-драйви (Рівень 2)

def add_test_drive(car_id, customer_name, phone, email, preferred_date, comment, user_id=None):
    """CREATE: нова заявка на тест-драйв."""
    db = get_db()
    with db:
        cur = db.execute(
            'INSERT INTO test_drives (car_id, customer_name, phone, email, preferred_date, comment, status, created_at, user_id) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (car_id, customer_name, phone, email, preferred_date, comment, TEST_DRIVE_STATUSES[0], now(), user_id),
        )
    return cur.lastrowid


def get_test_drives(status=''):
    """READ: заявки разом із назвою авто (JOIN з cars)."""
    sql = ('SELECT td.*, c.brand, c.name AS car_name '
           'FROM test_drives td JOIN cars c ON td.car_id = c.id')
    params = []
    if status:
        sql += ' WHERE td.status = ?'
        params.append(status)
    sql += ' ORDER BY td.preferred_date ASC, td.id DESC'
    return get_db().execute(sql, params).fetchall()


def update_test_drive_status(test_drive_id, status):
    """UPDATE: змінює статус заявки."""
    if status not in TEST_DRIVE_STATUSES:
        raise ValueError(f'Невідомий статус: {status}')
    db = get_db()
    with db:
        db.execute('UPDATE test_drives SET status = ? WHERE id = ?', (status, test_drive_id))


def delete_test_drive(test_drive_id):
    """DELETE: видаляє заявку."""
    db = get_db()
    with db:
        db.execute('DELETE FROM test_drives WHERE id = ?', (test_drive_id,))


def today():
    """Сьогоднішня дата рядком 2026-11-16 (для перевірки дати тест-драйву)."""
    return date.today().isoformat()


# ------------------------------------------------- користувачі (Рівень 3)

def create_user(name, email, password, role='client'):
    """Реєстрація. Пароль хешується (generate_password_hash), відкрито не зберігається.
    Якщо email уже зайнятий, SQLite кине sqlite3.IntegrityError (UNIQUE)."""
    if role not in ROLES:
        raise ValueError(f'Невідома роль: {role}')
    db = get_db()
    with db:
        cur = db.execute(
            'INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)',
            (name, email, generate_password_hash(password), role, now()),
        )
    return cur.lastrowid


def get_user(user_id):
    return get_db().execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


def get_user_by_email(email):
    return get_db().execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()


def check_user(email, password):
    """Повертає користувача, якщо email і пароль правильні, інакше None."""
    user = get_user_by_email(email)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None


def get_users():
    """Користувачі з кількістю їхніх замовлень (підзапит)."""
    return get_db().execute(
        'SELECT u.*, (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS orders_count '
        'FROM users u ORDER BY u.id'
    ).fetchall()


def update_user_role(user_id, role):
    if role not in ROLES:
        raise ValueError(f'Невідома роль: {role}')
    db = get_db()
    with db:
        db.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))


def delete_user(user_id):
    """Замовлення й заявки користувача залишаються (user_id стане NULL)."""
    db = get_db()
    with db:
        db.execute('DELETE FROM users WHERE id = ?', (user_id,))


def get_user_orders(user_id):
    """Історія замовлень користувача для особистого кабінету."""
    return get_db().execute(
        'SELECT o.*, GROUP_CONCAT(c.brand || \' \' || c.name, \', \') AS cars '
        'FROM orders o '
        'JOIN order_items oi ON oi.order_id = o.id '
        'JOIN cars c ON c.id = oi.car_id '
        'WHERE o.user_id = ? GROUP BY o.id ORDER BY o.id DESC',
        (user_id,),
    ).fetchall()


def get_user_test_drives(user_id):
    """Заявки на тест-драйв користувача."""
    return get_db().execute(
        'SELECT td.*, c.brand, c.name AS car_name FROM test_drives td '
        'JOIN cars c ON c.id = td.car_id WHERE td.user_id = ? ORDER BY td.id DESC',
        (user_id,),
    ).fetchall()
