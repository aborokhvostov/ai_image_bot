## 📄 ФАЙЛ 1: `main.py` — ГЛАВНЫЙ ФАЙЛ БОТА

```python
# main.py
"""
AI Image Generator Bot — Telegram бот для генерации изображений через ИИ
Бесплатный старт на Railway + Supabase + Replicate
"""

import asyncio
import logging
import replicate
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from config import *
from database import Database
from keyboards import *

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация
load_dotenv()
bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
db = Database()

# Состояния для FSM
class GenerationStates(StatesGroup):
    waiting_for_prompt = State()
    waiting_for_negative_prompt = State()

# ===== КОМАНДА /start =====
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user = message.from_user
    
    # Создаём пользователя
    await db.create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Проверяем, новый ли пользователь
    balance = await db.get_balance(user.id)
    is_new = balance == 0
    
    if is_new:
        await db.add_credits(user.id, FREE_GENERATIONS)
        balance = FREE_GENERATIONS
    
    welcome_text = (
        "🎨 <b>Добро пожаловать в AI Image Generator!</b>\n\n"
        "✨ Создавайте потрясающие изображения с помощью искусственного интеллекта.\n\n"
        "📝 <b>Как это работает:</b>\n"
        "1️⃣ Напишите описание изображения на русском или английском языке.\n"
        "2️⃣ Получите результат за 10-15 секунд.\n"
        "3️⃣ Наслаждайтесь!\n\n"
        f"💰 <b>Ваш баланс:</b> {balance} генераций"
    )
    
    if is_new:
        welcome_text += "\n\n🎁 <b>Вам начислено 3 бесплатных генерации!</b>"
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())
    await state.clear()

# ===== КНОПКА "Создать изображение" =====
@dp.message(lambda message: message.text == "🎨 Создать изображение")
async def btn_generate(message: Message, state: FSMContext):
    balance = await db.get_balance(message.from_user.id)
    
    if balance <= 0:
        await message.answer(
            "❌ У вас закончились генерации!\nПополните баланс: /buy",
            reply_markup=get_buy_keyboard()
        )
        return
    
    await message.answer(
        "🎨 <b>Введите описание изображения:</b>\n\n"
        "💡 Можно на русском или английском.\n"
        "Пример: <code>Фотореалистичный портрет девушки с рыжими волосами в парке, закат, 85мм</code>",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GenerationStates.waiting_for_prompt)

# ===== ПОЛУЧЕНИЕ ПРОМПТА =====
@dp.message(GenerationStates.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    
    if len(prompt) < 5:
        await message.answer("❌ Промпт слишком короткий! Напишите подробнее (минимум 5 символов).")
        return
    
    if len(prompt) > MAX_PROMPT_LENGTH:
        await message.answer(f"❌ Промпт слишком длинный! Максимум {MAX_PROMPT_LENGTH} символов.")
        return
    
    await state.update_data(prompt=prompt)
    
    await message.answer(
        "🎨 Промпт получен!\n\n"
        "Хотите добавить негативный промпт? (что НЕ должно быть на изображении)\n"
        "Пример: <code>размытое, плохое качество, искажённые лица</code>\n\n"
        "Напишите или нажмите /skip чтобы пропустить.",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GenerationStates.waiting_for_negative_prompt)

# ===== ПРОПУСК НЕГАТИВНОГО ПРОМПТА =====
@dp.message(Command("skip"))
async def skip_negative_prompt(message: Message, state: FSMContext):
    await state.update_data(negative_prompt=None)
    await generate_image_final(message, state)

# ===== ПОЛУЧЕНИЕ НЕГАТИВНОГО ПРОМПТА =====
@dp.message(GenerationStates.waiting_for_negative_prompt)
async def process_negative_prompt(message: Message, state: FSMContext):
    await state.update_data(negative_prompt=message.text.strip())
    await generate_image_final(message, state)

# ===== ФИНАЛЬНАЯ ГЕНЕРАЦИЯ =====
async def generate_image_final(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    prompt = data.get('prompt', '')
    negative_prompt = data.get('negative_prompt')
    
    # Проверяем баланс
    balance = await db.get_balance(user_id)
    if balance < COST_STANDARD:
        await message.answer("❌ Недостаточно генераций! Пополните баланс: /buy")
        await state.clear()
        return
    
    # Индикатор "печатает..."
    await bot.send_chat_action(message.chat.id, "upload_photo")
    
    try:
        # Генерация через Replicate
        image_url = await generate_with_replicate(prompt, negative_prompt)
        
        # Отправка изображения
        sent_msg = await bot.send_photo(
            chat_id=message.chat.id,
            photo=image_url,
            caption=(
                f"✅ <b>Готово!</b>\n\n"
                f"📝 Промпт: <code>{prompt[:50]}...</code>\n"
                f"💰 Потрачено: {COST_STANDARD} генерация"
            ),
            reply_markup=get_image_actions_keyboard(image_url[:50])
        )
        
        # Списание кредитов
        success = await db.deduct_credits(user_id, COST_STANDARD)
        
        if success:
            # Сохранение в историю
            await db.save_generation(
                telegram_id=user_id,
                prompt=prompt,
                negative_prompt=negative_prompt,
                image_url=image_url,
                file_id=sent_msg.photo[-1].file_id,
                cost=COST_STANDARD
            )
            
            # Обновление баланса
            new_balance = await db.get_balance(user_id)
            await message.answer(
                f"💰 <b>Ваш баланс:</b> {new_balance} генераций",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer("⚠️ Ошибка при списании. Обратитесь в поддержку.")
            
    except Exception as e:
        error = str(e).lower()
        
        if "nsfw" in error or "inappropriate" in error:
            await message.answer(
                "❌ Контент распознан как неприемлемый.\n"
                "Измените промпт и попробуйте снова."
            )
        elif "rate limit" in error:
            await message.answer("⏳ Превышен лимит. Подождите 1-2 минуты.")
        else:
            await message.answer(f"❌ Ошибка: {str(e)[:100]}")
        
        # Возврат кредитов при ошибке
        await db.add_credits(user_id, COST_STANDARD)
    
    finally:
        await state.clear()

# ===== ГЕНЕРАЦИЯ ЧЕРЕЗ REPLICATE =====
async def generate_with_replicate(prompt: str, negative_prompt: str = None) -> str:
    """Генерация изображения через Replicate API"""
    
    # Улучшаем промпт
    enhanced = f"{prompt}, high quality, detailed, professional, 4k"
    
    input_data = {
        "prompt": enhanced,
        "aspect_ratio": DEFAULT_ASPECT_RATIO,
        "output_format": DEFAULT_OUTPUT_FORMAT
    }
    
    if negative_prompt:
        input_data["negative_prompt"] = negative_prompt
    
    # Асинхронный вызов
    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None,
        lambda: replicate.run(REPLICATE_MODEL, input=input_data)
    )
    
    if not output:
        raise Exception("Пустой ответ от модели")
    
    return output[0]

# ===== КОМАНДА /balance =====
@dp.message(Command("balance"))
@dp.message(lambda message: message.text == "💰 Баланс")
async def cmd_balance(message: Message):
    stats = await db.get_stats(message.from_user.id)
    
    if not stats:
        await message.answer("❌ Напишите /start для регистрации")
        return
    
    await message.answer(
        f"💰 <b>Ваш баланс:</b>\n\n"
        f"📊 Доступно: <b>{stats['balance']}</b> генераций\n"
        f"🎨 Создано: <b>{stats['generations_count']}</b> изображений",
        reply_markup=get_main_keyboard()
    )

# ===== КОМАНДА /buy =====
@dp.message(Command("buy"))
@dp.message(lambda message: message.text == "📦 Купить")
async def cmd_buy(message: Message):
    await message.answer(
        "📦 <b>Выберите пакет:</b>\n\n"
        "🔥 Старт — 10 генераций за 99₽\n"
        "⭐ Популярный — 50 за 299₽ (экономия 40%)\n"
        "🚀 Про — 200 за 999₽ (экономия 50%)\n"
        "💎 Безлимит — 7 дней за 499₽",
        reply_markup=get_buy_keyboard()
    )

# ===== ОБРАБОТКА ПОКУПКИ =====
@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    packages = {
        "buy_10": {"credits": 10, "price": 99, "name": "Старт"},
        "buy_50": {"credits": 50, "price": 299, "name": "Популярный"},
        "buy_200": {"credits": 200, "price": 999, "name": "Про"},
        "buy_unlimited_week": {"credits": 500, "price": 499, "name": "Безлимит неделя"}
    }
    
    pkg_key = callback.data.replace("buy_", "")
    pkg = packages.get(pkg_key)
    
    if not pkg:
        await callback.answer("❌ Пакет не найден")
        return
    
    # Генерация ID платежа
    from datetime import datetime
    payment_id = f"{callback.from_user.id}_{int(datetime.now().timestamp())}"
    
    # Создание записи о покупке
    await db.create_purchase(
        telegram_id=callback.from_user.id,
        package=pkg_key,
        amount_rub=pkg['price'],
        credits_added=pkg['credits'],
        payment_id=payment_id
    )
    
    # ЗАГЛУШКА ПЛАТЕЖА (интеграция ЮKassa будет позже)
    await callback.message.edit_text(
        f"💳 <b>Оплата пакета «{pkg['name']}»</b>\n\n"
        f"🔢 Генераций: <b>{pkg['credits']}</b>\n"
        f"💰 Сумма: <b>{pkg['price']}₽</b>\n\n"
        f"🆔 Заказ: <code>{payment_id}</code>\n\n"
        "⚠️ <b>Платёжная система в разработке.</b>\n\n"
        "Для тестирования напишите администратору (@ваш_ник) с номером заказа для ручного пополнения.",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

# ===== КОМАНДА /history =====
@dp.message(Command("history"))
@dp.message(lambda message: message.text == "📚 История")
async def cmd_history(message: Message):
    gens = await db.get_user_generations(message.from_user.id, limit=10)
    
    if not gens:
        await message.answer(
            "📚 <b>История пуста.</b>\nСоздайте первое изображение!",
            reply_markup=get_main_keyboard()
        )
        return
    
    text = "📚 <b>Ваши последние генерации:</b>\n\n"
    for i, gen in enumerate(gens, 1):
        prompt = gen['prompt'][:40] + "..." if len(gen['prompt']) > 40 else gen['prompt']
        date = gen['created_at'].strftime("%d.%m %H:%M")
        text += f"{i}. {date} — <code>{prompt}</code>\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML)

# ===== КОМАНДА /help =====
@dp.message(Command("help"))
@dp.message(lambda message: message.text == "❓ Помощь")
async def cmd_help(message: Message):
    await message.answer(
        "❓ <b>Помощь</b>\n\n"
        "<b>Как писать хорошие промпты:</b>\n\n"
        "✅ <b>Будьте конкретны:</b>\n"
        "«Кот» → «Фотореалистичный кот сиамской породы на подоконнике, солнечный свет, 85мм»\n\n"
        
        "✅ <b>Добавляйте детали:</b>\n"
        "• Стиль: фотография, аниме, цифровая живопись\n"
        "• Освещение: закат, студийный свет, неоновое\n"
        "• Качество: 4к, высокая детализация, профессионально\n\n"
        
        "✅ <b>Примеры:</b>\n"
        "• Портрет женщины с рыжими волосами, винтажное платье 1950-х, студийное освещение, 85мм, f/1.8\n"
        "• Киберпанк город в дождь ночью, неоновые вывески, цифровая живопись",
        parse_mode=ParseMode.HTML,
        reply_markup=get_help_keyboard()
    )

# ===== ОБРАБОТКА КНОПОК =====
@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎨 Выберите действие:",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

# ===== ЗАПУСК БОТА =====
async def main():
    """Основная функция запуска"""
    logger.info("Инициализация базы данных...")
    await db.connect()
    await db.create_tables()
    logger.info("База данных готова")
    
    logger.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    finally:
        asyncio.run(db.close())
