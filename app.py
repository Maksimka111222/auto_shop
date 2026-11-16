"""Точка входу вебзастосунку MOTOREX.

Тут створюється Flask-застосунок, задається конфігурація,
реєструються Blueprint-и (групи маршрутів) і загальні для всіх
шаблонів змінні та фільтри.
"""
import os
from datetime import datetime

from flask import Flask, render_template

import models
from routes import admin_bp, feedback_bp

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


@app.context_processor
def inject_globals():
    """Змінні, доступні в усіх шаблонах."""
    return {
        'current_year': datetime.now().year,
    }


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/about')
def about():
    return render_template('about.html')


# Магазин поки що статичний; у наступному етапі він переїде в routes/shop.py
@app.route('/shop')
def shop():
    return render_template('shop.html')


if __name__ == '__main__':
    # debug=True: автоматичний перезапуск після змін і детальні помилки.
    # Використовується лише під час розробки.
    app.run(debug=True)
