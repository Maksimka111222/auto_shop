"""Точка входу вебзастосунку MOTOREX.

Тут створюється Flask-застосунок, задається конфігурація,
реєструються Blueprint-и (групи маршрутів), загальні для всіх
шаблонів змінні та фільтри, документація Swagger і обробники помилок.

ЛР5: додано REST API (routes/api_v1.py, routes/api_v2.py), Swagger UI (/apidocs/)
і централізовану обробку помилок: для адрес /api/... завжди JSON, для сайту — HTML-сторінки.
"""
import os
from datetime import datetime

from flasgger import Swagger
from flask import Flask, render_template, session, url_for
from werkzeug.exceptions import HTTPException

import models
from routes import (admin_bp, api_v1_bp, api_v2_bp, auth_bp, feedback_bp,
                    shop_bp, test_drive_bp)
from routes.api_common import ApiError, error_response, is_api_request
from routes.auth import load_current_user
from swagger_config import SWAGGER_CONFIG, SWAGGER_TEMPLATE

app = Flask(__name__)

# Шлях до файлу БД зберігаємо в конфігурації. Файл лежить поруч з app.py,
# незалежно від того, з якої папки запущено застосунок.
app.config['DATABASE'] = os.environ.get('DATABASE', os.path.join(app.root_path, 'db.sqlite'))

# Секретний ключ підписує cookie сесії (кошик, повідомлення, вхід користувача).
# Для навчання є значення за замовчуванням; для реального сайту його задають
# через змінну середовища SECRET_KEY.
app.secret_key = os.environ.get('SECRET_KEY', 'motorex-dev-key-change-me')

# JSON з кирилицею без \uXXXX і з полями в тому порядку, в якому ми їх склали.
app.json.ensure_ascii = False
app.json.sort_keys = False

# Після кожного запиту закриваємо з'єднання з БД (див. models.close_db).
app.teardown_appcontext(models.close_db)

# Під час запуску створюємо таблиці, яких ще немає (і додаємо нові колонки міграціями).
with app.app_context():
    models.init_db()

# Реєструємо групи маршрутів.
app.register_blueprint(feedback_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(shop_bp)
app.register_blueprint(test_drive_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(api_v1_bp)   # /api/v1/...
app.register_blueprint(api_v2_bp)   # /api/v2/...

# Swagger UI: /apidocs/ (дві специфікації: v1 і v2).
swagger = Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)

# Перед кожним запитом визначаємо, хто увійшов (g.user).
app.before_request(load_current_user)


@app.template_filter('money')
def money(value):
    """Форматує ціну: 32500 -> '$32 500'."""
    return '$' + f'{value:,.0f}'.replace(',', ' ')


@app.template_filter('car_image')
def car_image(path):
    """Повертає адресу фото авто: зовнішнє посилання або файл із папки static."""
    if not path:
        return ''
    if path.startswith(('http://', 'https://')):
        return path
    return url_for('static', filename=path)


@app.context_processor
def inject_globals():
    """Змінні, доступні в усіх шаблонах."""
    return {
        'current_year': datetime.now().year,
        # Кількість авто в кошику для значка в меню
        'cart_count': sum(session.get('cart', {}).values()),
    }


# ------------------------------------------------------ обробка помилок
# Один набір обробників на весь застосунок. Рішення «JSON чи HTML» залежить від адреси:
# /api/... -> JSON {"error": ..., "status_code": ...}; решта сайту -> сторінка error.html.

API_ERROR_MESSAGES = {
    400: 'Некоректний запит',
    403: 'Доступ заборонено',
    404: 'Ресурс не знайдено',
    405: 'Метод не дозволений для цієї адреси',
    500: 'Внутрішня помилка сервера',
}


def handle_http_error(error):
    """Помилки Flask/Werkzeug з кодом (400, 403, 404, 405, 500 ...)."""
    code = error.code or 500
    if is_api_request():
        return error_response(code, API_ERROR_MESSAGES.get(code, error.name))
    if code == 403:
        return render_template('error.html', code=403, title='Доступ заборонено',
                               message='Ця сторінка доступна лише адміністраторам.'), 403
    if code == 404:
        return render_template('error.html', code=404, title='Сторінку не знайдено',
                               message='Можливо, посилання застаріло або містить помилку.'), 404
    return error   # решта кодів на сайті — стандартна відповідь Werkzeug


for status_code in (400, 403, 404, 405, 500):
    app.register_error_handler(status_code, handle_http_error)


@app.errorhandler(ApiError)
def handle_api_error(error):
    """Наші власні помилки API (валідація, 404 за id, 409)."""
    return error_response(error.status_code, error.message, error.details)


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Усе інше: HTTP-помилки без власного обробника і непередбачені винятки."""
    if isinstance(error, HTTPException):
        return handle_http_error(error)
    if is_api_request():
        app.logger.exception('Необроблена помилка в API')
        return error_response(500, API_ERROR_MESSAGES[500])
    raise error   # для сайту лишається стандартна поведінка Flask (сторінка 500 / дебагер)


@app.route('/')
def home():
    # Блок «Популярне в каталозі» тепер наповнюється з БД
    return render_template('home.html', cars=models.get_latest_cars(3))


@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/api-demo')
def api_demo():
    return render_template('api-demo.html')


if __name__ == '__main__':
    # debug=True: автоматичний перезапуск після змін і детальні помилки.
    # Використовується лише під час розробки.
    app.run(debug=True)
