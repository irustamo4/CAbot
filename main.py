import telebot
from telebot import types
import sqlite3
from datetime import datetime
import logging

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================
API_TOKEN = "8561775820:AAFXatDo0qSUVLaOpJ5wfWzkEI3o9f2Efbo"

# ID чата для уведомлений 
NOTIFICATION_CHAT_ID = -1003634204170 

DATABASE_NAME = "defects.db"

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")

# ==================== БАЗА ДАННЫХ ====================
def init_database():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS defects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            defect_number TEXT UNIQUE,
            user_id INTEGER,
            user_name TEXT,
            defect_type TEXT,
            shift TEXT,
            line TEXT,
            description TEXT,
            photo_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'new'
        )
    ''')
    
    # Таблица для счётчика номеров NCR
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0
        )
    ''')
    
    # Инициализируем счётчик если его нет
    cursor.execute("INSERT OR IGNORE INTO counters (name, value) VALUES ('defect_counter', 0)")
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def get_next_defect_number():
    """Генерация следующего номера NCR"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # Увеличиваем счётчик и получаем новое значение
    cursor.execute("UPDATE counters SET value = value + 1 WHERE name = 'defect_counter'")
    cursor.execute("SELECT value FROM counters WHERE name = 'defect_counter'")
    counter = cursor.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    return f"NCR-{counter:03d}"

def save_defect(defect_data):
    """Сохранение дефекта в базу данных"""
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO defects 
            (defect_number, user_id, user_name, defect_type, shift, line, description, photo_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            defect_data['defect_number'],
            defect_data['user_id'],
            defect_data['user_name'],
            defect_data['defect_type'],
            defect_data['shift'],
            defect_data['line'],
            defect_data['description'],
            defect_data.get('photo_id')
        ))
        
        defect_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Сохранён дефект #{defect_data['defect_number']} (ID: {defect_id})")
        return defect_id
    except Exception as e:
        logger.error(f"Ошибка сохранения дефекта: {e}")
        return None

def get_defect_stats():
    """Получение статистики по дефектам"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM defects")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM defects WHERE DATE(created_at) = DATE('now')")
    today = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT defect_type, COUNT(*) as count 
        FROM defects 
        GROUP BY defect_type 
        ORDER BY count DESC
    """)
    by_type = cursor.fetchall()
    
    conn.close()
    
    return {
        'total': total,
        'today': today,
        'by_type': dict(by_type)
    }

# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard():
    """Главное меню"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "📝 Новое несоответствие",
        "📊 Статистика",
        "📋 Последние записи",
        "ℹ️ Помощь"
    ]
    keyboard.add(*buttons)
    return keyboard

def get_cancel_keyboard():
    """Клавиатура для отмены"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("❌ Отмена")
    return keyboard

def get_defect_type_keyboard():
    """Типы несоответствий"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    types_list = [
        "🧪 Сырье",
        "⚙️ Процесс",
        "📦 Упаковка",
        "🔧 Оборудование",
        "👥 Персонал",
        "❓ Другое"
    ]
    keyboard.add(*types_list)
    keyboard.add("❌ Отмена")
    return keyboard

def get_shift_keyboard():
    """Выбор смены"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    keyboard.add("Утренняя(6:00-15:30)", "Вечерняя(15:30-23:00)", "Ночная(23:00-6:00)")
    keyboard.add("❌ Отмена")
    return keyboard

def get_line_keyboard():
    """Выбор линии"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    lines = [
        "Линия 1",
        "Линия 2", 
        "Линия 3",
        "Линия 4",
        "Склад",
        "Другое"
    ]
    keyboard.add(*lines)
    keyboard.add("❌ Отмена")
    return keyboard

# ==================== СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ ====================
# Словарь для хранения состояния пользователей
user_sessions = {}

def start_defect_session(user_id, user_name):
    """Начало сессии регистрации дефекта"""
    user_sessions[user_id] = {
        'user_name': user_name,
        'step': 'waiting_type',
        'data': {}
    }

def update_defect_data(user_id, field, value):
    """Обновление данных дефекта"""
    if user_id in user_sessions:
        user_sessions[user_id]['data'][field] = value

def get_defect_data(user_id):
    """Получение данных дефекта"""
    return user_sessions[user_id]['data'] if user_id in user_sessions else None

def clear_session(user_id):
    """Очистка сессии пользователя"""
    if user_id in user_sessions:
        del user_sessions[user_id]

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@bot.message_handler(commands=['start'])
def handle_start(message):
    """Обработчик команды /start"""
    welcome_text = """
👋 <b>Добро пожаловать в Мобильный журнал несоответствий!</b>

Я помогу вам быстро зафиксировать любые проблемы на производстве.

<b>Основные функции:</b>
📝 <b>Новое несоответствие</b> - зарегистрировать проблему
📊 <b>Статистика</b> - общая статистика по дефектам
📋 <b>Последние записи</b> - история фиксаций
ℹ️ <b>Помощь</b> - инструкция по использованию

<b>Начните работу:</b> нажмите "📝 Новое несоответствие"
    """
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_keyboard())

@bot.message_handler(commands=['new_defect'])
def handle_new_defect(message):
    """Обработчик команды /new_defect"""
    start_defect_session(message.from_user.id, message.from_user.full_name)
    
    bot.send_message(
        message.chat.id,
        "🏷️ <b>Шаг 1 из 5: Выберите тип несоответствия</b>\n\n"
        "К какой категории относится проблема?",
        reply_markup=get_defect_type_keyboard()
    )

@bot.message_handler(commands=['help'])
def handle_help(message):
    """Обработчик команды /help"""
    help_text = """
<b>📚 Инструкция по использованию бота:</b>

<b>Процесс регистрации несоответствия:</b>
1. Нажмите "📝 Новое несоответствие"
2. Выберите тип проблемы:
   • <b>Сырье</b> - проблемы с исходными материалами
   • <b>Процесс</b> - нарушения технологического процесса
   • <b>Упаковка</b> - дефекты упаковки и маркировки
   • <b>Оборудование</b> - неисправности оборудования
   • <b>Персонал</b> - нарушения персоналом
   • <b>Другое</b> - прочие проблемы
3. Укажите смену (1, 2, 3)
4. Выберите линию/участок
5. Опишите проблему подробно
6. Прикрепите фото (опционально)

<b>После регистрации:</b>
• Запись сохраняется в базу данных
• Присваивается уникальный номер (NCR-XXX)
• Ответственные получают уведомление
    """
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    """Обработчик команды /stats"""
    stats = get_defect_stats()
    
    stats_text = f"""
📊 <b>Статистика несоответствий</b>

<b>Всего зарегистрировано:</b> {stats['total']}
<b>Сегодня:</b> {stats['today']}

<b>Распределение по типам:</b>
"""
    
    for defect_type, count in stats['by_type'].items():
        stats_text += f"• {defect_type}: {count}\n"
    
    bot.send_message(message.chat.id, stats_text)

# ==================== ОБРАБОТЧИКИ КНОПОК ====================
@bot.message_handler(func=lambda message: message.text == "📝 Новое несоответствие")
def handle_new_defect_button(message):
    """Обработчик кнопки нового несоответствия"""
    handle_new_defect(message)

@bot.message_handler(func=lambda message: message.text == "📊 Статистика")
def handle_stats_button(message):
    """Обработчик кнопки статистики"""
    handle_stats(message)
# ==================== ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ПОСЛЕДНИХ ЗАПИСЕЙ ====================
def get_user_recent_defects(user_id, limit=5):
    """Получение последних записей пользователя"""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT defect_number, defect_type, line, description, created_at 
        FROM defects 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (user_id, limit))
    rows = cursor.fetchall()
    conn.close() 
    return [dict(row) for row in rows]

# ==================== ОБРАБОТЧИК КНОПКИ "ПОСЛЕДНИЕ ЗАПИСИ" ====================
@bot.message_handler(func=lambda message: message.text == "📋 Последние записи")
def handle_last_records(message):
    """Показать последние записи пользователя"""
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    
    # Получаем последние 5 записей пользователя
    records = get_user_recent_defects(user_id, limit=5)
    
    if not records:
        bot.send_message(
            message.chat.id,
            f"📭 {user_name}, у вас пока нет зарегистрированных несоответствий.\n"
            f"Нажмите '📝 Новое несоответствие', чтобы создать первую запись."
        )
        return
    
    # Формируем красивый ответ
    records_text = f"""
📋 <b>Ваши последние записи</b> ({len(records)})

"""
    
    for i, record in enumerate(records, 1):
        # Преобразуем дату в читаемый формат
        created_date = datetime.strptime(
            record['created_at'], '%Y-%m-%d %H:%M:%S'
        ).strftime('%d.%m.%Y %H:%M') if 'T' not in record['created_at'] else record['created_at']
        
        # Обрезаем длинное описание
        short_description = (
            record['description'][:80] + "..."
            if len(record['description']) > 80
            else record['description']
        )
        
        records_text += f"""
{i}. <b>{record['defect_number']}</b>
   🏷️ Тип: {record['defect_type']}
   📍 Линия: {record['line']}
   📅 Дата: {created_date}
   📝 {short_description}
   ━━━━━━━━━━━━━━━━━━
"""
    
    # Добавляем подсказку
    records_text += f"\n<i>Всего у вас {len(records)} последних записей. Для просмотра деталей конкретной записи используйте её номер (например, {records[0]['defect_number']}).</i>"
    
    bot.send_message(message.chat.id, records_text, parse_mode="HTML")
     
@bot.message_handler(func=lambda message: message.text == "ℹ️ Помощь")
def handle_help_button(message):
    """Обработчик кнопки помощи"""
    handle_help(message)

@bot.message_handler(func=lambda message: message.text == "❌ Отмена")
def handle_cancel(message):
    """Обработчик отмены"""
    user_id = message.from_user.id
    clear_session(user_id)
    
    bot.send_message(
        message.chat.id,
        "❌ Регистрация отменена.",
        reply_markup=get_main_keyboard()
    )

# ==================== ОБРАБОТЧИКИ ДИАЛОГА ====================
@bot.message_handler(func=lambda message: True)
def handle_dialog(message):
    """Обработчик диалога регистрации дефекта"""
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        return
    
    session = user_sessions[user_id]
    step = session['step']
    
    if step == 'waiting_type':
        handle_type_step(message)
    
    elif step == 'waiting_shift':
        handle_shift_step(message)
    
    elif step == 'waiting_line':
        handle_line_step(message)
    
    elif step == 'waiting_description':
        handle_description_step(message)
    
    elif step == 'waiting_photo':
        handle_photo_step(message)

def handle_type_step(message):
    """Обработка выбора типа"""
    type_mapping = {
        "🧪 Сырье": "Сырье",
        "⚙️ Процесс": "Процесс",
        "📦 Упаковка": "Упаковка",
        "🔧 Оборудование": "Оборудование",
        "👥 Персонал": "Персонал",
        "❓ Другое": "Другое"
    }
    
    if message.text not in type_mapping:
        bot.send_message(message.chat.id, "❌ Пожалуйста, выберите тип из списка.")
        return
    
    update_defect_data(message.from_user.id, 'defect_type', type_mapping[message.text])
    user_sessions[message.from_user.id]['step'] = 'waiting_shift'
    
    bot.send_message(
        message.chat.id,
        "🕐 <b>Шаг 2 из 5: Укажите номер смены</b>\n\n"
        "Какая смена работает?",
        reply_markup=get_shift_keyboard()
    )

def handle_shift_step(message):
    """Обработка выбора смены"""
    if message.text not in ["Утренняя(6:00-15:30)", "Вечерняя(15:30-23:00)", "Ночная(23:00-6:00)"]:
        bot.send_message(message.chat.id, "❌ Пожалуйста, укажите смену (Утренняя(6:00-15:30),Вечерняя(15:30-23:00) или Ночная(23:00-6:00)).")
        return
    
    update_defect_data(message.from_user.id, 'shift', message.text)
    user_sessions[message.from_user.id]['step'] = 'waiting_line'
    
    bot.send_message(
        message.chat.id,
        "🏭 <b>Шаг 3 из 5: Выберите линию/участок</b>\n\n"
        "Где обнаружена проблема?",
        reply_markup=get_line_keyboard()
    )

def handle_line_step(message):
    """Обработка выбора линии"""
    valid_lines = ["Линия 1", "Линия 2", "Линия 3", "Линия 4", "Склад", "Другое"]
    
    if message.text not in valid_lines:
        bot.send_message(message.chat.id, "❌ Пожалуйста, выберите линию из списка.")
        return
    
    update_defect_data(message.from_user.id, 'line', message.text)
    user_sessions[message.from_user.id]['step'] = 'waiting_description'
    
    bot.send_message(
        message.chat.id,
        "📝 <b>Шаг 4 из 5: Опишите проблему</b>\n\n"
        "Подробно опишите несоответствие:\n"
        "• Что именно не так?\n"
        "• Когда обнаружено?\n"
        "• Каков масштаб проблемы?\n\n"
        "<i>Отправьте текстовое сообщение с описанием</i>",
        reply_markup=get_cancel_keyboard()
    )

def handle_description_step(message):
    """Обработка описания"""
    if len(message.text.strip()) < 10:
        bot.send_message(message.chat.id, "❌ Описание должно содержать минимум 10 символов.")
        return
    
    update_defect_data(message.from_user.id, 'description', message.text.strip())
    user_sessions[message.from_user.id]['step'] = 'waiting_photo'
    
    bot.send_message(
        message.chat.id,
        "📸 <b>Шаг 5 из 5: Прикрепите фото (опционально)</b>\n\n"
        "Пришлите фотографию проблемы для наглядности.\n"
        "<i>Если фото нет, отправьте \"пропустить\"</i>",
        reply_markup=get_cancel_keyboard()
    )

def handle_photo_step(message):
    """Обработка фото"""
    user_id = message.from_user.id
    session = user_sessions[user_id]
    defect_data = session['data']
    
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
        update_defect_data(user_id, 'photo_id', photo_id)
    
    # Если пользователь отправил "пропустить" или любой другой текст после описания
    # (кроме команды отмены), завершаем регистрацию
    if message.text and message.text.lower() == "пропустить":
        pass  # Просто продолжаем без фото
    elif not message.photo and message.text and message.text != "❌ Отмена":
        # Если это не фото и не отмена, просим прислать фото или пропустить
        bot.send_message(message.chat.id, "❌ Пожалуйста, пришлите фото или напишите \"пропустить\".")
        return
    
    # Генерируем номер дефекта
    defect_number = get_next_defect_number()
    
    # Формируем полные данные
    full_defect_data = {
        'defect_number': defect_number,
        'user_id': user_id,
        'user_name': session['user_name'],
        'defect_type': defect_data['defect_type'],
        'shift': defect_data['shift'],
        'line': defect_data['line'],
        'description': defect_data['description'],
        'photo_id': defect_data['photo_id']
    }
    
    # Сохраняем в базу
    defect_id = save_defect(full_defect_data)
    
    if defect_id:
        # Отправляем подтверждение пользователю
        send_confirmation(message.chat.id, full_defect_data)
        
        # Отправляем уведомление ответственному
        send_notification(full_defect_data)
    else:
        bot.send_message(message.chat.id, "❌ Ошибка при сохранении записи. Попробуйте снова.")
    
    # Очищаем сессию
    clear_session(user_id)

def send_confirmation(chat_id, defect_data):
    """Отправка подтверждения пользователю"""
    confirmation_text = f"""
✅ <b>Несоответствие зарегистрировано!</b>

<b>Номер:</b> {defect_data['defect_number']}
<b>Тип:</b> {defect_data['defect_type']}
<b>Смена:</b> {defect_data['shift']}
<b>Линия:</b> {defect_data['line']}
<b>Дата:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

<b>Описание:</b>
{defect_data['description']}

<i>Запись сохранена в базе данных.</i>
"""
    
    if defect_data.get('photo_id'):
        bot.send_photo(chat_id, defect_data['photo_id'], caption=confirmation_text, reply_markup=get_main_keyboard())
    else:
        bot.send_message(chat_id, confirmation_text, reply_markup=get_main_keyboard())

def send_notification(defect_data):
    """Отправка уведомления ответственному"""
    if not NOTIFICATION_CHAT_ID:
        logger.warning("NOTIFICATION_CHAT_ID не указан. Уведомления не отправляются.")
        return
    
    notification_text = f"""
🚨 <b>НОВОЕ НЕСООТВЕТСТВИЕ!</b>

<b>Номер:</b> {defect_data['defect_number']}
<b>Тип:</b> {defect_data['defect_type']}
<b>Смена:</b> {defect_data['shift']}
<b>Линия:</b> {defect_data['line']}
<b>Сотрудник:</b> {defect_data['user_name']}
<b>Время:</b> {datetime.now().strftime('%H:%M')}

<b>Описание:</b>
{defect_data['description']}

<b>Требует внимания!</b>
"""
    
    try:
        if defect_data.get('photo_id'):
            bot.send_photo(NOTIFICATION_CHAT_ID, defect_data['photo_id'], caption=notification_text)
        else:
            bot.send_message(NOTIFICATION_CHAT_ID, notification_text)
        logger.info(f"Уведомление отправлено в чат {NOTIFICATION_CHAT_ID}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")

# ==================== ОБРАБОТЧИК ФОТО ====================
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    """Обработчик фото (для шага ожидания фото)"""
    user_id = message.from_user.id
    
    if user_id in user_sessions and user_sessions[user_id]['step'] == 'waiting_photo':
        # Обрабатываем фото в основном обработчике диалога
        handle_dialog(message)

# ==================== ЗАПУСК БОТА ====================
def main():
    """Основная функция запуска бота"""
    # Инициализация базы данных
    init_database()
    
    logger.info("Бот запущен...")
    print("Бот запущен! Для остановки нажмите Ctrl+C")
    
    try:
        bot.polling(none_stop=True, interval=0)
    except Exception as e:
        logger.error(f"Ошибка в работе бота: {e}")
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()

