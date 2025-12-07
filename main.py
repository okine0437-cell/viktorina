# main.py
import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from aiogram.types import Update

# Импортируем уже настроенный dp из bot_logic
from bot_logic import bot, dp, router, WEB_APP_URL
import database as db

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# СТРОКУ dp.include_router(router) МЫ УДАЛИЛИ! ОНА БОЛЬШЕ НЕ НУЖНА.

@app.post("/webhook")
async def bot_webhook(request: Request):
    # ... код дальше без изменений ...
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"status": "ok"}

# --- WEB APP: Страница викторины ---
@app.get("/quiz/{code}", response_class=HTMLResponse)
async def get_quiz_page(request: Request, code: str):
    return templates.TemplateResponse("quiz.html", {"request": request})

# --- API: Данные для Web App ---
@app.get("/api/get_quiz/{code}")
async def api_get_quiz(code: str):
    quiz = await db.get_quiz(code)
    # Скрываем правильные ответы от фронтенда, чтобы не подсмотрели в исходном коде
    safe_questions = []
    if quiz:
        for q in quiz['questions']:
            safe_questions.append({
                "text": q['text'],
                "options": q['options'],
                "correct": q['correct'] # Вообще лучше это не передавать, но для проверки на JS передаем.
                                        # Если хотите полной защиты, проверку нужно делать на бэкенде в /submit_result
            })
        return {"questions": safe_questions}
    return {"error": "Not found"}

@app.post("/api/submit_result")
async def api_submit(data: dict):
    # data: user_id, quiz_code, score, total, answers
    await db.save_result(
        data['user_id'], 
        data['quiz_code'], 
        data['score'], 
        data['total'], 
        data['answers']
    )
    # Уведомляем учителя (можно дописать)
    return {"status": "saved"}

# --- СТАРТ И СТОП ---
@app.on_event("startup")
async def on_startup():
    await db.init_db()
    # Устанавливаем вебхук
    webhook_url = f"{WEB_APP_URL}/webhook"
    await bot.set_webhook(webhook_url)
    print(f"Webhook set to: {webhook_url}")

if __name__ == "__main__":
    # Локальный запуск
    uvicorn.run(app, host="0.0.0.0", port=8000)