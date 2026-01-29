# keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎨 Создать изображение")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="📦 Купить")],
            [KeyboardButton(text="📚 История"), KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True
    )

def get_buy_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Старт — 10 генераций (99₽)", callback_data="buy_10")],
        [InlineKeyboardButton(text="⭐ Популярный — 50 генераций (299₽)", callback_data="buy_50")],
        [InlineKeyboardButton(text="🚀 Про — 200 генераций (999₽)", callback_data="buy_200")],
        [InlineKeyboardButton(text="💎 Безлимит неделя (499₽)", callback_data="buy_unlimited_week")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_image_actions_keyboard(image_url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Вариации", callback_data=f"variations_{image_url}")],
        [InlineKeyboardButton(text="🔍 Upscale", callback_data=f"upscale_{image_url}")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
    ])

def get_help_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Примеры промптов", callback_data="examples")],
        [InlineKeyboardButton(text="💡 Советы", callback_data="tips")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
