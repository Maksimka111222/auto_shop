"""Запис на тест-драйв (Рівень 2: додаткова таблиця test_drives)."""
import re

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

import models

test_drive_bp = Blueprint('test_drive', __name__)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PHONE_RE = re.compile(r'^\+?[\d\s()-]{10,20}$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')  # формат, який надсилає <input type="date">


@test_drive_bp.route('/test-drive/<int:car_id>', methods=['GET', 'POST'])
def book(car_id):
    car = models.get_car(car_id)
    if car is None:
        flash('Такого авто не існує.', 'error')
        return redirect(url_for('shop.shop'))

    form = {'customer_name': '', 'phone': '', 'email': '', 'preferred_date': '', 'comment': ''}
    if g.user:
        form.update(customer_name=g.user['name'], email=g.user['email'])

    if request.method == 'POST':
        form = {key: request.form.get(key, '').strip() for key in form}
        errors = []
        if not form['customer_name']:
            errors.append("Вкажіть ім'я.")
        if not PHONE_RE.match(form['phone']):
            errors.append('Вкажіть телефон у форматі +380 XX XXX XX XX.')
        if not EMAIL_RE.match(form['email']):
            errors.append('Вкажіть коректний email.')
        # Рядки 'РРРР-ММ-ДД' можна порівнювати як текст: '2026-11-20' > '2026-11-16'
        if not DATE_RE.match(form['preferred_date']) or form['preferred_date'] < models.today():
            errors.append('Оберіть дату, не раніше сьогоднішньої.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('test_drive.html', car=car, form=form, min_date=models.today()), 400

        models.add_test_drive(car_id, form['customer_name'], form['phone'], form['email'],
                              form['preferred_date'], form['comment'],
                              user_id=g.user['id'] if g.user else None)
        flash(f'Заявку на тест-драйв {car["brand"]} {car["name"]} прийнято. '
              f'Ми зателефонуємо, щоб підтвердити час.', 'success')
        return redirect(url_for('shop.shop'))

    return render_template('test_drive.html', car=car, form=form, min_date=models.today())
