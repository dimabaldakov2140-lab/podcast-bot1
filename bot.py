import asyncio
import logging
import sqlite3
import secrets
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.utils.deep_linking import create_start_link
from aiogram.enums import ParseMode

BOT_TOKEN = "8908733506:AAE8dxfIqLeWW6M5SuK-ggR4Cr0WKR8H0Tk"

CHANNEL_ID = "@Pod_Cast_shop"
CHANNEL_URL = "https://t.me/Pod_Cast_shop"
MANAGER_USERNAME = "@Manager_Pod_Cast"
MAIN_CHANNEL_URL = "https://t.me/Pod_Cast_shop"

POINTS_PER_REFERRAL = 0.5
MAX_POINTS = 10.0
PROMO_DISCOUNT = 10
PROMO_PREFIX = "PODCAST"

conn = sqlite3.connect("referral.db")
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        referral_count INTEGER DEFAULT 0,
        invited_by INTEGER DEFAULT NULL,
        referral_awarded INTEGER DEFAULT 0,
        promo_issued INTEGER DEFAULT 0,
        promo_code TEXT DEFAULT NULL
    )
""")
conn.commit()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_user(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def add_user(user_id: int, username: str = None, invited_by: int = None):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, invited_by) VALUES (?, ?, ?)",
        (user_id, username, invited_by)
    )
    conn.commit()

def update_invited_by(user_id: int, invited_by: int):
    cursor.execute(
        "UPDATE users SET invited_by = ?, referral_awarded = 0 WHERE user_id = ? AND invited_by IS NULL",
        (invited_by, user_id)
    )
    conn.commit()

def increment_referral_count(referrer_id: int):
    cursor.execute(
        "UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?",
        (referrer_id,)
    )
    conn.commit()

def mark_referral_awarded(user_id: int):
    cursor.execute(
        "UPDATE users SET referral_awarded = 1 WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()

def get_points(referral_count: int) -> float:
    return min(referral_count * POINTS_PER_REFERRAL, MAX_POINTS)

def generate_promo_code(user_id: int) -> str:
    code = f"{PROMO_PREFIX}{secrets.token_hex(3).upper()}-{user_id}"
    cursor.execute(
        "UPDATE users SET promo_code = ?, promo_issued = 1 WHERE user_id = ?",
        (code, user_id)
    )
    conn.commit()
    return code

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def process_referral_bonus(invited_by: int, new_user_id: int):
    increment_referral_count(invited_by)
    mark_referral_awarded(new_user_id)
    user_data = get_user(invited_by)
    if not user_data:
        return
    count = user_data[2]
    points = get_points(count)
    await bot.send_message(
        invited_by,
        f"🎉 Новый подписчик! +{POINTS_PER_REFERRAL} балла. У вас {points} баллов."
    )
    if points >= MAX_POINTS and user_data[5] == 0:
        promo = generate_promo_code(invited_by)
        await bot.send_message(
            invited_by,
            f"🏆 Вы накопили {MAX_POINTS} баллов! Промокод на скидку {PROMO_DISCOUNT}%:\n<code>{promo}</code>",
            parse_mode=ParseMode.HTML
        )

@dp.message(CommandStart())
async def start_cmd(message: Message):
    user = message.from_user
    args = message.text.split()
    invited_by = None
    if len(args) > 1:
        try:
            invited_by = int(args[1])
        except:
            pass
    existing = get_user(user.id)
    if not existing:
        add_user(user.id, user.username, invited_by)
        if invited_by and invited_by != user.id:
            if await check_subscription(user.id):
                await process_referral_bonus(invited_by, user.id)
                await message.answer("✅ Подписка подтверждена! Бонус начислен.")
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL)],
                    [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
                ])
                await message.answer("Подпишись на канал и нажми кнопку проверки:", reply_markup=keyboard)
                return
    else:
        if invited_by and invited_by != user.id and existing[3] is None:
            update_invited_by(user.id, invited_by)
            if not await check_subscription(user.id):
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL)],
                    [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
                ])
                await message.answer("Подпишись на канал, чтобы друг получил бонус:", reply_markup=keyboard)
                return
            else:
                if existing[4] == 0:
                    await process_referral_bonus(invited_by, user.id)
                    await message.answer("✅ Подписка подтверждена!")
    ref_link = await create_start_link(bot, str(user.id), encode=True)
    text = (
        "🔥 <b>Реферальная программа Pod-Cast</b>\n\n"
        f"Ссылка: <code>{ref_link}</code>\n\n"
        f"+{POINTS_PER_REFERRAL} балла за друга. 1 балл = 1% скидки. Максимум 10%.\n"
        "/balance — статистика\n/share — текст для рекламы"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(Command("ref"))
async def ref_cmd(message: Message):
    ref_link = await create_start_link(bot, str(message.from_user.id), encode=True)
    await message.answer(f"🔗 {ref_link}")

@dp.message(Command("balance"))
async def balance_cmd(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    count = user[2]
    points = get_points(count)
    promo_code = user[6] if user[6] else "ещё не получен"
    await message.answer(
        f"📊 Приглашено: <b>{count}</b>\n⭐ Баллов: <b>{points}</b>/10\n"
        f"🎁 Скидка: <b>{min(points, MAX_POINTS)}%</b>\n🏷 Промокод: <code>{promo_code}</code>",
        parse_mode=ParseMode.HTML
    )

@dp.message(Command("share"))
async def share_cmd(message: Message):
    ref_link = await create_start_link(bot, str(message.from_user.id), encode=True)
    share_text = (
        "🔥 Добро пожаловать в Pod-Cast\n\n"
        "💯 Ваш надежный проводник в мир\n😋 вкусного пара!\n\n"
        f"🔗 В наличии {ref_link}\n\n"
        "Задать вопрос:\n👉 @Manager_Pod_Cast 👈\n\n"
        "👉 Основной канал: https://t.me/Pod_Cast_shop"
    )
    await message.answer(
        f"<b>📢 Твой пост:</b>\n\n{share_text}",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery):
    user = call.from_user
    if not await check_subscription(user.id):
        await call.answer("Не подписан ❌", show_alert=True)
        return
    user_data = get_user(user.id)
    if not user_data:
        await call.message.edit_text("Сначала /start")
        return
    invited_by = user_data[3]
    awarded = user_data[4]
    if invited_by and invited_by != user.id and awarded == 0:
        await process_referral_bonus(invited_by, user.id)
        await call.message.edit_text("✅ Готово!")
    else:
        await call.message.edit_text("✅ Уже подписан.")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
