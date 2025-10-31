import telebot
import sqlite3
import json
import os
from telebot import types
from datetime import datetime, timezone, timedelta
import html

# === ПУТЬ К КОНФИГУ ===
CONFIG_PATH = 'config.json'

# === ДЕФОЛТНЫЕ НАСТРОЙКИ (если config.json не существует) ===
DEFAULT_CONFIG = {
    "token": "ВАШ_ТОКЕН_ЗДЕСЬ",
    "account_ids": [123456789],  # Для заметок
    "admin_ids": [123456789]  # Для ДЗ
}

# === Загрузка или создание config.json ===
def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"Файл {CONFIG_PATH} не найден. Создаю с настройками по умолчанию...")
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        print(f"Файл {CONFIG_PATH} создан. Отредактируйте его и перезапустите бота.")
        exit("Настройте config.json и запустите бота снова.")

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        try:
            config = json.load(f)
            required = ["token", "account_ids", "admin_ids"]
            for key in required:
                if key not in config:
                    raise ValueError(f"Отсутствует обязательное поле: {key}")
            if not config["token"] or config["token"] == "ВАШ_ТОКЕН_ЗДЕСЬ":
                raise ValueError("Укажите валидный токен в config.json")
            return config
        except json.JSONDecodeError as e:
            exit(f"Ошибка чтения {CONFIG_PATH}: {e}")
        except Exception as e:
            exit(f"Ошибка в {CONFIG_PATH}: {e}")

# === ЗАГРУЗКА НАСТРОЕК ===
config = load_config()
TOKEN = config["token"]
ACCOUNT_IDS = config["account_ids"]
ADMIN_IDS = config["admin_ids"]

bot = telebot.TeleBot(TOKEN)

# === БАЗЫ ДАННЫХ ===
def init_notes_db():
    conn = sqlite3.connect('notes.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            photo_file_ids TEXT,
            file_file_ids TEXT,
            created_at TEXT,
            creator_username TEXT
        )
    ''')
    c.execute("PRAGMA table_info(notes)")
    columns = [info[1] for info in c.fetchall()]
    if 'photo_file_ids' not in columns:
        c.execute('ALTER TABLE notes ADD COLUMN photo_file_ids TEXT')
    if 'file_file_ids' not in columns:
        c.execute('ALTER TABLE notes ADD COLUMN file_file_ids TEXT')
    if 'creator_username' not in columns:
        c.execute('ALTER TABLE notes ADD COLUMN creator_username TEXT')
    conn.commit()
    conn.close()

def init_hw_db():
    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            task TEXT NOT NULL,
            due_date TEXT,
            photo_file_ids TEXT,
            file_file_ids TEXT,
            created_at TEXT
        )
    ''')
    c.execute("PRAGMA table_info(homework)")
    columns = [info[1] for info in c.fetchall()]
    if 'photo_file_ids' not in columns:
        c.execute('ALTER TABLE homework ADD COLUMN photo_file_ids TEXT')
    if 'file_file_ids' not in columns:
        c.execute('ALTER TABLE homework ADD COLUMN file_file_ids TEXT')
    conn.commit()
    conn.close()

init_notes_db()
init_hw_db()

# === Проверка админа ===
def is_notes_admin(user_id):
    return user_id in ACCOUNT_IDS

def is_hw_admin(user_id):
    return user_id in ADMIN_IDS

# === КНОПКИ ===
def main_menu(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_notes = types.InlineKeyboardButton("Заметки", callback_data="notes_list")
    btn_hw = types.InlineKeyboardButton("Домашние задания", callback_data="hw_list")
    markup.add(btn_notes, btn_hw)
    return markup

# === /start ===
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    text = "Привет! Это бот для хранения заметок и домашнего задания.\n\nНовости последнего обновления:\nДобавлен раздел с заметками! Писать там можно что угодно и когда удобно (эксклюзивно людям из группы МЕХАТРОНИКОВ :). Другим нельзя). Жду мемчики и всякую ересь. Полезной инфы не надо (шутка). Good Luck!\n\n"
    if is_notes_admin(user_id) or is_hw_admin(user_id):
        text += "Вы — админ. Можете добавлять и редактировать записи."
    else:
        text += "Просматривайте записи через кнопки ниже."
    bot.send_message(message.chat.id, text, reply_markup=main_menu(user_id))

# === Обработка кнопок ===
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    if call.data == "notes_list":
        show_notes_titles_list(call.message, user_id)
        return
    elif call.data.startswith("notes_show_"):
        note_id = int(call.data.split("_", 2)[2])
        show_notes_details(call.message, note_id, user_id)
        return
    elif call.data == "hw_list":
        show_hw_subjects_list(call.message, user_id)
        return
    elif call.data.startswith("hw_show_"):
        hw_id = int(call.data.split("_", 2)[2])
        show_hw_details(call.message, hw_id, user_id)
        return
    elif call.data == "back_to_main":
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="Новости последнего обновления:\nДобавлен раздел с заметками! Писать там можно что угодно и когда удобно (эксклюзивно людям из группы МЕХАТРОНИКОВ :). Другим нельзя). Жду мемчики и всякую ересь. Полезной инфы не надо (шутка). Good Luck!\n\nГлавное меню:", reply_markup=main_menu(user_id))
        return

    if call.data.startswith("notes_") and not is_notes_admin(user_id):
        bot.answer_callback_query(call.id, "Доступ запрещён для заметок.", show_alert=True)
        return
    if call.data.startswith("hw_") and not is_hw_admin(user_id):
        bot.answer_callback_query(call.id, "Доступ запрещён для ДЗ.", show_alert=True)
        return

    if call.data == "notes_add":
        creator_identifier = call.from_user.username if call.from_user.username else str(call.from_user.id)
        notes_start_add_note(call.message, user_id, creator_identifier)
    elif call.data == "notes_add_more_photos":
        notes_continue_adding_photos(call, user_id)
    elif call.data == "notes_add_more_files":
        notes_continue_adding_files(call, user_id)
    elif call.data == "notes_finish_adding":
        notes_finish_adding_note(call, user_id)
    elif call.data.startswith("notes_edit_title_"):
        title_id = call.data.split("_", 3)[3]
        notes_start_edit_note(call.message, title_id, user_id)
    elif call.data.startswith("notes_delete_title_"):
        title_id = call.data.split("_", 3)[3]
        notes_confirm_delete_by_title_id(call.message, title_id)
    elif call.data.startswith("notes_confirm_delete_title_"):
        title_id = call.data.split("_", 4)[4]
        notes_do_delete_title_by_id(call, title_id)
    elif call.data == "hw_add":
        hw_start_add_hw(call.message, user_id)
    elif call.data == "hw_add_more_photos":
        hw_continue_adding_photos(call, user_id)
    elif call.data == "hw_add_more_files":
        hw_continue_adding_files(call, user_id)
    elif call.data == "hw_finish_adding":
        hw_finish_adding_hw(call, user_id)
    elif call.data.startswith("hw_edit_subject_"):
        subject_id = call.data.split("_", 3)[3]
        hw_start_edit_hw(call.message, subject_id, user_id)
    elif call.data.startswith("hw_delete_subject_"):
        subject_id = call.data.split("_", 3)[3]
        hw_confirm_delete_by_subject_id(call.message, subject_id)
    elif call.data.startswith("hw_confirm_delete_subject_"):
        subject_id = call.data.split("_", 4)[4]
        hw_do_delete_subject_by_id(call, subject_id)
    elif call.data == "cancel":
        if user_id in notes_add_state:
            del notes_add_state[user_id]
        if user_id in notes_edit_state:
            del notes_edit_state[user_id]
        if user_id in hw_add_state:
            del hw_add_state[user_id]
        if user_id in hw_edit_state:
            del hw_edit_state[user_id]
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="Действие отменено.", reply_markup=None)
        bot.send_message(chat_id, "Новости последнего обновления:\nДобавлен раздел с заметками! Писать там можно что угодно и когда удобно (эксклюзивно людям из группы МЕХАТРОНИКОВ :). Другим нельзя). Жду мемчики и всякую ересь. Полезной инфы не надо (шутка). Good Luck!\n\nГлавное меню:", reply_markup=main_menu(user_id))

# === ЗАМЕТКИ ===

notes_add_state = {}
notes_edit_state = {}

def show_notes_titles_list(message, user_id=None):
    if user_id is None:
        user_id = message.from_user.id if hasattr(message, 'from_user') else message.chat.id

    conn = sqlite3.connect('notes.db')
    c = conn.cursor()
    c.execute('SELECT title, MIN(id) as min_id, photo_file_ids, file_file_ids FROM notes GROUP BY title ORDER BY min_id')
    rows = c.fetchall()
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=1)

    if not rows:
        text = "Нет заметок."
    else:
        text = "<b>Выберите заметку:</b>"

    for title, min_id, photo_json, file_json in rows:
        photos = json.loads(photo_json) if photo_json else []
        files = json.loads(file_json) if file_json else []
        label = title
        if photos: label += f" (фото: {len(photos)})"
        if files: label += f" (файлы: {len(files)})"
        btn = types.InlineKeyboardButton(label, callback_data=f"notes_show_{min_id}")
        markup.add(btn)

    if is_notes_admin(user_id):
        btn_add = types.InlineKeyboardButton("Добавить заметку", callback_data="notes_add")
        markup.add(btn_add)

    btn_back = types.InlineKeyboardButton("Назад", callback_data="back_to_main")
    markup.add(btn_back)

    if hasattr(message, 'callback_query'):
        bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id,
                              text=text, parse_mode='HTML', reply_markup=markup)
    else:
        bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def show_notes_details(message, note_id, user_id):
    conn = sqlite3.connect('notes.db')
    c = conn.cursor()
    c.execute('SELECT id, title, content, photo_file_ids, file_file_ids, created_at, creator_username FROM notes WHERE id = ?', (note_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        bot.send_message(message.chat.id, "Заметка не найдена.", parse_mode='HTML')
        return

    title_id = row[0]
    title = row[1]
    content = row[2]
    all_photos = json.loads(row[3]) if row[3] else []
    all_files = json.loads(row[4]) if row[4] else []
    created_at = row[5]
    creator_identifier = row[6]

    text = f"<b>Заметка: {html.escape(title)}</b>\n\n"
    photo_mark = f" (фото: {len(all_photos)})" if all_photos else ""
    file_mark = f" (файлы: {len(all_files)})" if all_files else ""
    text += f"{photo_mark}{file_mark}\n{html.escape(content)}\n\n"

    if creator_identifier.isdigit():
        creator_display = f"ID {html.escape(creator_identifier)}"
    else:
        creator_display = f"@{html.escape(creator_identifier)}"
    text += f"Создатель: {creator_display} | Дата создания: {html.escape(created_at)}\n"

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_back = types.InlineKeyboardButton("Назад к списку", callback_data="notes_list")
    markup.add(btn_back)

    if is_notes_admin(user_id):
        btn_edit = types.InlineKeyboardButton("Редактировать", callback_data=f"notes_edit_title_{title_id}")
        btn_delete = types.InlineKeyboardButton("Удалить", callback_data=f"notes_delete_title_{title_id}")
        markup.add(btn_edit, btn_delete)

    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

    if all_photos:
        media = [types.InputMediaPhoto(all_photos[0], caption=f"<b>{html.escape(title)}</b>", parse_mode='HTML')]
        media += [types.InputMediaPhoto(p) for p in all_photos[1:]]
        try:
            bot.send_media_group(message.chat.id, media)
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка отправки фото: {e}")

    for file_id in all_files:
        try:
            bot.send_document(message.chat.id, file_id)
        except Exception as e:
            bot.send_message(message.chat.id, f"Не удалось отправить файл: {e}")

def notes_start_add_note(message, user_id, creator_identifier):
    notes_add_state[user_id] = {'step': 'title', 'photos': [], 'files': [], 'creator_identifier': creator_identifier}
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id, "Введите <b>заголовок</b> заметки:", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: notes_add_state.get(m.from_user.id, {}).get('step') == 'title')
def notes_get_title(message):
    user_id = message.from_user.id
    if not is_notes_admin(user_id): return
    notes_add_state[user_id]['title'] = message.text.strip()
    notes_add_state[user_id]['step'] = 'content'
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id, "Введите <b>содержание</b> заметки:", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: notes_add_state.get(m.from_user.id, {}).get('step') == 'content', content_types=['text'])
def notes_get_content(message):
    user_id = message.from_user.id
    if not is_notes_admin(user_id): return
    notes_add_state[user_id]['content'] = message.text
    notes_add_state[user_id]['step'] = 'attachments'

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_photo = types.InlineKeyboardButton("Фото", callback_data="notes_add_more_photos")
    btn_file = types.InlineKeyboardButton("Файлы", callback_data="notes_add_more_files")
    btn_done = types.InlineKeyboardButton("Готово", callback_data="notes_finish_adding")
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_photo, btn_file)
    markup.add(btn_done)
    markup.add(btn_cancel)

    sent = bot.send_message(message.chat.id,
                            "Добавьте <b>фото</b> или <b>файлы</b> (PDF, DOC, ZIP и др.)\n"
                            "или нажмите <b>Готово</b>", parse_mode='HTML', reply_markup=markup)
    notes_add_state[user_id]['last_msg_id'] = sent.message_id

def notes_continue_adding_photos(call, user_id):
    if notes_add_state.get(user_id, {}).get('step') != 'attachments': return
    bot.answer_callback_query(call.id, "Отправьте фото...")

def notes_continue_adding_files(call, user_id):
    if notes_add_state.get(user_id, {}).get('step') != 'attachments': return
    bot.answer_callback_query(call.id, "Отправьте файлы...")

@bot.message_handler(func=lambda m: notes_add_state.get(m.from_user.id, {}).get('step') == 'attachments', content_types=['photo'])
def notes_get_photos(message):
    user_id = message.from_user.id
    if not is_notes_admin(user_id): return
    file_id = message.photo[-1].file_id
    notes_add_state[user_id]['photos'].append(file_id)
    count = len(notes_add_state[user_id]['photos'])
    bot.reply_to(message, f"Добавлено фото: {count}. Отправьте ещё или нажмите <b>Готово</b>.", parse_mode='HTML')

@bot.message_handler(func=lambda m: notes_add_state.get(m.from_user.id, {}).get('step') == 'attachments', content_types=['document'])
def notes_get_files(message):
    user_id = message.from_user.id
    if not is_notes_admin(user_id): return
    file_id = message.document.file_id
    notes_add_state[user_id]['files'].append(file_id)
    count = len(notes_add_state[user_id]['files'])
    bot.reply_to(message, f"Добавлен файл: {count}. Отправьте ещё или нажмите <b>Готово</b>.", parse_mode='HTML')

def notes_finish_adding_note(call, user_id):
    data = notes_add_state[user_id]
    title = data['title']
    content = data['content']
    photos = data['photos']
    files = data['files']
    creator_identifier = data['creator_identifier']
    photo_json = json.dumps(photos) if photos else None
    file_json = json.dumps(files) if files else None
    local_tz = timezone(timedelta(hours=3))
    created_at = datetime.now(tz=local_tz).strftime('%Y-%m-%d %H:%M')

    conn = sqlite3.connect('notes.db')
    c = conn.cursor()

    # УДАЛЯЕМ СТАРУЮ ЗАМЕТКУ
    c.execute('DELETE FROM notes WHERE title = ?', (title,))
    deleted = c.rowcount

    # ДОБАВЛЯЕМ НОВУЮ
    c.execute('''
        INSERT INTO notes (title, content, photo_file_ids, file_file_ids, created_at, creator_username)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (title, content, photo_json, file_json, created_at, creator_identifier))
    conn.commit()
    conn.close()

    action = "обновлена" if deleted > 0 else "добавлена"
    response = f"<b>Заметка <code>{html.escape(title)}</code> {action}!</b>\n\n<b>{html.escape(content)}</b>"
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton("Назад к списку", callback_data="notes_list")
    markup.add(btn_back)

    sent_text = False

    if photos:
        media = [types.InputMediaPhoto(photos[0], caption=response, parse_mode='HTML')]
        media += [types.InputMediaPhoto(p) for p in photos[1:]]
        try:
            bot.send_media_group(call.message.chat.id, media)
            sent_text = True
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка при отправке фото: {e}")

    if files:
        for file_id in files:
            try:
                bot.send_document(call.message.chat.id, file_id)
            except Exception as e:
                bot.send_message(call.message.chat.id, f"Ошибка при отправке файла: {e}")

    if not sent_text:
        bot.send_message(call.message.chat.id, response, parse_mode='HTML', reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, "Готово!", reply_markup=markup)

    del notes_add_state[user_id]

def notes_start_edit_note(message, title_id, user_id):
    conn = sqlite3.connect('notes.db')
    c = conn.cursor()
    c.execute('SELECT title, content FROM notes WHERE id = ?', (title_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        bot.send_message(message.chat.id, "Заметка не найдена.")
        return

    title, content = row
    notes_edit_state[user_id] = {
        'title': title,
        'step': 'edit_content',
        'old_content': content
    }

    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id,
                     f"Редактируем: <b>{html.escape(title)}</b>\nТекущее содержание:\n<code>{html.escape(content)}</code>\n\nВведите новое:",
                     parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: notes_edit_state.get(m.from_user.id, {}).get('step') == 'edit_content')
def notes_edit_content(message):
    user_id = message.from_user.id
    if not is_notes_admin(user_id): return
    data = notes_edit_state[user_id]
    content = message.text

    conn = sqlite3.connect('notes.db')
    c = conn.cursor()
    c.execute('UPDATE notes SET content = ? WHERE title = ?', (content, data['title']))
    conn.commit()
    conn.close()

    bot.send_message(message.chat.id, f"Заметка <b>{html.escape(data['title'])}</b> обновлена!", parse_mode='HTML')
    show_notes_titles_list(message, user_id)
    del notes_edit_state[user_id]

def notes_confirm_delete_by_title_id(message, title_id):
    conn = sqlite3.connect('notes.db')
    c = conn.cursor()
    c.execute('SELECT title FROM notes WHERE id = ?', (title_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        bot.send_message(message.chat.id, "Заметка не найдена.")
        return

    title = row[0]
    markup = types.InlineKeyboardMarkup()
    btn_yes = types.InlineKeyboardButton("Да, удалить", callback_data=f"notes_confirm_delete_title_{title_id}")
    btn_no = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_yes, btn_no)
    bot.send_message(message.chat.id, f"Удалить заметку <b>{html.escape(title)}</b>?", parse_mode='HTML', reply_markup=markup)

def notes_do_delete_title_by_id(call, title_id):
    user_id = call.from_user.id
    if not is_notes_admin(user_id): return

    conn = sqlite3.connect('notes.db')
    c = conn.cursor()
    c.execute('SELECT title FROM notes WHERE id = ?', (title_id,))
    row = c.fetchone()
    title = row[0] if row else "Неизвестно"

    c.execute('DELETE FROM notes WHERE title = ?', (title,))
    deleted = c.rowcount
    conn.commit()
    conn.close()

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"Удалено {deleted} записей по <b>{html.escape(title)}</b>." if deleted else "Ничего не удалено.",
        parse_mode='HTML'
    )
    show_notes_titles_list(call.message, user_id)

# === ДОМАШНИЕ ЗАДАНИЯ ===

hw_add_state = {}
hw_edit_state = {}

def show_hw_subjects_list(message, user_id=None):
    if user_id is None:
        user_id = message.from_user.id if hasattr(message, 'from_user') else message.chat.id

    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('SELECT subject, MIN(id) as min_id, photo_file_ids, file_file_ids FROM homework GROUP BY subject ORDER BY min_id')
    rows = c.fetchall()
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=1)

    if not rows:
        text = "Нет ДЗ."
    else:
        text = "<b>Выберите предмет:</b>"

    for subject, min_id, photo_json, file_json in rows:
        photos = json.loads(photo_json) if photo_json else []
        files = json.loads(file_json) if file_json else []
        label = subject
        if photos: label += f" (фото: {len(photos)})"
        if files: label += f" (файлы: {len(files)})"
        btn = types.InlineKeyboardButton(label, callback_data=f"hw_show_{min_id}")
        markup.add(btn)

    if is_hw_admin(user_id):
        btn_add = types.InlineKeyboardButton("Добавить ДЗ", callback_data="hw_add")
        markup.add(btn_add)

    btn_back = types.InlineKeyboardButton("Назад", callback_data="back_to_main")
    markup.add(btn_back)

    if hasattr(message, 'callback_query'):
        bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id,
                              text=text, parse_mode='HTML', reply_markup=markup)
    else:
        bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def show_hw_details(message, hw_id, user_id):
    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('SELECT id, subject, task, due_date, photo_file_ids, file_file_ids FROM homework WHERE id = ?', (hw_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        bot.send_message(message.chat.id, "ДЗ не найдено.", parse_mode='HTML')
        return

    subject_id = row[0]
    subject = row[1]
    task = row[2]
    due = row[3]
    all_photos = json.loads(row[4]) if row[4] else []
    all_files = json.loads(row[5]) if row[5] else []

    text = f"<b>ДЗ по предмету: {html.escape(subject)}</b>\n\n"
    due_text = f"Срок: {html.escape(due)}" if due else "Срок: Не указано"
    photo_mark = f" (фото: {len(all_photos)})" if all_photos else ""
    file_mark = f" (файлы: {len(all_files)})" if all_files else ""
    text += f"{photo_mark}{file_mark}\n{html.escape(task)}\n{due_text}\n\n"

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_back = types.InlineKeyboardButton("Назад к списку", callback_data="hw_list")
    markup.add(btn_back)

    if is_hw_admin(user_id):
        btn_edit = types.InlineKeyboardButton("Редактировать", callback_data=f"hw_edit_subject_{subject_id}")
        btn_delete = types.InlineKeyboardButton("Удалить", callback_data=f"hw_delete_subject_{subject_id}")
        markup.add(btn_edit, btn_delete)

    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

    if all_photos:
        media = [types.InputMediaPhoto(all_photos[0], caption=f"<b>{html.escape(subject)}</b>", parse_mode='HTML')]
        media += [types.InputMediaPhoto(p) for p in all_photos[1:]]
        try:
            bot.send_media_group(message.chat.id, media)
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка отправки фото: {e}")

    for file_id in all_files:
        try:
            bot.send_document(message.chat.id, file_id)
        except Exception as e:
            bot.send_message(message.chat.id, f"Не удалось отправить файл: {e}")

def hw_start_add_hw(message, user_id):
    hw_add_state[user_id] = {'step': 'subject', 'photos': [], 'files': []}
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id, "Введите <b>предмет</b>:", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: hw_add_state.get(m.from_user.id, {}).get('step') == 'subject')
def hw_get_subject(message):
    user_id = message.from_user.id
    if not is_hw_admin(user_id): return
    hw_add_state[user_id]['subject'] = message.text.strip()
    hw_add_state[user_id]['step'] = 'task'
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id, "Введите <b>задание</b>:", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: hw_add_state.get(m.from_user.id, {}).get('step') == 'task', content_types=['text'])
def hw_get_task(message):
    user_id = message.from_user.id
    if not is_hw_admin(user_id): return
    hw_add_state[user_id]['task'] = message.text
    hw_add_state[user_id]['step'] = 'due_date'
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id, "Введите <b>срок сдачи</b> (или `нет`):", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: hw_add_state.get(m.from_user.id, {}).get('step') == 'due_date')
def hw_get_due_date(message):
    user_id = message.from_user.id
    if not is_hw_admin(user_id): return
    due = message.text.strip()
    hw_add_state[user_id]['due_date'] = due if due.lower() != 'нет' else None
    hw_add_state[user_id]['step'] = 'attachments'

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_photo = types.InlineKeyboardButton("Фото", callback_data="hw_add_more_photos")
    btn_file = types.InlineKeyboardButton("Файлы", callback_data="hw_add_more_files")
    btn_done = types.InlineKeyboardButton("Готово", callback_data="hw_finish_adding")
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_photo, btn_file)
    markup.add(btn_done)
    markup.add(btn_cancel)

    sent = bot.send_message(message.chat.id,
                            "Добавьте <b>фото</b> или <b>файлы</b> (PDF, DOC, ZIP и др.)\n"
                            "или нажмите <b>Готово</b>", parse_mode='HTML', reply_markup=markup)
    hw_add_state[user_id]['last_msg_id'] = sent.message_id

def hw_continue_adding_photos(call, user_id):
    if hw_add_state.get(user_id, {}).get('step') != 'attachments': return
    bot.answer_callback_query(call.id, "Отправьте фото...")

def hw_continue_adding_files(call, user_id):
    if hw_add_state.get(user_id, {}).get('step') != 'attachments': return
    bot.answer_callback_query(call.id, "Отправьте файлы...")

@bot.message_handler(func=lambda m: hw_add_state.get(m.from_user.id, {}).get('step') == 'attachments', content_types=['photo'])
def hw_get_photos(message):
    user_id = message.from_user.id
    if not is_hw_admin(user_id): return
    file_id = message.photo[-1].file_id
    hw_add_state[user_id]['photos'].append(file_id)
    count = len(hw_add_state[user_id]['photos'])
    bot.reply_to(message, f"Добавлено фото: {count}. Отправьте ещё или нажмите <b>Готово</b>.", parse_mode='HTML')

@bot.message_handler(func=lambda m: hw_add_state.get(m.from_user.id, {}).get('step') == 'attachments', content_types=['document'])
def hw_get_files(message):
    user_id = message.from_user.id
    if not is_hw_admin(user_id): return
    file_id = message.document.file_id
    hw_add_state[user_id]['files'].append(file_id)
    count = len(hw_add_state[user_id]['files'])
    bot.reply_to(message, f"Добавлен файл: {count}. Отправьте ещё или нажмите <b>Готово</b>.", parse_mode='HTML')

def hw_finish_adding_hw(call, user_id):
    data = hw_add_state[user_id]
    subject = data['subject']
    task = data['task']
    due_date = data['due_date']
    photos = data['photos']
    files = data['files']
    photo_json = json.dumps(photos) if photos else None
    file_json = json.dumps(files) if files else None

    conn = sqlite3.connect('homework.db')
    c = conn.cursor()

    # УДАЛЯЕМ СТАРОЕ ДЗ
    c.execute('DELETE FROM homework WHERE subject = ?', (subject,))
    deleted = c.rowcount

    # ДОБАВЛЯЕМ НОВОЕ
    c.execute('''
        INSERT INTO homework (subject, task, due_date, photo_file_ids, file_file_ids, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (subject, task, due_date, photo_json, file_json, datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit()
    conn.close()

    action = "обновлено" if deleted > 0 else "добавлено"
    response = f"<b>ДЗ по предмету <code>{html.escape(subject)}</code> {action}!</b>\n\n<b>{html.escape(task)}</b>\nСрок: {html.escape(due_date or 'Не указано')}"
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton("Назад к списку", callback_data="hw_list")
    markup.add(btn_back)

    sent_text = False

    if photos:
        media = [types.InputMediaPhoto(photos[0], caption=response, parse_mode='HTML')]
        media += [types.InputMediaPhoto(p) for p in photos[1:]]
        try:
            bot.send_media_group(call.message.chat.id, media)
            sent_text = True
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка при отправке фото: {e}")

    if files:
        for file_id in files:
            try:
                bot.send_document(call.message.chat.id, file_id)
            except Exception as e:
                bot.send_message(call.message.chat.id, f"Ошибка при отправке файла: {e}")

    if not sent_text:
        bot.send_message(call.message.chat.id, response, parse_mode='HTML', reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, "Готово!", reply_markup=markup)

    del hw_add_state[user_id]

def hw_start_edit_hw(message, subject_id, user_id):
    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('SELECT subject, task, due_date FROM homework WHERE id = ?', (subject_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        bot.send_message(message.chat.id, "ДЗ не найдено.")
        return

    subject, task, due = row
    hw_edit_state[user_id] = {
        'subject': subject,
        'step': 'edit_task',
        'old_task': task,
        'old_due': due
    }

    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id,
                     f"Редактируем: <b>{html.escape(subject)}</b>\nТекущее задание:\n<code>{html.escape(task)}</code>\n\nВведите новое:",
                     parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: hw_edit_state.get(m.from_user.id, {}).get('step') == 'edit_task')
def hw_edit_task(message):
    user_id = message.from_user.id
    if not is_hw_admin(user_id): return
    hw_edit_state[user_id]['task'] = message.text
    hw_edit_state[user_id]['step'] = 'edit_due'
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_cancel)
    bot.send_message(message.chat.id,
                     f"Текущий срок: <code>{html.escape(hw_edit_state[user_id]['old_due'] or 'Не указано')}</code>\nВведите новый (или `нет`):",
                     parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: hw_edit_state.get(m.from_user.id, {}).get('step') == 'edit_due')
def hw_edit_due(message):
    user_id = message.from_user.id
    if not is_hw_admin(user_id): return
    data = hw_edit_state[user_id]
    due = message.text.strip()
    due = due if due.lower() != 'нет' else None

    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('UPDATE homework SET task = ?, due_date = ? WHERE subject = ?', (data['task'], due, data['subject']))
    conn.commit()
    conn.close()

    bot.send_message(message.chat.id, f"ДЗ по <b>{html.escape(data['subject'])}</b> обновлено!", parse_mode='HTML')
    show_hw_subjects_list(message, user_id)
    del hw_edit_state[user_id]

def hw_confirm_delete_by_subject_id(message, subject_id):
    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('SELECT subject FROM homework WHERE id = ?', (subject_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        bot.send_message(message.chat.id, "Предмет не найден.")
        return

    subject = row[0]
    markup = types.InlineKeyboardMarkup()
    btn_yes = types.InlineKeyboardButton("Да, удалить", callback_data=f"hw_confirm_delete_subject_{subject_id}")
    btn_no = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(btn_yes, btn_no)
    bot.send_message(message.chat.id, f"Удалить ВСЁ ДЗ по предмету <b>{html.escape(subject)}</b>?", parse_mode='HTML', reply_markup=markup)

def hw_do_delete_subject_by_id(call, subject_id):
    user_id = call.from_user.id
    if not is_hw_admin(user_id): return

    conn = sqlite3.connect('homework.db')
    c = conn.cursor()
    c.execute('SELECT subject FROM homework WHERE id = ?', (subject_id,))
    row = c.fetchone()
    subject = row[0] if row else "Неизвестно"

    c.execute('DELETE FROM homework WHERE subject = ?', (subject,))
    deleted = c.rowcount
    conn.commit()
    conn.close()

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"Удалено {deleted} записей по <b>{html.escape(subject)}</b>." if deleted else "Ничего не удалено.",
        parse_mode='HTML'
    )
    show_hw_subjects_list(call.message, user_id)

# === Команды ===
@bot.message_handler(commands=['notes_list'])
def notes_list_cmd(message):
    show_notes_titles_list(message, message.from_user.id)

@bot.message_handler(commands=['hw_list'])
def hw_list_cmd(message):
    show_hw_subjects_list(message, message.from_user.id)

@bot.message_handler(commands=['notes_add'])
def notes_add_cmd(message):
    if is_notes_admin(message.from_user.id):
        creator_identifier = message.from_user.username if message.from_user.username else str(message.from_user.id)
        notes_start_add_note(message, message.from_user.id, creator_identifier)
    else:
        bot.reply_to(message, "Доступ запрещён для заметок.")

@bot.message_handler(commands=['hw_add'])
def hw_add_cmd(message):
    if is_hw_admin(message.from_user.id):
        hw_start_add_hw(message, message.from_user.id)
    else:
        bot.reply_to(message, "Доступ запрещён для ДЗ.")

# === Запуск ===
if __name__ == '__main__':
    print("Бот запущен: настройки из config.json")
    bot.infinity_polling()