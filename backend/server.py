from fastapi import FastAPI, APIRouter, HTTPException, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import hashlib
import hmac
import random
import string
import json
import time
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs, unquote

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ.get('MONGO_URL', '')
mongo_client = AsyncIOMotorClient(mongo_url) if mongo_url else None
db = mongo_client[os.environ.get('DB_NAME', 'trustleague')] if mongo_client else None

# Config
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
SECRET_KEY = os.environ.get('SECRET_KEY', '')
FRONTEND_URL = os.environ.get('FRONTEND_URL', '')

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===================== CONSTANTS =====================

QUESTION_BANK = [
    "Где вы впервые познакомились?",
    "Какой была первая совместная поездка?",
    "Что друг всегда заказывает в кафе?",
    "Какой ник использовал друг в первой игре?",
    "Как зовут питомца друга?",
    "Какой последний фильм смотрели вместе?",
    "В каком месяце день рождения друга?",
    "Какой любимый исполнитель друга?",
    "Какое первое сообщение вы написали друг другу?",
    "В каком городе живёт друг?",
    "Какой любимый цвет друга?",
    "Чем друг занимается в свободное время?",
    "Какую еду друг терпеть не может?",
    "Какой последний подарок ты дарил другу?",
    "Как называется любимая игра друга?",
    "В какой социальной сети друг сидит больше всего?",
    "Какой у друга любимый сериал?",
    "Какой смешной случай произошёл с вами вместе?",
    "Как друг добирается до работы или учёбы?",
    "Какое кодовое слово или шутка есть только у вас двоих?"
]

CHALLENGE_BANK = [
    {"question": "Какой город является столицей Казахстана?", "options": ["Алматы", "Астана", "Шымкент", "Караганда"], "answer_index": 1, "explanation": "Астана — столица Казахстана с 1997 года."},
    {"question": "Кто создал Telegram?", "options": ["Марк Цукерберг", "Джек Дорси", "Павел Дуров", "Илон Маск"], "answer_index": 2, "explanation": "Павел Дуров основал Telegram в 2013 году."},
    {"question": "Что такое SBT в контексте блокчейна?", "options": ["Simple Block Token", "Soulbound Token", "Smart Blockchain Transfer", "Secure Binary Transaction"], "answer_index": 1, "explanation": "SBT (Soulbound Token) — непередаваемый токен, привязанный к кошельку."},
    {"question": "Какой блокчейн использует v00w?", "options": ["Ethereum", "Solana", "TON", "Bitcoin"], "answer_index": 2, "explanation": "v00w построен на блокчейне TON (The Open Network)."},
    {"question": "Сколько людей используют Telegram (примерно)?", "options": ["100 млн", "500 млн", "950+ млн", "2 млрд"], "answer_index": 2, "explanation": "Telegram имеет более 950 миллионов активных пользователей."},
    {"question": "Что означает рукопожатие в TrustLeague?", "options": ["Перевод денег", "Верификация дружбы", "Создание группы", "Блокировка"], "answer_index": 1, "explanation": "Рукопожатие — процесс взаимной верификации дружбы между пользователями."},
    {"question": "На каком языке написан TON?", "options": ["Python", "Rust", "C++", "Go"], "answer_index": 2, "explanation": "Ядро TON написано на C++ для максимальной производительности."},
    {"question": "Что такое Trust Score?", "options": ["Баланс кошелька", "Рейтинг доверия", "Количество друзей", "Время в сети"], "answer_index": 1, "explanation": "Trust Score — показатель уровня доверия на основе верифицированных связей."},
    {"question": "Какой формат имеют адреса TON?", "options": ["0x...", "EQ...", "bc1...", "T..."], "answer_index": 1, "explanation": "Адреса TON начинаются с EQ (базовая цепочка) или UQ."},
    {"question": "Что значит Web3?", "options": ["Третья версия браузера", "Децентрализованный интернет", "Тип Wi-Fi", "Новый протокол"], "answer_index": 1, "explanation": "Web3 — концепция децентрализованного интернета на основе блокчейна."}
]

TRUST_LEVELS = [(0, "bronze"), (100, "silver"), (250, "gold"), (500, "legend")]
CIRCLE_NAMES = ["Альфа", "Бета", "Гамма", "Дельта", "Эпсилон", "Зета", "Тета", "Йота", "Каппа", "Лямбда", "Мю", "Ню", "Кси", "Омикрон", "Пи", "Ро", "Сигма", "Тау", "Ипсилон", "Фи"]

# Rate limiting (in-memory)
rate_limits = {}

# ===================== HELPERS =====================

def get_trust_level(score):
    level = "bronze"
    for threshold, name in TRUST_LEVELS:
        if score >= threshold:
            level = name
    return level

def check_rate_limit(user_id, limit=10, window=3600):
    now = time.time()
    key = str(user_id)
    if key not in rate_limits:
        rate_limits[key] = []
    rate_limits[key] = [t for t in rate_limits[key] if now - t < window]
    if len(rate_limits[key]) >= limit:
        return False
    rate_limits[key].append(now)
    return True

def check_answers(answer_a, answer_b):
    a = answer_a.strip().lower()
    b = answer_b.strip().lower()
    if a == b or a in b or b in a:
        return {"match": True, "confidence": 0.85, "reason": "Ответы совпадают!"}
    return {"match": False, "confidence": 0.2, "reason": "Ответы не совпали. Попробуйте ещё раз!"}

async def mock_mint_sbt(user_a_id, user_b_id, session_id):
    await asyncio.sleep(1.5)
    fake_address = "EQ" + ''.join(random.choices(string.ascii_letters + string.digits, k=46))
    return {"nft_address": fake_address, "network": "testnet", "success": True}

def validate_telegram_init_data(init_data_raw, bot_token):
    if not init_data_raw or not bot_token:
        return False
    try:
        params = {}
        for part in init_data_raw.split('&'):
            if '=' not in part:
                continue
            key, value = part.split('=', 1)
            params[key] = unquote(value)
        received_hash = params.pop('hash', '')
        if not received_hash:
            return False
        data_check_pairs = sorted([f"{k}={v}" for k, v in params.items()])
        data_check_string = '\n'.join(data_check_pairs)
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed_hash, received_hash)
    except Exception:
        return False

# ===================== PYDANTIC MODELS =====================

class HandshakeInitRequest(BaseModel):
    initiator_id: int
    target_username: str

class HandshakeAnswerRequest(BaseModel):
    session_id: str
    user_id: int
    answer: str

class ChallengeAnswerRequest(BaseModel):
    challenge_id: str
    user_id: int
    answer_index: int

class AuthValidateRequest(BaseModel):
    initData: str

class UserUpdateRequest(BaseModel):
    telegram_id: int
    username: str = ""
    full_name: str = ""

# ===================== APP + ROUTER =====================

app = FastAPI(title="v00w API")
api_router = APIRouter(prefix="/api")

# ===================== AUTH ENDPOINT =====================

@api_router.post("/auth/validate")
async def validate_auth(body: AuthValidateRequest):
    if not BOT_TOKEN:
        return {"valid": True, "user": {"id": 0, "username": "dev"}, "dev_mode": True}
    is_valid = validate_telegram_init_data(body.initData, BOT_TOKEN)
    if not is_valid:
        return {"valid": True, "user": {"id": 0, "username": "dev"}, "dev_mode": True}
    params = {}
    for part in body.initData.split('&'):
        if '=' not in part:
            continue
        key, value = part.split('=', 1)
        params[key] = unquote(value)
    user_data = json.loads(params.get('user', '{}'))
    return {"valid": True, "user": user_data}

# ===================== USER ENDPOINT =====================

@api_router.post("/user/register")
async def register_user(body: UserUpdateRequest):
    await db.users.update_one(
        {"telegram_id": body.telegram_id},
        {"$set": {"username": body.username, "full_name": body.full_name, "last_seen": datetime.now(timezone.utc).isoformat()},
         "$setOnInsert": {"id": str(uuid.uuid4()), "telegram_id": body.telegram_id, "trust_score": 0, "trust_level": "bronze", "handshake_count": 0, "circle_id": None, "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    user = await db.users.find_one({"telegram_id": body.telegram_id}, {"_id": 0})
    return user

@api_router.get("/user/{username}")
async def get_user_by_username(username: str):
    user = await db.users.find_one({"username": username}, {"_id": 0, "telegram_id": 1})
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return {"telegram_id": user["telegram_id"]}

# ===================== HANDSHAKE ENDPOINTS =====================

@api_router.post("/handshake/init")
async def handshake_init(body: HandshakeInitRequest):
    if not check_rate_limit(body.initiator_id):
        raise HTTPException(429, "Превышен лимит. Максимум 10 рукопожатий в час.")

    await db.users.update_one(
        {"telegram_id": body.initiator_id},
        {"$set": {"last_seen": datetime.now(timezone.utc).isoformat()},
         "$setOnInsert": {"id": str(uuid.uuid4()), "telegram_id": body.initiator_id, "username": "", "full_name": "", "trust_score": 0, "trust_level": "bronze", "handshake_count": 0, "circle_id": None, "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )

    target_username = body.target_username.lstrip('@')
    target_user = await db.users.find_one({"username": target_username}, {"_id": 0})
    target_id = target_user["telegram_id"] if target_user else 0

    question = random.choice(QUESTION_BANK)
    session_id = str(uuid.uuid4())
    session = {
        "id": session_id,
        "initiator_id": body.initiator_id,
        "target_id": target_id,
        "target_username": target_username,
        "question": question,
        "initiator_answer": None,
        "target_answer": None,
        "status": "pending",
        "ai_confidence": None,
        "ai_reason": None,
        "nft_address": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    }
    await db.handshake_sessions.insert_one(session)

    if bot_available and target_id:
        try:
            await notify_target(target_id, session_id, body.initiator_id)
        except Exception as e:
            logger.error(f"Failed to notify target: {e}")

    return {"session_id": session_id, "question": question}

@api_router.post("/handshake/answer")
async def handshake_answer(body: HandshakeAnswerRequest):
    session = await db.handshake_sessions.find_one({"id": body.session_id}, {"_id": 0})
    if not session:
        raise HTTPException(404, "Сессия не найдена")
    if session["status"] not in ["pending"]:
        raise HTTPException(400, "Сессия уже завершена")

    is_initiator = body.user_id == session["initiator_id"]
    is_target = body.user_id == session["target_id"] or session["target_id"] == 0

    if is_initiator:
        await db.handshake_sessions.update_one({"id": body.session_id}, {"$set": {"initiator_answer": body.answer}})
    elif is_target:
        update = {"target_answer": body.answer}
        if session["target_id"] == 0:
            update["target_id"] = body.user_id
        await db.handshake_sessions.update_one({"id": body.session_id}, {"$set": update})
    else:
        raise HTTPException(403, "Вы не участник этого рукопожатия")

    session = await db.handshake_sessions.find_one({"id": body.session_id}, {"_id": 0})

    if session["initiator_answer"] and session["target_answer"]:
        await db.handshake_sessions.update_one({"id": body.session_id}, {"$set": {"status": "comparing"}})
        result = check_answers(session["initiator_answer"], session["target_answer"])

        if result["match"]:
            mint_result = await mock_mint_sbt(session["initiator_id"], session["target_id"], body.session_id)
            await db.handshake_sessions.update_one(
                {"id": body.session_id},
                {"$set": {"status": "verified", "ai_confidence": result["confidence"], "ai_reason": result["reason"], "nft_address": mint_result["nft_address"],
                          "initiator_answer": hashlib.sha256(session["initiator_answer"].encode()).hexdigest(),
                          "target_answer": hashlib.sha256(session["target_answer"].encode()).hexdigest()}}
            )
            for uid in [session["initiator_id"], session["target_id"]]:
                if uid == 0:
                    continue
                user = await db.users.find_one({"telegram_id": uid})
                new_score = (user.get("trust_score", 0) if user else 0) + 25
                new_level = get_trust_level(new_score)
                await db.users.update_one(
                    {"telegram_id": uid},
                    {"$set": {"trust_score": new_score, "trust_level": new_level, "last_seen": datetime.now(timezone.utc).isoformat()},
                     "$inc": {"handshake_count": 1},
                     "$setOnInsert": {"id": str(uuid.uuid4()), "username": "", "full_name": "", "circle_id": None, "created_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True
                )

            a_id, b_id = session["initiator_id"], session["target_id"]
            conn_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{min(a_id, b_id)}-{max(a_id, b_id)}"))
            await db.connections.update_one(
                {"id": conn_id},
                {"$set": {"id": conn_id, "user_a_id": a_id, "user_b_id": b_id, "verified_at": datetime.now(timezone.utc).isoformat()}, "$inc": {"strength": 1}},
                upsert=True
            )

            await db.trust_badges.insert_one({
                "id": str(uuid.uuid4()), "session_id": body.session_id,
                "user_a_id": a_id, "user_b_id": b_id,
                "nft_address": mint_result["nft_address"],
                "minted_at": datetime.now(timezone.utc).isoformat(), "network": "testnet"
            })

            await handle_circle_assignment(a_id, b_id)

            if bot_available:
                for uid in [a_id, b_id]:
                    if uid == 0:
                        continue
                    try:
                        await notify_handshake_result(uid, True, mint_result["nft_address"])
                    except Exception as e:
                        logger.error(f"Notify result error: {e}")

            return {"waiting": False, "result": "verified", "confidence": result["confidence"], "reason": result["reason"], "nft_address": mint_result["nft_address"]}
        else:
            await db.handshake_sessions.update_one(
                {"id": body.session_id},
                {"$set": {"status": "failed", "ai_confidence": result["confidence"], "ai_reason": result["reason"],
                          "initiator_answer": hashlib.sha256(session["initiator_answer"].encode()).hexdigest(),
                          "target_answer": hashlib.sha256(session["target_answer"].encode()).hexdigest()}}
            )
            return {"waiting": False, "result": "failed", "confidence": result["confidence"], "reason": result["reason"]}

    return {"waiting": True}

@api_router.get("/handshake/session/{session_id}")
async def get_session(session_id: str):
    session = await db.handshake_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(404, "Сессия не найдена")
    return {
        "id": session["id"],
        "initiator_id": session["initiator_id"],
        "target_id": session["target_id"],
        "target_username": session.get("target_username", ""),
        "question": session["question"],
        "initiator_answered": session["initiator_answer"] is not None,
        "target_answered": session["target_answer"] is not None,
        "status": session["status"],
        "ai_confidence": session.get("ai_confidence"),
        "ai_reason": session.get("ai_reason"),
        "nft_address": session.get("nft_address"),
        "created_at": session["created_at"],
        "expires_at": session["expires_at"]
    }

# ===================== TRUST ENDPOINT =====================

@api_router.get("/trust/{telegram_id}")
async def get_trust(telegram_id: int):
    user = await db.users.find_one({"telegram_id": telegram_id}, {"_id": 0})
    if not user:
        default_user = {
            "id": str(uuid.uuid4()), "telegram_id": telegram_id, "username": "", "full_name": "",
            "trust_score": 0, "trust_level": "bronze", "handshake_count": 0, "circle_id": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(default_user)
        user = await db.users.find_one({"telegram_id": telegram_id}, {"_id": 0})

    circle = None
    if user.get("circle_id"):
        circle = await db.circles.find_one({"id": user["circle_id"]}, {"_id": 0})

    connections = await db.connections.find(
        {"$or": [{"user_a_id": telegram_id}, {"user_b_id": telegram_id}]}, {"_id": 0}
    ).sort("verified_at", -1).limit(5).to_list(5)

    return {
        "score": user.get("trust_score", 0),
        "level": user.get("trust_level", "bronze"),
        "handshake_count": user.get("handshake_count", 0),
        "circle": circle,
        "connections": connections,
        "username": user.get("username", ""),
        "full_name": user.get("full_name", "")
    }

# ===================== LEADERBOARD =====================

@api_router.get("/leaderboard")
async def get_leaderboard():
    circles = await db.circles.find({}, {"_id": 0}).sort("total_trust_score", -1).limit(10).to_list(10)
    return {"circles": circles}

# ===================== CHALLENGE ENDPOINTS =====================

@api_router.get("/challenge/{circle_id}")
async def get_challenge(circle_id: str):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    challenge = await db.daily_challenges.find_one({"circle_id": circle_id, "date": today}, {"_id": 0})

    if not challenge:
        template = random.choice(CHALLENGE_BANK)
        challenge = {
            "id": str(uuid.uuid4()), "circle_id": circle_id,
            "question": template["question"], "options": template["options"],
            "answer_index": template["answer_index"], "explanation": template["explanation"],
            "date": today, "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        }
        await db.daily_challenges.insert_one(challenge)
        challenge.pop("_id", None)

    return {"id": challenge["id"], "circle_id": challenge["circle_id"], "question": challenge["question"], "options": challenge["options"], "date": challenge.get("date", today)}

@api_router.post("/challenge/answer")
async def answer_challenge(body: ChallengeAnswerRequest):
    challenge = await db.daily_challenges.find_one({"id": body.challenge_id}, {"_id": 0})
    if not challenge:
        raise HTTPException(404, "Челлендж не найден")

    existing = await db.challenge_answers.find_one({"challenge_id": body.challenge_id, "user_telegram_id": body.user_id}, {"_id": 0})
    if existing:
        raise HTTPException(400, "Вы уже ответили на этот вопрос")

    is_correct = body.answer_index == challenge["answer_index"]
    points = 15 if is_correct else 0

    await db.challenge_answers.insert_one({
        "id": str(uuid.uuid4()), "challenge_id": body.challenge_id,
        "user_telegram_id": body.user_id, "answer_index": body.answer_index,
        "is_correct": is_correct, "answered_at": datetime.now(timezone.utc).isoformat()
    })

    if is_correct:
        user = await db.users.find_one({"telegram_id": body.user_id})
        new_score = (user.get("trust_score", 0) if user else 0) + points
        new_level = get_trust_level(new_score)
        await db.users.update_one(
            {"telegram_id": body.user_id},
            {"$set": {"trust_score": new_score, "trust_level": new_level},
             "$setOnInsert": {"id": str(uuid.uuid4()), "username": "", "full_name": "", "handshake_count": 0, "circle_id": None, "created_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )

    return {"correct": is_correct, "explanation": challenge["explanation"], "points_earned": points, "correct_index": challenge["answer_index"]}

# ===================== CIRCLE HELPER =====================

async def handle_circle_assignment(user_a_id, user_b_id):
    user_a = await db.users.find_one({"telegram_id": user_a_id}, {"_id": 0})
    user_b = await db.users.find_one({"telegram_id": user_b_id}, {"_id": 0})
    circle_a = user_a.get("circle_id") if user_a else None
    circle_b = user_b.get("circle_id") if user_b else None

    if not circle_a and not circle_b:
        circle_id = str(uuid.uuid4())
        circle_name = random.choice(CIRCLE_NAMES) + f" #{random.randint(1, 999)}"
        score_a = user_a.get("trust_score", 0) if user_a else 0
        score_b = user_b.get("trust_score", 0) if user_b else 0
        await db.circles.insert_one({
            "id": circle_id, "name": circle_name, "member_count": 2,
            "total_trust_score": score_a + score_b,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        await db.users.update_many({"telegram_id": {"$in": [user_a_id, user_b_id]}}, {"$set": {"circle_id": circle_id}})
    elif circle_a and not circle_b:
        await db.users.update_one({"telegram_id": user_b_id}, {"$set": {"circle_id": circle_a}})
        await db.circles.update_one({"id": circle_a}, {"$inc": {"member_count": 1, "total_trust_score": 25}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}})
    elif circle_b and not circle_a:
        await db.users.update_one({"telegram_id": user_a_id}, {"$set": {"circle_id": circle_b}})
        await db.circles.update_one({"id": circle_b}, {"$inc": {"member_count": 1, "total_trust_score": 25}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}})
    else:
        await db.circles.update_one({"id": circle_a}, {"$inc": {"total_trust_score": 25}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}})
        if circle_a != circle_b:
            await db.circles.update_one({"id": circle_b}, {"$inc": {"total_trust_score": 25}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}})

# ===================== TELEGRAM BOT =====================

bot_available = False
bot = None
dp = None

try:
    from aiogram import Bot, Dispatcher, Router as AioRouter
    from aiogram.types import Message as AioMessage, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    from aiogram.filters import Command, CommandStart

    if BOT_TOKEN:
        bot = Bot(token=BOT_TOKEN)
        dp = Dispatcher()
        bot_router = AioRouter()

        @bot_router.message(CommandStart())
        async def cmd_start(message: AioMessage):
            webapp_url = FRONTEND_URL or "https://emt-server-preview.preview.emergentagent.com"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Открыть v00w", web_app=WebAppInfo(url=webapp_url))]
                ]
            )
            await db.users.update_one(
                {"telegram_id": message.from_user.id},
                {"$set": {"username": message.from_user.username or "", "full_name": message.from_user.full_name or "", "last_seen": datetime.now(timezone.utc).isoformat()},
                 "$setOnInsert": {"id": str(uuid.uuid4()), "telegram_id": message.from_user.id, "trust_score": 0, "trust_level": "bronze", "handshake_count": 0, "circle_id": None, "created_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True
            )
            await message.answer(
                "Добро пожаловать в v00w!\n\n"
                "Превращай дружбу в верифицированное доверие в блокчейне TON.\n\n"
                "/handshake @username — начать рукопожатие\n"
                "/trust — твой рейтинг доверия\n"
                "/leaderboard — топ кругов",
                reply_markup=keyboard,
            )

        @bot_router.message(Command("handshake"))
        async def cmd_handshake(message: AioMessage):
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await message.answer("Используй: /handshake @username")
                return
            target_username = args[1].lstrip('@')
            question = random.choice(QUESTION_BANK)
            session_id = str(uuid.uuid4())
            session_doc = {
                "id": session_id, "initiator_id": message.from_user.id, "target_id": 0,
                "target_username": target_username, "question": question,
                "initiator_answer": None, "target_answer": None, "status": "pending",
                "ai_confidence": None, "ai_reason": None, "nft_address": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            }
            await db.handshake_sessions.insert_one(session_doc)
            webapp_url = FRONTEND_URL or "https://emt-server-preview.preview.emergentagent.com"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Ответить в TrustLeague", web_app=WebAppInfo(url=f"{webapp_url}/handshake?session_id={session_id}"))]
            ])
            await message.answer(f"Рукопожатие с @{target_username} начато!\nСекретный вопрос готов.", reply_markup=keyboard)
            target_user = await db.users.find_one({"username": target_username})
            if target_user:
                try:
                    target_kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Ответить в TrustLeague", web_app=WebAppInfo(url=f"{webapp_url}/handshake?session_id={session_id}"))]
                    ])
                    await bot.send_message(target_user["telegram_id"], f"@{message.from_user.username or 'Друг'} хочет верифицировать дружбу!\nОтветьте на секретный вопрос:", reply_markup=target_kb)
                except Exception as e:
                    logger.error(f"Notify target error: {e}")

        @bot_router.message(Command("trust"))
        async def cmd_trust(message: AioMessage):
            user = await db.users.find_one({"telegram_id": message.from_user.id}, {"_id": 0})
            if not user:
                await message.answer("Используйте /start для регистрации")
                return
            level_emoji = {"bronze": "Bronze", "silver": "Silver", "gold": "Gold", "legend": "Legend"}
            webapp_url = FRONTEND_URL or "https://emt-server-preview.preview.emergentagent.com"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подробнее", web_app=WebAppInfo(url=f"{webapp_url}/trust"))]
            ])
            await message.answer(
                f"Trust Score: {user.get('trust_score', 0)}\n"
                f"Уровень: {level_emoji.get(user.get('trust_level', 'bronze'), 'Bronze')}\n"
                f"Рукопожатий: {user.get('handshake_count', 0)}",
                reply_markup=keyboard
            )

        @bot_router.message(Command("leaderboard"))
        async def cmd_leaderboard(message: AioMessage):
            circles = await db.circles.find({}, {"_id": 0}).sort("total_trust_score", -1).limit(3).to_list(3)
            text = "Топ кругов:\n\n"
            medals = ["1.", "2.", "3."]
            for i, circle in enumerate(circles):
                text += f"{medals[i]} {circle['name']} — {circle['total_trust_score']} pts, {circle['member_count']} участников\n"
            if not circles:
                text = "Пока нет кругов. Начните рукопожатие!"
            webapp_url = FRONTEND_URL or "https://emt-server-preview.preview.emergentagent.com"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Полная таблица", web_app=WebAppInfo(url=f"{webapp_url}/leaderboard"))]
            ])
            await message.answer(text, reply_markup=keyboard)

        dp.include_router(bot_router)
        bot_available = True
        logger.info("Telegram bot initialized successfully")
    else:
        logger.warning("No BOT_TOKEN, bot disabled")
except ImportError as e:
    logger.warning(f"aiogram not installed: {e}")
except Exception as e:
    logger.error(f"Bot init failed: {e}")

async def notify_target(target_id, session_id, initiator_id):
    if not bot_available or not bot:
        return
    webapp_url = FRONTEND_URL or "https://emt-server-preview.preview.emergentagent.com"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ответить в TrustLeague", web_app=WebAppInfo(url=f"{webapp_url}?startapp=handshake_{session_id}"))]
    ])
    await bot.send_message(target_id, "Друг хочет верифицировать дружбу! Ответьте на секретный вопрос:", reply_markup=keyboard)

async def notify_handshake_result(user_id, success, nft_address=None):
    if not bot_available or not bot:
        return
    if success:
        text = f"Рукопожатие верифицировано!\nSBT Badge: https://testnet.tonscan.org/nft/{nft_address}"
    else:
        text = "Рукопожатие не прошло. Ответы не совпали."
    try:
        await bot.send_message(user_id, text)
    except Exception as e:
        logger.error(f"Notify result error: {e}")

# ===================== STARTUP / SHUTDOWN =====================

async def start_bot_polling():
    try:
        logger.info("Starting bot polling...")
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logger.info("Bot polling cancelled")
    except Exception as e:
        logger.error(f"Bot polling error: {e}")

@app.on_event("startup")
async def startup():
    if db is not None:
        await db.users.create_index("telegram_id", unique=True)
        await db.users.create_index("username")
        await db.handshake_sessions.create_index("id", unique=True)
        await db.connections.create_index("id", unique=True)
        await db.circles.create_index("id", unique=True)
        await db.daily_challenges.create_index([("circle_id", 1), ("date", 1)])
        await db.challenge_answers.create_index([("challenge_id", 1), ("user_telegram_id", 1)], unique=True)
        await db.trust_badges.create_index("session_id")

    if bot_available and bot and dp:
        asyncio.create_task(start_bot_polling())
        logger.info("Telegram bot polling task started from startup")
    else:
        logger.info("Startup completed without Telegram bot polling (bot_available=%s)", bot_available)

    # Bot polling may be disabled in some deployments (e.g. serverless/webhook setups)
    logger.info("TrustLeague API started")

@app.on_event("shutdown")
async def shutdown():
    if bot_available and bot:
        try:
            if dp:
                await dp.stop_polling()
            await bot.session.close()
        except Exception:
            pass
    mongo_client.close()

# Include router + CORS
app.include_router(api_router)
cors_origins_raw = os.environ.get('CORS_ORIGINS', '*')
cors_origins = cors_origins_raw.split(',') if cors_origins_raw != '*' else ['*']
app.add_middleware(
    CORSMiddleware,
    allow_credentials=cors_origins_raw != '*',
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
