# NEXORA Backend

FastAPI бэкенд для NEXORA — AI-платформы бизнес-аналитики.

## Стек
- **FastAPI** — API фреймворк
- **SQLAlchemy** — ORM, работает с SQLite (dev) и PostgreSQL (prod)
- **JWT** — авторизация
- **Anthropic Claude** — AI-аналитик
- **Stripe** — приём платежей
- **Pandas** — обработка CSV данных

## API эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| POST | /auth/register | Регистрация |
| POST | /auth/login | Вход, возвращает JWT токен |
| GET  | /auth/me | Профиль текущего юзера |
| POST | /data/upload | Загрузить CSV файл |
| GET  | /data/datasets | Список датасетов |
| POST | /data/chat | Задать вопрос AI о данных |
| POST | /waitlist/join | Добавить email в waitlist |
| GET  | /waitlist/count | Кол-во человек в waitlist |
| GET  | /waitlist/list | Список всех email (для тебя) |
| POST | /payments/create-checkout | Создать Stripe checkout |
| POST | /payments/webhook | Stripe webhook |
| GET  | /payments/subscription | Статус подписки |

## Быстрый старт (локально)

```bash
# 1. Клонируй / распакуй папку
cd nexora-backend

# 2. Создай виртуальное окружение
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Установи зависимости
pip install -r requirements.txt

# 4. Настрой переменные окружения
cp .env.example .env
# Открой .env и заполни ANTHROPIC_API_KEY и SECRET_KEY

# 5. Запусти сервер
python server.py
```

Сервер запустится на http://localhost:8000
Документация API: http://localhost:8000/docs

## Деплой на Railway (рекомендую)

```bash
# 1. Установи Railway CLI
npm install -g @railway/cli

# 2. Войди
railway login

# 3. Создай проект
railway init

# 4. Добавь PostgreSQL
railway add postgresql

# 5. Задай переменные окружения в Railway Dashboard:
#    DATABASE_URL — автоматически (из PostgreSQL плагина)
#    SECRET_KEY, ANTHROPIC_API_KEY, STRIPE_SECRET_KEY и т.д.

# 6. Деплой
railway up
```

## Подключение Stripe

1. Зарегистрируйся на stripe.com
2. Создай продукт "NEXORA Business" с ценой $49/месяц
3. Скопируй Price ID → в .env как STRIPE_PRICE_BUSINESS
4. Включи webhook на dashboard.stripe.com/webhooks:
   - URL: https://твой-домен.railway.app/payments/webhook
   - События: checkout.session.completed, customer.subscription.deleted

## Подключение лендинга к бэкенду

В файле startup-million.html найди функцию submitWaitlist() и замени:
```javascript
// Было (localStorage):
localStorage.setItem('nexora_waitlist', ...)

// Стало (реальный API):
await fetch('https://твой-домен.railway.app/waitlist/join', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({ email, source: 'landing' })
})
```
