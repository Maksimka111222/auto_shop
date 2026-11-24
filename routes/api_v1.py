"""REST API v1 (ЛР5): базове CRUD для авто, замовлень і відгуків. Префікс: /api/v1.

Правила, яких дотримуємось:
- усі відповіді (і помилки) у JSON; помилки кидаємо як ApiError, а форматує їх app.py;
- 200 OK — прочитано/оновлено, 201 Created + заголовок Location — створено,
  204 No Content — видалено, 400 — невалідні дані, 404 — немає такого id,
  409 — конфлікт (авто є в замовленнях / немає в наявності);
- SQL тут не пишемо: працюємо через функції models.py (параметризовані запити з ЛР4);
- опис кожного ендпоінта для Swagger — це YAML після рядка `---` у docstring.
"""
import sqlite3

from flask import Blueprint, jsonify, request, url_for

import models
from .api_common import (ApiError, car_to_dict, check_cars_available, feedback_to_dict,
                         get_json_body, order_to_dict, orders_with_details, problem,
                         validate_car, validate_feedback, validate_order, validate_status)

api_v1_bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')


# ---------------------------------------------------------------- допоміжне

def get_car_or_404(car_id):
    car = models.get_car(car_id)
    if car is None:
        raise ApiError(404, f'Авто з id={car_id} не знайдено')
    return car


def get_order_or_404(order_id):
    order, items = models.get_order_details(order_id)
    if order is None:
        raise ApiError(404, f'Замовлення з id={order_id} не знайдено')
    return order, items


def created(payload, location):
    """201 Created із заголовком Location — адресою нового ресурсу."""
    response = jsonify(payload)
    response.status_code = 201
    response.headers['Location'] = location
    return response


def car_payload(clean):
    """Повний набір полів для INSERT/UPDATE (необов'язкові, яких не передали, отримують значення за замовчуванням)."""
    return {
        'brand': clean['brand'], 'name': clean['name'], 'body_type': clean['body_type'],
        'fuel': clean['fuel'], 'transmission': clean['transmission'],
        'year': clean['year'], 'price': clean['price'],
        'image': clean.get('image'), 'description': clean.get('description'),
        'in_stock': 1 if clean.get('in_stock', True) else 0,
    }


# ================================================================ АВТОМОБІЛІ

@api_v1_bp.route('/cars', methods=['GET'])
def list_cars():
    """Список усіх автомобілів
    Повертає JSON-масив усіх авто каталогу (без фільтрів і пагінації; вони є у v2).
    ---
    tags:
      - v1 - Cars
    responses:
      200:
        description: Масив автомобілів
        schema:
          type: array
          items:
            $ref: '#/definitions/Car'
    """
    return jsonify([car_to_dict(car) for car in models.get_cars()]), 200


@api_v1_bp.route('/cars/<int:car_id>', methods=['GET'])
def get_car(car_id):
    """Отримати автомобіль за id
    ---
    tags:
      - v1 - Cars
    parameters:
      - name: car_id
        in: path
        type: integer
        required: true
        description: Ідентифікатор авто
        default: 1
    responses:
      200:
        description: Дані автомобіля
        schema:
          $ref: '#/definitions/Car'
      404:
        description: Авто не знайдено
        schema:
          $ref: '#/definitions/Error'
    """
    return jsonify(car_to_dict(get_car_or_404(car_id))), 200


@api_v1_bp.route('/cars', methods=['POST'])
def create_car():
    """Створити автомобіль
    Обов'язкові поля - brand, name, body_type, fuel, transmission, year, price.
    Необов'язкові - image, description, in_stock (за замовчуванням true).
    ---
    tags:
      - v1 - Cars
    parameters:
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/CarInput'
    responses:
      201:
        description: Авто створено. Адреса нового ресурсу в заголовку Location
        headers:
          Location:
            type: string
            description: URL створеного авто
        schema:
          $ref: '#/definitions/Car'
      400:
        description: Помилка валідації (немає ціни, ціна не більша за 0, неправильний тип тощо)
        schema:
          $ref: '#/definitions/Error'
    """
    payload = car_payload(validate_car(get_json_body()))
    car_id = models.add_car(payload)
    models.patch_car(car_id, {'in_stock': payload['in_stock']})
    return created(car_to_dict(models.get_car(car_id)), url_for('api_v1.get_car', car_id=car_id))


@api_v1_bp.route('/cars/<int:car_id>', methods=['PUT'])
def replace_car(car_id):
    """Повністю замінити автомобіль (PUT)
    Потрібні всі обов'язкові поля. Необов'язкові, яких немає в тілі,
    скидаються до значень за замовчуванням (image і description - null, in_stock - true).
    PUT ідемпотентний - повторний однаковий запит дає той самий результат.
    ---
    tags:
      - v1 - Cars
    parameters:
      - name: car_id
        in: path
        type: integer
        required: true
        default: 1
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/CarInput'
    responses:
      200:
        description: Авто оновлено
        schema:
          $ref: '#/definitions/Car'
      400:
        description: Помилка валідації
        schema:
          $ref: '#/definitions/Error'
      404:
        description: Авто не знайдено
        schema:
          $ref: '#/definitions/Error'
    """
    get_car_or_404(car_id)
    payload = car_payload(validate_car(get_json_body()))
    models.update_car(car_id, payload)
    models.patch_car(car_id, {'in_stock': payload['in_stock']})
    return jsonify(car_to_dict(models.get_car(car_id))), 200


@api_v1_bp.route('/cars/<int:car_id>', methods=['PATCH'])
def update_car_partially(car_id):
    """Частково оновити автомобіль (PATCH)
    Передайте лише ті поля, які треба змінити, наприклад ціну або наявність.
    ---
    tags:
      - v1 - Cars
    parameters:
      - name: car_id
        in: path
        type: integer
        required: true
        default: 1
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/CarPatch'
    responses:
      200:
        description: Авто оновлено
        schema:
          $ref: '#/definitions/Car'
      400:
        description: Помилка валідації (порожнє тіло, ціна не більша за 0, невідоме поле)
        schema:
          $ref: '#/definitions/Error'
      404:
        description: Авто не знайдено
        schema:
          $ref: '#/definitions/Error'
    """
    get_car_or_404(car_id)
    clean = validate_car(get_json_body(), partial=True)
    if 'in_stock' in clean:
        clean['in_stock'] = 1 if clean['in_stock'] else 0
    models.patch_car(car_id, clean)
    return jsonify(car_to_dict(models.get_car(car_id))), 200


@api_v1_bp.route('/cars/<int:car_id>', methods=['DELETE'])
def delete_car(car_id):
    """Видалити автомобіль
    Авто, яке вже є в замовленнях, видалити не можна (ON DELETE RESTRICT у БД) - буде 409.
    ---
    tags:
      - v1 - Cars
    parameters:
      - name: car_id
        in: path
        type: integer
        required: true
        default: 1
    responses:
      204:
        description: Видалено, тіла відповіді немає
      404:
        description: Авто не знайдено
        schema:
          $ref: '#/definitions/Error'
      409:
        description: Авто є в замовленнях, видалення заборонено
        schema:
          $ref: '#/definitions/Error'
    """
    get_car_or_404(car_id)
    try:
        models.delete_car(car_id)
    except sqlite3.IntegrityError:
        raise ApiError(409, 'Авто вже є в замовленнях, тому його не можна видалити')
    return '', 204


# ================================================================ ЗАМОВЛЕННЯ

@api_v1_bp.route('/orders', methods=['GET'])
def list_orders():
    """Список замовлень з позиціями
    Можна відфільтрувати за статусом: ?status=Нове
    ---
    tags:
      - v1 - Orders
    parameters:
      - name: status
        in: query
        type: string
        required: false
        enum: ["Нове", "В обробці", "Підтверджене", "Виконане", "Скасоване"]
        description: Показати лише замовлення з цим статусом
    responses:
      200:
        description: Масив замовлень, кожне містить масив items
        schema:
          type: array
          items:
            $ref: '#/definitions/Order'
      400:
        description: Невідомий статус
        schema:
          $ref: '#/definitions/Error'
    """
    status = request.args.get('status', '')
    if status:
        validate_status(status, field='status')
    return jsonify(orders_with_details(status)), 200


@api_v1_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Отримати замовлення за id
    ---
    tags:
      - v1 - Orders
    parameters:
      - name: order_id
        in: path
        type: integer
        required: true
        default: 1
    responses:
      200:
        description: Замовлення з позиціями
        schema:
          $ref: '#/definitions/Order'
      404:
        description: Замовлення не знайдено
        schema:
          $ref: '#/definitions/Error'
    """
    order, items = get_order_or_404(order_id)
    return jsonify(order_to_dict(order, items)), 200


@api_v1_bp.route('/orders', methods=['POST'])
def create_order():
    """Створити замовлення
    Перевіряє дані клієнта, що кожне авто існує (інакше 400) і є в наявності (інакше 409).
    Ціни беруться з бази, а не з запиту. Замовлення й позиції пишуться однією транзакцією.
    ---
    tags:
      - v1 - Orders
    parameters:
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/OrderInput'
    responses:
      201:
        description: Замовлення створено (статус Нове)
        headers:
          Location:
            type: string
            description: URL створеного замовлення
        schema:
          $ref: '#/definitions/Order'
      400:
        description: Помилка валідації або авто з таким id не існує
        schema:
          $ref: '#/definitions/Error'
      409:
        description: Якесь авто зараз немає в наявності
        schema:
          $ref: '#/definitions/Error'
    """
    clean = validate_order(get_json_body())
    check_cars_available(clean['cart'])
    order_id = models.create_order(clean['customer_name'], clean['email'], clean['phone'],
                                   clean['comment'], clean['cart'])
    order, items = models.get_order_details(order_id)
    return created(order_to_dict(order, items), url_for('api_v1.get_order', order_id=order_id))


@api_v1_bp.route('/orders/<int:order_id>/status', methods=['PATCH'])
def change_order_status(order_id):
    """Змінити статус замовлення
    Допустимі статуси - Нове, В обробці, Підтверджене, Виконане, Скасоване.
    ---
    tags:
      - v1 - Orders
    parameters:
      - name: order_id
        in: path
        type: integer
        required: true
        default: 1
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/StatusInput'
    responses:
      200:
        description: Статус змінено, повертається оновлене замовлення
        schema:
          $ref: '#/definitions/Order'
      400:
        description: Немає поля status або статус некоректний
        schema:
          $ref: '#/definitions/Error'
      404:
        description: Замовлення не знайдено
        schema:
          $ref: '#/definitions/Error'
    """
    get_order_or_404(order_id)
    data = get_json_body()
    extra = [problem(key, 'невідоме поле') for key in data if key != 'status']
    if extra:
        raise ApiError(400, 'Помилка валідації', extra)
    if 'status' not in data:
        raise ApiError(400, 'Помилка валідації', [problem('status', "обов'язкове поле")])
    models.update_order_status(order_id, validate_status(data['status']))
    order, items = models.get_order_details(order_id)
    return jsonify(order_to_dict(order, items)), 200


# ================================================================== ВІДГУКИ

@api_v1_bp.route('/feedback', methods=['GET'])
def list_feedback():
    """Список відгуків
    Спочатку неопрацьовані, потім новіші.
    ---
    tags:
      - v1 - Feedback
    responses:
      200:
        description: Масив відгуків
        schema:
          type: array
          items:
            $ref: '#/definitions/Feedback'
    """
    return jsonify([feedback_to_dict(row) for row in models.get_feedback()]), 200


@api_v1_bp.route('/feedback/<int:feedback_id>', methods=['GET'])
def get_feedback(feedback_id):
    """Отримати відгук за id
    ---
    tags:
      - v1 - Feedback
    parameters:
      - name: feedback_id
        in: path
        type: integer
        required: true
        default: 1
    responses:
      200:
        description: Відгук
        schema:
          $ref: '#/definitions/Feedback'
      404:
        description: Відгук не знайдено
        schema:
          $ref: '#/definitions/Error'
    """
    row = models.get_feedback_item(feedback_id)
    if row is None:
        raise ApiError(404, f'Відгук з id={feedback_id} не знайдено')
    return jsonify(feedback_to_dict(row)), 200


@api_v1_bp.route('/feedback', methods=['POST'])
def create_feedback():
    """Залишити відгук
    ---
    tags:
      - v1 - Feedback
    parameters:
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/FeedbackInput'
    responses:
      201:
        description: Відгук збережено
        headers:
          Location:
            type: string
            description: URL створеного відгуку
        schema:
          $ref: '#/definitions/Feedback'
      400:
        description: Помилка валідації (порожнє ім'я, некоректний email, надто коротке повідомлення)
        schema:
          $ref: '#/definitions/Error'
    """
    clean = validate_feedback(get_json_body())
    feedback_id = models.create_feedback(clean['name'], clean['email'], clean['message'])
    return created(feedback_to_dict(models.get_feedback_item(feedback_id)),
                   url_for('api_v1.get_feedback', feedback_id=feedback_id))
