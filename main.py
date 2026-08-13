import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import aiohttp
import re
import os

TOKEN = "7906311130:AAHm6Sz5N0YJ82L1yT1GNjm1Q3jjchofmMQ"

REPORT_TYPE, QUERY_VALUE = range(2)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

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
        "🕵️ OSINT-бот\nВыбери тип:",
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

    result = {}

    if report_type == 'phone':
        result = parse_phone(value)
    elif report_type == 'email':
        result = await parse_email(value)
    elif report_type == 'nickname':
        result = await parse_nickname(value)
    elif report_type == 'passport':
        result = parse_passport(value)
    elif report_type == 'snils':
        result = parse_snils(value)
    elif report_type == 'inn':
        result = parse_inn(value)
    else:
        result = {'ошибка': 'неизвестный тип'}

    report = f"🔍 Отчёт: `{value}`\n\n"
    for key, val in result.items():
        if isinstance(val, dict):
            for k, v in val.items():
                report += f"• {k}: {v}\n"
        else:
            report += f"• {key}: {val}\n"

    await msg.delete()
    await update.message.reply_text(report[:4000], parse_mode='Markdown')
    return ConversationHandler.END

# ===============================================
# ПАРСЕРЫ (ТОЛЬКО ЛОКАЛЬНЫЕ, МГНОВЕННЫЕ)
# ===============================================

def parse_phone(phone):
    data = {'оператор': 'Неизвестно', 'страна': 'Неизвестно'}
    if phone.startswith('+7'):
        data['страна'] = 'Россия'
        data['оператор'] = 'МТС/Билайн/Мегафон' if phone.startswith('+79') else 'Ростелеком'
    elif phone.startswith('+38'):
        data['страна'] = 'Украина'
        data['оператор'] = 'Киевстар/Vodafone'
    return data

async def parse_email(email):
    data = {'домен': 'Неизвестен', 'утечки': 'Не проверено'}
    if '@' in email:
        data['домен'] = email.split('@')[1]
    # Have I Been Pwned (один запрос, 3 сек)
    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f'https://haveibeenpwned.com/api/v3/breachedaccount/{email}'
            async with session.get(url) as resp:
                if resp.status == 200:
                    breaches = await resp.json()
                    data['утечки'] = f"Найден в {len(breaches)} утечках"
                elif resp.status == 404:
                    data['утечки'] = 'Не найден в утечках'
    except:
        data['утечки'] = 'Ошибка проверки'
    return data

async def parse_nickname(nickname):
    found = {}
    platforms = {
        'Telegram': f'https://t.me/{nickname}',
        'VK': f'https://vk.com/{nickname}',
        'GitHub': f'https://github.com/{nickname}',
    }
    timeout = aiohttp.ClientTimeout(total=2)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for name, url in platforms.items():
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        found[name] = '✅ Найден'
                    else:
                        found[name] = '❌ Не найден'
            except:
                found[name] = '❌ Ошибка'
    return {'соцсети': found}

def parse_passport(passport_data):
    clean = re.sub(r'[\s\-]', '', passport_data)
    if not clean.isdigit() or len(clean) != 10:
        return {'ошибка': 'Нужно 10 цифр'}
    return {
        'серия': clean[:4],
        'номер': clean[4:],
        'валидность': '✅ Формат корректный' if int(clean[:4]) != 0 else '❌ Невалидный'
    }

def parse_snils(snils_data):
    clean = re.sub(r'[\s\-]', '', snils_data)
    if not clean.isdigit() or len(clean) != 11:
        return {'ошибка': 'Нужно 11 цифр'}
    digits = [int(d) for d in clean]
    total = sum(digits[i] * (9 - i) for i in range(9))
    calculated = total if total < 100 else 0 if total in (100, 101) else total % 101
    control = digits[-2] * 10 + digits[-1]
    return {'валидность': '✅ Валидный' if calculated == control else '❌ Невалидный'}

def parse_inn(inn_data):
    clean = re.sub(r'[\s\-]', '', inn_data)
    if not clean.isdigit() or len(clean) not in (10, 12):
        return {'ошибка': 'Нужно 10 или 12 цифр'}
    return {'валидность': '✅ Формат корректный'}

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
    print("✅ Бот запущен")
    app.run_polling()

if __name__ == '__main__':
    main()
