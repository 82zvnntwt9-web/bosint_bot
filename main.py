import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import re

TOKEN = "7906311130:AAHm6Sz5N0YJ82L1yT1GNjm1Q3jjchofmMQ"

REPORT_TYPE, QUERY_VALUE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📱 Номер телефона", callback_data='phone')],
        [InlineKeyboardButton("📧 Email", callback_data='email')],
        [InlineKeyboardButton("👤 Никнейм", callback_data='nickname')],
        [InlineKeyboardButton("🆔 Паспорт", callback_data='passport')],
        [InlineKeyboardButton("📋 СНИЛС", callback_data='snils')],
        [InlineKeyboardButton("📊 ИНН", callback_data='inn')],
    ]
    await update.message.reply_text(
        "🕵️ OSINT-бот\nВыбери тип данных:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['report_type'] = query.data
    await query.edit_message_text("Введи данные:")
    return QUERY_VALUE

async def value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text.strip()
    report_type = context.user_data['report_type']
    msg = await update.message.reply_text("⏳ Проверяю...")

    if report_type == 'phone':
        result = parse_phone(value)
    elif report_type == 'email':
        result = parse_email(value)
    elif report_type == 'nickname':
        result = parse_nickname(value)
    elif report_type == 'passport':
        result = parse_passport(value)
    elif report_type == 'snils':
        result = parse_snils(value)
    elif report_type == 'inn':
        result = parse_inn(value)
    else:
        result = {'ошибка': 'неизвестный тип'}

    report = f"🔍 Результат: `{value}`\n\n"
    for key, val in result.items():
        if isinstance(val, dict):
            for k, v in val.items():
                report += f"• {k}: {v}\n"
        else:
            report += f"• {key}: {val}\n"

    await msg.delete()
    await update.message.reply_text(report[:4000], parse_mode='Markdown')
    return ConversationHandler.END

# ============================================================
# ВСЕ ПРОВЕРКИ ТОЛЬКО ЛОКАЛЬНЫЕ — БЕЗ ИНТЕРНЕТА
# ============================================================

def parse_phone(phone):
    data = {'номер': phone, 'страна': 'Неизвестно', 'оператор': 'Неизвестно'}
    if phone.startswith('+7'):
        data['страна'] = 'Россия'
        data['оператор'] = 'МТС/Билайн/Мегафон' if phone.startswith('+79') else 'Ростелеком'
    elif phone.startswith('+38'):
        data['страна'] = 'Украина'
        data['оператор'] = 'Киевстар/Vodafone'
    elif phone.startswith('+1'):
        data['страна'] = 'США/Канада'
    elif phone.startswith('+44'):
        data['страна'] = 'Великобритания'
    elif phone.startswith('+49'):
        data['страна'] = 'Германия'
    return data

def parse_email(email):
    data = {'email': email, 'домен': 'Неизвестен', 'валидность': 'Не проверено'}
    if '@' in email:
        data['домен'] = email.split('@')[1]
        if '.' in data['домен']:
            data['валидность'] = 'Формат корректный'
        else:
            data['валидность'] = 'Неполный домен'
    return data

def parse_nickname(nickname):
    return {'никнейм': nickname, 'результат': 'Проверка вручную на соцсети'}

def parse_passport(passport_data):
    clean = re.sub(r'[\s\-]', '', passport_data)
    if not clean.isdigit() or len(clean) != 10:
        return {'ошибка': 'Нужно 10 цифр'}
    return {
        'серия': clean[:4],
        'номер': clean[4:],
        'валидность': '✅ Корректный' if int(clean[:4]) != 0 and int(clean[4:]) != 0 else '❌ Невалидный'
    }

def parse_snils(snils_data):
    clean = re.sub(r'[\s\-]', '', snils_data)
    if not clean.isdigit() or len(clean) != 11:
        return {'ошибка': 'Нужно 11 цифр'}
    try:
        digits = [int(d) for d in clean]
        total = 0
        for i in range(9):
            total += digits[i] * (9 - i)
        if total < 100:
            calculated = total
        elif total in (100, 101):
            calculated = 0
        else:
            calculated = total % 101
            if calculated == 100:
                calculated = 0
        control = digits[-2] * 10 + digits[-1]
        status = '✅ Валидный' if calculated == control else '❌ Невалидный'
        return {'контрольная_сумма': calculated, 'валидность': status}
    except:
        return {'ошибка': 'Ошибка проверки'}

def parse_inn(inn_data):
    clean = re.sub(r'[\s\-]', '', inn_data)
    if not clean.isdigit() or len(clean) not in (10, 12):
        return {'ошибка': 'Нужно 10 или 12 цифр'}
    inn_type = 'ЮЛ' if len(clean) == 10 else 'ФЛ'
    try:
        digits = [int(d) for d in clean]
        if len(clean) == 10:
            weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
            total = sum(digits[i] * weights[i] for i in range(9))
            control = total % 11
            if control == 10:
                control = 0
            status = '✅ Валидный' if control == digits[9] else '❌ Невалидный'
        else:  # 12 цифр
            weights1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
            total1 = sum(digits[i] * weights1[i] for i in range(10))
            control1 = total1 % 11
            if control1 == 10:
                control1 = 0
            weights2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
            total2 = sum(digits[i] * weights2[i] for i in range(11))
            control2 = total2 % 11
            if control2 == 10:
                control2 = 0
            status = '✅ Валидный' if (control1 == digits[10] and control2 == digits[11]) else '❌ Невалидный'
        return {'тип': inn_type, 'валидность': status}
    except:
        return {'ошибка': 'Ошибка проверки'}

def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REPORT_TYPE: [CallbackQueryHandler(button_handler)],
            QUERY_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, value_handler)]
        },
        fallbacks=[CommandHandler('start', start)]
    )
    app.add_handler(conv)
    print("✅ Бот запущен (полностью локальный)")
    app.run_polling()

if __name__ == '__main__':
    main()
