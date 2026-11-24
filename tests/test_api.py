"""Автотести REST API (ЛР5). Запуск: python -m unittest -v

Як і в tests/test_app.py, кожен тест працює з окремою тимчасовою БД,
тому ваш db.sqlite не змінюється.
"""
import contextlib
import io
import os
import tempfile
import unittest

from app import app
import models
import seed_data

JSON_HEADERS = {'Content-Type': 'application/json'}

NEW_CAR = {
    'brand': 'Toyota', 'name': 'Corolla', 'body_type': 'Седан', 'fuel': 'Бензин',
    'transmission': 'Автомат', 'year': 2022, 'price': 24500,
}
NEW_ORDER = {
    'customer_name': 'Іван Петренко', 'email': 'ivan@example.com',
    'phone': '+380 67 123 45 67', 'comment': '', 'items': [{'car_id': 1, 'quantity': 2}],
}


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.sqlite')
        os.close(fd)
        app.config.update(TESTING=True, DATABASE=self.db_path)
        with app.app_context(), contextlib.redirect_stdout(io.StringIO()):
            seed_data.seed()
        self.client = app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def assert_json_error(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertTrue(response.is_json, 'помилка API має бути JSON, а не HTML')
        body = response.get_json()
        self.assertEqual(body['status_code'], status)
        self.assertIn('error', body)
        return body

    # ------------------------------------------------------------- v1: авто
    def test_v1_list_and_get_car(self):
        response = self.client.get('/api/v1/cars')
        self.assertEqual(response.status_code, 200)
        cars = response.get_json()
        self.assertEqual(len(cars), len(seed_data.CARS))
        self.assertIs(cars[0]['in_stock'], True)
        one = self.client.get(f'/api/v1/cars/{cars[0]["id"]}')
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.get_json()['id'], cars[0]['id'])

    def test_v1_unknown_car_is_404_json(self):
        self.assert_json_error(self.client.get('/api/v1/cars/9999'), 404)

    def test_v1_car_full_lifecycle(self):
        created = self.client.post('/api/v1/cars', json=NEW_CAR)
        self.assertEqual(created.status_code, 201)
        car = created.get_json()
        self.assertTrue(created.headers['Location'].endswith(f'/api/v1/cars/{car["id"]}'))
        self.assertIs(car['in_stock'], True)

        put = self.client.put(f'/api/v1/cars/{car["id"]}', json={**NEW_CAR, 'price': 25000, 'in_stock': False})
        self.assertEqual(put.status_code, 200)
        self.assertEqual(put.get_json()['price'], 25000)
        self.assertIs(put.get_json()['in_stock'], False)

        patch = self.client.patch(f'/api/v1/cars/{car["id"]}', json={'price': 23900, 'in_stock': True})
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.get_json()['price'], 23900)
        self.assertEqual(patch.get_json()['brand'], 'Toyota')   # інші поля не зачеплено

        self.assertEqual(self.client.delete(f'/api/v1/cars/{car["id"]}').status_code, 204)
        self.assert_json_error(self.client.get(f'/api/v1/cars/{car["id"]}'), 404)

    def test_v1_car_validation(self):
        body = self.assert_json_error(self.client.post('/api/v1/cars', json={'brand': 'X'}), 400)
        self.assertIn('price', [d['field'] for d in body['details']])
        self.assert_json_error(self.client.post('/api/v1/cars', json={**NEW_CAR, 'price': 0}), 400)
        self.assert_json_error(self.client.post('/api/v1/cars', json={**NEW_CAR, 'year': '2022'}), 400)
        self.assert_json_error(self.client.post('/api/v1/cars', json={**NEW_CAR, 'fuel': 'Вода'}), 400)
        self.assert_json_error(self.client.patch('/api/v1/cars/1', json={'price': -5}), 400)
        self.assert_json_error(self.client.patch('/api/v1/cars/1', json={}), 400)

    def test_non_json_body_is_400(self):
        response = self.client.post('/api/v1/cars', data='це не json', headers={'Content-Type': 'text/plain'})
        self.assert_json_error(response, 400)

    def test_delete_car_from_order_is_409(self):
        with app.app_context():
            order_id = models.get_orders()[0]['id']
            car_id = models.get_order_details(order_id)[1][0]['car_id']
        self.assert_json_error(self.client.delete(f'/api/v1/cars/{car_id}'), 409)

    # ------------------------------------------------------- v1: замовлення
    def test_v1_create_order(self):
        response = self.client.post('/api/v1/orders', json=NEW_ORDER)
        self.assertEqual(response.status_code, 201)
        order = response.get_json()
        self.assertTrue(response.headers['Location'].endswith(f'/api/v1/orders/{order["id"]}'))
        self.assertEqual(order['status'], 'Нове')
        self.assertEqual(len(order['items']), 1)
        self.assertEqual(order['total_price'], order['items'][0]['unit_price'] * 2)

    def test_order_validation(self):
        self.assert_json_error(self.client.post('/api/v1/orders', json={**NEW_ORDER, 'items': []}), 400)
        bad_qty = {**NEW_ORDER, 'items': [{'car_id': 1, 'quantity': 0}]}
        self.assert_json_error(self.client.post('/api/v1/orders', json=bad_qty), 400)
        unknown_car = {**NEW_ORDER, 'items': [{'car_id': 9999, 'quantity': 1}]}
        self.assert_json_error(self.client.post('/api/v1/orders', json=unknown_car), 400)

    def test_order_for_out_of_stock_car_is_409(self):
        self.client.patch('/api/v1/cars/1', json={'in_stock': False})
        self.assert_json_error(self.client.post('/api/v1/orders', json=NEW_ORDER), 409)

    def test_order_status_patch(self):
        with app.app_context():
            order_id = models.get_orders()[0]['id']
        ok = self.client.patch(f'/api/v1/orders/{order_id}/status', json={'status': 'Виконане'})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.get_json()['status'], 'Виконане')
        self.assert_json_error(self.client.patch(f'/api/v1/orders/{order_id}/status', json={'status': 'Невідомий'}), 400)
        self.assert_json_error(self.client.patch('/api/v1/orders/9999/status', json={'status': 'Нове'}), 404)

    # --------------------------------------------------------- v1: відгуки
    def test_v1_feedback(self):
        created = self.client.post('/api/v1/feedback', json={
            'name': 'Олена', 'email': 'olena@example.com', 'message': 'Чудовий сайт!'})
        self.assertEqual(created.status_code, 201)
        self.assertIn('Location', created.headers)
        self.assertEqual(len(self.client.get('/api/v1/feedback').get_json()), 2)
        self.assert_json_error(self.client.post('/api/v1/feedback', json={
            'name': '', 'email': 'bad', 'message': 'x'}), 400)

    # ---------------------------------------------------- помилки загалом
    def test_unknown_api_path_and_wrong_method_are_json(self):
        self.assert_json_error(self.client.get('/api/v1/nothing'), 404)
        self.assert_json_error(self.client.delete('/api/v1/orders/1'), 405)

    def test_site_still_returns_html_404(self):
        response = self.client.get('/no-such-page')
        self.assertEqual(response.status_code, 404)
        self.assertIn('text/html', response.content_type)

    # ------------------------------------------------------------------ v2
    def test_v2_pagination_meta(self):
        body = self.client.get('/api/v2/cars?per_page=4&page=3').get_json()
        self.assertEqual(body['total'], len(seed_data.CARS))
        self.assertEqual((body['page'], body['per_page'], body['pages']), (3, 4, 3))
        self.assertEqual(len(body['items']), 1)
        self.assertIn('links', body['items'][0])

    def test_v2_search_filter_sort(self):
        body = self.client.get('/api/v2/cars?q=toyota&sort=price_desc').get_json()
        prices = [car['price'] for car in body['items']]
        self.assertEqual(len(prices), 2)
        self.assertEqual(prices, sorted(prices, reverse=True))
        electric = self.client.get('/api/v2/cars?fuel=Електро').get_json()
        self.assertEqual(electric['total'], 1)
        cheap = self.client.get('/api/v2/cars?price_max=20000').get_json()
        self.assertTrue(all(car['price'] <= 20000 for car in cheap['items']))

    def test_v2_bad_query_params_are_400(self):
        for url in ['/api/v2/cars?per_page=abc', '/api/v2/cars?page=0', '/api/v2/cars?sort=bad',
                    '/api/v2/cars?price_min=10&price_max=5', '/api/v2/cars?fuel=Вода',
                    '/api/v2/orders?status=Невідомий']:
            with self.subTest(url=url):
                self.assert_json_error(self.client.get(url), 400)

    def test_v2_orders_and_feedback(self):
        orders = self.client.get('/api/v2/orders').get_json()
        self.assertEqual(orders['total'], 1)
        self.assertIn('items', orders['items'][0])
        feedback = self.client.get('/api/v2/feedback?is_processed=false').get_json()
        self.assertEqual(feedback['total'], 1)

    # ------------------------------------------------------------- Swagger
    def test_swagger_is_available(self):
        self.assertEqual(self.client.get('/apidocs/').status_code, 200)
        for version in ('v1', 'v2'):
            spec = self.client.get(f'/apispec_{version}.json')
            self.assertEqual(spec.status_code, 200)
            self.assertTrue(any(path.startswith(f'/api/{version}') for path in spec.get_json()['paths']))


if __name__ == '__main__':
    unittest.main()
