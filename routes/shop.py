"""Магазин: каталог із пошуком і фільтрами, кошик, оформлення замовлення."""
import re

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

import models

shop_bp = Blueprint('shop', __name__)

MAX_QUANTITY = 5  # більше 5 однакових авто в одному замовленні не дозволяємо
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PHONE_RE = re.compile(r'^\+?[\d\s()-]{10,20}$')


# ------------------------------------------------------------------ кошик

def get_cart():
    """Кошик у сесії: {id авто: кількість}. JSON у cookie зберігає ключі рядками,
    тому перетворюємо їх на int."""
    return {int(car_id): qty for car_id, qty in session.get('cart', {}).items()}


def save_cart(cart):
    session['cart'] = {str(car_id): qty for car_id, qty in cart.items()}


def build_cart_lines():
    """Рядки кошика з актуальними даними з БД (назва й ціна беруться з бази, не з сесії)."""
    cart = get_cart()
    lines = [
        {'car': car, 'quantity': cart[car['id']], 'subtotal': car['price'] * cart[car['id']]}
        for car in models.get_cars_by_ids(cart.keys())
    ]
    # Якщо авто видалили з каталогу, прибираємо його і з кошика
    if len(lines) != len(cart):
        save_cart({line['car']['id']: line['quantity'] for line in lines})
    return lines


def parse_price(value):
    """'25000' -> 25000.0; порожнє або некоректне значення -> None (фільтр не застосовується)."""
    try:
        price = float(value)
        return price if price >= 0 else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- каталог

@shop_bp.route('/shop')
def shop():
    # Параметри фільтрів приходять з адресного рядка: /shop?q=bmw&fuel=Бензин
    filters = {
        'q': request.args.get('q', '').strip(),
        'brand': request.args.get('brand', ''),
        'body_type': request.args.get('body_type', ''),
        'fuel': request.args.get('fuel', ''),
        'transmission': request.args.get('transmission', ''),
        'price_min': request.args.get('price_min', ''),
        'price_max': request.args.get('price_max', ''),
        'sort': request.args.get('sort', 'new'),
    }
    cars = models.search_cars(
        q=filters['q'],
        brand=filters['brand'],
        body_type=filters['body_type'],
        fuel=filters['fuel'],
        transmission=filters['transmission'],
        price_min=parse_price(filters['price_min']),
        price_max=parse_price(filters['price_max']),
        sort=filters['sort'],
    )
    # Чи вибрано хоч один фільтр (щоб показати кнопку «Скинути»)
    is_filtered = any(value for key, value in filters.items() if key != 'sort')
    return render_template(
        'shop.html',
        cars=cars,
        filters=filters,
        is_filtered=is_filtered,
        brands=models.get_brands(),
        body_types=models.BODY_TYPES,
        fuel_types=models.FUEL_TYPES,
        transmissions=models.TRANSMISSIONS,
        sort_options=models.SORT_OPTIONS,
    )


# ------------------------------------------------------------------ кошик

@shop_bp.route('/cart/add/<int:car_id>', methods=['POST'])
def add_to_cart(car_id):
    car = models.get_car(car_id)
    if car is None:
        flash('Такого авто не існує.', 'error')
        return redirect(url_for('shop.shop'))

    cart = get_cart()
    cart[car_id] = min(cart.get(car_id, 0) + 1, MAX_QUANTITY)
    save_cart(cart)
    flash(f'«{car["brand"]} {car["name"]}» додано до кошика.', 'success')
    # Повертаємо туди, звідки натиснули кнопку (зі збереженням фільтрів).
    # Дозволяємо лише внутрішні адреси нашого сайту ('/shop?...'), а не чужі сайти.
    next_url = request.form.get('next', '')
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = url_for('shop.shop')
    return redirect(next_url)


@shop_bp.route('/cart')
def cart():
    lines = build_cart_lines()
    total = sum(line['subtotal'] for line in lines)
    form = {'customer_name': '', 'email': '', 'phone': '', 'comment': ''}
    return render_template('cart.html', lines=lines, total=total,
                           max_quantity=MAX_QUANTITY, form=form)


@shop_bp.route('/cart/update/<int:car_id>', methods=['POST'])
def update_cart(car_id):
    cart = get_cart()
    if car_id in cart:
        try:
            quantity = int(request.form.get('quantity', 1))
        except ValueError:
            quantity = 1
        quantity = max(0, min(quantity, MAX_QUANTITY))
        if quantity == 0:
            del cart[car_id]
        else:
            cart[car_id] = quantity
        save_cart(cart)
    return redirect(url_for('shop.cart'))


@shop_bp.route('/cart/remove/<int:car_id>', methods=['POST'])
def remove_from_cart(car_id):
    cart = get_cart()
    cart.pop(car_id, None)
    save_cart(cart)
    flash('Авто прибрано з кошика.', 'success')
    return redirect(url_for('shop.cart'))


# ------------------------------------------------------- оформлення замовлення

@shop_bp.route('/checkout', methods=['POST'])
def checkout():
    form = {key: request.form.get(key, '').strip()
            for key in ('customer_name', 'email', 'phone', 'comment')}

    errors = []
    if not form['customer_name']:
        errors.append("Вкажіть ім'я та прізвище.")
    if not EMAIL_RE.match(form['email']):
        errors.append('Вкажіть коректний email.')
    if not PHONE_RE.match(form['phone']):
        errors.append('Вкажіть телефон у форматі +380 XX XXX XX XX.')
    if not get_cart():
        errors.append('Кошик порожній.')

    if errors:
        for error in errors:
            flash(error, 'error')
        lines = build_cart_lines()
        return render_template('cart.html', lines=lines, total=sum(l['subtotal'] for l in lines),
                               max_quantity=MAX_QUANTITY, form=form), 400

    order_id = models.create_order(form['customer_name'], form['email'], form['phone'],
                                   form['comment'], get_cart())
    save_cart({})
    flash(f'Замовлення №{order_id} оформлено. Менеджер зв’яжеться з вами найближчим часом.', 'success')
    return redirect(url_for('shop.shop'))
