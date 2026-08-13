import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import aiohttp
from bs4 import BeautifulSoup
import random

TOKEN = "7906311130:AAHm6Sz5N0YJ82L1yT1GNjm1Q3jjchofmMQ"  # замени на свой

REPORT_TYPE, QUERY_VALUE = range(2)

PROXIES = [
    None,
    'http://178.128.196.98:8080',
    'http://103.152.112.120:80',
]

def get_proxy():
    return random.choice(PROXIES)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📱 Номер телефона", callback_data='phone')],
        [InlineKeyboardButton("📧 Email", callback_data='email')],
        [InlineKeyboardButton("👤 Никнейм", callback_data='nickname')],
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
    value = update.message.text
    report_type = context.user_data['report_type']
    await update.message.reply_text("⏳ Ищу...")

    result = {}
    if report_type == 'phone':
        result = await parse_phone(value)
    elif report_type == 'email':
        result = await parse_email(value)
    elif report_type == 'nickname':
        result = await parse_nickname(value)

    report = f"🔍 Отчёт по {report_type}: `{value}`\n\n"
    for key, val in result.items():
        if isinstance(val, list):
            report += f"• {key}: {', '.join(val) if val else 'Не найдено'}\n"
        else:
            report += f"• {key}: {val or 'Не найдено'}\n"

    await update.message.reply_text(report[:4000], parse_mode='Markdown')
    return ConversationHandler.END

async def parse_phone(phone):
    data = {'имя': None, 'страна': None, 'спам': None, 'утечки': []}
    async with aiohttp.ClientSession() as session:
        try:
            url = f'https://www.truecaller.com/search?q={phone}'
            async with session.get(url, proxy=get_proxy(), timeout=10) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                name = soup.find('div', class_='name')
                if name:
                    data['имя'] = name.text.strip()
        except:
            pass
        try:
            url = f'https://getcontact.com/search/{phone}'
            async with session.get(url, proxy=get_proxy(), timeout=10) as resp:
                html = await resp.text()
                if 'spam' in html.lower():
                    data['спам'] = 'Высокий риск'
        except:
            pass
    return data

async def parse_email(email):
    data = {'домен': None, 'утечки': []}
    async with aiohttp.ClientSession() as session:
        try:
            domain = email.split('@')[1]
            data['домен'] = domain
        except:
            pass
        try:
            url = f'https://haveibeenpwned.com/api/v3/breachedaccount/{email}'
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    breaches = await resp.json()
                    data['утечки'] = [b['Name'] for b in breaches][:5]
        except:
            pass
    return data

async def parse_nickname(nickname):
    platforms = {
        'telegram': f'https://t.me/{nickname}',
        'vk': f'https://vk.com/{nickname}',
        'instagram': f'https://instagram.com/{nickname}',
        'github': f'https://github.com/{nickname}',
        'reddit': f'https://reddit.com/user/{nickname}',
    }
    found = {}
    async with aiohttp.ClientSession() as session:
        for name, url in platforms.items():
            try:
                async with session.get(url, proxy=get_proxy(), timeout=5) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        if 'not found' not in text.lower():
                            found[name] = url
            except:
                pass
    return {'найдено': found}

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
    print("Бот запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
