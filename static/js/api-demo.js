// ============================================
// НАЛАШТУВАННЯ
// ============================================

// Відносна адреса: сторінку віддає той самий Flask-сервер, що й API,
// тому джерело (origin) одне й те саме і CORS не потрібен.
const API_URL = '/api/v1/feedback';

const MESSAGE_HIDE_MS = 5000;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;   // той самий вираз, що й на сервері (api_common.py)
const FIELD_LABELS = { name: "Ім'я", email: 'Email', message: 'Повідомлення' };

const addForm = document.getElementById('addForm');
const submitButton = document.getElementById('submitButton');
const reloadButton = document.getElementById('reloadButton');
const loadingBox = document.getElementById('loading');
const messageBox = document.getElementById('message');
const dataList = document.getElementById('dataList');
const itemsCount = document.getElementById('itemsCount');

// Помилка, яку повернув API (400, 404, 500...). status = 0: відповіді від сервера не було.
class ApiError extends Error {
    constructor(message, status = 0, details = []) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.details = details;
    }
}

// ============================================
// ДОПОМІЖНІ ФУНКЦІЇ
// ============================================

let hideTimer = null;

function showLoading(show) {
    loadingBox.classList.toggle('hidden', !show);
}

function hideMessage() {
    clearTimeout(hideTimer);
    messageBox.textContent = '';
    messageBox.className = 'hidden';
}

// Успіх зникає за 5 секунд, помилка лишається, поки користувач не зробить наступну дію.
function showMessage(text, type) {
    clearTimeout(hideTimer);
    const isSuccess = type === 'success';
    messageBox.textContent = (isSuccess ? '✅ ' : '❌ ') + text;   // textContent: це текст, а не HTML
    messageBox.className = 'mb-6 whitespace-pre-line rounded-lg border px-4 py-3 ' +
        (isSuccess ? 'border-green-300 bg-green-50 text-green-800'
                   : 'border-red-300 bg-red-50 text-red-800');
    if (isSuccess) hideTimer = setTimeout(hideMessage, MESSAGE_HIDE_MS);
}

// Читає тіло помилки API: {"error": "...", "status_code": 400, "details": [{"field", "message"}]}
async function readApiError(response) {
    let body = null;
    try {
        body = await response.json();
    } catch {
        // відповідь не JSON (наприклад, HTML-сторінка помилки): покажемо загальний текст
    }
    const message = body?.error || `HTTP помилка! Статус: ${response.status}`;
    const details = Array.isArray(body?.details) ? body.details : [];
    return new ApiError(message, response.status, details);
}

// Перетворює будь-яку помилку на зрозумілий текст для користувача.
function friendlyMessage(error) {
    if (error instanceof ApiError) {
        if (error.status >= 500) return 'На сервері сталася помилка. Спробуйте пізніше.';
        if (error.status === 404) return 'Потрібний ресурс не знайдено.';
        const lines = error.details.map(d => `${FIELD_LABELS[d.field] || d.field}: ${d.message}`);
        return [error.message, ...lines].join('\n');
    }
    if (error instanceof TypeError) {
        // fetch кидає TypeError, коли відповіді немає взагалі: сервер вимкнено, немає мережі, CORS
        return "Не вдалося зв'язатися із сервером. Перевірте, що застосунок запущено.";
    }
    return 'Сталася невідома помилка. Подивіться консоль браузера (F12).';
}

// ============================================
// ВАЛІДАЦІЯ ФОРМИ (на клієнті, до відправки)
// ============================================

function validate(values) {
    const errors = {};
    if (!values.name) errors.name = "Вкажіть ім'я.";
    else if (values.name.length > 100) errors.name = "Ім'я задовге (до 100 символів).";

    if (!EMAIL_RE.test(values.email)) errors.email = 'Вкажіть коректний email.';

    if (values.message.length < 5) errors.message = 'Повідомлення має містити щонайменше 5 символів.';
    else if (values.message.length > 2000) errors.message = 'Повідомлення задовге (до 2000 символів).';
    return errors;
}

function clearFieldErrors() {
    document.querySelectorAll('[data-error-for]').forEach(slot => { slot.textContent = ''; });
}

function showFieldErrors(errors) {
    clearFieldErrors();
    for (const [field, message] of Object.entries(errors)) {
        const slot = document.querySelector(`[data-error-for="${field}"]`);
        if (slot) slot.textContent = message;
    }
}

// Помилки сервера [{"field": "email", "message": "..."}] -> {email: "..."}
function detailsToFieldErrors(details) {
    const errors = {};
    for (const d of details) errors[d.field] = d.message;
    return errors;
}

// ============================================
// ВІДОБРАЖЕННЯ ДАНИХ
// ============================================

function buildItem(item) {
    // Дані від користувача вставляємо через textContent, а не innerHTML:
    // так введений у форму HTML-код не виконається на сторінці.
    const card = document.createElement('div');
    card.className = 'rounded-lg border border-zinc-200 p-3';

    const head = document.createElement('div');
    head.className = 'flex items-center justify-between gap-2';

    const title = document.createElement('h3');
    title.className = 'font-semibold';
    title.textContent = item.name || 'Без імені';

    const date = document.createElement('span');
    date.className = 'text-xs text-zinc-500';
    date.textContent = item.created_at || '';

    const text = document.createElement('p');
    text.className = 'mt-1 whitespace-pre-line break-words text-zinc-700';
    text.textContent = item.message || 'Без тексту';

    head.append(title, date);
    card.append(head, text);

    if (item.is_processed) {
        const badge = document.createElement('span');
        badge.className = 'mt-2 inline-block rounded bg-green-100 px-2 py-0.5 text-xs text-green-800';
        badge.textContent = 'Опрацьовано';
        card.append(badge);
    }
    return card;
}

function displayData(items) {
    dataList.replaceChildren();
    itemsCount.textContent = String(items ? items.length : 0);

    if (!items || items.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-zinc-500';
        empty.textContent = '📭 Відгуків поки немає. Залиште перший!';
        dataList.append(empty);
        return;
    }
    for (const item of items) {
        dataList.append(buildItem(item));
    }
}

// ============================================
// РОБОТА З API
// ============================================

// Завантажує всі відгуки (GET)
async function loadData() {
    try {
        showLoading(true);
        const response = await fetch(API_URL, { headers: { Accept: 'application/json' } });

        // fetch НЕ вважає 404/500 помилкою, тому перевіряємо response.ok самі
        if (!response.ok) throw await readApiError(response);

        displayData(await response.json());
    } catch (error) {
        showMessage('Помилка завантаження. ' + friendlyMessage(error), 'error');
        console.error('Помилка:', error);
    } finally {
        showLoading(false);   // виконається і при успіху, і при помилці
    }
}

// Додає новий відгук (POST). Повертає true, якщо запис збережено.
async function addItem(itemData) {
    submitButton.disabled = true;   // захист від подвійного кліку
    try {
        showLoading(true);
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify(itemData),
        });
        if (!response.ok) throw await readApiError(response);

        const created = await response.json();
        showMessage(`Дякуємо! Відгук №${created.id} збережено.`, 'success');
        await loadData();
        return true;
    } catch (error) {
        if (error instanceof ApiError && error.status === 400) {
            showFieldErrors(detailsToFieldErrors(error.details));   // помилки сервера під полями
        }
        showMessage('Помилка додавання. ' + friendlyMessage(error), 'error');
        console.error('Помилка:', error);
        return false;
    } finally {
        submitButton.disabled = false;
        showLoading(false);
    }
}

// ============================================
// ОБРОБКА ФОРМИ
// ============================================

addForm.addEventListener('submit', async (event) => {
    event.preventDefault();   // не дозволяємо браузеру перезавантажити сторінку
    hideMessage();
    clearFieldErrors();

    const data = new FormData(addForm);
    const itemData = {
        name: String(data.get('name')).trim(),
        email: String(data.get('email')).trim(),
        message: String(data.get('message')).trim(),
    };

    const errors = validate(itemData);
    if (Object.keys(errors).length > 0) {
        showFieldErrors(errors);
        showMessage('Виправте помилки у формі.', 'error');
        return;   // на сервер нічого не відправляємо
    }

    const saved = await addItem(itemData);
    if (saved) addForm.reset();   // форму очищуємо лише після успішного збереження
});

reloadButton.addEventListener('click', loadData);

// ============================================
// ІНІЦІАЛІЗАЦІЯ
// ============================================

loadData();
