# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# 🔴 ДОБАВЛЕНА ПРОВЕРКА НАЛИЧИЯ ПЕРЕМЕННЫХ
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не установлен в переменных окружения")

REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY")
if not REPLICATE_API_KEY:
    raise ValueError("❌ REPLICATE_API_KEY не установлен в переменных окружения")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не установлен в переменных окружения")

# Настройки моделей
REPLICATE_MODEL = "black-forest-labs/flux-1-dev"
DEFAULT_ASPECT_RATIO = "1:1"
DEFAULT_OUTPUT_FORMAT = "webp"

# Бизнес-логика
COST_STANDARD = 1
FREE_GENERATIONS = 3
MAX_PROMPT_LENGTH = 1000
