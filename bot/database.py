# database.py
import os
import json
import asyncpg
from urllib.parse import urlparse

# На Render URL базы будет в переменной окружения DATABASE_URL
# Для локального теста можно вставить свой url: postgres://user:pass@localhost/dbname
DB_URL = os.getenv("DATABASE_URL")

async def get_pool():
    return await asyncpg.create_pool(DB_URL)

async def init_db():
    if not DB_URL:
        print("ОШИБКА: Не задана DATABASE_URL. Бот не сможет работать с БД.")
        return

    conn = await asyncpg.connect(DB_URL)
    try:
        # Таблица пользователей
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                name TEXT,
                role TEXT DEFAULT 'student',
                lang TEXT DEFAULT 'ru',
                username TEXT,
                telegram_name TEXT,
                is_banned INT DEFAULT 0,
                ban_reason TEXT
            )
        ''')
        # Таблица викторин
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS quizzes (
                code TEXT PRIMARY KEY,
                title TEXT,
                creator_id BIGINT,
                questions JSONB,
                is_random INT DEFAULT 0
            )
        ''')
        # Таблица результатов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS results (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                quiz_code TEXT,
                score INT,
                total INT,
                answers JSONB
            )
        ''')
    finally:
        await conn.close()

# --- ФУНКЦИИ ---

async def add_user(user_id, name, lang, username, telegram_name, role="student"):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute('''
            INSERT INTO users (user_id, name, role, lang, username, telegram_name)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id) DO UPDATE 
            SET name=$2, lang=$4, username=$5, telegram_name=$6
        ''', user_id, name, role, lang, username, telegram_name)
    finally:
        await conn.close()

async def get_user(user_id):
    conn = await asyncpg.connect(DB_URL)
    row = await conn.fetchrow('SELECT * FROM users WHERE user_id=$1', user_id)
    await conn.close()
    return row

async def get_all_users():
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch('SELECT user_id, name, username, telegram_name, role, is_banned FROM users')
    await conn.close()
    return rows

async def set_role(user_id, role):
    conn = await asyncpg.connect(DB_URL)
    await conn.execute('UPDATE users SET role=$1 WHERE user_id=$2', role, user_id)
    await conn.close()

async def ban_user(user_id, reason):
    conn = await asyncpg.connect(DB_URL)
    await conn.execute('UPDATE users SET is_banned=1, ban_reason=$1 WHERE user_id=$2', reason, user_id)
    await conn.close()

async def reset_user(user_id):
    conn = await asyncpg.connect(DB_URL)
    # Снимаем бан
    await conn.execute('UPDATE users SET is_banned=0, ban_reason=NULL WHERE user_id=$1', user_id)
    # Удаляем результаты
    await conn.execute('DELETE FROM results WHERE user_id=$1', user_id)
    await conn.close()

async def create_quiz(code, title, creator_id, questions_list, is_random):
    conn = await asyncpg.connect(DB_URL)
    # В asyncpg json передается как строка, если поле JSONB
    q_json = json.dumps(questions_list, ensure_ascii=False)
    await conn.execute('INSERT INTO quizzes (code, title, creator_id, questions, is_random) VALUES ($1, $2, $3, $4, $5)',
                       code, title, creator_id, q_json, is_random)
    await conn.close()

async def get_quiz(code):
    conn = await asyncpg.connect(DB_URL)
    row = await conn.fetchrow('SELECT * FROM quizzes WHERE code=$1', code)
    await conn.close()
    if row:
        return {
            'code': row['code'],
            'title': row['title'],
            'questions': json.loads(row['questions']),
            'is_random': row['is_random']
        }
    return None

async def save_result(user_id, quiz_code, score, total, answers):
    conn = await asyncpg.connect(DB_URL)
    a_json = json.dumps(answers)
    await conn.execute('INSERT INTO results (user_id, quiz_code, score, total, answers) VALUES ($1, $2, $3, $4, $5)',
                       user_id, quiz_code, score, total, a_json)
    await conn.close()

async def check_if_taken(user_id, quiz_code):
    conn = await asyncpg.connect(DB_URL)
    row = await conn.fetchrow('SELECT * FROM results WHERE user_id=$1 AND quiz_code=$2', user_id, quiz_code)
    await conn.close()
    return row is not None

async def get_results(quiz_code):
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch('''
        SELECT u.name, r.score, r.total 
        FROM results r 
        JOIN users u ON r.user_id = u.user_id 
        WHERE r.quiz_code=$1
    ''', quiz_code)
    await conn.close()
    return rows