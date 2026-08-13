import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import aiohttp
import asyncio
import re
import os
from email_validator import validate_email, EmailNotValidError

TOKEN = "7906311130:AAHm6Sz5N0YJ82L1yT1GNjm1Q3jjchofmMQ"

REPORT_TYPE, QUERY_VALUE = range(2)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# ============== СТАРТ И МЕНЮ ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📱 Номер телефона", callback_data='phone')],
        [InlineKeyboardButton("📧 Email", callback_data='email')],
        [InlineKeyboardButton("👤 Никнейм", callback_data='nickname')],
        [InlineKeyboardButton("🖼 Фото (по ссылке)", callback_data='face')],
        [InlineKeyboardButton("🆔 Паспорт", callback_data='passport')],
        [InlineKeyboardButton("📋 СНИЛС", callback_data='snils')],
        [InlineKeyboardButton("📊 ИНН", callback_data='inn')],
        [InlineKeyboardButton("👤 ФИО + дата", callback_data='fio')],
    ]
    await update.message.reply_text(
        "🕵️ OSINT-бот (быстрый + документы)\n"
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
        "• Для фото: прямую ссылку на картинку\n"
        "• Для паспорта: 10 цифр (XXXXNNNNNN)\n"
        "• Для СНИЛС: 11 цифр (XXX-XXX-XXX XX)\n"
        "• Для ИНН: 10 или 12 цифр\n"
        "• Для ФИО: Иванов Иван Иванович 01.01.1990"
    )
    return QUERY_VALUE

async def value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text
    report_type = context.user_data['report_type']
    msg = await update.message.reply_text("⏳ Ищу... 3-8 секунд.")

    result = {}

    if report_type == 'phone':
        result = await parse_phone(value)
    elif report_type == 'email':
        result = await parse_email(value)
    elif report_type == 'nickname':
        result = await parse_nickname(value)
    elif report_type == 'face':
        result = await parse_face(value)
    elif report_type == 'passport':
        result = await parse_passport(value)
    elif report_type == 'snils':
        result = await parse_snils(value)
    elif report_type == 'inn':
        result = await parse_inn(value)
    elif report_type == 'fio':
        result = await parse_fio(value)
    else:
        result = {'ошибка': 'неизвестный тип'}

    report = f"🔍 Отчёт по {report_type}: `{value}`\n\n"
    for key, val in result.items():
        if isinstance(val, dict):
            report += f"• {key}:\n"
            for k, v in val.items():
                report += f"  - {k}: {v}\n"
        elif isinstance(val, list):
            report += f"• {key}: {', '.join(val) if val else 'Не найдено'}\n"
        else:
            report += f"• {key}: {val or 'Не найдено'}\n"

    await msg.delete()
    if len(report) > 4000:
        await update.message.reply_document(
            document=report.encode(),
            filename=f"osint_{value}.txt",
            caption="Отчёт"
        )
    else:
        await update.message.reply_text(report, parse_mode='Markdown')

    return ConversationHandler.END

# ============== ПАРСЕР ТЕЛЕФОНА ==============

async def parse_phone(phone):
    data = {
        'номер': phone,
        'оператор': None,
        'страна': None,
        'валидность': None,
        'гео': None,
        'примечание': None
    }

    if phone.startswith('+7'):
        data['страна'] = 'Россия'
        if phone.startswith('+79'):
            data['оператор'] = 'МТС / Билайн / Мегафон'
        elif phone.startswith('+78'):
            data['оператор'] = 'Ростелеком'
        else:
            data['оператор'] = 'Неизвестный оператор РФ'
    elif phone.startswith('+38'):
        data['страна'] = 'Украина'
        data['оператор'] = 'Киевстар / Vodafone'
    elif phone.startswith('+1'):
        data['страна'] = 'США / Канада'
        data['оператор'] = 'Неизвестно'
    elif phone.startswith('+44'):
        data['страна'] = 'Великобритания'
        data['оператор'] = 'Неизвестно'
    elif phone.startswith('+49'):
        data['страна'] = 'Германия'
        data['оператор'] = 'Неизвестно'
    else:
        data['страна'] = 'Неизвестно'
        data['оператор'] = 'Неизвестно'

    digits = ''.join(filter(str.isdigit, phone))
    if len(digits) < 10:
        data['примечание'] = '❌ Слишком короткий номер'
        data['валидность'] = 'Невалидный'
        return data

    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f'http://apilayer.net/api/validate?access_key=free&number={phone}'
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status == 200:
                    resp_data = await resp.json()
                    if resp_data.get('valid'):
                        data['валидность'] = '✅ Валидный'
                        data['гео'] = resp_data.get('location', 'Неизвестно')
                    else:
                        data['валидность'] = '❌ Невалидный'
    except:
        data['валидность'] = '⚠️ Проверка не выполнена'

    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f'https://leak-lookup.com/api/search?query={phone}'
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status == 200:
                    leak_data = await resp.json()
                    if leak_data.get('found'):
                        data['примечание'] = '⚠️ Найден в утечках'
    except:
        pass

    return data

# ============== ПАРСЕР EMAIL ==============

async def parse_email(email):
    data = {
        'email': email,
        'домен': None,
        'валидность': None,
        'утечки': None,
        'соцсети': []
    }

    try:
        valid = validate_email(email)
        data['валидность'] = '✅ Валидный'
        data['домен'] = valid.domain
    except EmailNotValidError:
        data['валидность'] = '❌ Невалидный'
        data['домен'] = 'Ошибка'
        return data

    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f'https://haveibeenpwned.com/api/v3/breachedaccount/{email}'
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status == 200:
                    breaches = await resp.json()
                    data['утечки'] = f"⚠️ Найден в {len(breaches)} утечках"
                elif resp.status == 404:
                    data['утечки'] = '✅ Не найден в утечках'
    except:
        data['утечки'] = '⚠️ Проверка не выполнена'

    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f'https://api.emailrep.io/email?email={email}'
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status == 200:
                    rep_data = await resp.json()
                    if rep_data.get('profiles'):
                        data['соцсети'] = list(rep_data['profiles'].keys())[:5]
    except:
        pass

    return data

# ============== ПАРСЕР НИКНЕЙМА ==============

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
        'Spotify': f'https://open.spotify.com/user/{nickname}',
    }

    found = {}
    timeout = aiohttp.ClientTimeout(total=3)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for name, url in platforms.items():
            try:
                async with session.get(url, headers=HEADERS, allow_redirects=True) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        not_found = ['not found', 'does not exist', '404', 'not exist']
                        if not any(x in text.lower() for x in not_found):
                            found[name] = '✅ Найден'
                        else:
                            found[name] = '❌ Не найден'
            except:
                found[name] = '❌ Не найден'

    return {'соцсети': found}

# ============== ПАРСЕР ФОТО ==============

async def parse_face(image_url):
    data = {
        'результат': '🔍 Ищем совпадения...',
        'ссылки': [],
        'альтернатива': 'Попробуй вручную на yandex.ru/images'
    }

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            search_url = f'https://www.google.com/search?tbm=isch&q={image_url}'
            async with session.get(search_url, headers=HEADERS) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    matches = re.findall(r'https://[^"]+\.(jpg|png|jpeg|webp)', html)
                    data['ссылки'] = matches[:3] if matches else ['Не найдено']
    except:
        data['результат'] = '⚠️ Ошибка поиска'

    return data

# ============== ПАРСЕР ПАСПОРТА ==============

async def parse_passport(passport_data):
    data = {
        'входные_данные': passport_data,
        'серия': None,
        'номер': None,
        'валидность': None,
        'статус': None,
        'примечание': None
    }

    clean = re.sub(r'[\s\-]', '', passport_data)
    
    if not clean.isdigit() or len(clean) != 10:
        data['примечание'] = '❌ Неверный формат. Нужно 10 цифр (XXXXNNNNNN)'
        return data

    data['серия'] = clean[:4]
    data['номер'] = clean[4:]

    try:
        series = int(data['серия'])
        number = int(data['номер'])
        if series == 0 or number == 0:
            data['валидность'] = '❌ Невалидный'
        else:
            data['валидность'] = '✅ Формат корректный'
    except:
        data['валидность'] = '❌ Ошибка проверки'

    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f'https://проверка-паспорта.рф/api/check?series={data["серия"]}&number={data["номер"]}'
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status == 200:
                    result = await resp.text()
                    if 'действителен' in result.lower():
                        data['статус'] = '✅ Действителен'
                    elif 'недействителен' in result.lower():
                        data['статус'] = '❌ Недействителен'
                    else:
                        data['статус'] = '⚠️ Неизвестно'
    except:
        data['статус'] = '⚠️ Проверка не выполнена'

    return data

# ============== ПАРСЕР СНИЛС ==============

async def parse_snils(snils_data):
    data = {
        'входные_данные': snils_data,
        'снилс': None,
        'валидность': None,
        'контрольная_сумма': None,
        'примечание': None
    }

    clean = re.sub(r'[\s\-]', '', snils_data)
    
    if not clean.isdigit() or len(clean) != 11:
        data['примечание'] = '❌ Неверный формат. Нужно 11 цифр'
        return data

    data['снилс'] = clean

    try:
        digits = [int(d) for d in clean]
        control = digits[-2] * 10 + digits[-1]
        
        total = 0
        for i in range(9):
            total += digits[i] * (9 - i)
        
        if total < 100:
            calculated = total
        elif total == 100 or total == 101:
            calculated = 0
        else:
            calculated = total % 101
            if calculated == 100:
                calculated = 0
        
        data['контрольная_сумма'] = calculated
        
        if calculated == control:
            data['валидность'] = '✅ Валидный'
        else:
            data['валидность'] = '❌ Невалидный'
            
    except Exception as e:
        data['примечание'] = f'Ошибка проверки: {str(e)}'

    return data

# ============== ПАРСЕР ИНН ==============

async def parse_inn(inn_data):
    data = {
        'входные_данные': inn_data,
        'инн': None,
        'тип': None,
        'валидность': None,
        'примечание': None
    }

    clean = re.sub(r'[\s\-]', '', inn_data)
    
    if not clean.isdigit():
        data['примечание'] = '❌ Только цифры'
        return data

    if len(clean) == 10:
        data['тип'] = 'ИНН ЮЛ'
    elif len(clean) == 12:
        data['тип'] = 'ИНН ФЛ'
    else:
        data['примечание'] = '❌ Нужно 10 или 12 цифр'
        return data

    data['инн'] = clean

    try:
        digits = [int(d) for d in clean]
        
        if len(clean) == 10:
            weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
            total = sum(digits[i] * weights[i] for i in range(9))
            control = total % 11
            if control == 10:
                control = 0
            if control == digits[9]:
                data['валидность'] = '✅ Валидный'
            else:
                data['валидность'] = '❌ Невалидный'
                
        elif len(clean) == 12:
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
                
            if control1 == digits[10] and control2 == digits[11]:
                data['валидность'] = '✅ Валидный'
            else:
                data['валидность'] = '❌ Невалидный'
                
    except Exception as e:
        data['примечание'] = f'Ошибка: {str(e)}'

    return data

# ============== ПАРСЕР ФИО ==============

async def parse_fio(fio_data):
    data = {
        'входные_данные': fio_data,
        'фамилия': None,
        'имя': None,
        'отчество': None,
        'дата_рождения': None,
        'найден': None,
        'источники': [],
        'примечание': None
    }

    parts = fio_data.strip().split()
    if len(parts) >= 2:
        data['фамилия'] = parts[0]
        data['имя'] = parts[1] if len(parts) > 1 else None
        data['отчество'] = parts[2] if len(parts) > 2 else None
        if parts[-1].replace('.', '').isdigit():
            data['дата_рождения'] = parts[-1]

    found = []
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if data['фамилия'] and data['имя']:
                url = f'https://api.sudrf.ru/search?lastname={data["фамилия"]}&firstname={data["имя"]}'
                async with session.get(url, headers=HEADERS) as resp:
                    if resp.status == 200:
                        result = await resp.text()
                        if 'найден' in result.lower():
                            found.append('Судебные решения')
            if data['фамилия']:
                url = f'https://api.fns.ru/search?name={data["фамилия"]}'
                async with session.get(url, headers=HEADERS) as resp:
                    if resp.status == 200:
                        result = await resp.text()
                        if 'найден' in result.lower():
                            found.append('ФНС (юрлица)')
    except:
        pass

    if found:
        data['найден'] = '✅ Найден'
        data['источники'] = found
    else:
        data['найден'] = '❌ Не найден'

    return data

# ============== ЗАПУСК ==============

def main():
    if not TOKEN:
        print("❌ Ошибка: токен не задан")
        return

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
    print("✅ OSINT-бот запущен (с документами)")
    app.run_polling()

if __name__ == '__main__':
    main()
