"""Налаштування Swagger UI (flasgger). Документація: /apidocs/

Дві специфікації (v1 і v2) обираються у випадному списку вгорі сторінки.
Схеми (definitions) описані один раз тут, а в docstring ендпоінтів на них посилаємось через $ref.
"""

SWAGGER_CONFIG = {
    'headers': [],
    'specs': [
        {
            'endpoint': 'apispec_v1',
            'route': '/apispec_v1.json',
            'rule_filter': lambda rule: rule.endpoint.startswith('api_v1.'),
            'model_filter': lambda tag: True,
        },
        {
            'endpoint': 'apispec_v2',
            'route': '/apispec_v2.json',
            'rule_filter': lambda rule: rule.endpoint.startswith('api_v2.'),
            'model_filter': lambda tag: True,
        },
    ],
    'static_url_path': '/flasgger_static',
    'swagger_ui': True,
    'specs_route': '/apidocs/',
}

CAR_EXAMPLE = {
    'brand': 'Toyota', 'name': 'Corolla', 'body_type': 'Седан', 'fuel': 'Бензин',
    'transmission': 'Автомат', 'year': 2022, 'price': 24500,
    'image': None, 'description': 'Надійний седан для щоденних поїздок.', 'in_stock': True,
}

SWAGGER_TEMPLATE = {
    'swagger': '2.0',
    'info': {
        'title': 'MOTOREX REST API',
        'description': (
            'REST API автомагазину MOTOREX (Flask + SQLite). '
            'v1 - базове CRUD (авто, замовлення, відгуки). '
            'v2 - розширене читання: пошук, фільтри, сортування, пагінація, метадані у відповіді. '
            'Усі відповіді, включно з помилками, у форматі JSON.'),
        'version': '2.0.0',
        'contact': {'name': 'Команда ІПЗ-22: Хомич М., Жук Д., Сієнко В.'},
    },
    'schemes': ['http'],
    'consumes': ['application/json'],
    'produces': ['application/json'],
    'tags': [
        {'name': 'v1 - Cars', 'description': 'v1: CRUD автомобілів'},
        {'name': 'v1 - Orders', 'description': 'v1: замовлення'},
        {'name': 'v1 - Feedback', 'description': 'v1: відгуки'},
        {'name': 'v2 - Search and Pagination', 'description': 'v2: пошук, фільтри, пагінація'},
    ],
    'definitions': {
        'Car': {
            'type': 'object',
            'properties': {
                'id': {'type': 'integer', 'example': 1},
                'brand': {'type': 'string', 'example': 'Toyota'},
                'name': {'type': 'string', 'example': 'Camry'},
                'body_type': {'type': 'string', 'example': 'Седан'},
                'fuel': {'type': 'string', 'example': 'Бензин'},
                'transmission': {'type': 'string', 'example': 'Автомат'},
                'year': {'type': 'integer', 'example': 2018},
                'price': {'type': 'number', 'example': 21500},
                'image': {'type': 'string', 'example': 'img/toyota-camry.jpg'},
                'description': {'type': 'string'},
                'in_stock': {'type': 'boolean', 'example': True},
            },
        },
        'CarInput': {
            'type': 'object',
            'required': ['brand', 'name', 'body_type', 'fuel', 'transmission', 'year', 'price'],
            'properties': {
                'brand': {'type': 'string'},
                'name': {'type': 'string'},
                'body_type': {'type': 'string', 'enum': ['Седан', 'Хетчбек', 'Ліфтбек', 'Купе', 'Кросовер', 'Універсал']},
                'fuel': {'type': 'string', 'enum': ['Бензин', 'Дизель', 'Гібрид', 'Електро']},
                'transmission': {'type': 'string', 'enum': ['Автомат', 'Механіка']},
                'year': {'type': 'integer', 'minimum': 1950, 'maximum': 2100},
                'price': {'type': 'number', 'exclusiveMinimum': True, 'minimum': 0},
                'image': {'type': 'string'},
                'description': {'type': 'string'},
                'in_stock': {'type': 'boolean'},
            },
            'example': CAR_EXAMPLE,
        },
        'CarPatch': {
            'type': 'object',
            'description': 'Будь-яка непорожня підмножина полів авто',
            'properties': {
                'price': {'type': 'number'},
                'in_stock': {'type': 'boolean'},
            },
            'example': {'price': 23900, 'in_stock': False},
        },
        'OrderItemInput': {
            'type': 'object',
            'required': ['car_id', 'quantity'],
            'properties': {
                'car_id': {'type': 'integer', 'minimum': 1},
                'quantity': {'type': 'integer', 'minimum': 1, 'maximum': 5},
            },
        },
        'OrderInput': {
            'type': 'object',
            'required': ['customer_name', 'email', 'phone', 'items'],
            'properties': {
                'customer_name': {'type': 'string'},
                'email': {'type': 'string'},
                'phone': {'type': 'string'},
                'comment': {'type': 'string'},
                'items': {'type': 'array', 'items': {'$ref': '#/definitions/OrderItemInput'}},
            },
            'example': {
                'customer_name': 'Іван Петренко', 'email': 'ivan@example.com',
                'phone': '+380 67 123 45 67', 'comment': 'Зателефонуйте після 15:00',
                'items': [{'car_id': 1, 'quantity': 1}, {'car_id': 2, 'quantity': 2}],
            },
        },
        'Order': {
            'type': 'object',
            'properties': {
                'id': {'type': 'integer'},
                'customer_name': {'type': 'string'},
                'email': {'type': 'string'},
                'phone': {'type': 'string'},
                'comment': {'type': 'string'},
                'total_price': {'type': 'number'},
                'status': {'type': 'string', 'example': 'Нове'},
                'created_at': {'type': 'string', 'example': '2026-11-24 12:00:00'},
                'user_id': {'type': 'integer'},
                'items_count': {'type': 'integer'},
                'items': {'type': 'array', 'items': {'type': 'object'}},
            },
        },
        'StatusInput': {
            'type': 'object',
            'required': ['status'],
            'properties': {
                'status': {'type': 'string', 'enum': ['Нове', 'В обробці', 'Підтверджене', 'Виконане', 'Скасоване']},
            },
            'example': {'status': 'В обробці'},
        },
        'Feedback': {
            'type': 'object',
            'properties': {
                'id': {'type': 'integer'},
                'name': {'type': 'string'},
                'email': {'type': 'string'},
                'message': {'type': 'string'},
                'is_processed': {'type': 'boolean'},
                'created_at': {'type': 'string'},
            },
        },
        'FeedbackInput': {
            'type': 'object',
            'required': ['name', 'email', 'message'],
            'properties': {
                'name': {'type': 'string'},
                'email': {'type': 'string'},
                'message': {'type': 'string', 'minLength': 5, 'maxLength': 2000},
            },
            'example': {'name': 'Олена', 'email': 'olena@example.com',
                        'message': 'Чи є Škoda Octavia з автоматом?'},
        },
        'Error': {
            'type': 'object',
            'properties': {
                'error': {'type': 'string', 'example': 'Помилка валідації'},
                'status_code': {'type': 'integer', 'example': 400},
                'details': {
                    'type': 'array',
                    'items': {'type': 'object', 'properties': {
                        'field': {'type': 'string', 'example': 'price'},
                        'message': {'type': 'string', 'example': "обов'язкове поле"}}},
                },
            },
        },
        'CarPage': {
            'type': 'object',
            'properties': {
                'items': {'type': 'array', 'items': {'$ref': '#/definitions/Car'}},
                'total': {'type': 'integer', 'example': 9},
                'page': {'type': 'integer', 'example': 1},
                'per_page': {'type': 'integer', 'example': 10},
                'pages': {'type': 'integer', 'example': 1},
                'sort': {'type': 'string', 'example': 'new'},
            },
        },
        'OrderPage': {
            'type': 'object',
            'properties': {
                'items': {'type': 'array', 'items': {'$ref': '#/definitions/Order'}},
                'total': {'type': 'integer'}, 'page': {'type': 'integer'},
                'per_page': {'type': 'integer'}, 'pages': {'type': 'integer'},
            },
        },
        'FeedbackPage': {
            'type': 'object',
            'properties': {
                'items': {'type': 'array', 'items': {'$ref': '#/definitions/Feedback'}},
                'total': {'type': 'integer'}, 'page': {'type': 'integer'},
                'per_page': {'type': 'integer'}, 'pages': {'type': 'integer'},
            },
        },
    },
}
