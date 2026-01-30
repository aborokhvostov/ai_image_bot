# main.py
import asyncio
import logging
import replicate
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
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

bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
db = Database()

# ===== КОМАНДА /start =====
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = message.from_user
    
    # Создаём/обновляем пользователя
    await db.create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Проверяем баланс
    balance = await db.get_balance(user.id)
    
    # Если новый пользователь — даём бонус
    if balance == 0:
        await db.add_credits(user.id, FREE_GENERATIONS)
        balance = FREE_GENERATIONS
        bonus_text = "\n\n🎁 <b>Вам начислено 3 бесплатных генерации!</b>"
    else:
        bonus_text = ""
    
    welcome_text = (
        "🎨 <b>Добро пожаловать в AI Image Generator!</b>\n\n"
        "✨ Создавайте изображения с помощью искусственного интеллекта.\n"
        "Напишите описание на русском или английском языке.\n\n"
        f"💰 <b>Ваш баланс:</b> {balance} генераций"
        f"{bonus_text}"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

# ===== ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЯ (любой текст) =====
@dp.message()
async def generate_image(message: Message):
    # Игнорируем команды и служебные сообщения
    if message.text and message.text.startswith('/'):
        return
    
    user_id = message.from_user.id
    prompt = message.text.strip()
    
    # Проверяем баланс
    balance = await db.get_balance(user_id)
    if balance < COST_STANDARD:
        await message.answer(
            "❌ У вас закончились генерации!\nПополните баланс: /buy",
            reply_markup=get_buy_keyboard()
        )
        return
    
    # Минимальная длина промпта
    if len(prompt) < 5:
        await message.answer("❌ Промпт слишком короткий! Напишите подробнее (минимум 5 символов).")
        return
    
    # Индикатор "печатает..."
    await bot.send_chat_action(message.chat.id, "upload_photo")
    
    try:
        # Генерация через Replicate
        image_url = await generate_with_replicate(prompt)
        
        # Отправка изображения
        sent_msg = await bot.send_photo(
            chat_id=message.chat.id,
            photo=image_url,
            caption=(
                f"✅ <b>Готово!</b>\n\n"
                f"📝 Промпт: <code>{prompt[:60]}...</code>\n"
                f"💰 Потрачено: {COST_STANDARD} генерация"
            )
        )
        
        # Списание кредитов
        success = await db.deduct_credits(user_id, COST_STANDARD)
        
        if success:
            # Сохранение в историю
            await db.save_generation(
                telegram_id=user_id,
                prompt=prompt,
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

async def generate_with_replicate(prompt: str) -> str:
    """ЗАГЛУШКА: возвращает тестовое изображение без вызова API"""
    return "https://picsum.photos/1024/1024?random=1"

# ===== КОМАНДА /balance =====
@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    stats = await db.get_stats(message.from_user.id)
    
    if not stats:
        await message.answer("❌ Напишите /start для регистрации")
        return
    
    await message.answer(
        f"💰 <b>Ваш баланс:</b> {stats['balance']} генераций\n"
        f"🎨 Создано изображений: {stats['generations_count']}"
    )

# ===== КОМАНДА /buy =====
@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    await message.answer(
        "📦 <b>Выберите пакет:</b>\n\n"
        "🔥 Старт — 10 генераций за 99₽\n"
        "⭐ Популярный — 50 за 299₽\n"
        "🚀 Про — 200 за 999₽",
        reply_markup=get_buy_keyboard()
    )

# ===== ОБРАБОТКА ПОКУПКИ =====
@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    packages = {
        "buy_10": {"credits": 10, "price": 99, "name": "Старт"},
        "buy_50": {"credits": 50, "price": 299, "name": "Популярный"},
        "buy_200": {"credits": 200, "price": 999, "name": "Про"}
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
    
    # ЗАГЛУШКА ПЛАТЕЖА
    await callback.message.edit_text(
        f"💳 <b>Оплата пакета «{pkg['name']}»</b>\n\n"
        f"🔢 Генераций: <b>{pkg['credits']}</b>\n"
        f"💰 Сумма: <b>{pkg['price']}₽</b>\n\n"
        f"🆔 Заказ: <code>{payment_id}</code>\n\n"
        "⚠️ <b>Платёжная система в разработке.</b>\n\n"
        "Для тестирования напишите администратору с номером заказа для ручного пополнения.",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

# ===== ЗАПУСК БОТА =====
async def main():
    """Основная функция запуска"""
    # Проверка переменных окружения
    required_vars = {
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "REPLICATE_API_KEY": REPLICATE_API_KEY,
        "DATABASE_URL": os.getenv("DATABASE_URL")
    }
    
    missing = [k for k, v in required_vars.items() if not v]
    if missing:
        logger.error(f"❌ Отсутствуют переменные: {', '.join(missing)}")
        logger.error("Проверьте Variables в Railway")
        return
    
    logger.info("✅ Все переменные окружения загружены")
    
    try:
        logger.info("Инициализация базы данных...")
        await db.connect()
        await db.create_tables()
        logger.info("✅ База данных готова")
        
        # Установка токена Replicate
        replicate.default_client.api_token = REPLICATE_API_KEY
        
        logger.info("🚀 Запуск бота...")
        await dp.start_polling(bot)
        
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
    finally:
        if hasattr(db, 'pool') and db.pool:
            await db.close()
        else:
            logger.warning("⚠️ Соединение с БД не было установлено")

if __name__ == "__main__":
    asyncio.run(main())
