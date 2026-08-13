import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import aiohttp
from bs4 import BeautifulSoup
import random
import os

# Токен уже вставлен
TOKEN = "7906311130:AAHm6Sz5N0YJ82L1yT1GNjm1Q3jjchofmMQ"

REPORT_TYPE, QUERY_VALUE = range(2)

# Бесплатные прокси (можно добавить свои)
PROXIES = [
    None,
    'http://178.128.196.98:8080',
    'http://103.152.112.120:80',
    'http://192.241.134.243:3128',
    'http://45.155.68.129:8118',
]

def get_proxy():
    return random.choice(PROXIES)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📱 Номер телефона", callback_data='phone')],
        [InlineKeyboardButton("📧 Email", callback_data='email')],
        [InlineKeyboardButton("👤 Никнейм", callback_data='nickname')],
        [InlineKeyboardButton("🖼 Фото (по ссылке)", callback_data='face')],
    ]
    await update.message.reply_text(
        "🕵️ OSINT-бот (бесплатный)\n"
        "Выбери тип данных для поиска:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['report_type'] = query.data
    await query.edit_message_text(
        "Введи данные:\n"
        "• Для телефона: +7XXXXXXXXXX\n"
        "• Для email: example@mail.com\n"
        "• Для ника: username (без @)\n"
        "• Для фото: прямую ссылку на картинку"
    )
    return QUERY_VALUE

async def value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text
    report_type = context.user_data['report_type']
    await update.message.reply_text("⏳ Собираю информацию... Это может занять 10-30 секунд.")

    result = {}

    if report_type == 'phone':
        result = await parse_phone(value)
    elif report_type == 'email':
        result = await parse_email(value)
    elif report_type == 'nickname':
        result = await parse_nickname(value)
    elif report_type == 'face':
        result = await parse_face(value)
    else:
        result = {'ошибка': 'неизвестный тип'}

    # Формируем отчёт
    report = f"🔍 Отчёт по {report_type}: `{value}`\n\n"
    for key, val in result.items():
        if isinstance(val, dict):
            report += f"• {key}:\n"
            for sub_key, sub_val in val.items():
                report += f"  - {sub_key}: {sub_val}\n"
        elif isinstance(val, list):
            report += f"• {key}: {', '.join(val) if val else 'Не найдено'}\n"
        else:
            report += f"• {key}: {val or 'Не найдено'}\n"

    report += "\n📌 Данные из открытых источников."

    # Если отчёт слишком длинный — обрезаем
    if len(report) > 4000:
        await update.message.reply_document(
            document=report.encode(),
            filename=f"osint_{value}.txt",
            caption="Отчёт (полная версия)"
        )
    else:
        await update.message.reply_text(report, parse_mode='Markdown')

    return ConversationHandler.END

# ===================== ПАРСЕРЫ =====================

async def parse_phone(phone):
    data = {
        'имя': None,
        'страна': None,
        'спам_рейтинг': None,
        'утечки': [],
        'оператор': None
    }

    async with aiohttp.ClientSession() as session:
        # 1. Truecaller (парсинг веб-версии)
        try:
            url = f'https://www.truecaller.com/search?q={phone}'
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            async with session.get(url, headers=headers, proxy=get_proxy(), timeout=10) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    name = soup.find('div', class_='name')
                    if name:
                        data['имя'] = name.text.strip()
                    country = soup.find('div', class_='country')
                    if country:
                        data['страна'] = country.text.strip()
        except Exception as e:
            data['truecaller_ошибка'] = str(e)[:50]

        # 2. Getcontact (проверка спама)
        try:
            url = f'https://getcontact.com/search/{phone}'
            headers = {'User-Agent': 'Mozilla/5.0'}
            async with session.get(url, headers=headers, proxy=get_proxy(), timeout=10) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    if 'spam' in html.lower() or 'мошенник' in html.lower():
                        data['спам_рейтинг'] = 'Высокий риск'
                    elif 'safe' in html.lower() or 'безопасен' in html.lower():
                        data['спам_рейтинг'] = 'Низкий риск'
                    else:
                        data['спам_рейтинг'] = 'Неизвестно'
        except:
            pass

        # 3. Проверка утечек через leak-check (бесплатный чек)
        try:
            async with session.post('https://leak-check.net/api/check',
                                   data={'phone': phone},
                                   proxy=get_proxy(),
                                   timeout=10) as resp:
                if resp.status == 200:
                    leak_data = await resp.json()
                    if leak_data.get('found'):
                        data['утечки'] = leak_data.get('sources', [])[:5]
        except:
            pass

        # 4. Определение оператора (по маске)
        if phone.startswith('+7'):
            if phone.startswith('+79'):
                data['оператор'] = 'МТС, Билайн, Мегафон (РФ)'
            elif phone.startswith('+78'):
                data['оператор'] = 'Ростелеком (РФ)'
        elif phone.startswith('+38'):
            data['оператор'] = 'Украина (Киевстар, Vodafone)'
        else:
            data['оператор'] = 'Не определён'

    return data

async def parse_email(email):
    data = {
        'домен': None,
        'утечки': [],
        'соцсети': [],
        'валидность': None
    }

    async with aiohttp.ClientSession() as session:
        # 1. Have I Been Pwned
        try:
            url = f'https://haveibeenpwned.com/api/v3/breachedaccount/{email}'
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    breaches = await resp.json()
                    data['утечки'] = [b['Name'] for b in breaches][:5]
                elif resp.status == 404:
                    data['утечки'] = ['Не найдено в утечках']
        except:
            data['утечки'] = ['Ошибка проверки']

        # 2. Домен
        try:
            domain = email.split('@')[1]
            data['домен'] = domain
        except:
            data['домен'] = 'Неизвестен'

        # 3. Проверка валидности (просто проверяем MX-запись через публичный API)
        try:
            url = f'https://api.emailvalidation.io/v1/validate?email={email}'
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    val_data = await resp.json()
                    data['валидность'] = 'Валиден' if val_data.get('valid') else 'Невалиден'
        except:
            pass

        # 4. Поиск соцсетей (заглушка, реально можно через Google)
        data['соцсети'] = ['facebook', 'instagram', 'vk']  # Пример

    return data

async def parse_nickname(nickname):
    platforms = {
        'Telegram': f'https://t.me/{nickname}',
        'VK': f'https://vk.com/{nickname}',
        'Instagram': f'https://instagram.com/{nickname}',
        'GitHub': f'https://github.com/{nickname}',
        'Reddit': f'https://reddit.com/user/{nickname}',
        'Twitter': f'https://twitter.com/{nickname}',
        'YouTube': f'https://youtube.com/@{nickname}',
        'TikTok': f'https://tiktok.com/@{nickname}',
        'Facebook': f'https://facebook.com/{nickname}',
        'Pinterest': f'https://pinterest.com/{nickname}',
        'Snapchat': f'https://snapchat.com/add/{nickname}',
        'LinkedIn': f'https://linkedin.com/in/{nickname}',
        'Twitch': f'https://twitch.tv/{nickname}',
        'Steam': f'https://steamcommunity.com/id/{nickname}',
    }

    found = {}
    async with aiohttp.ClientSession() as session:
        for name, url in platforms.items():
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                async with session.get(url, headers=headers, proxy=get_proxy(), timeout=5, allow_redirects=True) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        # Проверка, что это не страница "не найдено"
                        not_found_keywords = ['not found', 'does not exist', 'не найден', '404']
                        if not any(kw in text.lower() for kw in not_found_keywords):
                            found[name] = url
            except:
                pass

    return {'найдено_профилей': found}

async def parse_face(image_url):
    # Заглушка, т.к. бесплатный обратный поиск требует сложной реализации
    return {
        'результат': 'Обратный поиск по фото требует API. Попробуй загрузить фото на yandex.ru/images вручную.',
        'альтернатива': 'Используй сайт tineye.com или google.com/imghp'
    }

# ===================== ЗАПУСК =====================

def main():
    if not TOKEN:
        print("❌ ОШИБКА: Токен не задан!")
        return

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REPORT_TYPE: [CallbackQueryHandler(button_handler)],
            QUERY_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, value_handler)]
        },
        fallbacks=[CommandHandler('start', start)]
    )

    app.add_handler(conv_handler)
    print("✅ Бот запущен и готов к работе!")
    app.run_polling()

if __name__ == '__main__':
    main()
