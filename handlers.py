from aiogram import types, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
from config import ADMIN_ID
from bot.states import AccessRequestState
from utils.access import client, check_user_access
from .keyboards import get_simulator_keyboard
import logging
import json
import random
from speech_recognition_old import recognize_speech_from_file
import random
import os
import base64
import aiohttp
from sever import send_request


conversation_state = {
    "greeting_done": False,
    "product_mentioned": False,
    "price_mentioned": False,
    "closing_attempted": False
}

async def get_response(conversation_history):
    system_message = {
        "role": "system",
        "content": "Отыгрывай роль человека, которому позвонили по телефону. Возвращай только свои реплики."
    }
    
    messages = [system_message] + conversation_history
    
    async with aiohttp.ClientSession() as session:
        response_json = await send_request(session, messages)
        
    if response_json and 'choices' in response_json:
        return response_json['choices'][0]['message']['content']
    else:
        return "Извините, произошла ошибка при обработке вашего запроса."



router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    keyboard = get_simulator_keyboard(message)
    if check_user_access(user_id):
        await message.answer("Добро пожаловать! У вас есть доступ к боту. Используйте клавиатуру для использования симулятора.", reply_markup=keyboard)
    else:
        await message.answer("У вас нет доступа к этому боту. Пожалуйста, отправьте вашу Фамилию Имя для подачи заявки на доступ.")
        await state.set_state(AccessRequestState.waiting_for_full_name)

@router.message(AccessRequestState.waiting_for_full_name)
async def process_access_request(message: types.Message, state: FSMContext):
    full_name = message.text
    user_id = message.from_user.id
    username = message.from_user.username or "Нет username"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Открываем второй лист (индекс 1) в таблице "Белый лист"
    sheet = client.open('Доступ_нейротренер')
    access_sheet = sheet.get_worksheet(1)  # Получаем второй лист (индекс 1)

    # Добавляем данные во второй лист
    row = [timestamp, full_name, str(user_id), username]
    access_sheet.append_row(row)

    await message.answer("Ваша заявка на доступ принята. Пожалуйста, ожидайте одобрения администратором.")
    await state.clear()

    # Отправляем оповещение админу о новой заявке
    admin_message = f"Новая заявка на доступ:\n" \
                    f"Фамилия Имя: {full_name}\n" \
                    f"ID пользователя: {user_id}\n" \
                    f"Имя пользователя: @{username}\n" \
                    f"Дата и время: {timestamp}"
    await message.bot.send_message(ADMIN_ID, admin_message)

@router.message(lambda message: message.web_app_data)
async def handle_web_app_data(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        if data['action'] == 'log':
            logging.info(f"Log from WebApp: {data['message']}")
        elif data['action'] == 'startCall':
            await message.reply("Звонок начат. Говорите...")
        elif data['action'] == 'endCall':
            await message.reply("Звонок завершен")
        elif data['action'] == 'sendAudio':
            # Здесь мы ожидаем, что аудиоданные будут отправлены в формате base64
            audio_data = data.get('audio')
            if audio_data:
                # Декодируем base64 в байты
                audio_bytes = base64.b64decode(audio_data)
                
                # Сохраняем временный файл
                temp_filename = f"temp_audio_{message.from_user.id}.webm"
                with open(temp_filename, "wb") as temp_file:
                    temp_file.write(audio_bytes)
                
                # Распознаем речь
                user_speech = recognize_speech_from_file(temp_filename)
                
                # Получаем ответ от бота
                response = await get_response(user_speech)
                
                # Отправляем ответ пользователю
                await message.reply(f"Вы сказали: {user_speech}\nОтвет собеседника: {response}")
                
                # Удаляем временный файл
                os.remove(temp_filename)
            else:
                await message.reply("Аудиоданные не получены")
    except json.JSONDecodeError:
        await message.reply("Получены некорректные данные от Web App")
    except KeyError:
        await message.reply("В данных от Web App отсутствует необходимая информация")

def register_handlers(dp):
    dp.include_router(router)