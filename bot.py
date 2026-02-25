import json
import os
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ========== НАСТРОЙКИ ==========
TOKEN = "8683322789:AAFF-L3OIOfIfKgQIiAevbj9l1BKf4gb9CM"
ADMIN_ID = 1595538164
CHANNEL_ID = "@Scambasebynoflixx"  # ✅ ТВОЙ КАНАЛ
# ================================

# Отключаем все логи
import logging
logging.basicConfig(level=logging.CRITICAL)
logging.getLogger('httpx').setLevel(logging.CRITICAL)
logging.getLogger('telegram').setLevel(logging.CRITICAL)

# Функция для экранирования Markdown символов
def escape_markdown(text):
    """Экранирует специальные символы Markdown"""
    if not text:
        return "-"
    # Символы, которые нужно экранировать в Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, '\\' + char)
    return text

# Хранилище заявок
pending_reports = {}
user_sessions = {}

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С СЧЕТЧИКОМ ==========
COUNTER_FILE = "report_counter.txt"

def get_next_report_id():
    """Получить следующий номер жалобы"""
    try:
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, 'r') as f:
                report_counter = int(f.read().strip())
        else:
            report_counter = 0
    except:
        report_counter = 0
    
    report_counter += 1
    
    try:
        with open(COUNTER_FILE, 'w') as f:
            f.write(str(report_counter))
    except:
        pass
    
    return str(report_counter)

def format_report_number(num):
    """Форматировать номер жалобы"""
    return f"#{str(num).zfill(4)}"
# ====================================================

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    keyboard = [[InlineKeyboardButton("📋 Подать заявку на скамера", callback_data="new_report")]]
    
    await update.message.reply_text(
        "👋 **Привет!**\n\n"
        "Я бот для подачи жалоб на скамеров.\n\n"
        "📝 **Чтобы подать заявку, нажми кнопку ниже:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data="back_to_menu")]]
    
    await update.message.reply_text(
        "❓ **Помощь**\n\n"
        "📋 **Как подать заявку на скамера?**\n"
        "1. Нажми /start\n"
        "2. Нажми кнопку «Подать заявку»\n"
        "3. Заполни форму с помощью кнопок\n"
        "4. Отправь фото доказательств\n\n"
        "✅ После проверки админом заявка появится в канале @Scambasebynoflixx!\n\n"
        "📋 **Команды:**\n"
        "/start - Главное меню\n"
        "/help - Эта помощь\n"
        "/myreports - Мои заявки",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def myreports_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /myreports - показать свои заявки"""
    user_id = update.effective_user.id
    user_reports = [r for r in pending_reports.values() if r['user_id'] == user_id]
    
    if not user_reports:
        keyboard = [[InlineKeyboardButton("📋 Подать заявку", callback_data="new_report")]]
        await update.message.reply_text(
            "📭 У вас нет активных заявок.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    text = "📊 **Ваши заявки:**\n\n"
    keyboard = []
    
    for report in user_reports[-5:]:
        status_emoji = {
            'pending': '⏳',
            'approved': '✅',
            'rejected': '❌'
        }.get(report['status'], '⏳')
        
        report_num = format_report_number(int(report['id']))
        text += f"{status_emoji} {report_num}: {report['scammer_username']} | {report['amount']}₽\n"
    
    keyboard.append([InlineKeyboardButton("🔙 В меню", callback_data="back_to_menu")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться в главное меню"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("📋 Подать заявку на скамера", callback_data="new_report")]]
    
    await query.edit_message_text(
        "👋 **Главное меню**\n\n"
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ========== СОЗДАНИЕ ЗАЯВКИ ==========
async def new_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания заявки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_sessions[user_id] = {
        'step': 'username',
        'data': {}
    }
    
    keyboard = [
        [InlineKeyboardButton("⏭ Пропустить (поставить -)", callback_data="skip_username")],
        [InlineKeyboardButton("❌ Отменить создание заявки", callback_data="cancel_report")]
    ]
    
    await query.edit_message_text(
        "📝 **Шаг 1 из 9**\n\n"
        "Введите @username скамера:\n"
        "Например: @scammer123\n\n"
        "Или нажмите кнопку «Пропустить»\n\n"
        "⚠️ **На этом этапе можно отменить создание заявки**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ========== ФУНКЦИИ ДЛЯ ВОЗВРАТА ==========
async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться на предыдущий шаг"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_sessions:
        return
    
    current_step = user_sessions[user_id].get('step')
    
    # Определяем предыдущий шаг
    step_order = ['username', 'id', 'profile', 'channel', 'scam_date', 'other_profiles', 'description', 'amount', 'waiting_photo']
    current_index = step_order.index(current_step) if current_step in step_order else -1
    
    if current_index > 0:
        previous_step = step_order[current_index - 1]
        user_sessions[user_id]['step'] = previous_step
        
        # Показываем соответствующий шаг
        if previous_step == 'username':
            keyboard = [
                [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_username")],
                [InlineKeyboardButton("❌ Отменить", callback_data="cancel_report")]
            ]
            text = "📝 **Шаг 1 из 9**\n\nВведите @username скамера:"
        
        elif previous_step == 'id':
            keyboard = [
                [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
                [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_id")]
            ]
            text = (
                "📝 **Шаг 2 из 9**\n\n"
                "Введите ID скамера:\n\n"
                "💡 **ID пользователя можно узнать, отправив скамера боту @userinfobot**\n\n"
                "Например: 123456789"
            )
        
        elif previous_step == 'profile':
            keyboard = [
                [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
                [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_profile")]
            ]
            text = "📝 **Шаг 3 из 9**\n\nВведите ссылку на профиль скамера:\nФормат: `tg://user?id=123456789`"
        
        elif previous_step == 'channel':
            keyboard = [
                [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
                [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_channel")]
            ]
            text = "📝 **Шаг 4 из 9**\n\nВведите канал или чат, где нашли скамера:"
        
        elif previous_step == 'scam_date':
            keyboard = [
                [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
                [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_scam_date")]
            ]
            text = "📝 **Шаг 5 из 9**\n\nВведите дату скама (ДД.ММ.ГГГГ):"
        
        elif previous_step == 'other_profiles':
            keyboard = [
                [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
                [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_other_profiles")]
            ]
            text = "📝 **Шаг 6 из 9**\n\nВведите ссылки на другие профили скамера:"
        
        elif previous_step == 'description':
            keyboard = [
                [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
                [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_description")]
            ]
            text = "📝 **Шаг 7 из 9**\n\nВведите описание скамера:"
        
        elif previous_step == 'amount':
            keyboard = [
                [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
                [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_amount")]
            ]
            text = "📝 **Шаг 8 из 9**\n\nВведите сумму скама:"
        
        else:
            return
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

# ========== ФУНКЦИИ ПРОПУСКА ==========
async def skip_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить ввод username"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_sessions:
        return
    
    user_sessions[user_id]['data']['scammer_username'] = '-'
    user_sessions[user_id]['step'] = 'id'
    
    keyboard = [
        [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_id")]
    ]
    
    await query.edit_message_text(
        "✅ Username пропущен\n\n"
        "📝 **Шаг 2 из 9**\n\n"
        "Введите ID скамера:\n\n"
        "💡 **ID пользователя можно узнать, отправив скамера боту @userinfobot**\n\n"
        "Например: 123456789",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def skip_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить ввод ID"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_sessions:
        return
    
    user_sessions[user_id]['data']['scammer_id'] = '-'
    user_sessions[user_id]['step'] = 'profile'
    
    keyboard = [
        [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_profile")]
    ]
    
    await query.edit_message_text(
        "✅ ID пропущен\n\n"
        "📝 **Шаг 3 из 9**\n\n"
        "Введите ссылку на профиль скамера:\n"
        "Формат: `tg://user?id=123456789`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def skip_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить ввод ссылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_sessions:
        return
    
    user_sessions[user_id]['data']['profile_link'] = '-'
    user_sessions[user_id]['step'] = 'channel'
    
    keyboard = [
        [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_channel")]
    ]
    
    await query.edit_message_text(
        "✅ Ссылка пропущена\n\n"
        "📝 **Шаг 4 из 9**\n\n"
        "Введите канал или чат, где нашли скамера:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def skip_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить ввод канала"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_sessions:
        return
    
    user_sessions[user_id]['data']['channel'] = '-'
    user_sessions[user_id]['step'] = 'scam_date'
    
    keyboard = [
        [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_scam_date")]
    ]
    
    await query.edit_message_text(
        "✅ Канал пропущен\n\n"
        "📝 **Шаг 5 из 9**\n\n"
        "Введите дату скама:\n"
        "Формат: ДД.ММ.ГГГГ",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def skip_scam_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить ввод даты"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_sessions:
        return
    
    user_sessions[user_id]['data']['scam_date'] = '-'
    user_sessions[user_id]['step'] = 'other_profiles'
    
    keyboard = [
        [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_other_profiles")]
    ]
    
    await query.edit_message_text(
        "✅ Дата пропущена\n\n"
        "📝 **Шаг 6 из 9**\n\n"
        "Введите ссылки на другие профили скамера:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def skip_other_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить ввод других профилей"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_sessions:
        return
    
    user_sessions[user_id]['data']['other_profiles'] = '-'
    user_sessions[user_id]['step'] = 'description'
    
    keyboard = [
        [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_description")]
    ]
    
    await query.edit_message_text(
        "✅ Другие профили пропущены\n\n"
        "📝 **Шаг 7 из 9**\n\n"
        "Введите описание скамера:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить ввод описания"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_sessions:
        return
    
    user_sessions[user_id]['data']['description'] = '-'
    user_sessions[user_id]['step'] = 'amount'
    
    keyboard = [
        [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_amount")]
    ]
    
    await query.edit_message_text(
        "✅ Описание пропущено\n\n"
        "📝 **Шаг 8 из 9**\n\n"
        "Введите сумму скама (в рублях):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def skip_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить ввод суммы"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_sessions:
        return
    
    user_sessions[user_id]['data']['amount'] = '-'
    user_sessions[user_id]['step'] = 'waiting_photo'
    
    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data="go_back")]]
    
    await query.edit_message_text(
        "✅ Сумма пропущена\n\n"
        "📸 **Шаг 9 из 9**\n\n"
        "**Отправьте фото доказательств**\n"
        "Фото обязательно для подтверждения скама!\n\n"
        "Отправьте фото прямо сейчас:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def cancel_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить создание заявки (доступно только на 1 шаге)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверяем, что пользователь действительно на 1 шаге
    if user_id in user_sessions and user_sessions[user_id].get('step') == 'username':
        del user_sessions[user_id]
        
        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data="back_to_menu")]]
        
        await query.edit_message_text(
            "❌ Создание заявки отменено.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text(
            "❌ Отмена доступна только на первом шаге!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ Назад", callback_data="go_back")
            ]])
        )

# ========== ОБРАБОТКА ТЕКСТОВЫХ ШАГОВ ==========
async def handle_text_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых шагов формы"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id not in user_sessions:
        return
    
    step = user_sessions[user_id].get('step')
    
    if step == 'username':
        if not text.startswith('@'):
            text = '@' + text
        user_sessions[user_id]['data']['scammer_username'] = text
        user_sessions[user_id]['step'] = 'id'
        
        keyboard = [
            [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_id")]
        ]
        
        await update.message.reply_text(
            "✅ Username сохранен!\n\n"
            "📝 **Шаг 2 из 9**\n\n"
            "Введите ID скамера:\n\n"
            "💡 **ID пользователя можно узнать, отправив скамера боту @userinfobot**\n\n"
            "Например: 123456789",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif step == 'id':
        user_sessions[user_id]['data']['scammer_id'] = text
        user_sessions[user_id]['step'] = 'profile'
        
        keyboard = [
            [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_profile")]
        ]
        
        await update.message.reply_text(
            "✅ ID сохранен!\n\n"
            "📝 **Шаг 3 из 9**\n\n"
            "Введите ссылку на профиль скамера:\n"
            "Формат: `tg://user?id=123456789`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif step == 'profile':
        if text != '-' and not text.startswith('tg://user?id='):
            await update.message.reply_text(
                "❌ Неверный формат! Используйте: `tg://user?id=123456789`\n"
                "Или отправьте `-` чтобы пропустить",
                parse_mode="Markdown"
            )
            return
        
        user_sessions[user_id]['data']['profile_link'] = text
        user_sessions[user_id]['step'] = 'channel'
        
        keyboard = [
            [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_channel")]
        ]
        
        await update.message.reply_text(
            "✅ Ссылка сохранена!\n\n"
            "📝 **Шаг 4 из 9**\n\n"
            "Введите канал или чат, где нашли скамера:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif step == 'channel':
        user_sessions[user_id]['data']['channel'] = text
        user_sessions[user_id]['step'] = 'scam_date'
        
        keyboard = [
            [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_scam_date")]
        ]
        
        await update.message.reply_text(
            "✅ Канал сохранен!\n\n"
            "📝 **Шаг 5 из 9**\n\n"
            "Введите дату скама (ДД.ММ.ГГГГ):",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif step == 'scam_date':
        if text != '-':
            try:
                datetime.strptime(text, '%d.%m.%Y')
            except:
                await update.message.reply_text(
                    "❌ Неверный формат! Используйте ДД.ММ.ГГГГ\n"
                    "Например: 15.01.2024"
                )
                return
        
        user_sessions[user_id]['data']['scam_date'] = text
        user_sessions[user_id]['step'] = 'other_profiles'
        
        keyboard = [
            [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_other_profiles")]
        ]
        
        await update.message.reply_text(
            "✅ Дата сохранена!\n\n"
            "📝 **Шаг 6 из 9**\n\n"
            "Введите ссылки на другие профили скамера:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif step == 'other_profiles':
        user_sessions[user_id]['data']['other_profiles'] = text
        user_sessions[user_id]['step'] = 'description'
        
        keyboard = [
            [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_description")]
        ]
        
        await update.message.reply_text(
            "✅ Другие профили сохранены!\n\n"
            "📝 **Шаг 7 из 9**\n\n"
            "Введите описание скамера:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif step == 'description':
        user_sessions[user_id]['data']['description'] = text
        user_sessions[user_id]['step'] = 'amount'
        
        keyboard = [
            [InlineKeyboardButton("↩️ Назад", callback_data="go_back")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_amount")]
        ]
        
        await update.message.reply_text(
            "✅ Описание сохранено!\n\n"
            "📝 **Шаг 8 из 9**\n\n"
            "Введите сумму скама (в рублях):\n"
            "Например: 5000",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif step == 'amount':
        if text != '-':
            try:
                float(text)
            except:
                await update.message.reply_text(
                    "❌ Введите число (сумму в рублях) или отправьте `-` чтобы пропустить"
                )
                return
        
        user_sessions[user_id]['data']['amount'] = text
        user_sessions[user_id]['step'] = 'waiting_photo'
        
        keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data="go_back")]]
        
        await update.message.reply_text(
            "✅ Сумма сохранена!\n\n"
            "📸 **Шаг 9 из 9**\n\n"
            "**Отправьте фото доказательств**\n"
            "Фото обязательно для подтверждения скама!\n\n"
            "Отправьте фото прямо сейчас:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

# ========== ОБРАБОТКА ФОТО ==========
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото доказательств"""
    user_id = update.effective_user.id
    
    try:
        # Проверяем, есть ли активная сессия
        if user_id not in user_sessions:
            await update.message.reply_text(
                "❌ Сначала начните заполнение формы через /start"
            )
            return
        
        # Проверяем, что мы на шаге ожидания фото
        if user_sessions[user_id].get('step') != 'waiting_photo':
            await update.message.reply_text(
                "❌ Сначала заполните все поля формы"
            )
            return
        
        # Проверяем, что это действительно фото
        if not update.message.photo:
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте фото, а не другой файл"
            )
            return
        
        # Получаем данные сессии
        session_data = user_sessions[user_id]['data']
        
        # Проверяем обязательные поля
        required_fields = ['scammer_username', 'scammer_id', 'profile_link', 
                           'channel', 'scam_date', 'other_profiles', 'description', 'amount']
        
        missing_fields = []
        for field in required_fields:
            if field not in session_data:
                missing_fields.append(field)
        
        if missing_fields:
            await update.message.reply_text(
                f"❌ Ошибка: не все данные заполнены. Отсутствуют: {', '.join(missing_fields)}. Начните заново через /start"
            )
            del user_sessions[user_id]
            return
        
        # Генерируем ID заявки
        report_id = get_next_report_id()
        
        # Получаем фото
        photo = update.message.photo[-1]
        photo_file_id = photo.file_id
        
        # Форматируем номер
        formatted_number = format_report_number(int(report_id))
        
        # Сохраняем заявку
        report_data = {
            'id': report_id,
            'formatted_id': formatted_number,
            'user_id': user_id,
            'username': update.effective_user.username or '-',
            'full_name': update.effective_user.full_name or '-',
            'scammer_username': session_data['scammer_username'],
            'scammer_id': session_data['scammer_id'],
            'profile_link': session_data['profile_link'],
            'channel': session_data['channel'],
            'scam_date': session_data['scam_date'],
            'other_profiles': session_data['other_profiles'],
            'description': session_data['description'],
            'amount': session_data['amount'],
            'photo': photo_file_id,
            'status': 'pending',
            'date': str(datetime.now())
        }
        pending_reports[report_id] = report_data
        
        # Экранируем специальные символы для Markdown
        safe_username = escape_markdown(report_data['username'])
        safe_full_name = escape_markdown(report_data['full_name'])
        safe_scammer_username = escape_markdown(report_data['scammer_username'])
        safe_scammer_id = escape_markdown(report_data['scammer_id'])
        safe_profile_link = report_data['profile_link']  # Ссылки не экранируем
        safe_channel = escape_markdown(report_data['channel'])
        safe_scam_date = escape_markdown(report_data['scam_date'])
        safe_other_profiles = escape_markdown(report_data['other_profiles'])
        safe_description = escape_markdown(report_data['description'])
        safe_amount = escape_markdown(report_data['amount'])
        
        # Кнопки для админа
        admin_keyboard = [[
            InlineKeyboardButton("✅ Опубликовать", callback_data=f"approve_{report_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{report_id}")
        ]]
        
        # Отправляем админу (БЕЗ parse_mode, чтобы избежать ошибок Markdown)
        admin_text = (
            f"📨 Новая заявка {formatted_number}\n\n"
            f"👤 От заявителя:\n"
            f"• Имя: {safe_full_name}\n"
            f"• Username: @{safe_username}\n"
            f"• ID: {user_id}\n\n"
            f"🔹 Данные скамера:\n"
            f"• Username: {safe_scammer_username}\n"
            f"• ID: {safe_scammer_id}\n"
            f"• Ссылка: {safe_profile_link}\n"
            f"• Канал/чат: {safe_channel}\n"
            f"• Дата скама: {safe_scam_date}\n"
            f"• Другие профили: {safe_other_profiles}\n\n"
            f"📝 Описание:\n{safe_description}\n\n"
            f"💰 Сумма скама: {safe_amount}₽\n\n"
            f"📸 Доказательства: (на фото)"
        )
        
        # Отправляем админу без Markdown парсинга
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_file_id,
            caption=admin_text,
            reply_markup=InlineKeyboardMarkup(admin_keyboard)
            # Убрали parse_mode="Markdown"
        )
        
        # Подтверждение пользователю (тоже без Markdown)
        await update.message.reply_text(
            f"✅ Заявка {formatted_number} отправлена на проверку!\n\n"
            f"📋 Данные заявки:\n"
            f"• Скамер: {report_data['scammer_username']}\n"
            f"• Ссылка: {report_data['profile_link']}\n"
            f"• Сумма: {report_data['amount']}₽\n\n"
            f"Администратор рассмотрит её в ближайшее время.\n"
            f"Сохраните номер заявки: {formatted_number}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 В меню", callback_data="back_to_menu")
            ]])
            # Убрали parse_mode="Markdown"
        )
        
        # Очищаем сессию
        del user_sessions[user_id]
        
    except Exception as e:
        error_text = str(e)
        print(f"Ошибка: {error_text}")  # Для отладки
        
        # Определяем тип ошибки и даем понятное сообщение
        if "chat not found" in error_text or "channel" in error_text.lower():
            await update.message.reply_text(
                "❌ Ошибка: бот не добавлен в канал @Scambasebynoflixx как администратор!\n\n"
                "Пожалуйста, сообщите администратору об этой проблеме."
            )
        elif "bot was blocked" in error_text:
            await update.message.reply_text(
                "❌ Ошибка: бот заблокирован пользователем"
            )
        else:
            await update.message.reply_text(
                f"❌ Произошла ошибка при отправке заявки. Попробуйте позже.\n\n"
                f"Техническая информация: {error_text[:100]}"
            )

# ========== ОБРАБОТКА КНОПОК АДМИНА ==========
async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки админа"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ У вас нет прав для этого действия.")
        return
    
    data = query.data.split('_')
    action = data[0]
    report_id = data[1]
    
    report = pending_reports.get(report_id)
    if not report:
        await query.edit_message_text("❌ Заявка не найдена.")
        return
    
    formatted_number = format_report_number(int(report_id))
    
    if action == "approve":
        try:
            # Экранируем специальные символы
            safe_scammer_username = escape_markdown(report['scammer_username'])
            safe_scammer_id = escape_markdown(report['scammer_id'])
            safe_profile_link = report['profile_link']  # Ссылки не экранируем
            safe_channel = escape_markdown(report['channel'])
            safe_scam_date = escape_markdown(report['scam_date'])
            safe_other_profiles = escape_markdown(report['other_profiles'])
            safe_description = escape_markdown(report['description'])
            safe_amount = escape_markdown(report['amount'])
            
            # Публикуем в канал (БЕЗ Markdown)
            channel_text = (
                f"🚨 СКАМЕР 🚨\n\n"
                f"📋 Номер заявки: {formatted_number}\n\n"
                f"📌 Данные скамера:\n"
                f"• Username: {safe_scammer_username}\n"
                f"• ID: {safe_scammer_id}\n"
                f"• Ссылка: {safe_profile_link}\n"
                f"• Канал/чат: {safe_channel}\n"
                f"• Дата скама: {safe_scam_date}\n"
                f"• Другие профили: {safe_other_profiles}\n\n"
                f"📝 Описание:\n{safe_description}\n\n"
                f"💰 Сумма скама: {safe_amount}₽\n\n"
                f"📅 Дата публикации: {datetime.now().strftime('%d.%m.%Y')}\n\n"
                f"⚠️ Будьте осторожны при сделках с этим пользователем!"
            )
            
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=report['photo'],
                caption=channel_text
                # Убрали parse_mode="Markdown"
            )
            
            report['status'] = 'approved'
            
            # Обновляем сообщение админа
            await query.edit_message_caption(
                caption=query.message.caption + f"\n\n✅ Заявка {formatted_number} ОДОБРЕНА и опубликована в @Scambasebynoflixx!"
                # Убрали parse_mode="Markdown"
            )
            
            # Уведомляем пользователя
            try:
                await context.bot.send_message(
                    chat_id=report['user_id'],
                    text=f"✅ Ваша заявка {formatted_number} одобрена!\n\n"
                         f"Информация о скамере опубликована в канале @Scambasebynoflixx.\n"
                         f"Спасибо за помощь сообществу!"
                    # Убрали parse_mode="Markdown"
                )
            except:
                pass
                
        except Exception as e:
            error_text = str(e)
            await query.edit_message_caption(
                caption=query.message.caption + f"\n\n❌ Ошибка публикации!\n\n{error_text[:200]}"
                # Убрали parse_mode="Markdown"
            )
        
    elif action == "reject":
        report['status'] = 'rejected'
        
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n❌ Заявка {formatted_number} ОТКЛОНЕНА"
            # Убрали parse_mode="Markdown"
        )
        
        try:
            await context.bot.send_message(
                chat_id=report['user_id'],
                text=f"❌ Ваша заявка {formatted_number} отклонена.\n\n"
                     f"Причины могут быть:\n"
                     f"• Недостаточно доказательств\n"
                     f"• Неверные данные\n"
                     f"• Скам не подтвердился\n\n"
                     f"Вы можете подать новую заявку через /start"
                # Убрали parse_mode="Markdown"
            )
        except:
            pass

# ========== ОБЩИЙ ОБРАБОТЧИК ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Общий обработчик сообщений"""
    user_id = update.effective_user.id
    
    # Если это фото
    if update.message.photo:
        await handle_photo(update, context)
        return
    
    # Если это текст
    if update.message.text:
        text = update.message.text.strip()
        
        # Проверяем команды
        if text.startswith('/'):
            return
        
        # Проверяем активную сессию
        if user_id in user_sessions:
            await handle_text_step(update, context)
            return
        
        # Если нет активной сессии
        await update.message.reply_text(
            "❓ Чтобы подать заявку, нажмите /start и выберите «Подать заявку»"
        )

# ========== ЗАПУСК ==========
def main():
    print("✅ Бот для жалоб на скамеров запущен!")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print(f"📢 Канал: {CHANNEL_ID}")
    
    # Проверяем существование файла счетчика
    if not os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, 'w') as f:
            f.write("0")
        print("📊 Счетчик заявок инициализирован")
    
    app = Application.builder().token(TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("myreports", myreports_command))
    
    # Callback кнопки для формы
    app.add_handler(CallbackQueryHandler(new_report, pattern="^new_report$"))
    app.add_handler(CallbackQueryHandler(go_back, pattern="^go_back$"))
    app.add_handler(CallbackQueryHandler(skip_username, pattern="^skip_username$"))
    app.add_handler(CallbackQueryHandler(skip_id, pattern="^skip_id$"))
    app.add_handler(CallbackQueryHandler(skip_profile, pattern="^skip_profile$"))
    app.add_handler(CallbackQueryHandler(skip_channel, pattern="^skip_channel$"))
    app.add_handler(CallbackQueryHandler(skip_scam_date, pattern="^skip_scam_date$"))
    app.add_handler(CallbackQueryHandler(skip_other_profiles, pattern="^skip_other_profiles$"))
    app.add_handler(CallbackQueryHandler(skip_description, pattern="^skip_description$"))
    app.add_handler(CallbackQueryHandler(skip_amount, pattern="^skip_amount$"))
    app.add_handler(CallbackQueryHandler(cancel_report, pattern="^cancel_report$"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    
    # Callback кнопки админа
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^(approve_|reject_)"))
    
    # Обработка сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    
    print("✅ Бот готов к работе!")
    app.run_polling()

if __name__ == "__main__":
    main()
