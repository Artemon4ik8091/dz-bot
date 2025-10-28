import telebot
import sqlite3
import json
from telebot import types
from datetime import datetime

# === НАСТРОЙКИ ===
TOKEN = 'TOKEN'  # ← Замени на свой
ADMIN_IDS = [123, 321]   # ← Твой ID (можно добавить другие)

bot = telebot.TeleBot(TOKEN)

# === БАЗА ДАННЫХ + МИГРАЦИЯ ===
def init_db():
    conn = sqlite3.connect('homework.db')
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            task TEXT NOT NULL,
            due_date TEXT,
            photo_file_ids TEXT,
            created_at TEXT
        )
    ''')

    c.execute("PRAGMA table_info(homework)")
    columns = [info[1] for info in c.fetchall()]
    if 'photo_file_ids' not in columns:
        print("Миграция: добавляю photo_file_ids")
        c.execute('ALTER TABLE homework ADD COLUMN photo_file_ids TEXT')

    conn.commit()
    conn.close()

init_db()

# === Проверка админа ===
def is_admin(user_id):
    return user_id in ADMIN_IDS

# === КНОПКИ ===
def main_menu(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_list = types.InlineKeyboardButton("Список ДЗ", callback_data="list")
    markup.add(btn_list)
    if is_admin(user_id):
        btn_add = types.InlineKeyboardButton("Добавить ДЗ", callback_data="add")
        markup.add(btn_add)
    return markup

# === /start ===
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    text = "Привет! Это бот для хранения ДЗ.\n"
    if is_admin(user_id):
        text += "Вы — админ. Можете управлять заданиями."
    else:
        text += "Просматривайте ДЗ через кнопки ниже."
    bot.send_message(message.chat.id, text, reply_markup=main_menu(user_id))

# === Обработка кнопок ===
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    # === ПРОСМОТР ДОСТУПЕН ВСЕМ ===
    if call.data == "list":
        show_subjects_list(call.message)
        return
    elif call.data.startswith("show_subject_"):
        subject = call.data.split("_", 2)[2]
        show_subject_details(call.message, subject, user_id)
        return
    elif call.data == "back_to_main":
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="Главное меню:", reply_markup=main_menu(user_id))
        return

    # === ОСТАЛЬНОЕ — ТОЛЬКО АДМИНАМ ===
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "Доступ запрещён.", show_alert=True)
        return

    if call.data == "add":
        start_add_hw(call.message, user_id)
    elif call.data == "add_more_photos":
        continue_adding_photos(call, user_id)
    elif call.data == "finish_adding":
        finish_adding_hw(call, user_id)
    elif call.data.startswith("edit_subject_"):
        subject = call.data.split("_", 2)[2]
        start_edit_hw(call.message, subject, user_id)
    elif call.data.startswith("delete_subject_"):
        subject = call.data.split("_", 2)[2]
        confirm_delete_by_subject(call.message, subject)
    elif call.data.startswith("confirm_delete_subject_"):
        subject = call.data.split("_", 3)[3]
        do_delete_subject(call, subject)
    elif call.data == "cancel":
        if user_id in add_state:
            del add_state[user_id]
        if user_id in edit_state:
            del edit_state[user_id]
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="Действие отменено.", reply_markup=None)
        bot.send_message(chat_id, "Главное меню:", reply_markup=main_menu(user_id))

# === Список предметов с (фото) — БЕЗ ДУБЛЕЙ ===
def show_subjects_list(message):
    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('SELECT subject, photo_file_ids FROM homework GROUP BY subject ORDER BY MIN(id)')
    rows = c.fetchall()
    conn.close()

    if not rows:
        user_id = message.from_user.id if hasattr(message, 'from_user') else message.chat.id
        bot.send_message(message.chat.id, "Нет ДЗ.", reply_markup=main_menu(user_id))
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []

    for subject, photo_json in rows:
        photos = json.loads(photo_json) if photo_json else []
        label = subject + (f" (фото: {len(photos)})" if photos else "")
        btn = types.InlineKeyboardButton(label, callback_data=f"show_subject_{subject}")
        buttons.append(btn)

    # КОРРЕКТНОЕ ДОБАВЛЕНИЕ: 1 или 2 кнопки в ряд
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            markup.add(buttons[i], buttons[i + 1])
        else:
            markup.add(buttons[i])  # ← Только одна кнопка

    btn_back = types.InlineKeyboardButton("Назад", callback_data="back_to_main")
    markup.add(btn_back)

    bot.send_message(message.chat.id, "*Выберите предмет:*", parse_mode='Markdown', reply_markup=markup)

# === Показать ДЗ + фото + кнопки (админ/не админ) ===
def show_subject_details(message, subject, user_id):
    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('SELECT task, due_date, photo_file_ids FROM homework WHERE subject = ? ORDER BY id', (subject,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, f"ДЗ по *{subject}* не найдено.", parse_mode='Markdown')
        return

    text = f"*ДЗ по предмету: {subject}*\n\n"
    all_photos = []

    for idx, (task, due, photo_json) in enumerate(rows, 1):
        due_text = f"Срок: {due}" if due else "Срок: Не указано"
        photos = json.loads(photo_json) if photo_json else []
        photo_mark = f" (фото: {len(photos)})" if photos else ""
        text += f"*{idx}.*{photo_mark}\n{task}\n{due_text}\n\n"
        all_photos.extend(photos)

    # КНОПКИ
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_back = types.InlineKeyboardButton("Назад к списку", callback_data="list")
    markup.add(btn_back)

    if is_admin(user_id):
        btn_edit = types.InlineKeyboardButton("Редактировать", callback_data=f"edit_subject_{subject}")
        btn_delete = types.InlineKeyboardButton("Удалить", callback_data=f"delete_subject_{subject}")
        markup.add(btn_edit, btn_delete)

    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

    # Фото
    if all_photos:
        media = []
        for i, file_id in enumerate(all_photos):
            caption = f"*{subject}*" if i == 0 else ""
            media.append(types.InputMediaPhoto(file_id, caption=caption, parse_mode='Markdown'))
        try:
            bot.send_media_group(message.chat.id, media)
        except:
            bot.send_message(message.chat.id, "Ошибка при отправке фото.")

# === Добавление ДЗ (только админы) ===
add_state = {}

def start_add_hw(message, user_id):
    add_state[user_id] = {'step': 'subject', 'photos': []}
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id, "Введите *предмет*:", parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: add_state.get(m.from_user.id, {}).get('step') == 'subject')
def get_subject(message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    add_state[user_id]['subject'] = message.text
    add_state[user_id]['step'] = 'task'
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id, "Введите *задание*:", parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: add_state.get(m.from_user.id, {}).get('step') == 'task', content_types=['text'])
def get_task(message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    add_state[user_id]['task'] = message.text
    add_state[user_id]['step'] = 'due_date'
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id, "Введите *срок сдачи* (или `нет`):", parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: add_state.get(m.from_user.id, {}).get('step') == 'due_date')
def get_due_date(message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    due = message.text.strip()
    add_state[user_id]['due_date'] = due if due.lower() != 'нет' else None
    add_state[user_id]['step'] = 'photos'

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_add = types.InlineKeyboardButton("Добавить фото", callback_data="add_more_photos")
    btn_done = types.InlineKeyboardButton("Готово", callback_data="finish_adding")
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_add, btn_done)
    markup.add(btn_cancel)

    sent = bot.send_message(message.chat.id,
                            "Отправьте фото (можно несколько)\n"
                            "или нажмите *Готово*", parse_mode='Markdown', reply_markup=markup)
    add_state[user_id]['last_msg_id'] = sent.message_id

def continue_adding_photos(call, user_id):
    if add_state.get(user_id, {}).get('step') != 'photos': return
    bot.answer_callback_query(call.id, "Отправьте фото...")

@bot.message_handler(func=lambda m: add_state.get(m.from_user.id, {}).get('step') == 'photos', content_types=['photo'])
def get_photos(message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    new_photos = [photo.file_id for photo in message.photo[-1:]]
    add_state[user_id]['photos'].extend(new_photos)
    count = len(add_state[user_id]['photos'])
    bot.reply_to(message, f"Добавлено фото: {count}. Отправьте ещё или нажмите *Готово*.", parse_mode='Markdown')

def finish_adding_hw(call, user_id):
    data = add_state[user_id]
    photos = data['photos']
    photo_json = json.dumps(photos) if photos else None

    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO homework (subject, task, due_date, photo_file_ids, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (data['subject'], data['task'], data['due_date'], photo_json, datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit()
    conn.close()

    response = f"*ДЗ добавлено!*\n\n*{data['subject']}*\n{data['task']}\nСрок: {data['due_date'] or 'Не указано'}"
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton("Назад", callback_data="back_to_main")
    markup.add(btn_back)

    if photos:
        media = [types.InputMediaPhoto(photos[0], caption=response, parse_mode='Markdown')]
        media += [types.InputMediaPhoto(p) for p in photos[1:]]
        bot.send_media_group(call.message.chat.id, media)
    else:
        bot.send_message(call.message.chat.id, response, parse_mode='Markdown', reply_markup=markup)

    del add_state[user_id]

# === Редактирование (только админы) ===
edit_state = {}

def start_edit_hw(message, subject, user_id):
    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('SELECT task, due_date, photo_file_ids FROM homework WHERE subject = ?', (subject,))
    row = c.fetchone()
    conn.close()

    if not row:
        bot.send_message(message.chat.id, "ДЗ не найдено.")
        return

    edit_state[user_id] = {
        'subject': subject,
        'step': 'edit_task',
        'old_task': row[0],
        'old_due': row[1],
        'old_photos': json.loads(row[2]) if row[2] else []
    }

    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id,
                     f"Редактируем: *{subject}*\nТекущее задание:\n`{row[0]}`\n\nВведите новое:",
                     parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: edit_state.get(m.from_user.id, {}).get('step') == 'edit_task')
def edit_task(message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    edit_state[user_id]['task'] = message.text
    edit_state[user_id]['step'] = 'edit_due'
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id,
                     f"Текущий срок: `{edit_state[user_id]['old_due'] or 'Не указано'}`\nВведите новый (или `нет`):",
                     parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: edit_state.get(m.from_user.id, {}).get('step') == 'edit_due')
def edit_due(message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    subject = edit_state[user_id]['subject']
    task = edit_state[user_id]['task']
    due = message.text.strip()
    due = due if due.lower() != 'нет' else None
    photo_json = json.dumps(edit_state[user_id]['old_photos']) if edit_state[user_id]['old_photos'] else None

    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('UPDATE homework SET task = ?, due_date = ?, photo_file_ids = ? WHERE subject = ?', (task, due, photo_json, subject))
    conn.commit()
    conn.close()

    bot.send_message(message.chat.id, f"ДЗ по *{subject}* обновлено!", parse_mode='Markdown')
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu(user_id))
    del edit_state[user_id]

# === Удаление (только админы) ===
def confirm_delete_by_subject(message, subject):
    markup = types.InlineKeyboardMarkup()
    btn_yes = types.InlineKeyboardButton("Да, удалить", callback_data=f"confirm_delete_subject_{subject}")
    btn_no = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_yes, btn_no)
    bot.send_message(message.chat.id, f"Удалить ВСЁ ДЗ по предмету *{subject}*?", parse_mode='Markdown', reply_markup=markup)

def do_delete_subject(call, subject):
    user_id = call.from_user.id
    if not is_admin(user_id): return

    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('DELETE FROM homework WHERE subject = ?', (subject,))
    deleted = c.rowcount
    conn.commit()
    conn.close()

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"Удалено {deleted} записей по *{subject}*." if deleted else "Ничего не удалено.",
        parse_mode='Markdown'
    )
    bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=main_menu(user_id))

# === Команды ===
@bot.message_handler(commands=['list'])
def list_cmd(message):
    show_subjects_list(message)

@bot.message_handler(commands=['add'])
def add_cmd(message):
    if is_admin(message.from_user.id):
        start_add_hw(message, message.from_user.id)
    else:
        bot.reply_to(message, "Доступ запрещён.")

# === Запуск ===
if __name__ == '__main__':
    print("Бот запущен: ВСЕ могут смотреть, АДМИНЫ — управлять!")
    bot.infinity_polling()