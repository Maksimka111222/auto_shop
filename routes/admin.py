"""Адмін-панель MOTOREX (усі адреси починаються з /admin)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

import models

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/')
def dashboard():
    """Головна сторінка адмінки: короткі підсумки по таблицях."""
    stats = {
        'feedback': models.count_rows('feedback'),
        'cars': models.count_rows('cars'),
        'orders': models.count_rows('orders'),
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
