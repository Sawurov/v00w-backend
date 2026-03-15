# TrustLeague Backend - Инструкции для Frontend

## Backend API URL

**Production URL для Vercel:** Нужно задеплоить backend и использовать его URL

**Для тестирования на Emergent:**
```
https://emt-8ed5e7d7-7037-4afe-b989-9609f9a4ccd7.preview.emergentagent.com
```

---

## API Endpoints

### 1. Авторизация через Telegram WebApp

```
POST /api/auth/validate
Content-Type: application/json

Body:
{
  "initData": "<Telegram.WebApp.initData string>"
}

Response:
{
  "valid": true,
  "user": {
    "id": 123456789,
    "username": "user_name",
    "first_name": "Имя",
    "last_name": "Фамилия"
  }
}

// В dev режиме (без BOT_TOKEN) возвращает:
{
  "valid": true,
  "user": {"id": 0, "username": "dev"},
  "dev_mode": true
}
```

### 2. Регистрация/Обновление пользователя

```
POST /api/user/register
Content-Type: application/json

Body:
{
  "telegram_id": 123456789,
  "username": "user_name",
  "full_name": "Имя Фамилия"
}

Response:
{
  "id": "uuid",
  "telegram_id": 123456789,
  "username": "user_name",
  "full_name": "Имя Фамилия",
  "trust_score": 0,
  "trust_level": "bronze",
  "handshake_count": 0,
  "circle_id": null,
  "created_at": "2026-03-15T16:58:17.059575+00:00"
}
```

### 3. Получить Trust Score пользователя

```
GET /api/trust/{telegram_id}

Response:
{
  "score": 0,
  "level": "bronze",        // bronze | silver | gold | legend
  "handshake_count": 0,
  "circle": null,           // или объект круга
  "connections": [],        // последние 5 связей
  "username": "user_name",
  "full_name": "Имя Фамилия"
}
```

**Trust Levels:**
- bronze: 0+ баллов
- silver: 100+ баллов
- gold: 250+ баллов
- legend: 500+ баллов

### 4. Начать рукопожатие

```
POST /api/handshake/init
Content-Type: application/json

Body:
{
  "initiator_id": 123456789,
  "target_username": "friend_username"  // без @
}

Response:
{
  "session_id": "uuid",
  "question": "Какой последний фильм смотрели вместе?"
}
```

### 5. Ответить на вопрос рукопожатия

```
POST /api/handshake/answer
Content-Type: application/json

Body:
{
  "session_id": "uuid",
  "user_id": 123456789,
  "answer": "Ответ пользователя"
}

Response (ожидание второго участника):
{
  "waiting": true
}

Response (успешная верификация):
{
  "waiting": false,
  "result": "verified",
  "confidence": 0.85,
  "reason": "Ответы совпадают!",
  "nft_address": "EQ..."
}

Response (ответы не совпали):
{
  "waiting": false,
  "result": "failed",
  "confidence": 0.2,
  "reason": "Ответы не совпали. Попробуйте ещё раз!"
}
```

### 6. Получить статус сессии рукопожатия

```
GET /api/handshake/session/{session_id}

Response:
{
  "id": "uuid",
  "initiator_id": 123456789,
  "target_id": 987654321,
  "target_username": "friend",
  "question": "Вопрос",
  "initiator_answered": true,
  "target_answered": false,
  "status": "pending",      // pending | comparing | verified | failed
  "ai_confidence": null,
  "ai_reason": null,
  "nft_address": null,
  "created_at": "...",
  "expires_at": "..."
}
```

### 7. Лидерборд (топ кругов)

```
GET /api/leaderboard

Response:
{
  "circles": [
    {
      "id": "uuid",
      "name": "Альфа #123",
      "member_count": 5,
      "total_trust_score": 250,
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### 8. Получить ежедневный челлендж

```
GET /api/challenge/{circle_id}

Response:
{
  "id": "uuid",
  "circle_id": "uuid",
  "question": "Какой город является столицей Казахстана?",
  "options": ["Алматы", "Астана", "Шымкент", "Караганда"],
  "date": "2026-03-15"
}
```

### 9. Ответить на челлендж

```
POST /api/challenge/answer
Content-Type: application/json

Body:
{
  "challenge_id": "uuid",
  "user_id": 123456789,
  "answer_index": 1
}

Response:
{
  "correct": true,
  "explanation": "Астана — столица Казахстана с 1997 года.",
  "points_earned": 15,
  "correct_index": 1
}
```

---

## Настройка Frontend

### Environment Variables (.env)

```env
REACT_APP_BACKEND_URL=https://your-backend-url.vercel.app
```

### Пример интеграции (React)

```javascript
const API_URL = process.env.REACT_APP_BACKEND_URL;

// Авторизация при запуске WebApp
useEffect(() => {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    
    fetch(`${API_URL}/api/auth/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ initData: tg.initData })
    })
    .then(res => res.json())
    .then(data => {
      if (data.valid) {
        setUser(data.user);
        // Регистрация пользователя
        return fetch(`${API_URL}/api/user/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            telegram_id: data.user.id,
            username: data.user.username || '',
            full_name: `${data.user.first_name || ''} ${data.user.last_name || ''}`.trim()
          })
        });
      }
    });
  }
}, []);
```

---

## Requirements.txt (исправленный)

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

---

## Vercel Deployment

1. Создать `vercel.json` в корне backend:

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

2. Добавить Environment Variables в Vercel Dashboard:
   - `MONGO_URL` - MongoDB Atlas connection string
   - `DB_NAME` - trustleague
   - `BOT_TOKEN` - Telegram Bot Token (опционально)
   - `SECRET_KEY` - секретный ключ
   - `FRONTEND_URL` - URL фронтенда для WebApp кнопок
   - `CORS_ORIGINS` - разрешённые домены (или *)

---

## Тестирование API

```bash
# Проверка работы
curl https://your-backend-url/api/leaderboard

# Регистрация пользователя
curl -X POST https://your-backend-url/api/user/register \
  -H "Content-Type: application/json" \
  -d '{"telegram_id": 123, "username": "test", "full_name": "Test"}'
```
