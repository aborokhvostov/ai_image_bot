# database.py
import asyncpg
import os
import urllib.parse
from datetime import datetime

class Database:
    def __init__(self):
        self.pool = None
    
    async def connect(self):
        """Подключение к базе данных с полной диагностикой"""
        db_url = os.getenv("DATABASE_URL")
        
        if not db_url:
            raise ValueError(
                "❌ DATABASE_URL не установлен!\n"
                "Проверьте Variables в Railway → добавьте:\n"
                "DATABASE_URL = postgresql://postgres:пароль@db.xxxxx.supabase.co:5432/postgres?sslmode=require"
            )
        
        # 🔍 Диагностика строки подключения
        print(f"🔍 Проверка строки подключения:")
        print(f"   Хост: {self._extract_host(db_url)}")
        print(f"   SSL:  {'✅ включён' if 'sslmode=require' in db_url.lower() else '⚠️ отсутствует'}")
        
        # 🔧 Автоматическое добавление SSL если отсутствует
        if 'sslmode=' not in db_url.lower():
            if '?' in db_url:
                db_url += '&sslmode=require'
            else:
                db_url += '?sslmode=require'
            print(f"🔧 Добавлен параметр sslmode=require")
        
        try:
            self.pool = await asyncpg.create_pool(
                db_url,
                min_size=1,
                max_size=5,
                command_timeout=60,
                ssl='require'
            )
            print(f"✅ Подключение к БД установлено")
        except Exception as e:
            error_msg = str(e).lower()
            
            if 'network is unreachable' in error_msg or 'cannot assign requested address' in error_msg:
                raise ConnectionError(
                    "❌ Ошибка сети: Не удаётся подключиться к базе данных.\n"
                    "РЕШЕНИЕ:\n"
                    "1. В Supabase: Settings → Database → Network Restrictions\n"
                    "2. Добавьте правило: 0.0.0.0/0\n"
                    "3. Сохраните и перезапустите бота"
                )
            elif 'password authentication failed' in error_msg:
                raise ConnectionError(
                    "❌ Ошибка аутентификации: Неверный пароль.\n"
                    "Проверьте DATABASE_URL — пароль должен быть правильным."
                )
            else:
                raise ConnectionError(f"❌ Ошибка подключения: {str(e)}")
    
    def _extract_host(self, url):
        try:
            if '://' in url:
                url = url.split('://')[1]
            if '@' in url:
                url = url.split('@')[1]
            return url.split(':')[0].split('/')[0]
        except:
            return "неизвестно"
    
    async def close(self):
        """Безопасное закрытие соединения"""
        if self.pool:
            await self.pool.close()
            print("🔌 Соединение с БД закрыто")
    
    async def create_tables(self):
        """Создание таблиц если не существуют"""
        async with self.pool.acquire() as conn:
            # Таблица пользователей
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
            
            # Таблица генераций
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
            
            # Таблица покупок
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
            
            # Индексы
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_generations_telegram_id ON generations(telegram_id)')
            
            print("✅ Таблицы БД проверены/созданы")
    
    # ===== ОСНОВНЫЕ МЕТОДЫ (полная реализация) =====
    
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
