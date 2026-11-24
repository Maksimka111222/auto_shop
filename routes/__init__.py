"""Пакет маршрутів. Кожен файл — окремий Blueprint (група сторінок або API)."""
from .admin import admin_bp
from .api_v1 import api_v1_bp
from .api_v2 import api_v2_bp
from .auth import auth_bp
from .feedback import feedback_bp
from .shop import shop_bp
from .test_drive import test_drive_bp
