"""Користувачі та ролі (Рівень 3): реєстрація, вхід, вихід, особистий кабінет."""
import re
import sqlite3

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

import models

auth_bp = Blueprint('auth', __name__)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MIN_PASSWORD = 6


def load_current_user():
    """Перед кожним запитом: за user_id із сесії знаходимо користувача в БД.
    Результат кладемо в g.user (None — гість). У шаблонах доступно як g.user."""
    user_id = session.get('user_id')
    g.user = models.get_user(user_id) if user_id else None
    if user_id and g.user is None:
        # Користувача видалили, а cookie залишилась — «розлогінюємо»
        session.pop('user_id', None)


def safe_next(default_endpoint):
    """Адреса для переходу після входу. Тільки внутрішні адреси сайту (захист від open redirect)."""
    next_url = request.values.get('next', '')
    if next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return url_for(default_endpoint)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if g.user:
        return redirect(url_for('auth.account'))

    form = {'name': '', 'email': ''}
    if request.method == 'POST':
        form = {'name': request.form.get('name', '').strip(),
                'email': request.form.get('email', '').strip().lower()}
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        errors = []
        if not form['name']:
            errors.append("Вкажіть ім'я.")
        if not EMAIL_RE.match(form['email']):
            errors.append('Вкажіть коректний email.')
        if len(password) < MIN_PASSWORD:
            errors.append(f'Пароль має містити щонайменше {MIN_PASSWORD} символів.')
        if password != password2:
            errors.append('Паролі не збігаються.')

        if not errors:
            try:
                # Нові користувачі завжди отримують роль client.
                # Адміністратором може зробити лише інший адміністратор.
                user_id = models.create_user(form['name'], form['email'], password)
            except sqlite3.IntegrityError:
                # Спрацювало обмеження UNIQUE на колонці email
                errors.append('Користувач з таким email уже зареєстрований.')
            else:
                session.clear()
                session['user_id'] = user_id
                flash(f'Вітаємо, {form["name"]}! Обліковий запис створено.', 'success')
                return redirect(url_for('auth.account'))

        for error in errors:
            flash(error, 'error')
        return render_template('auth/register.html', form=form), 400

    return render_template('auth/register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        return redirect(url_for('auth.account'))

    email = ''
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = models.check_user(email, request.form.get('password', ''))
        if user is None:
            # Не уточнюємо, що саме неправильно (email чи пароль) — так безпечніше
            flash('Неправильний email або пароль.', 'error')
            return render_template('auth/login.html', email=email), 401

        # session.clear() перед входом — захист від фіксації сесії
        cart = session.get('cart', {})
        session.clear()
        session['cart'] = cart  # кошик гостя не губимо
        session['user_id'] = user['id']
        flash(f'Ви увійшли як {user["name"]}.', 'success')
        default = 'admin.dashboard' if user['role'] == 'admin' else 'auth.account'
        return redirect(safe_next(default))

    return render_template('auth/login.html', email=email)


@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    flash('Ви вийшли з облікового запису.', 'success')
    return redirect(url_for('home'))


@auth_bp.route('/account')
def account():
    """Особистий кабінет: історія замовлень і заявок на тест-драйв."""
    if g.user is None:
        flash('Увійдіть, щоб переглянути особистий кабінет.', 'error')
        return redirect(url_for('auth.login', next=request.path))
    return render_template(
        'auth/account.html',
        orders=models.get_user_orders(g.user['id']),
        test_drives=models.get_user_test_drives(g.user['id']),
        role_names=models.ROLE_NAMES,
    )
