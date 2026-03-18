# v00w - Связка Frontend + Backend

## Текущий статус

| Компонент | Статус | URL |
|-----------|--------|-----|
| Backend | ✅ Работает | `https://emt-8ed5e7d7-7037-4afe-b989-9609f9a4ccd7.preview.emergentagent.com/api/*` |
| MongoDB | ✅ Работает | localhost:27017 |
| Frontend | ⏳ Ждёт деплоя | Vercel |

---

## Для Frontend команды

### 1. Backend API URL для тестирования

```
https://emt-8ed5e7d7-7037-4afe-b989-9609f9a4ccd7.preview.emergentagent.com
```

### 2. Переменная окружения

В `.env` фронтенда:
```env
REACT_APP_BACKEND_URL=https://emt-8ed5e7d7-7037-4afe-b989-9609f9a4ccd7.preview.emergentagent.com
```

### 3. Проверка работы API

```bash
# Тест leaderboard
curl https://emt-8ed5e7d7-7037-4afe-b989-9609f9a4ccd7.preview.emergentagent.com/api/leaderboard

# Тест trust score
curl https://emt-8ed5e7d7-7037-4afe-b989-9609f9a4ccd7.preview.emergentagent.com/api/trust/123456789
```

---

## API Endpoints (Summary)

| Method | Endpoint | Описание |
|--------|----------|----------|
| POST | `/api/auth/validate` | Валидация Telegram WebApp |
| POST | `/api/user/register` | Регистрация пользователя |
| GET | `/api/trust/{telegram_id}` | Trust Score пользователя |
| POST | `/api/handshake/init` | Начать рукопожатие |
| POST | `/api/handshake/answer` | Ответить на вопрос |
| GET | `/api/handshake/session/{id}` | Статус сессии |
| GET | `/api/leaderboard` | Топ кругов |
| GET | `/api/challenge/{circle_id}` | Ежедневный челлендж |
| POST | `/api/challenge/answer` | Ответить на челлендж |

---

## Деплой Backend на Vercel

### 1. Структура файлов

```
backend/
├── server.py
├── requirements.txt
├── vercel.json
└── .env (НЕ коммитить!)
```

### 2. requirements.txt (исправленный)

```
fastapi==0.110.1
uvicorn==0.25.0
motor==3.3.1
python-dotenv==1.2.1
pydantic>=2.4.1,<3.0.0
starlette==0.37.2
aiogram==3.22.0
aiohttp>=3.9.0,<4.0.0
pymongo==4.5.0
dnspython==2.7.0
```

### 3. vercel.json

```json
{
  "builds": [
    {
      "src": "server.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "server.py"
    }
  ]
}
```

### 4. Vercel Environment Variables

В Vercel Dashboard → Settings → Environment Variables:

| Variable | Value |
|----------|-------|
| `MONGO_URL` | `mongodb+srv://user:pass@cluster.mongodb.net/` |
| `DB_NAME` | `trustleague` |
| `BOT_TOKEN` | `123456:ABC...` (опционально) |
| `SECRET_KEY` | `your_secret_key` |
| `FRONTEND_URL` | `https://your-frontend.vercel.app` |
| `CORS_ORIGINS` | `*` или `https://your-frontend.vercel.app` |

---

## Проблема которая была

**Причина:** В `requirements.txt` были несуществующие версии пакетов:
- `certifi==2026.2.25` ❌ (версия из будущего)
- `black==25.11.0` ❌ 
- Много лишних зависимостей

**Решение:** Оставлены только необходимые зависимости с корректными версиями.

---

## Тестовые данные в базе

После тестов в базе уже есть:
- 2 пользователя (Alice, Bob)
- 1 круг доверия (Гамма #379)
- 1 успешное рукопожатие
- 1 SBT Badge

---

## Следующие шаги

1. **Frontend:** Деплоить на Vercel с переменной `REACT_APP_BACKEND_URL`
2. **Backend:** 
   - Создать MongoDB Atlas кластер
   - Деплоить на Vercel с environment variables
   - Или использовать текущий preview URL для тестов
3. **Telegram Bot:** 
   - Создать бота через @BotFather
   - Добавить `BOT_TOKEN` в environment variables

---

## Контакт

Backend готов и работает. Можете тестировать API прямо сейчас!
