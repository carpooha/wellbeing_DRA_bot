# -*- coding: utf-8 -*-
import asyncio
import os
import json
from datetime import datetime
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from tinydb import TinyDB, Query

API_TOKEN = os.environ.get('TELEGRAM_TOKEN')

if not API_TOKEN:
    raise ValueError("ERROR: Token not found!")

ADMIN_ID = 152676166  # ЗАМЕНИТЕ НА СВОЙ ID

# --- База данных ---
db = TinyDB('coffee_db.json')
finances = db.table('finances')
users = db.table('users')  # новая таблица для пользателей и рассылки
feedbacks = db.table('feedbacks')  # Новая таблица для отзывов

if not finances.all():
    finances.insert({'collected': 0.0, 'spent': 0.0})

def add_collected(amount):
    data = finances.all()[0]
    data['collected'] += amount
    finances.update(data, doc_ids=[1])

def add_spent(amount, description):
    data = finances.all()[0]
    data['spent'] += amount
    finances.update(data, doc_ids=[1])

# --- функция сохранения пользователей ---
def save_user(user_id, username, first_name, last_name):
    User = Query()
    if not users.search(User.user_id == user_id):
        users.insert({
            'user_id': user_id,
            'username': username or "",
            'first_name': first_name or "",
            'last_name': last_name or "",
        })

# --- Функции для отзывов ---
def save_feedback(user_id, username, full_name, text):
    """Сохраняет отзыв в базу данных"""
    feedbacks.insert({
        'user_id': user_id,
        'username': username,
        'full_name': full_name,
        'text': text,
        'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status': 'new'  # new, read, answered
    })

def get_all_feedbacks():
    """Получить все отзывы"""
    return feedbacks.all()

def mark_feedback_read(feedback_id):
    """Отметить отзыв как прочитанный"""
    if feedbacks.update({'status': 'read'}, doc_ids=[feedback_id]):
        return True
    return False

# --- Хранение объявления ---
ANNOUNCEMENT_FILE = 'announcement.json'

def save_announcement(text):
    with open(ANNOUNCEMENT_FILE, 'w', encoding='utf-8') as f:
        json.dump({'text': text}, f, ensure_ascii=False)

def get_announcement():
    try:
        with open(ANNOUNCEMENT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('text', '')
    except:
        return ''

# --- Временное хранилище для ожидания отзыва ---
# Словарь: {user_id: True} - пользователь ожидает отправки отзыва
waiting_for_feedback = {}

# --- Flask для Render ---
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "Coffee bot is running!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app_flask.run(host='0.0.0.0', port=port)

# --- Клавиатура ---
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Где кофе и молоко?", callback_data="instruction")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="finance")],
        [InlineKeyboardButton(text="💸 Скинуться на кофе", callback_data="donate")],
        [InlineKeyboardButton(text="📝 Обратная связь", callback_data="feedback")]
    ])
    return keyboard

# --- Бот ---
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    save_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    ) # --- сохраняем пользователя ---
    announcement = get_announcement()
    
    # Формируем приветствие
    if announcement:
        welcome_text = f"☕️ Добро пожаловать в Кофе-Бот!\n\n📢 ОБЪЯВЛЕНИЕ:\n{announcement}\n\n---\nВыберите действие:"
    else:
        welcome_text = "☕️ Добро пожаловать в Кофе-Бот!\n\nВыберите действие:"
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@dp.message(Command("users")) # --- считаем пользователей ---
async def cmd_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав")
        return
    count = len(users.all())
    await message.answer(f"👥 Пользователей в базе: {count}")

@dp.callback_query(lambda c: c.data == "instruction")
async def show_instruction(callback: types.CallbackQuery):
    text = "📍 ГДЕ НАЙТИ КОФЕ И МОЛОКО:\n☕️ Кофе: В верхнем ящике над кофемашиной в жестяной коричневой банке\n🥛 Молоко: В холодильнике в верхнем выдвижном ящике или стоит в дверке\n👤 "
    await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "finance")
async def show_finance(callback: types.CallbackQuery):
    data = finances.all()[0]
    collected = data['collected']
    spent = data['spent']
    balance = collected - spent
    text = f"💰 ФИНАНСОВЫЙ ОТЧЕТ\n\nСобрано: {collected:.2f} руб.\nПотрачено: {spent:.2f} руб.\nБаланс: {balance:.2f} руб."
    await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "donate")
async def show_donate(callback: types.CallbackQuery):
    text = "💸 Ссылка на сбор: https://vtb.paymo.ru/collect-money/?transaction=c208d1eb-2b1a-47f8-9d41-835e1a005ee8"
    await callback.message.answer(text)
    await callback.answer()



# --- КОМАНДА ДЛЯ ПРОСМОТРА ОТЗЫВОВ (админ) ---
@dp.message(Command("feedbacks"))
async def show_feedbacks(message: types.Message):
    """Показать все отзывы (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав")
        return
    
    all_feedbacks = get_all_feedbacks()
    
    if not all_feedbacks:
        await message.answer("📭 Нет отзывов")
        return
    
    text = "📝 СПИСОК ОТЗЫВОВ:\n\n"
    for i, fb in enumerate(all_feedbacks[-10:], 1):  # последние 10
        status_emoji = "🟢" if fb['status'] == 'new' else "🔵"
        text += f"{i}. {status_emoji} {fb['full_name']} (@{fb['username']})\n   {fb['date']}\n   {fb['text'][:50]}...\n\n"
    
    text += f"\nВсего отзывов: {len(all_feedbacks)}"
    await message.answer(text)

# --- АДМИН КОМАНДЫ ---
@dp.message(Command("add"))
async def cmd_add_money(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав")
        return
    try:
        amount = float(message.text.split()[1])
        add_collected(amount)
        await message.answer(f"✅ Добавлено {amount:.2f} руб.")
    except (IndexError, ValueError):
        await message.answer("Использование: /add [сумма]")

@dp.message(Command("spend"))
async def cmd_spend_money(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав")
        return
    try:
        parts = message.text.split(maxsplit=2)
        amount = float(parts[1])
        description = parts[2] if len(parts) > 2 else ""
        add_spent(amount, description)
        await message.answer(f"✅ Списано {amount:.2f} руб.")
    except (IndexError, ValueError):
        await message.answer("Использование: /spend [сумма] [описание]")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав")
        return
    data = finances.all()[0]
    text = f"📊 СТАТИСТИКА\n\n💰 Собрано: {data['collected']:.2f} руб.\n💸 Потрачено: {data['spent']:.2f} руб.\n📈 Баланс: {data['collected'] - data['spent']:.2f} руб."
    await message.answer(text)

@dp.message(Command("announce"))
async def cmd_announce(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав")
        return
    try:
        text = message.text.split(maxsplit=1)[1]
        save_announcement(text)
        await message.answer("✅ Объявление сохранено!")
    except IndexError:
        await message.answer("Использование: /announce [текст]")

@dp.message(Command("clear_announce"))
async def cmd_clear_announce(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав")
        return
    save_announcement("")
    await message.answer("✅ Объявление удалено")

# --- ОБРАТНАЯ СВЯЗЬ (упрощённая) ---
@dp.callback_query(lambda c: c.data == "feedback")
async def start_feedback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    waiting_for_feedback[user_id] = True
    await callback.message.answer(
        "📝 Напишите ваш отзыв или предложение.\n\n"
        "Просто отправьте текстовое сообщение. Чтобы отменить — отправьте /cancel"
    )
    await callback.answer()

@dp.message(Command("cancel"))
async def cancel_feedback(message: types.Message):
    user_id = message.from_user.id
    if user_id in waiting_for_feedback:
        del waiting_for_feedback[user_id]
        await message.answer("✅ Отправка отзыва отменена.", reply_markup=get_main_keyboard())
    else:
        await message.answer("Нет активного действия для отмены")

@dp.message()
async def handle_feedback_text(message: types.Message):
    user_id = message.from_user.id
    
    # Проверяем, ожидает ли пользователь отправки отзыва
    if user_id not in waiting_for_feedback:
        return  # игнорируем сообщения не в режиме обратной связи
    
    # Убираем пользователя из ожидания
    del waiting_for_feedback[user_id]
    
    # Сохраняем отзыв
    username = message.from_user.username or "без username"
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
    feedback_text = message.text
    
    save_feedback(user_id, username, full_name, feedback_text)
    
    # Отправляем подтверждение пользователю
    await message.answer(
        "✅ Спасибо за ваш отзыв! Он сохранён и будет рассмотрен администратором.\n\n"
        "Возвращаемся в главное меню:",
        reply_markup=get_main_keyboard()
    )
    
    # Отправляем уведомление администратору
    try:
        admin_message = f"📝 НОВЫЙ ОТЗЫВ\n\nОтправитель: {full_name}\nUsername: @{username}\n\nСообщение:\n{feedback_text}"
        await bot.send_message(ADMIN_ID, admin_message)
    except:
        pass  # Если не отправилось — не страшно, отзыв сохранён в БД

# --- Запуск ---
async def start_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    print("🤖 Кофе-бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    thread = Thread(target=run_flask)
    thread.start()
    asyncio.run(start_bot())