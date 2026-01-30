# database_simple.py - для быстрого старта без Supabase
import aiosqlite
import os

class Database:
    def __init__(self):
        self.db_path = "/tmp/bot.db"  # временное хранилище в памяти сервера

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        await self.create_tables()

    async def close(self):
        await self.conn.close()

    async def create_tables(self):
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 3,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await self.conn.commit()

    async def get_balance(self, telegram_id):
        cursor = await self.conn.execute(
            'SELECT balance FROM users WHERE telegram_id = ?', 
            (telegram_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 3

    async def deduct_credits(self, telegram_id, amount):
        balance = await self.get_balance(telegram_id)
        if balance < amount:
            return False
        new_balance = balance - amount
        await self.conn.execute(
            'INSERT OR REPLACE INTO users (telegram_id, balance) VALUES (?, ?)',
            (telegram_id, new_balance)
        )
        await self.conn.commit()
        return True
