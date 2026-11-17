import asyncio
import json
import os
import aiosqlite
import hashlib
import hmac
from urllib.parse import parse_qsl
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- База данных ---
async def init_db():
    async with aiosqlite.connect("users.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 100
            )
        """)
        await db.commit()

async def get_balance(user_id: int) -> int:
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row: return row[0]
            await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            await db.commit()
            return 100

async def update_balance(user_id: int, amount: int):
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

# --- Проверка Telegram ---
def validate_init_data(init_data: str) -> dict | None:
    try:
        pairs = dict(parse_qsl(init_data))
        received_hash = pairs.pop("hash", None)
        if not received_hash: return None
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if calc != received_hash: return None
        return json.loads(pairs.get("user", "{}"))
    except Exception:
        return None

# --- WebSocket для игры ---
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    user = None
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            
            if msg["type"] == "auth":
                user = validate_init_data(msg.get("initData", ""))
                if not user:
                    await ws.send_json({"type": "error", "msg": "Auth failed"})
                    await ws.close()
                    break
                uid = user["id"]
                bal = await get_balance(uid)
                await ws.send_json({"type": "hello", "uid": uid, "balance": bal})

            elif msg["type"] == "bet" and user:
                amt = float(msg.get("amt", 0))
                bal = await get_balance(user["id"])
                if amt < 0.1 or amt > bal:
                    await ws.send_json({"type": "error", "msg": "Недостаточно средств"})
                    continue
                await update_balance(user["id"], -int(amt))
                await ws.send_json({"type": "bet_ok", "amt": amt})
                await ws.send_json({"type": "balance", "balance": await get_balance(user["id"])})

            elif msg["type"] == "get_gifts" and user:
                gifts = await bot.get_available_gifts()
                result = [{"id": g.id, "title": g.title, "stars": g.star_count} for g in gifts]
                await ws.send_json({"type": "gifts_list", "gifts": result})

            elif msg["type"] == "buy_gift" and user:
                gift_id = msg.get("gift_id")
                price = int(msg.get("price"))
                bal = await get_balance(user["id"])
                
                if bal < price:
                    await ws.send_json({"type": "error", "msg": "Недостаточно 💎"})
                    continue
                
                try:
                    # Отправляем РЕАЛЬНЫЙ подарок через бота
                    await bot.send_gift(user_id=user["id"], gift_id=gift_id)
                    await update_balance(user["id"], -price)
                    await ws.send_json({"type": "gift_bought", "msg": "Подарок отправлен!"})
                    await ws.send_json({"type": "balance", "balance": await get_balance(user["id"])})
                except Exception as e:
                    await ws.send_json({"type": "error", "msg": f"Ошибка: {e}"})

    except WebSocketDisconnect:
        pass

# Для запуска: uvicorn server:app --host 0.0.0.0 --port 8000