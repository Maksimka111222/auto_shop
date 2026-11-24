"""REST API v2 (ЛР5): розширене читання даних. Префікс: /api/v2.

Чим v2 відрізняється від v1:
- списки повертаються не масивом, а об'єктом-обгорткою з метаданими:
  {"items": [...], "total": 9, "page": 1, "per_page": 10, "pages": 1};
  ЦЕ ЗЛАМУЄ формат відповіді v1, тому це нова версія, а не зміна старої;
- пагінація ?page=1&per_page=10 (за замовчуванням 10, максимум 50);
- пошук за маркою/моделлю/описом (?q=), фільтри (brand, body_type, fuel, transmission,
  price_min, price_max, in_stock), сортування (?sort=price_asc);
- замовлення й відгуки теж з пагінацією та фільтрами (status, is_processed);
- кожен об'єкт має посилання links.self.
Запис (POST/PUT/PATCH/DELETE) лишається у v1, щоб не дублювати код: клієнти v1 працюють як раніше.
"""
from flask import Blueprint, jsonify, request, url_for

import models
from .api_common import (ApiError, car_to_dict, feedback_to_dict, order_to_dict, paginate,
                         parse_bool_arg, parse_choice_arg, parse_float_arg, parse_pagination,
                         problem, validate_status)

api_v2_bp = Blueprint('api_v2', __name__, url_prefix='/api/v2')


def car_v2(row):
    """У v2 до кожного авто додається посилання на нього самого."""
    car = car_to_dict(row)
    car['links'] = {'self': url_for('api_v2.get_car', car_id=car['id'])}
    return car


@api_v2_bp.route('/cars', methods=['GET'])
def list_cars():
    """Каталог з пошуком, фільтрами, сортуванням і пагінацією
    Пошук ?q= працює по марці, моделі та опису. Усі параметри необов'язкові.
    Невідоме значення фільтра або сортування - 400.
    ---
    tags:
      - v2 - Search and Pagination
    parameters:
      - name: q
        in: query
        type: string
        description: Пошук за маркою, моделлю або описом
        default: toyota
      - name: brand
        in: query
        type: string
        description: Точна марка, наприклад BMW
      - name: body_type
        in: query
        type: string
        enum: ["Седан", "Хетчбек", "Ліфтбек", "Купе", "Кросовер", "Універсал"]
      - name: fuel
        in: query
        type: string
        enum: ["Бензин", "Дизель", "Гібрид", "Електро"]
      - name: transmission
        in: query
        type: string
        enum: ["Автомат", "Механіка"]
      - name: price_min
        in: query
        type: number
        description: Мінімальна ціна
      - name: price_max
        in: query
        type: number
        description: Максимальна ціна
      - name: in_stock
        in: query
        type: boolean
        description: true - лише ті, що в наявності
      - name: sort
        in: query
        type: string
        enum: ["new", "price_asc", "price_desc", "name"]
        default: new
        description: Сортування
      - name: page
        in: query
        type: integer
        default: 1
        minimum: 1
      - name: per_page
        in: query
        type: integer
        default: 10
        minimum: 1
        maximum: 50
    responses:
      200:
        description: Сторінка авто з метаданими
        schema:
          $ref: '#/definitions/CarPage'
      400:
        description: Некоректний параметр запиту
        schema:
          $ref: '#/definitions/Error'
    """
    args = request.args
    page, per_page = parse_pagination(args)
    price_min = parse_float_arg(args, 'price_min')
    price_max = parse_float_arg(args, 'price_max')
    if price_min is not None and price_max is not None and price_min > price_max:
        raise ApiError(400, 'Некоректний параметр запиту',
                       [problem('price_min', 'не може бути більшим за price_max')])
    in_stock = parse_bool_arg(args, 'in_stock')
    sort = parse_choice_arg(args, 'sort', list(models.SORT_OPTIONS)) or 'new'

    cars = models.search_cars(
        q=args.get('q', '').strip(),
        brand=args.get('brand', '').strip(),
        body_type=parse_choice_arg(args, 'body_type', models.BODY_TYPES),
        fuel=parse_choice_arg(args, 'fuel', models.FUEL_TYPES),
        transmission=parse_choice_arg(args, 'transmission', models.TRANSMISSIONS),
        price_min=price_min, price_max=price_max, sort=sort)
    if in_stock is not None:
        cars = [car for car in cars if bool(car['in_stock']) == in_stock]

    result = paginate([car_v2(car) for car in cars], page, per_page)
    result['sort'] = sort
    return jsonify(result), 200


@api_v2_bp.route('/cars/<int:car_id>', methods=['GET'])
def get_car(car_id):
    """Автомобіль за id (з посиланням links.self)
    ---
    tags:
      - v2 - Search and Pagination
    parameters:
      - name: car_id
        in: path
        type: integer
        required: true
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
    car = models.get_car(car_id)
    if car is None:
        raise ApiError(404, f'Авто з id={car_id} не знайдено')
    return jsonify(car_v2(car)), 200


@api_v2_bp.route('/orders', methods=['GET'])
def list_orders():
    """Замовлення з позиціями, фільтром за статусом і пагінацією
    ---
    tags:
      - v2 - Search and Pagination
    parameters:
      - name: status
        in: query
        type: string
        enum: ["Нове", "В обробці", "Підтверджене", "Виконане", "Скасоване"]
      - name: page
        in: query
        type: integer
        default: 1
        minimum: 1
      - name: per_page
        in: query
        type: integer
        default: 10
        minimum: 1
        maximum: 50
    responses:
      200:
        description: Сторінка замовлень з метаданими
        schema:
          $ref: '#/definitions/OrderPage'
      400:
        description: Некоректний параметр запиту
        schema:
          $ref: '#/definitions/Error'
    """
    page, per_page = parse_pagination(request.args)
    status = request.args.get('status', '')
    if status:
        validate_status(status)

    orders = []
    for row in models.get_orders(status):
        order, items = models.get_order_details(row['id'])
        data = order_to_dict(order, items)
        data['links'] = {'self': url_for('api_v2.get_order', order_id=data['id'])}
        orders.append(data)
    return jsonify(paginate(orders, page, per_page)), 200


@api_v2_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Замовлення за id
    ---
    tags:
      - v2 - Search and Pagination
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
    order, items = models.get_order_details(order_id)
    if order is None:
        raise ApiError(404, f'Замовлення з id={order_id} не знайдено')
    data = order_to_dict(order, items)
    data['links'] = {'self': url_for('api_v2.get_order', order_id=order_id)}
    return jsonify(data), 200


@api_v2_bp.route('/feedback', methods=['GET'])
def list_feedback():
    """Відгуки з фільтром is_processed і пагінацією
    ---
    tags:
      - v2 - Search and Pagination
    parameters:
      - name: is_processed
        in: query
        type: boolean
        description: true - лише опрацьовані, false - лише нові
      - name: page
        in: query
        type: integer
        default: 1
        minimum: 1
      - name: per_page
        in: query
        type: integer
        default: 10
        minimum: 1
        maximum: 50
    responses:
      200:
        description: Сторінка відгуків з метаданими
        schema:
          $ref: '#/definitions/FeedbackPage'
      400:
        description: Некоректний параметр запиту
        schema:
          $ref: '#/definitions/Error'
    """
    page, per_page = parse_pagination(request.args)
    is_processed = parse_bool_arg(request.args, 'is_processed')
    items = [feedback_to_dict(row) for row in models.get_feedback()]
    if is_processed is not None:
        items = [item for item in items if item['is_processed'] == is_processed]
    return jsonify(paginate(items, page, per_page)), 200
