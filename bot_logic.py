# bot_logic.py
import os
import json
import re
# ДОБАВЛЕН Dispatcher в импорты
from aiogram import Router, F, types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import database as db

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 12345))
WEB_APP_URL = os.getenv("WEB_APP_URL", "") 

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

# --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
dp = Dispatcher()  # Создаем диспетчер
router = Router()  # Создаем роутер
dp.include_router(router) # Подключаем роутер к диспетчеру
# -------------------------

# --- СОСТОЯНИЯ ---
class Registration(StatesGroup):
    choosing_lang = State()
    input_name = State()

class QuizCreation(StatesGroup):
    waiting_title = State()
    waiting_code = State()
    waiting_smart_input = State()
    waiting_random = State()

class AdminActions(StatesGroup):
    waiting_role_id = State()
    waiting_role_name = State() 
    waiting_ban_id = State()
    waiting_ban_reason = State()

class StudentActions(StatesGroup):
    waiting_quiz_code = State()

# --- ТЕКСТЫ ---
MESSAGES = {
    "ru": {
        "menu_admin": "🛠 Админка",
        "menu_student": "👨‍🎓 Ученик",
        "menu_teacher": "👨‍🏫 Учитель",
        "btn_create": "➕ Создать тест",
        "btn_users": "👥 Пользователи",
        "btn_role": "👮‍♂️ Дать роль",
        "btn_start_web": "🚀 Пройти тест (Web App)",
        "users_list": "Список:\n{list}",
        "ban_ask": "Введите ID для бана/сброса:",
        "ban_reason": "Причина (или 'reset'):",
        "role_ask_id": "Введите ID пользователя:",
        "role_ask_role": "Выберите роль (admin, teacher, student):",
        "role_done": "Роль обновлена.",
        "smart_instr": "Отправьте вопросы списком (отметьте правильные через (v) или (+)).",
        "quiz_saved": "Тест сохранен! Код: {code}",
        "enter_code": "Введите код теста:",
        "open_webapp": "Нажмите кнопку ниже, чтобы начать тест 👇"
    }
}

# --- КЛАВИАТУРЫ ---
def get_main_menu(role):
    kb = []
    if role == "student":
        kb.append([InlineKeyboardButton(text="▶️ Пройти тест", callback_data="start_quiz")])
    if role == "admin":
        kb.append([InlineKeyboardButton(text="➕ Создать", callback_data="create_quiz")])
        kb.append([InlineKeyboardButton(text="👥 Люди & Бан", callback_data="view_users")])
        kb.append([InlineKeyboardButton(text="👮‍♂️ Сменить роль", callback_data="set_role")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_role_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Admin", callback_data="role_admin")],
        [InlineKeyboardButton(text="Teacher", callback_data="role_teacher")],
        [InlineKeyboardButton(text="Student", callback_data="role_student")]
    ])

# --- ЛОГИКА ---

@router.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await db.init_db() 
    uid = message.from_user.id
    
    user = await db.get_user(uid)
    if user and user['is_banned']:
        await message.answer(f"⛔ БАН: {user['ban_reason']}")
        return

    if uid == ADMIN_ID:
        if not user:
            await db.add_user(uid, "Admin", "ru", message.from_user.username, message.from_user.full_name, "admin")
        else:
            await db.set_role(uid, "admin")
        user = await db.get_user(uid)

    if not user:
        await db.add_user(uid, message.from_user.full_name, "ru", message.from_user.username, message.from_user.full_name, "student")
        user = await db.get_user(uid)
    
    await message.answer(MESSAGES['ru'][f"menu_{user['role']}"], 
                         reply_markup=get_main_menu(user['role']))

# --- АДМИН: СМЕНА РОЛИ ---
@router.callback_query(F.data == "set_role")
async def set_role_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer(MESSAGES['ru']["role_ask_id"])
    await state.set_state(AdminActions.waiting_role_id)
    await call.answer()

@router.message(AdminActions.waiting_role_id)
async def role_id_input(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(target_id=uid)
        await message.answer(MESSAGES['ru']["role_ask_role"], reply_markup=get_role_kb())
        await state.set_state(AdminActions.waiting_role_name)
    except:
        await message.answer("Нужно число (ID).")

@router.callback_query(AdminActions.waiting_role_name)
async def role_finish(call: types.CallbackQuery, state: FSMContext):
    role = call.data.split("_")[1] 
    data = await state.get_data()
    target_id = data['target_id']
    
    await db.set_role(target_id, role)
    await call.message.answer(f"✅ Роль {target_id} изменена на {role}")
    await state.clear()
    await call.answer()

# --- АДМИН: ПОЛЬЗОВАТЕЛИ И БАН ---
@router.callback_query(F.data == "view_users")
async def view_users(call: types.CallbackQuery, state: FSMContext):
    users = await db.get_all_users()
    txt = "\n".join([f"{u['user_id']} | {u['name']} | {u['role']} | Ban:{u['is_banned']}" for u in users])
    if len(txt) > 4000: txt = txt[:4000]
    
    await call.message.answer(f"Пользователи:\n{txt}\n\nВведите ID для действий:")
    await state.set_state(AdminActions.waiting_ban_id)
    await call.answer()

@router.message(AdminActions.waiting_ban_id)
async def ban_id_input(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(ban_id=uid)
        await message.answer("Причина бана (или напишите 'reset' для сброса):")
        await state.set_state(AdminActions.waiting_ban_reason)
    except:
        await message.answer("ID должен быть числом.")

@router.message(AdminActions.waiting_ban_reason)
async def ban_finish(message: types.Message, state: FSMContext):
    reason = message.text
    data = await state.get_data()
    uid = data['ban_id']
    
    if reason.lower().strip() == "reset":
        await db.reset_user(uid)
        await message.answer(f"♻️ Пользователь {uid} сброшен (разбанен, результаты удалены).")
    else:
        await db.ban_user(uid, reason)
        await message.answer(f"⛔ Пользователь {uid} забанен.")
    await state.clear()

# --- АДМИН: СОЗДАНИЕ ТЕСТА ---
@router.callback_query(F.data == "create_quiz")
async def create_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Название теста:")
    await state.set_state(QuizCreation.waiting_title)
    await call.answer()

@router.message(QuizCreation.waiting_title)
async def create_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Код теста (уникальный):")
    await state.set_state(QuizCreation.waiting_code)

@router.message(QuizCreation.waiting_code)
async def create_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    await state.update_data(code=code)
    await message.answer(MESSAGES['ru']['smart_instr'])
    await state.set_state(QuizCreation.waiting_smart_input)

@router.message(QuizCreation.waiting_smart_input)
async def create_parse(message: types.Message, state: FSMContext):
    text = message.text
    questions = []
    blocks = re.split(r'\n\s*\n', text.strip())
    for block in blocks:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(lines) < 2: continue
        q_text = lines[0]
        options = []
        correct = 0
        for i, line in enumerate(lines[1:]):
            if "(+)" in line or "(v)" in line or "(correct)" in line:
                correct = i
                line = line.replace("(+)", "").replace("(v)", "").replace("(correct)", "")
            options.append(line.strip())
        questions.append({"text": q_text, "options": options, "correct": correct})
    
    if not questions:
        await message.answer("Не удалось найти вопросы. Попробуйте еще раз.")
        return

    data = await state.get_data()
    await db.create_quiz(data['code'], data['title'], message.from_user.id, questions, is_random=0)
    await message.answer(f"✅ Тест создан! Код: {data['code']}")
    await state.clear()

# --- УЧЕНИК: WEB APP ---
@router.callback_query(F.data == "start_quiz")
async def enter_code(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите код теста:")
    await state.set_state(StudentActions.waiting_quiz_code)
    await call.answer()

@router.message(StudentActions.waiting_quiz_code)
async def give_webapp_link(message: types.Message, state: FSMContext):
    code = message.text.strip()
    quiz = await db.get_quiz(code)
    if not quiz:
        await message.answer("Нет такого теста.")
        return
    
    webapp_url = f"{WEB_APP_URL}/quiz/{code}?user_id={message.from_user.id}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 ОТКРЫТЬ ТЕСТ", web_app=WebAppInfo(url=webapp_url))]
    ])
    
    await message.answer(f"Тест: <b>{quiz['title']}</b> найден.\nНажмите кнопку, чтобы начать.", reply_markup=kb)
    await state.clear()