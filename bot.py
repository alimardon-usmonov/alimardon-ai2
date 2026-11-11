import os
import sys
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton
)

import database as db

# .env faylini yuklash
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW and ADMIN_ID_RAW.isdigit() else None

if not BOT_TOKEN:
    print("XATOLIK: BOT_TOKEN topilmadi!")
    sys.exit(1)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Bot va FSM
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Foydalanuvchi suhbat xotirasi
user_memory: Dict[int, List[Dict[str, str]]] = {}

SYSTEM_INSTRUCTION = (
    "Siz Alimardonning shaxsiy sun'iy intellekt yordamchisisiz. "
    "Agar sizdan 'sen kimsan', 'kimsan', 'kim bu', 'o'zing haqingda ayt' yoki shunga o'xshash savol so'ralsa, "
    "albatta: 'Men Alimardon yordamchisiman' deb javob bering. "
    "Siz aqlli, xushmuomala, do'stona va samimiy yordamchisiz. "
    "Foydalanuvchi qaysi tilda murojaat qilsa, shu tilda (asosan o'zbek tilida) "
    "aniq, qisqa va lo'nda, foydali javob bering."
)

# AI provayderlari ro'yxati
PROVIDERS = {
    "gemini": {"name": "Google Gemini", "icon": "⚡", "model": "gemini-3.1-flash-lite"},
    "openai": {"name": "OpenAI ChatGPT", "icon": "🤖", "model": "gpt-4o-mini"},
    "groq": {"name": "Groq (Llama 3.3)", "icon": "🚀", "model": "llama-3.3-70b-versatile"},
    "deepseek": {"name": "DeepSeek", "icon": "🧠", "model": "deepseek-chat"},
    "openrouter": {"name": "OpenRouter", "icon": "🌐", "model": "deepseek/deepseek-chat"}
}

# FSM holatlari
class BroadcastState(StatesGroup):
    waiting_for_message = State()
    confirm_send = State()

class KeyUpdateState(StatesGroup):
    waiting_for_key = State()

# --- SOZLAMALAR VA KALITLARNI OLISH ---
def get_provider_key(prov: str) -> str:
    key_name = f"{prov}_api_key"
    env_name = f"{prov.upper()}_API_KEY"
    return db.get_setting(key_name, os.getenv(env_name, ""))

def set_provider_key(prov: str, key_value: str):
    db.set_setting(f"{prov}_api_key", key_value)

def get_active_provider() -> str:
    return db.get_setting("active_provider", "gemini")

def set_active_provider(prov: str):
    db.set_setting("active_provider", prov)

# --- AI CHAQIRISH FUNKSIYALARI ---
def call_gemini(prompt: str, user_id: int) -> str:
    from google import genai
    from google.genai import types as genai_types

    api_key = get_provider_key("gemini")
    if not api_key:
        raise ValueError("Gemini API kaliti topilmadi!")

    client = genai.Client(api_key=api_key)

    contents = []
    history = user_memory.get(user_id, [])[-6:]
    for item in history:
        contents.append(f"{item['role'].capitalize()}: {item['content']}")
    contents.append(f"User: {prompt}")

    full_prompt = "\n".join(contents)

    try:
        res = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=full_prompt,
            config=genai_types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
        )
        return res.text
    except Exception:
        res = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=full_prompt,
            config=genai_types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
        )
        return res.text

def call_openai_compatible(prov: str, prompt: str, user_id: int) -> str:
    from openai import OpenAI

    api_key = get_provider_key(prov)
    if not api_key:
        raise ValueError(f"{prov.capitalize()} API kaliti topilmadi!")

    base_urls = {
        "openai": None,
        "groq": "https://api.groq.com/openai/v1",
        "deepseek": "https://api.deepseek.com",
        "openrouter": "https://openrouter.ai/api/v1"
    }

    base_url = base_urls.get(prov)
    model = PROVIDERS[prov]["model"]

    client = OpenAI(api_key=api_key, base_url=base_url)

    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    history = user_memory.get(user_id, [])[-6:]
    for item in history:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": prompt})

    res = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=1500
    )
    return res.choices[0].message.content

def call_single_ai(prov: str, prompt: str, user_id: int) -> str:
    if prov == "gemini":
        return call_gemini(prompt, user_id)
    else:
        return call_openai_compatible(prov, prompt, user_id)

async def get_ai_response(prompt: str, user_id: int) -> str:
    """Asosiy AI va barcha zaxira AI provayderlari bilan avtomatik ishlash"""
    active_prov = get_active_provider()
    provider_order = [active_prov] + [p for p in PROVIDERS.keys() if p != active_prov]

    last_error = None
    for prov in provider_order:
        key = get_provider_key(prov)
        if not key:
            continue
        try:
            return await asyncio.to_thread(call_single_ai, prov, prompt, user_id)
        except Exception as e:
            logger.warning(f"{prov.upper()} xatosi: {e}. Keyingi model tekshirilmoqda...")
            last_error = e

    raise Exception(f"Barcha sozlangan AI xizmatlarida xatolik yuz berdi: {last_error}")

# --- KLAVIATURALAR ---
def get_admin_main_kb() -> InlineKeyboardMarkup:
    active = get_active_provider()
    active_info = PROVIDERS.get(active, {"name": active, "icon": "🤖"})
    buttons = [
        [
            InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"),
            InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton(text="📢 Ommaviy xabar yuborish", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton(text=f"⚙️ AI Modellar va Kalitlar ({active_info['icon']})", callback_data="admin_ai_menu"),
        ],
        [
            InlineKeyboardButton(text="🔄 Yangilash", callback_data="admin_refresh"),
            InlineKeyboardButton(text="❌ Yopish", callback_data="admin_close")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_ai_menu_kb() -> InlineKeyboardMarkup:
    active = get_active_provider()
    buttons = []

    # Har bir modelni faollashtirish tugmalari
    row = []
    for prov_id, prov_info in PROVIDERS.items():
        is_active = (prov_id == active)
        mark = "✅ " if is_active else ""
        btn_text = f"{mark}{prov_info['icon']} {prov_info['name']}"
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"ai_switch:{prov_id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="🔑 API Kalitlarni o'zgartirish", callback_data="ai_keys_menu")])
    buttons.append([InlineKeyboardButton(text="◀️ Bosh Admin Panel", callback_data="admin_refresh")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_keys_menu_kb() -> InlineKeyboardMarkup:
    buttons = []
    for prov_id, prov_info in PROVIDERS.items():
        key = get_provider_key(prov_id)
        status = "✅" if key else "❌"
        btn_text = f"{status} 🔑 {prov_info['name']} kaliti"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"ai_setkey:{prov_id}")])

    buttons.append([InlineKeyboardButton(text="◀️ AI Menyusiga qaytish", callback_data="admin_ai_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_broadcast_confirm_kb() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Ha, barchaga yuborilsin", callback_data="broadcast_confirm"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="broadcast_cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_reply_kb() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="👑 Admin Panel"), KeyboardButton(text="🧹 Xotirani tozalash")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

async def send_split_message(message: types.Message, text: str):
    max_len = 4000
    if len(text) <= max_len:
        try:
            await message.answer(text, parse_mode="Markdown")
        except TelegramBadRequest:
            await message.answer(text)
        return

    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        try:
            await message.answer(chunk, parse_mode="Markdown")
        except TelegramBadRequest:
            await message.answer(chunk)
        await asyncio.sleep(0.2)

# --- ASOSIY BUYRUQLAR ---
@dp.message(CommandStart())
async def handle_start(message: types.Message):
    user = message.from_user
    db.add_or_update_user(user_id=user.id, first_name=user.first_name, username=user.username)

    is_admin = (user.id == ADMIN_ID)
    reply_markup = get_admin_reply_kb() if is_admin else None

    welcome = (
        f"Assalomu alaykum, {user.first_name or 'doʻstim'}! 👋\n\n"
        "Men **Alimardon yordamchisiman** (Sun'iy intellekt).\n"
        "Menga istalgan savolingizni berishingiz mumkin — sizga tezkor va aqlli javob qaytaraman!\n\n"
        "💡 *Buyruqlar:*\n"
        "• /clear — suhbat tarixini tozalash"
    )
    if is_admin:
        welcome += "\n\n👑 *Admin paneli:* /admin yoki pastdagi tugma orqali ochiladi."

    await message.answer(welcome, parse_mode="Markdown", reply_markup=reply_markup)

@dp.message(Command("clear"))
@dp.message(F.text == "🧹 Xotirani tozalash")
async def handle_clear(message: types.Message):
    user_id = message.from_user.id
    user_memory.pop(user_id, None)
    await message.answer("🧹 Suhbat xotirasi tozalandi! Yangi mavzudan boshlashingiz mumkin.")

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
@dp.message(F.text == "👑 Admin Panel")
async def handle_admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("👑 *Boshqaruv Admin Paneli:*\n\nKerakli bo'limni tanlang:", parse_mode="Markdown", reply_markup=get_admin_main_kb())

@dp.callback_query(F.data == "admin_refresh")
async def cb_admin_refresh(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await callback.message.edit_text(
        "👑 *Boshqaruv Admin Paneli:*\n\nKerakli bo'limni tanlang:",
        parse_mode="Markdown",
        reply_markup=get_admin_main_kb()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_close")
async def cb_admin_close(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.delete()
    await callback.answer("Yopildi.")

@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    stats = db.get_stats()
    prov = get_active_provider()
    p_info = PROVIDERS.get(prov, {"name": prov, "icon": "🤖"})
    text = (
        "📊 *Bot statistikasi:*\n\n"
        f"👥 Jami foydalanuvchilar: *{stats['total']}* ta\n"
        f"🆕 Bugun qo'shilganlar: *{stats['new_today']}* ta\n"
        f"⚡ Bugun faol bo'lganlar: *{stats['active_today']}* ta\n"
        f"🤖 Faol AI tizimi: *{p_info['icon']} {p_info['name']}*"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="admin_refresh")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    users = db.get_recent_users(limit=10)
    if not users:
        text = "👥 Hozircha foydalanuvchilar yo'q."
    else:
        text = "👥 *Oxirgi qo'shilgan 10 ta foydalanuvchi:*\n\n"
        for idx, (uid, fname, uname, joined) in enumerate(users, 1):
            uname_str = f"@{uname}" if uname else "username yo'q"
            fname_clean = fname or "Nomsiz"
            joined_str = str(joined)[:16] if joined else ""
            text += f"{idx}. *{fname_clean}* ({uname_str})\n   🆔 `{uid}` | 🕒 {joined_str}\n\n"

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="admin_refresh")]
        ])
    )
    await callback.answer()

# --- AI MODELLAR MENYUSI ---
@dp.callback_query(F.data == "admin_ai_menu")
async def cb_admin_ai_menu(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    active = get_active_provider()
    active_info = PROVIDERS.get(active, {"name": active, "icon": "🤖"})

    status_lines = []
    for prov_id, prov_info in PROVIDERS.items():
        k = get_provider_key(prov_id)
        if k:
            st = f"✅ Ulangan (`...{k[-5:]}`)"
        else:
            st = "❌ Kiritilmagan"
        cur = " *(Faol)*" if prov_id == active else ""
        status_lines.append(f"{prov_info['icon']} **{prov_info['name']}:** {st}{cur}")

    text = (
        "⚙️ *Sun'iy Intellekt va Modellar Boshqaruvi:*\n\n"
        + "\n".join(status_lines) +
        f"\n\n🎯 **Hozirgi asosiy model:** {active_info['icon']} *{active_info['name']}*\n\n"
        "👇 *Quyidagi tugmalar orqali asosiy modelni bosing yoki kalitlarni o'zgartiring:*"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_ai_menu_kb())
    await callback.answer()

@dp.callback_query(F.data.startswith("ai_switch:"))
async def cb_ai_switch_provider(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    new_prov = callback.data.split(":")[1]
    if new_prov in PROVIDERS:
        key = get_provider_key(new_prov)
        if not key:
            await callback.answer(f"⚠️ {PROVIDERS[new_prov]['name']} uchun avval API kalit kiriting!", show_alert=True)
            return

        set_active_provider(new_prov)
        await callback.answer(f"✅ Asosiy AI: {PROVIDERS[new_prov]['name']} ga o'zgartirildi!", show_alert=True)
        await cb_admin_ai_menu(callback)

@dp.callback_query(F.data == "ai_keys_menu")
async def cb_ai_keys_menu(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    text = (
        "🔑 *API Kalitlarni Kiritish va Yangilash:*\n\n"
        "Qaysi AI tizimining API kalitini kiritmoqchi yoki o'zgartirmoqchi bo'lsangiz, uni tanlang:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_keys_menu_kb())
    await callback.answer()

@dp.callback_query(F.data.startswith("ai_setkey:"))
async def cb_ai_setkey_prompt(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    prov_id = callback.data.split(":")[1]
    prov_info = PROVIDERS.get(prov_id, {"name": prov_id})

    await state.set_state(KeyUpdateState.waiting_for_key)
    await state.update_data(target_provider=prov_id)

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="ai_keys_menu")]
    ])
    await callback.message.edit_text(
        f"🔑 *{prov_info['name']} uchun API kalitni yuboring:*\n\n"
        f"Telegram orqali yangi kalit matnini yuboring. U xavfsiz saqlanadi va bot unga darhol ulanadi.",
        parse_mode="Markdown",
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.message(KeyUpdateState.waiting_for_key)
async def handle_received_api_key(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    prov_id = data.get("target_provider")
    await state.clear()

    new_key = message.text.strip()
    if len(new_key) < 10:
        await message.answer("⚠️ Yaroqsiz kalit! Kalit juda qisqa.")
        return

    set_provider_key(prov_id, new_key)
    p_name = PROVIDERS.get(prov_id, {}).get("name", prov_id)

    await message.answer(
        f"✅ *{p_name} API kaliti muvaffaqiyatli saqlandi!*\nKalit: `{new_key[:8]}...{new_key[-5:]}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ AI Menyusiga qaytish", callback_data="admin_ai_menu")]
        ])
    )

# --- OMMAVIY XABAR (BROADCAST) ---
@dp.callback_query(F.data == "admin_broadcast")
async def cb_start_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(BroadcastState.waiting_for_message)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_refresh")]
    ])
    await callback.message.edit_text(
        "📢 *Ommaviy xabar yuborish bo'limi*\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring.\n"
        "💡 *Matn, rasm, video yoki fayl yuborishingiz mumkin!*",
        parse_mode="Markdown",
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.message(BroadcastState.waiting_for_message)
async def handle_broadcast_preview(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(message_id=message.message_id, chat_id=message.chat.id)
    await state.set_state(BroadcastState.confirm_send)

    users_count = len(db.get_all_user_ids())
    await message.reply(
        f"👆 *Yuqoridagi xabar {users_count} ta foydalanuvchiga yuboriladi.*\n\n"
        "Xabarni tarqatishni tasdiqlaysizmi?",
        parse_mode="Markdown",
        reply_markup=get_broadcast_confirm_kb()
    )

@dp.callback_query(BroadcastState.confirm_send, F.data == "broadcast_confirm")
async def cb_broadcast_execute(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    msg_id = data.get("message_id")
    from_chat_id = data.get("chat_id")
    await state.clear()

    user_ids = db.get_all_user_ids()
    total = len(user_ids)
    await callback.message.edit_text(f"⏳ Xabar {total} ta foydalanuvchiga yuborilmoqda, kuting...")

    success = 0
    blocked = 0
    failed = 0

    for uid in user_ids:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=msg_id)
            success += 1
            await asyncio.sleep(0.05)
        except TelegramForbiddenError:
            blocked += 1
        except Exception:
            failed += 1

    report = (
        "✅ *Ommaviy xabar yuborish yakunlandi!*\n\n"
        f"📊 Jami a'zolar: *{total}*\n"
        f"🟢 Yetkazildi: *{success}*\n"
        f"🔴 Botni bloklagan: *{blocked}*\n"
        f"⚠️ Xatolik: *{failed}*"
    )
    await callback.message.answer(
        report,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Admin Panel", callback_data="admin_refresh")]
        ])
    )
    await callback.answer()

@dp.callback_query(BroadcastState.confirm_send, F.data == "broadcast_cancel")
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Ommaviy xabar yuborish bekor qilindi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Admin Panel", callback_data="admin_refresh")]
        ])
    )
    await callback.answer()

INSTANT_IDENTITY_WORDS = {
    "sen kimsan", "kimsan", "kim bu", "kimsen", "kimsan?", "sen kimsan?",
    "siz kimsiz", "siz kimsiz?", "isming nima", "isming nima?", "kim bu?"
}

# --- ODDIY SUHBAT (AI) ---
@dp.message(F.text)
async def handle_user_ai_prompt(message: types.Message):
    user = message.from_user
    user_prompt = message.text.strip()
    clean_text = user_prompt.lower()

    db.add_or_update_user(user_id=user.id, first_name=user.first_name, username=user.username)

    if clean_text in INSTANT_IDENTITY_WORDS or clean_text.rstrip("?").strip() in {"sen kimsan", "kimsan", "kim bu", "siz kimsiz"}:
        await message.answer("Men **Alimardon yordamchisiman**! 😊\nSizga qanday yordam bera olaman?", parse_mode="Markdown")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    try:
        reply_text = await get_ai_response(user_prompt, user.id)

        if user.id not in user_memory:
            user_memory[user.id] = []
        user_memory[user.id].append({"role": "user", "content": user_prompt})
        user_memory[user.id].append({"role": "assistant", "content": reply_text})

        await send_split_message(message, reply_text)

    except Exception as e:
        logger.error(f"AI umumiy xatosi: {e}")
        await message.answer(
            "Kechirasiz, sun'iy intellekt javob berishida xatolik yuz berdi.\n"
            "Iltimos, qaytadan urinib ko'ring yoki /clear buyrug'ini bering."
        )

# --- ISHGA TUSHIRISH ---
async def start_render_health_server():
    """Render.com da bot o'chib qolmasligi uchun port ochib berish"""
    port = os.getenv("PORT")
    if port and port.isdigit():
        from aiohttp import web
        app = web.Application()
        app.router.add_get("/", lambda r: web.Response(text="Telegram AI Bot is running!"))
        app.router.add_get("/health", lambda r: web.Response(text="OK"))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", int(port))
        await site.start()
        logger.info(f"Render uchun HTTP server {port}-portda faollashdi.")

async def main():
    db.init_db()
    logger.info("Baza va AI sozlamalari tayyor.")

    # Render portini ochish (agar Render-da ishlayotgan bo'lsa)
    await start_render_health_server()

    if ADMIN_ID:
        try:
            active = get_active_provider()
            p_info = PROVIDERS.get(active, {"name": active, "icon": "🤖"})
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚀 *Bot ishga tushdi!*\n\nAsosiy AI: {p_info['icon']} *{p_info['name']}*\nZaxira tizimi: *Barcha modellar faol*\n\nBoshqaruv: /admin",
                parse_mode="Markdown",
                reply_markup=get_admin_reply_kb()
            )
        except Exception as e:
            logger.warning(f"Adminga xabar yuborib bo'lmadi: {e}")

    logger.info("Bot tayyor!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
