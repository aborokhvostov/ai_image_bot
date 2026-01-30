# keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎨 Создать изображение")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="📦 Купить")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_buy_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Старт — 10 генераций (99₽)", callback_data="buy_10")],
        [InlineKeyboardButton(text="⭐ Популярный — 50 генераций (299₽)", callback_data="buy_50")],
        [InlineKeyboardButton(text="🚀 Про — 200 генераций (999₽)", callback_data="buy_200")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel")]
    ])
