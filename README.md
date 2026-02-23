# GenZ Quiz Bot — Управленческий профиль

Telegram-бот для тестирования руководителей на готовность к работе с новым поколением Z.
Включает веб-дашборд для управления сессиями, редактирования теста и просмотра аналитики.

## Быстрый старт (Docker)

```bash
cd uprav_quizze_bot
cp .env.example .env
# Заполните .env: BOT_TOKEN, DB_PASSWORD, ADMIN_SECRET, BOT_USERNAME

docker compose up -d --build
```

Дашборд: `http://localhost:8080`

## Без Docker

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# Создайте БД PostgreSQL: CREATE DATABASE uprav_quiz;
# Заполните .env
python main.py
```

## Архитектура

```
main.py                 — точка входа (бот + web)
config.py               — конфигурация из .env
database.py             — PostgreSQL через asyncpg
quiz.py                 — логика подсчёта и форматирование
quiz_defaults.py        — начальный контент (сидится в БД при первом запуске)
bot/handlers.py         — Telegram-хендлеры (aiogram 3 + FSM)
web/app.py              — aiohttp web-сервер + маршруты
web/templates/          — Jinja2 шаблоны дашборда
Dockerfile              — образ приложения
docker-compose.yml      — app + PostgreSQL
```

## Веб-дашборд

- **Сессии** — создание/удаление, deep link для QR-кода
- **Редактор теста** — редактирование вопросов, ответов и текстов результатов
- **Аналитика по сессии** — распределение стилей, разбивка по возрастам, автообновление
- **Общая аналитика** — агрегация по всем сессиям

## Режимы работы бота

- **Свободный**: `/start` — тест без привязки к мероприятию
- **Сессионный**: `t.me/BotName?start=session_id` — результат привязан к сессии
