"""Точка входу вебзастосунку MOTOREX.

Тут створюється Flask-застосунок, задається конфігурація,
реєструються Blueprint-и (групи маршрутів) і загальні для всіх
шаблонів змінні та фільтри.
"""
import os
from datetime import datetime

from flask import Flask, render_template, session, url_for

import models
from routes import admin_bp, feedback_bp, shop_bp

app = Flask(__name__)

# Шлях до файлу БД зберігаємо в конфігурації. Файл лежить поруч з app.py,
# незалежно від того, з якої папки запущено застосунок.
app.config['DATABASE'] = os.environ.get('DATABASE', os.path.join(app.root_path, 'db.sqlite'))

# Секретний ключ підписує cookie сесії (кошик, повідомлення, вхід користувача).
# Для навчання є значення за замовчуванням; для реального сайту його задають
# через змінну середовища SECRET_KEY.
app.secret_key = os.environ.get('SECRET_KEY', 'motorex-dev-key-change-me')

# Після кожного запиту закриваємо з'єднання з БД (див. models.close_db).
app.teardown_appcontext(models.close_db)

# Під час запуску створюємо таблиці, яких ще немає.
with app.app_context():
    models.init_db()

# Реєструємо групи маршрутів.
app.register_blueprint(feedback_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(shop_bp)


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


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == '__main__':
    # debug=True: автоматичний перезапуск після змін і детальні помилки.
    # Використовується лише під час розробки.
    app.run(debug=True)
