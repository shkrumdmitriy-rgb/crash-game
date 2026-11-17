import asyncio
import os
import aiosqlite
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")

dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: Message):
    # Создаем юзера, но НЕ показываем баланс в сообщении
    async with aiosqlite.connect("users.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()

    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))
    kb.button(text="💎 Пополнить баланс", callback_data="topup")
    
    await message.answer(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        "Добро пожаловать в <b>Crash Rocket</b> 🚀\n"
        "Нажми кнопку ниже, чтобы начать играть!",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "topup")
async def process_topup(callback):
    await callback.message.answer_invoice(
        title="Пополнение", description="10 💎", payload="topup_10",
        provider_token="", currency="XTR",
        prices=[LabeledPrice(label="💎", amount=10)]
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_paid(message: Message):
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET balance = balance + 10 WHERE user_id = ?", (message.from_user.id,))
        await db.commit()
    await message.answer("✅ Баланс пополнен на 10 💎! Открой игру заново.")

async def main():
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())