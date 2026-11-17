"""Адмін-панель MOTOREX (усі адреси починаються з /admin)."""
import sqlite3

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

import models

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
def require_admin():
    """Виконується перед КОЖНИМ маршрутом адмінки.
    Гість -> на сторінку входу; клієнт -> помилка 403 (доступ заборонено)."""
    if g.user is None:
        flash('Увійдіть як адміністратор, щоб відкрити адмін-панель.', 'error')
        return redirect(url_for('auth.login', next=request.path))
    if g.user['role'] != 'admin':
        abort(403)


@admin_bp.route('/')
def dashboard():
    """Головна сторінка адмінки: короткі підсумки по таблицях."""
    stats = {
        'feedback': models.count_rows('feedback'),
        'cars': models.count_rows('cars'),
        'orders': models.count_rows('orders'),
        'test_drives': models.count_rows('test_drives'),
        'users': models.count_rows('users'),
    }
    return render_template('admin/dashboard.html', stats=stats)


# ------------------------------------------------------------------ відгуки

@admin_bp.route('/feedback')
def feedback():
    return render_template('admin/feedback.html', feedback=models.get_feedback())


@admin_bp.route('/feedback/<int:feedback_id>/toggle', methods=['POST'])
def toggle_feedback(feedback_id):
    models.toggle_feedback(feedback_id)
    flash('Статус відгуку змінено.', 'success')
    return redirect(url_for('admin.feedback'))


@admin_bp.route('/feedback/<int:feedback_id>/delete', methods=['POST'])
def delete_feedback(feedback_id):
    # Видалення лише через POST: GET-посилання може випадково «відкрити»
    # браузер або пошуковий робот, і дані зникнуть.
    models.delete_feedback(feedback_id)
    flash('Відгук видалено.', 'success')
    return redirect(url_for('admin.feedback'))


# --------------------------------------------------------------- автомобілі

CAR_FIELDS = ['brand', 'name', 'body_type', 'fuel', 'transmission', 'year', 'price', 'image', 'description']


def parse_car_form(form):
    """Читає і перевіряє поля форми авто. Повертає (data, errors)."""
    data = {field: form.get(field, '').strip() for field in CAR_FIELDS}
    errors = []

    if not data['brand'] or not data['name']:
        errors.append('Вкажіть марку та модель.')
    if data['body_type'] not in models.BODY_TYPES:
        errors.append('Оберіть тип кузова зі списку.')
    if data['fuel'] not in models.FUEL_TYPES:
        errors.append('Оберіть тип пального зі списку.')
    if data['transmission'] not in models.TRANSMISSIONS:
        errors.append('Оберіть коробку передач зі списку.')
    try:
        data['year'] = int(data['year'])
        if not 1950 <= data['year'] <= 2100:
            raise ValueError
    except ValueError:
        errors.append('Рік має бути числом від 1950 до 2100.')
    try:
        data['price'] = float(data['price'])
        if data['price'] < 0:
            raise ValueError
    except ValueError:
        errors.append('Ціна має бути невідʼємним числом.')
    return data, errors


@admin_bp.route('/cars')
def cars():
    return render_template('admin/cars.html', cars=models.get_cars())


@admin_bp.route('/cars/new', methods=['GET', 'POST'])
def car_new():
    if request.method == 'POST':
        data, errors = parse_car_form(request.form)
        if not errors:
            models.add_car(data)
            flash(f'Авто «{data["brand"]} {data["name"]}» додано.', 'success')
            return redirect(url_for('admin.cars'))
        for error in errors:
            flash(error, 'error')
        return render_template('admin/car_form.html', car=data, models=models), 400
    return render_template('admin/car_form.html', car=None, models=models)


@admin_bp.route('/cars/<int:car_id>/edit', methods=['GET', 'POST'])
def car_edit(car_id):
    car = models.get_car(car_id)
    if car is None:
        flash('Такого авто не існує.', 'error')
        return redirect(url_for('admin.cars'))

    if request.method == 'POST':
        data, errors = parse_car_form(request.form)
        if not errors:
            models.update_car(car_id, data)
            flash('Зміни збережено.', 'success')
            return redirect(url_for('admin.cars'))
        for error in errors:
            flash(error, 'error')
        return render_template('admin/car_form.html', car={**data, 'id': car_id}, models=models), 400
    return render_template('admin/car_form.html', car=car, models=models)


@admin_bp.route('/cars/<int:car_id>/delete', methods=['POST'])
def car_delete(car_id):
    try:
        models.delete_car(car_id)
        flash('Авто видалено.', 'success')
    except sqlite3.IntegrityError:
        # Спрацював ON DELETE RESTRICT: авто є в замовленнях
        flash('Не можна видалити авто, яке вже є в замовленнях.', 'error')
    return redirect(url_for('admin.cars'))


# --------------------------------------------------------------- замовлення

@admin_bp.route('/orders')
def orders():
    status = request.args.get('status', '')
    return render_template('admin/orders.html', orders=models.get_orders(status),
                           statuses=models.ORDER_STATUSES, current_status=status)


@admin_bp.route('/orders/<int:order_id>')
def order_details(order_id):
    order, items = models.get_order_details(order_id)
    if order is None:
        flash('Замовлення не знайдено.', 'error')
        return redirect(url_for('admin.orders'))
    return render_template('admin/order_details.html', order=order, items=items,
                           statuses=models.ORDER_STATUSES)


@admin_bp.route('/orders/<int:order_id>/status', methods=['POST'])
def order_status(order_id):
    try:
        models.update_order_status(order_id, request.form.get('status', ''))
        flash(f'Статус замовлення №{order_id} оновлено.', 'success')
    except ValueError as error:
        flash(str(error), 'error')
    return redirect(url_for('admin.order_details', order_id=order_id))


@admin_bp.route('/orders/<int:order_id>/delete', methods=['POST'])
def order_delete(order_id):
    models.delete_order(order_id)
    flash(f'Замовлення №{order_id} видалено.', 'success')
    return redirect(url_for('admin.orders'))


# ------------------------------------------------- тест-драйви (Рівень 2)

@admin_bp.route('/test-drives')
def test_drives():
    status = request.args.get('status', '')
    return render_template('admin/test_drives.html', test_drives=models.get_test_drives(status),
                           statuses=models.TEST_DRIVE_STATUSES, current_status=status)


@admin_bp.route('/test-drives/<int:test_drive_id>/status', methods=['POST'])
def test_drive_status(test_drive_id):
    try:
        models.update_test_drive_status(test_drive_id, request.form.get('status', ''))
        flash('Статус заявки оновлено.', 'success')
    except ValueError as error:
        flash(str(error), 'error')
    return redirect(url_for('admin.test_drives'))


@admin_bp.route('/test-drives/<int:test_drive_id>/delete', methods=['POST'])
def test_drive_delete(test_drive_id):
    models.delete_test_drive(test_drive_id)
    flash('Заявку видалено.', 'success')
    return redirect(url_for('admin.test_drives'))


# ------------------------------------------------- користувачі (Рівень 3)

@admin_bp.route('/users')
def users():
    return render_template('admin/users.html', users=models.get_users(),
                           roles=models.ROLES, role_names=models.ROLE_NAMES)


@admin_bp.route('/users/<int:user_id>/role', methods=['POST'])
def user_role(user_id):
    # Захист від ситуації «адмін забрав права сам у себе і більше не може зайти»
    if user_id == g.user['id']:
        flash('Не можна змінити роль власного облікового запису.', 'error')
        return redirect(url_for('admin.users'))
    try:
        models.update_user_role(user_id, request.form.get('role', ''))
        flash('Роль користувача змінено.', 'success')
    except ValueError as error:
        flash(str(error), 'error')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def user_delete(user_id):
    if user_id == g.user['id']:
        flash('Не можна видалити власний обліковий запис.', 'error')
        return redirect(url_for('admin.users'))
    models.delete_user(user_id)
    flash('Користувача видалено.', 'success')
    return redirect(url_for('admin.users'))
