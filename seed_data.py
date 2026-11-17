"""Наповнює базу демонстраційними даними.
Запуск:  python seed_data.py   (на macOS: python3 seed_data.py)

Скрипт можна запускати повторно: якщо дані вже є, він їх не дублює.
Щоб почати «з чистого аркуша», видаліть файл db.sqlite і запустіть скрипт знову.
"""
from app import app
import models

# (марка, модель, кузов, пальне, коробка, рік, ціна $, фото, опис)
CARS = [
    ('Mercedes-AMG', 'CLS 53', 'Купе', 'Бензин', 'Автомат', 2019, 52900, 'img/mercedes-cls.jpg',
     'Чотиридверне купе зі спортивним характером, світлодіодною оптикою та багатою комплектацією.'),
    ('BMW', '3 Series', 'Седан', 'Бензин', 'Автомат', 2022, 38500, 'img/bmw-3.jpg',
     'Динамічний седан для тих, хто любить кермувати й цінує точну керованість.'),
    ('Audi', 'A6', 'Седан', 'Бензин', 'Автомат', 2025, 61000, 'img/audi-a6.jpg',
     'Просторий і тихий автомобіль для далеких поїздок та щоденних ділових справ.'),
    ('Volkswagen', 'Golf', 'Хетчбек', 'Бензин', 'Механіка', 2020, 17900, 'img/vw-golf.jpg',
     'Компактний і практичний хетчбек — зручний у місті та економний у повсякденних поїздках.'),
    ('Toyota', 'Camry', 'Седан', 'Бензин', 'Автомат', 2018, 21500, 'img/toyota-camry.jpg',
     'Надійний сімейний седан із просторим салоном і великим багажником.'),
    ('Škoda', 'Octavia', 'Ліфтбек', 'Дизель', 'Автомат', 2021, 22800, 'img/skoda-octavia.jpg',
     "Практичний автомобіль для сім'ї: місткий багажник і помірна витрата пального."),
    ('Tesla', 'Model 3', 'Седан', 'Електро', 'Автомат', 2023, 36900, 'img/tesla-model3.jpg',
     'Електромобіль із запасом ходу понад 400 км, мінімалістичним салоном і швидким розгоном.'),
    ('Toyota', 'RAV4 Plug-in Hybrid', 'Кросовер', 'Гібрид', 'Автомат', 2024, 44500, 'img/toyota-rav4.jpg',
     'Гібридний кросовер із повним приводом: економний у місті та впевнений на ґрунтовій дорозі.'),
    ('Kia', 'Sportage', 'Кросовер', 'Бензин', 'Автомат', 2025, 31200, 'img/kia-sportage.jpg',
     'Сучасний сімейний кросовер із великим екраном мультимедіа та довгою гарантією.'),
]

# Демонстраційні облікові записи. Паролі — ЛИШЕ для навчального проєкту.
USERS = [
    ('Адміністратор MOTOREX', 'admin@motorex.ua', 'admin123', 'admin'),
    ('Тестовий клієнт', 'client@motorex.ua', 'client123', 'client'),
]


def seed():
    models.init_db()

    for name, email, password, role in USERS:
        if models.get_user_by_email(email) is None:
            models.create_user(name, email, password, role)
            print(f'Користувач {email} ({role}) створений, пароль: {password}')

    if models.get_cars():
        print('Автомобілі вже є в базі — пропускаю.')
        return

    db = models.get_db()
    with db:  # усі авто — однією транзакцією
        db.executemany(
            'INSERT INTO cars (brand, name, body_type, fuel, transmission, year, price, image, description) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            CARS,
        )
    print(f'Додано автомобілів: {len(CARS)}')

    cars = models.get_cars()
    models.create_order('Іван Петренко', 'ivan@example.com', '+380 67 123 45 67',
                        'Цікавить кредит', {cars[0]['id']: 1})
    models.add_feedback('Тестовий користувач', 'user@example.com',
                        'Підкажіть, будь ласка, чи є Škoda Octavia з автоматом?')
    models.add_test_drive(cars[1]['id'], 'Олена Коваль', '+380 50 765 43 21', 'olena@example.com',
                          models.today(), 'Зручно після 15:00')
    print('Додано тестове замовлення та відгук.')


if __name__ == '__main__':
    with app.app_context():
        seed()
