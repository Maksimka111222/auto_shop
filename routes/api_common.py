"""Спільні утиліти REST API (ЛР5): помилки, валідація, серіалізація, пагінація.

Що тут є:
- ApiError — виняток, який view-функції кидають замість ручного return jsonify(...).
  Єдиний обробник у app.py перетворює його на JSON {"error", "status_code", "details"};
- валідація тіла JSON (get_json_body, validate_car, validate_order, validate_feedback);
- розбір query-параметрів (parse_int_arg, parse_float_arg, parse_bool_arg);
- перетворення рядків БД у словники (car_to_dict, order_to_dict, feedback_to_dict);
- paginate() для відповіді v2.

Принцип: уся логіка перевірки живе тут один раз, а v1 і v2 її перевикористовують.
"""
import math
import re

from flask import jsonify, request

import models

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PHONE_RE = re.compile(r'^\+?[\d\s()-]{10,20}$')   # той самий формат, що й у routes/shop.py

MAX_QUANTITY = 5            # як і на сайті: не більше 5 однакових авто в одній позиції
MAX_ITEMS_PER_ORDER = 20    # скільки різних позицій може бути в одному замовленні
DEFAULT_PER_PAGE = 10
MAX_PER_PAGE = 50


# ------------------------------------------------------------------ помилки

class ApiError(Exception):
    """Помилка API з HTTP-кодом. details — список {"field": ..., "message": ...}."""

    def __init__(self, status_code, message, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details or []


def problem(field, message):
    """Один елемент списку details: яке саме поле невалідне й чому."""
    return {'field': field, 'message': message}


def error_response(status_code, message, details=None):
    """Єдиний формат помилки для всього API."""
    body = {'error': message, 'status_code': status_code}
    if details:
        body['details'] = details
    return jsonify(body), status_code


def is_api_request():
    """True, якщо запит іде на /api/... (тоді помилки треба віддавати JSON-ом, а не HTML)."""
    return request.path == '/api' or request.path.startswith('/api/')


# ------------------------------------------------------- перевірка типів

def is_int(value):
    # bool у Python — підклас int, тому True/False треба відсікати окремо
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def get_json_body():
    """Повертає тіло запиту як dict або кидає 400.

    request.get_json(silent=True) повертає None, якщо Content-Type не JSON
    або JSON зламаний (без silent=True Flask сам кинув би 400/415 з HTML).
    """
    data = request.get_json(silent=True)
    if data is None:
        raise ApiError(400, 'Тіло запиту має бути коректним JSON із заголовком Content-Type: application/json')
    if not isinstance(data, dict):
        raise ApiError(400, "Тіло запиту має бути JSON-об'єктом, а не масивом чи окремим значенням")
    return data


def reject_unknown(data, allowed, errors):
    """Суворий режим: невідомі поля — це помилка, а не мовчазне ігнорування."""
    for key in data:
        if key not in allowed:
            errors.append(problem(str(key), 'невідоме поле'))


# ----------------------------------------------------------- автомобілі

CAR_REQUIRED = ('brand', 'name', 'body_type', 'fuel', 'transmission', 'year', 'price')
CAR_OPTIONAL = ('image', 'description', 'in_stock')
CAR_FIELDS = CAR_REQUIRED + CAR_OPTIONAL


def check_car_field(field, value):
    """Перевіряє одне поле авто. Повертає (очищене_значення, None) або (None, текст_помилки)."""
    if field in ('brand', 'name'):
        if not isinstance(value, str) or not value.strip():
            return None, 'має бути непорожнім рядком'
        if len(value.strip()) > 100:
            return None, 'задовге (до 100 символів)'
        return value.strip(), None

    if field in ('body_type', 'fuel', 'transmission'):
        allowed = {'body_type': models.BODY_TYPES, 'fuel': models.FUEL_TYPES,
                   'transmission': models.TRANSMISSIONS}[field]
        if not isinstance(value, str) or value not in allowed:
            return None, 'має бути одним із: ' + ', '.join(allowed)
        return value, None

    if field == 'year':
        if not is_int(value) or not 1950 <= value <= 2100:
            return None, 'має бути цілим числом від 1950 до 2100'
        return value, None

    if field == 'price':
        if not is_number(value) or value <= 0:
            return None, 'має бути числом більше 0'
        return round(float(value), 2), None

    if field == 'image':
        if value is not None and (not isinstance(value, str) or len(value) > 255):
            return None, 'має бути рядком (до 255 символів) або null'
        return value, None

    if field == 'description':
        if value is not None and (not isinstance(value, str) or len(value) > 2000):
            return None, 'має бути рядком (до 2000 символів) або null'
        return value, None

    if field == 'in_stock':
        if not isinstance(value, bool):
            return None, 'має бути true або false'
        return value, None

    return None, 'невідоме поле'


def validate_car(data, partial=False):
    """Перевіряє тіло для POST/PUT (partial=False) або PATCH (partial=True).

    Повертає словник очищених значень або кидає ApiError(400) зі списком усіх помилок одразу.
    """
    errors = []
    clean = {}
    reject_unknown(data, CAR_FIELDS, errors)

    if partial:
        if not data:
            errors.append(problem('body', 'передайте хоча б одне поле для оновлення'))
    else:
        for field in CAR_REQUIRED:
            if field not in data:
                errors.append(problem(field, "обов'язкове поле"))

    for field in CAR_FIELDS:
        if field in data:
            value, error = check_car_field(field, data[field])
            if error:
                errors.append(problem(field, error))
            else:
                clean[field] = value

    if errors:
        raise ApiError(400, 'Помилка валідації', errors)
    return clean


def car_to_dict(row):
    car = dict(row)
    car['in_stock'] = bool(car['in_stock'])   # у SQLite це 0/1, у JSON має бути true/false
    return car


# ---------------------------------------------------------- замовлення

def validate_order(data):
    """Перевіряє тіло POST /orders. Повертає чисті дані; cart має вигляд {car_id: quantity}."""
    errors = []
    reject_unknown(data, ('customer_name', 'email', 'phone', 'comment', 'items'), errors)

    name = data.get('customer_name')
    if not isinstance(name, str) or not name.strip():
        errors.append(problem('customer_name', "обов'язкове непорожнє поле (рядок)"))
    elif len(name.strip()) > 100:
        errors.append(problem('customer_name', 'задовге (до 100 символів)'))

    email = data.get('email')
    if not isinstance(email, str) or not EMAIL_RE.match(email.strip()):
        errors.append(problem('email', 'потрібен коректний email'))

    phone = data.get('phone')
    if not isinstance(phone, str) or not PHONE_RE.match(phone.strip()):
        errors.append(problem('phone', 'потрібен телефон у форматі +380 XX XXX XX XX'))

    comment = data.get('comment')
    if comment is not None and (not isinstance(comment, str) or len(comment) > 1000):
        errors.append(problem('comment', 'має бути рядком (до 1000 символів) або null'))

    cart = {}
    items = data.get('items')
    if not isinstance(items, list) or not items:
        errors.append(problem('items', "обов'язковий непорожній масив позицій"))
    elif len(items) > MAX_ITEMS_PER_ORDER:
        errors.append(problem('items', f'забагато позицій (максимум {MAX_ITEMS_PER_ORDER})'))
    else:
        for index, item in enumerate(items):
            where = f'items[{index}]'
            if not isinstance(item, dict):
                errors.append(problem(where, "має бути об'єктом {car_id, quantity}"))
                continue
            reject_unknown(item, ('car_id', 'quantity'), errors)
            car_id, quantity = item.get('car_id'), item.get('quantity')
            if not is_int(car_id) or car_id <= 0:
                errors.append(problem(f'{where}.car_id', 'має бути цілим числом більше 0'))
            if not is_int(quantity) or not 1 <= quantity <= MAX_QUANTITY:
                errors.append(problem(f'{where}.quantity', f'має бути цілим числом від 1 до {MAX_QUANTITY}'))
            if is_int(car_id) and car_id > 0 and is_int(quantity) and 1 <= quantity <= MAX_QUANTITY:
                # Якщо те саме авто вказали двічі, кількості додаються
                cart[car_id] = cart.get(car_id, 0) + quantity

    if not errors and any(qty > MAX_QUANTITY for qty in cart.values()):
        errors.append(problem('items', f'сумарна кількість одного авто не може перевищувати {MAX_QUANTITY}'))

    if errors:
        raise ApiError(400, 'Помилка валідації', errors)
    return {'customer_name': name.strip(), 'email': email.strip().lower(), 'phone': phone.strip(),
            'comment': (comment or '').strip(), 'cart': cart}


def check_cars_available(cart):
    """Перевіряє, що кожне авто з кошика існує (інакше 400) і є в наявності (інакше 409)."""
    missing, unavailable = [], []
    for car_id in cart:
        car = models.get_car(car_id)
        if car is None:
            missing.append(problem(f'car_id={car_id}', 'авто з таким id не існує'))
        elif not car['in_stock']:
            unavailable.append(problem(f'car_id={car_id}', f'«{car["brand"]} {car["name"]}» зараз немає в наявності'))
    if missing:
        raise ApiError(400, 'Деякі авто з замовлення не існують', missing)
    if unavailable:
        raise ApiError(409, 'Деяких авто немає в наявності', unavailable)


def order_to_dict(order, items):
    """Замовлення разом з позиціями (items — результат models.get_order_details)."""
    data = dict(order)
    data.pop('items_count', None)
    data['items'] = [dict(item) for item in items]
    data['items_count'] = sum(item['quantity'] for item in items)
    return data


def orders_with_details(status=''):
    """Усі замовлення (можна відфільтрувати за статусом) разом з позиціями."""
    result = []
    for row in models.get_orders(status):
        order, items = models.get_order_details(row['id'])
        result.append(order_to_dict(order, items))
    return result


def validate_status(status, field='status'):
    if not isinstance(status, str) or status not in models.ORDER_STATUSES:
        raise ApiError(400, 'Помилка валідації', [
            problem(field, 'має бути одним із: ' + ', '.join(models.ORDER_STATUSES))])
    return status


# -------------------------------------------------------------- відгуки

def validate_feedback(data):
    errors = []
    reject_unknown(data, ('name', 'email', 'message'), errors)

    name = data.get('name')
    if not isinstance(name, str) or not name.strip():
        errors.append(problem('name', "обов'язкове непорожнє поле (рядок)"))
    elif len(name.strip()) > 100:
        errors.append(problem('name', 'задовге (до 100 символів)'))

    email = data.get('email')
    if not isinstance(email, str) or not EMAIL_RE.match(email.strip()):
        errors.append(problem('email', 'потрібен коректний email'))

    message = data.get('message')
    if not isinstance(message, str) or not 5 <= len(message.strip()) <= 2000:
        errors.append(problem('message', 'має бути рядком від 5 до 2000 символів'))

    if errors:
        raise ApiError(400, 'Помилка валідації', errors)
    return {'name': name.strip(), 'email': email.strip(), 'message': message.strip()}


def feedback_to_dict(row):
    item = dict(row)
    item['is_processed'] = bool(item['is_processed'])
    return item


# ------------------------------------------------- query-параметри (v2)

def parse_int_arg(args, name, default, minimum, maximum):
    raw = args.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, 'Некоректний параметр запиту', [problem(name, 'має бути цілим числом')])
    if not minimum <= value <= maximum:
        raise ApiError(400, 'Некоректний параметр запиту',
                       [problem(name, f'має бути від {minimum} до {maximum}')])
    return value


def parse_float_arg(args, name):
    raw = args.get(name)
    if raw is None or raw == '':
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ApiError(400, 'Некоректний параметр запиту', [problem(name, 'має бути числом')])
    if not math.isfinite(value) or value < 0:
        raise ApiError(400, 'Некоректний параметр запиту', [problem(name, 'має бути числом від 0')])
    return value


def parse_bool_arg(args, name):
    raw = args.get(name)
    if raw is None or raw == '':
        return None
    if raw.lower() in ('true', '1'):
        return True
    if raw.lower() in ('false', '0'):
        return False
    raise ApiError(400, 'Некоректний параметр запиту', [problem(name, 'має бути true або false')])


def parse_choice_arg(args, name, allowed):
    value = args.get(name, '')
    if value and value not in allowed:
        raise ApiError(400, 'Некоректний параметр запиту',
                       [problem(name, 'має бути одним із: ' + ', '.join(allowed))])
    return value


def parse_pagination(args):
    page = parse_int_arg(args, 'page', 1, 1, 1_000_000)
    per_page = parse_int_arg(args, 'per_page', DEFAULT_PER_PAGE, 1, MAX_PER_PAGE)
    return page, per_page


def paginate(items, page, per_page):
    """Нарізає список на сторінку й додає метадані.

    Для навчального каталогу з десятками записів це простіше й надійніше за LIMIT/OFFSET.
    Для великої таблиці пагінацію варто робити в SQL (LIMIT ? OFFSET ?).
    """
    total = len(items)
    pages = max(1, math.ceil(total / per_page))
    start = (page - 1) * per_page
    return {'items': items[start:start + per_page], 'total': total,
            'page': page, 'per_page': per_page, 'pages': pages}
