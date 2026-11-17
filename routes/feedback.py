"""Сторінка «Зворотний зв'язок»: показ контактів і форма відгуку (CREATE)."""
import re

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

import models

feedback_bp = Blueprint('feedback', __name__)

# Проста перевірка формату email: щось@щось.щось
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def validate_feedback(form):
    """Повертає список помилок. Порожній список = дані коректні."""
    errors = []
    if not form['name']:
        errors.append("Вкажіть ім'я.")
    elif len(form['name']) > 100:
        errors.append("Ім'я задовге (до 100 символів).")
    if not EMAIL_RE.match(form['email']):
        errors.append('Вкажіть коректний email.')
    if len(form['message']) < 5:
        errors.append('Повідомлення має містити щонайменше 5 символів.')
    elif len(form['message']) > 2000:
        errors.append('Повідомлення задовге (до 2000 символів).')
    return errors


@feedback_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    # Порожня форма для GET-запиту
    form = {'name': '', 'email': '', 'message': ''}
    # Якщо користувач увійшов, підставляємо його ім'я та email
    if g.user:
        form.update(name=g.user['name'], email=g.user['email'])

    if request.method == 'POST':
        form = {key: request.form.get(key, '').strip() for key in form}
        errors = validate_feedback(form)
        if errors:
            for error in errors:
                flash(error, 'error')
            # Повертаємо форму з уже введеними даними, щоб не набирати знову
            return render_template('contact.html', form=form), 400

        models.add_feedback(form['name'], form['email'], form['message'])
        flash('Дякуємо! Ваше повідомлення надіслано.', 'success')
        # PRG (Post/Redirect/Get): після POST робимо redirect,
        # щоб оновлення сторінки (F5) не надсилало форму повторно
        return redirect(url_for('feedback.contact'))

    return render_template('contact.html', form=form)
