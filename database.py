# database.py — ИСПРАВЛЕННАЯ ВЕРСИЯ ДЛЯ RAILWAY
import asyncpg
import os
from urllib.parse import urlparse

class Database:
    def __init__(self):
        self.pool = None
    
    async def connect(self):
        """Подключение к базе данных с правильной обработкой хостов Railway"""
        db_url = os.getenv("DATABASE_URL")
        
        if not db_url:
            raise ValueError("❌ DATABASE_URL не установлен в переменных окружения")
        
        # 🔍 Диагностика
        parsed = urlparse(db_url)
        host = parsed.hostname or "неизвестно"
        is_internal = "railway.internal" in host
        
        print(f"🔍 Подключение к БД:")
        print(f"   Хост: {host}")
        print(f"   Внутренний: {'✅ да' if is_internal else '❌ нет'}")
        
        try:
            # 🔧 Для внутренних хостов НЕ используем SSL (ломает подключение)
            # 🔧 Для публичных хостов используем стандартные настройки
            if is_internal:
                # Внутреннее подключение без SSL
                self.pool = await asyncpg.create_pool(
                    db_url,
                    min_size=1,
                    max_size=5,
                    command_timeout=60,
                    ssl=None  # ЯВНО отключаем SSL для внутренних хостов
                )
            else:
                # Публичное подключение с автоматическим SSL
                self.pool = await asyncpg.create_pool(
                    db_url,
                    min_size=1,
                    max_size=5,
                    command_timeout=60
                )
            
            print(f"✅ Подключение к БД установлено")
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if 'name or service not known' in error_msg or 'gaierror' in error_msg:
                raise ConnectionError(
                    "❌ Ошибка: хост базы данных не найден.\n"
                    "РЕШЕНИЕ:\n"
                    "1. Убедитесь, что БД и бот в одном проекте Railway\n"
                    "2. Используйте ПУБЛИЧНУЮ строку подключения (не *.railway.internal)\n"
                    "3. Скопируйте Connection URL из вкладки 'Connect' сервиса PostgreSQL"
                )
            elif 'network is unreachable' in error_msg:
                raise ConnectionError(
                    "❌ Ошибка сети. Используйте публичный URL базы данных из вкладки 'Connect'"
                )
            else:
                raise ConnectionError(f"❌ Ошибка подключения: {str(e)}")
    
    async def close(self):
        """Безопасное закрытие соединения"""
        if self.pool:
            await self.pool.close()
            print("🔌 Соединение с БД закрыто")
    
    async def create_tables(self):
        """Создание таблиц если не существуют"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    balance INTEGER DEFAULT 0,
                    total_generations INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_active TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS generations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    telegram_id BIGINT NOT NULL,
                    prompt TEXT NOT NULL,
                    negative_prompt TEXT,
                    image_url TEXT,
                    telegram_file_id VARCHAR(255),
                    cost INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS purchases (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    telegram_id BIGINT NOT NULL,
                    package VARCHAR(50) NOT NULL,
                    amount_rub INTEGER NOT NULL,
                    credits_added INTEGER NOT NULL,
                    payment_id VARCHAR(255) UNIQUE,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW(),
                    paid_at TIMESTAMP
                )
            ''')
            
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_generations_telegram_id ON generations(telegram_id)')
            
            print("✅ Таблицы БД проверены/созданы")
    
    # ===== ОСНОВНЫЕ МЕТОДЫ =====
    async def create_user(self, telegram_id, username=None, first_name=None, last_name=None):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users (telegram_id, username, first_name, last_name, balance)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (telegram_id) DO UPDATE 
                SET last_active = NOW(),
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name
            ''', telegram_id, username, first_name, last_name, 0)
    
    async def add_credits(self, telegram_id, amount):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE users SET balance = balance + $1, last_active = NOW()
                WHERE telegram_id = $2
            ''', amount, telegram_id)
    
    async def deduct_credits(self, telegram_id, amount):
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE users SET balance = balance - $1, last_active = NOW()
                WHERE telegram_id = $2 AND balance >= $1
            ''', amount, telegram_id)
            return "UPDATE 1" in result
    
    async def get_balance(self, telegram_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT balance FROM users WHERE telegram_id = $1',
                telegram_id
            )
            return row['balance'] if row else 0
    
    async def get_stats(self, telegram_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow('''
                SELECT 
                    COALESCE(balance, 0) as balance,
                    (SELECT COUNT(*) FROM generations WHERE telegram_id = $1) as generations_count
                FROM users WHERE telegram_id = $1
            ''', telegram_id)
    
    async def save_generation(self, telegram_id, prompt, image_url=None, file_id=None, 
                             cost=1, negative_prompt=None):
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow(
                'SELECT id FROM users WHERE telegram_id = $1',
                telegram_id
            )
            if not user:
                return
            
            await conn.execute('''
                INSERT INTO generations 
                (user_id, telegram_id, prompt, negative_prompt, image_url, telegram_file_id, cost)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            ''', user['id'], telegram_id, prompt, negative_prompt, image_url, file_id, cost)
            
            await conn.execute('''
                UPDATE users SET total_generations = total_generations + 1
                WHERE telegram_id = $1
            ''', telegram_id)
    
    async def get_user_generations(self, telegram_id, limit=10):
        async with self.pool.acquire() as conn:
            return await conn.fetch('''
                SELECT * FROM generations
                WHERE telegram_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            ''', telegram_id, limit)
    
    async def create_purchase(self, telegram_id, package, amount_rub, credits_added, payment_id):
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow(
                'SELECT id FROM users WHERE telegram_id = $1',
                telegram_id
            )
            if not user:
                return
            
            await conn.execute('''
                INSERT INTO purchases 
                (user_id, telegram_id, package, amount_rub, credits_added, payment_id, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            ''', user['id'], telegram_id, package, amount_rub, credits_added, payment_id, 'pending')
