"""Автоматичні тести MOTOREX (стандартна бібліотека unittest, нічого встановлювати не треба).

Запуск із папки проєкту:
    python -m unittest -v        (на macOS: python3 -m unittest -v)

Кожен тест працює з ОКРЕМОЮ тимчасовою БД, тому ваш db.sqlite не змінюється.
"""
import contextlib
import io
import os
import sqlite3
import tempfile
import unittest

from app import app
import models
import seed_data


class MotorexTestCase(unittest.TestCase):
    def setUp(self):
        # Тимчасовий файл БД для кожного тесту
        fd, self.db_path = tempfile.mkstemp(suffix='.sqlite')
        os.close(fd)
        app.config.update(TESTING=True, DATABASE=self.db_path)
        with app.app_context(), contextlib.redirect_stdout(io.StringIO()):
            seed_data.seed()  # повідомлення скрипта в тестах не виводимо
        self.client = app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def login(self, email='admin@motorex.ua', password='admin123'):
        return self.client.post('/login', data={'email': email, 'password': password})

    # ---------------------------------------------------------- сторінки
    def test_public_pages_open(self):
        for url in ['/', '/shop', '/about', '/contact', '/cart', '/login', '/register']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    # ----------------------------------------------------------- відгуки
    def test_feedback_create_and_delete(self):
        response = self.client.post('/contact', data={
            'name': 'Тест', 'email': 'test@example.com', 'message': 'Перевірка форми'})
        self.assertEqual(response.status_code, 302)  # PRG: redirect після POST
        with app.app_context():
            self.assertEqual(len(models.get_feedback()), 2)
            feedback_id = models.get_feedback()[0]['id']

        self.login()
        self.client.post(f'/admin/feedback/{feedback_id}/toggle')  # UPDATE
        with app.app_context():
            self.assertEqual(models.get_db().execute(
                'SELECT is_processed FROM feedback WHERE id = ?', (feedback_id,)).fetchone()[0], 1)
        self.client.post(f'/admin/feedback/{feedback_id}/delete')
        with app.app_context():
            self.assertEqual(len(models.get_feedback()), 1)

    def test_feedback_validation(self):
        response = self.client.post('/contact', data={'name': '', 'email': 'bad', 'message': ''})
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------ пошук і фільтри
    def test_search_and_filters(self):
        self.assertIn('Tesla Model 3'.encode(), self.client.get('/shop?fuel=Електро').data)
        self.assertNotIn(b'Golf', self.client.get('/shop?fuel=%D0%95%D0%BB%D0%B5%D0%BA%D1%82%D1%80%D0%BE').data)
        self.assertIn(b'Golf', self.client.get('/shop?q=golf').data)
        with app.app_context():
            cheap = models.search_cars(price_max=20000)
            self.assertTrue(all(car['price'] <= 20000 for car in cheap))

    def test_sql_injection_is_harmless(self):
        response = self.client.get("/shop?q=' OR 1=1 --&sort=price; DROP TABLE cars")
        self.assertEqual(response.status_code, 200)
        with app.app_context():
            self.assertEqual(len(models.get_cars()), len(seed_data.CARS))

    # ------------------------------------------------- кошик і замовлення
    def test_cart_and_checkout(self):
        with app.app_context():
            car = models.get_cars()[0]
        self.client.post(f'/cart/add/{car["id"]}')
        self.client.post(f'/cart/add/{car["id"]}')
        response = self.client.post('/checkout', data={
            'customer_name': 'Покупець', 'email': 'buyer@example.com',
            'phone': '+380 67 000 00 00', 'comment': ''})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            order = models.get_orders()[0]
            self.assertEqual(order['total_price'], car['price'] * 2)
            self.assertEqual(order['status'], 'Нове')

    def test_order_cascade_delete(self):
        with app.app_context():
            order_id = models.get_orders()[0]['id']
            models.delete_order(order_id)
            items = models.get_db().execute(
                'SELECT COUNT(*) FROM order_items WHERE order_id = ?', (order_id,)).fetchone()[0]
            self.assertEqual(items, 0)  # ON DELETE CASCADE

    def test_car_in_order_cannot_be_deleted(self):
        with app.app_context():
            order_id = models.get_orders()[0]['id']
            _, items = models.get_order_details(order_id)
            with self.assertRaises(sqlite3.IntegrityError):  # ON DELETE RESTRICT
                models.delete_car(items[0]['car_id'])

    # ----------------------------------------------------------- тест-драйв
    def test_test_drive_booking(self):
        with app.app_context():
            car_id = models.get_cars()[0]['id']
            today = models.today()
        ok = self.client.post(f'/test-drive/{car_id}', data={
            'customer_name': 'Олег', 'phone': '+380 63 111 22 33', 'email': 'oleg@example.com',
            'preferred_date': today, 'comment': ''})
        self.assertEqual(ok.status_code, 302)
        past = self.client.post(f'/test-drive/{car_id}', data={
            'customer_name': 'Олег', 'phone': '+380 63 111 22 33', 'email': 'oleg@example.com',
            'preferred_date': '2000-01-01', 'comment': ''})
        self.assertEqual(past.status_code, 400)

    # ------------------------------------------------------ користувачі й ролі
    def test_admin_requires_login(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_client_gets_403_in_admin(self):
        self.login('client@motorex.ua', 'client123')
        self.assertEqual(self.client.get('/admin/').status_code, 403)

    def test_admin_pages_open(self):
        self.login()
        for url in ['/admin/', '/admin/feedback', '/admin/cars', '/admin/cars/new',
                    '/admin/orders', '/admin/test-drives', '/admin/users']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_register_and_order_history(self):
        response = self.client.post('/register', data={
            'name': 'Новий', 'email': 'new@example.com', 'password': 'secret1', 'password2': 'secret1'})
        self.assertEqual(response.status_code, 302)
        # Повторна реєстрація з тим самим email (іншим регістром) -> помилка UNIQUE
        self.client.post('/logout')
        again = self.client.post('/register', data={
            'name': 'Дубль', 'email': 'NEW@example.com', 'password': 'secret1', 'password2': 'secret1'})
        self.assertEqual(again.status_code, 400)

        self.client.post('/login', data={'email': 'new@example.com', 'password': 'secret1'})
        with app.app_context():
            car_id = models.get_cars()[0]['id']
        self.client.post(f'/cart/add/{car_id}')
        self.client.post('/checkout', data={'customer_name': 'Новий', 'email': 'new@example.com',
                                            'phone': '+380 67 000 00 00', 'comment': ''})
        self.assertIn('Мої замовлення'.encode(), self.client.get('/account').data)
        with app.app_context():
            user = models.get_user_by_email('new@example.com')
            self.assertEqual(len(models.get_user_orders(user['id'])), 1)

    def test_password_is_hashed(self):
        with app.app_context():
            user = models.get_user_by_email('admin@motorex.ua')
            self.assertNotEqual(user['password_hash'], 'admin123')


if __name__ == '__main__':
    unittest.main()
