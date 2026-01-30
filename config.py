# config.py
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY")

# Настройки моделей
REPLICATE_MODEL = "black-forest-labs/flux-1-dev"
DEFAULT_ASPECT_RATIO = "1:1"
DEFAULT_OUTPUT_FORMAT = "webp"

# Бизнес-логика
COST_STANDARD = 1
FREE_GENERATIONS = 3
