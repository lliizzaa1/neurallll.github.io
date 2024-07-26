from flask import Flask, jsonify, request, session, make_response
from flask_cors import CORS
import logging
import random
from speech_recognition_mine import recognize_speech_from_file
import os
import aiohttp
import asyncio
from dotenv import load_dotenv
from gtts import gTTS
import tempfile
import uuid
import pyttsx3
import io
import base64
import wave
from flask_cors import cross_origin
import json
from flask import render_template
from aiogram import Bot
from bot_instance import bot

async def send_end_call_message(bot: Bot, user_id: int, text: str, duration: int):
    """Отправляет сообщение о завершении звонка пользователю в Telegram, 
       разбивая длинные сообщения на части.
    """
    try:
        MAX_MESSAGE_LENGTH = 4096
        
        # Формирование начала сообщения с информацией о продолжительности
        header_text = f"Звонок завершен. Продолжительность: {duration} сек.\n История диалога:\n"
        
        # Вычисление доступной длины для текста диалога
        available_length = MAX_MESSAGE_LENGTH - len(header_text) 
        
        # Разделение текста диалога на части
        text_parts = [text[i:i + available_length] for i in range(0, len(text), available_length)]
        
        # Отправка частей сообщения
        for i, part in enumerate(text_parts):
            # Добавляем заголовок только к первой части
            if i == 0:
                await bot.send_message(user_id, header_text + part) 
            else:
                await bot.send_message(user_id, part)
            
    except Exception as e:
        print(f"Ошибка при отправке сообщения в Telegram: {e}")
    

semaphore = asyncio.Semaphore(50)

load_dotenv()
API_KEY = os.getenv("API_KEY")

def format_conversation(conversation_history: list) -> str:
  """
  Преобразует массив словарей с историей диалога в форматированный текст.

  Args:
    conversation_history: Массив словарей, где каждый словарь представляет 
                          сообщение с ключами 'role' и 'content'.

  Returns:
    Строка с отформатированной историей диалога.
  """

  formatted_text = ""

  for message in conversation_history:
    role = message['role']
    content = message['content']

    # Удаляем префикс "пользователь-инвестиционный консультант:" и "бот-потенциальный клиент:"
    if content.startswith('пользователь-инвестиционный консультант:'):
        content = content[len('пользователь-инвестиционный консультант:'):]
    elif content.startswith('бот-потенциальный клиент:'):
        content = content[len('бот-потенциальный клиент:'):].replace("бот-потенциальный клиент:", "", 1)

    formatted_text += f"{role}: {content}\n"

  return formatted_text

async def get_response(conversation_history, person_characteristics=None):
    system_message = {
        "role": "system",
        "content": f"""Ты — клиент, который отвечает на холодный звонок. Твоя задача — вести себя максимально реалистично, как настоящий человек. Ты можешь быть разным: доброжелательным, агрессивным, заинтересованным, негативным, нейтральным, занятым или даже равнодушным. Ты можешь менять свое настроение в течение разговора. Твоя главная цель — дать тому, кто звонит, почувствовать, что он разговаривает с настоящим, живым человеком, а не с моделью. Ты можешь задавать вопросы, выражать сомнения, отказываться от предложений, вести переговоры или даже завершить звонок. Помни, что люди могут быть непредсказуемыми, и твоя задача отражать это в ходе разговора.
        Всегда возвращай только свои реплики, без пометок, кто это говорит. Учти, ты будучи клиентом можешь в любой момент сбросить звонок, в этом случае верни строго только слово СБРОС.
        Учти следующие, что ты обладаешь следующими характеристиками: {person_characteristics} 
        """
    }
    
    messages = [system_message] + conversation_history
    print(messages)
    async with aiohttp.ClientSession() as session:
        response_json = await send_request(session, messages, temperature=0.7)
        
    if response_json and 'choices' in response_json:
        return response_json['choices'][0]['message']['content']
    else:
        return "Извините, произошла ошибка при обработке вашего запроса."
    
async def get_report(communication, duration=0, start_call=0):
    system_message = {
        "role": "system",
        "content": f"""Ты - ассистент для оценки качества коммуникации в телефонных разговорах. Твоя задача - проанализировать диалог между консультантом и клиентом, а затем предоставить подробный отчет в соответствии со следующими критериями, оценивать ты должен именно то, как общался СОТРУДНИК:
                Сначала дай краткую устную обратную связь: оцени, был ли звонок хорошим или нет. Укажи одну ключевую ошибку, если она есть, или одну сильную сторону, если что-то было сделано особенно хорошо.
                Затем предоставь развернутый текстовый отчет в следующем формате:
                🔴/🟡/🟢 Результат: [Выбери подходящий вариант]
                Встреча назначена. Есть ошибки 🟡
                Встреча назначена. Ошибок нет 🟢
                Встреча не назначена. Есть ошибки 🔴
                Встреча не назначена. Ошибок нет 🟢
                📆 Начало звонка: [дата и время] {start_call}
                ⏳ Длительность: [в секундах или в формате "минуты:секунды" если больше 60 секунд] {duration}
                ✍️ Транскрипция по ролям: [полная расшифровка диалога]
                💡 Обратная связь
                🦾 Сильные стороны:
                [Перечисли сильные стороны консультанта в разговоре. Если их нет, оставь пустым]
                ❌ Ошибки:
                [Перечисли ошибки консультанта, включая следующие, если они присутствуют:
                Использование фраз: "АЛЛО", "Не отвлекаю?", "Сотрудничество", слова-паразиты и междометия, "Занимаемся инвестициями", "Размещение денежных средств"
                Не спрашивает почту, если клиент не готов встретиться сейчас, но имеет интерес в будущем
                Не договаривается о необходимости и формате подтверждения встречи, если она назначена
                Если ошибок нет, напиши "Ошибок нет"]
                Для статистики, кластеризируй ошибки по общим категориям.
                Не давай обратную связь по ходу звонка, только в итоговом отчете.
                Сохраняй всю информацию о звонке для дальнейшего анализа и статистики.
                assistant - это КЛИЕНТ (его имитирует бот), user - это СОТРУДНИК. НЕ ПУТАЙ. ВСЕГДА ДИАЛОГ НАЧИНАЕТ СОТРУДНИК
                Проанализируй предоставленный диалог и дай отчет в соответствии с этими инструкциями: {communication}
                        """
    }
    
    messages = [system_message]
    print('########################################################')
    print(messages)
    print('########################################################')
    async with aiohttp.ClientSession() as session:
        response_json = await send_request(session, messages)
        
    if response_json and 'choices' in response_json:
        return response_json['choices'][0]['message']['content']
    else:
        return "Извините, произошла ошибка при обработке вашего запроса."

async def send_request(session, messages, max_retries=10, retry_delay=2, temperature=0.1):
    for attempt in range(max_retries):
        try:
            async with semaphore:
                async with session.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                    },
                    json={
                        "model": "anthropic/claude-3.5-sonnet",
                        "messages": messages,
                        "provider": {"order": ["Anthropic"]},
                        "max_tokens": 200000,
                        "temperature": temperature,
                        "top_p": 0.5,
                        "top_k": 50,
                        "samplingParameters": {
                            "temperature": temperature,
                            "top_p": 0.5,
                            "top_k": 50
                        },
                    }
                ) as response:
                    if response.status == 200:
                        response_json = await response.json()
                        return response_json
                    else:
                        error_message = f"API request failed with status {response.status}: {response.reason}"
                        print(error_message)  # Или запишите в лог
        except Exception as e:
            print(f"Error in send_request: {str(e)}")  # Или запишите в лог

        if attempt == max_retries - 1:
            return None

        await asyncio.sleep(retry_delay)

    return None

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Замените на свой секретный ключ
#CORS(app, resources={r"/*": {"origins": "https://lliizzaa1.github.io"}}) #http://localhost:5000/
origins = [
    "http://127.0.0.1:5000",  #  <-  Если ты используешь этот адрес для разработки
    "https://lliizzaa1.github.io"  #  <- Домен GitHub Pages 
]

# Создаём экземпляр CORS, указав origins
#cors = CORS(app, resources={r"/*": {"origins": origins}})
#cors = CORS(app, resources={r"/*": {"origins": "https://lliizzaa1.github.io"}})
#cors = CORS(app, resources={r"/*": {"origins": "https://lliizzaa1.github.io"}}, supports_credentials=True)
cors = CORS(app, resources={r"/*": {"origins": ["https://lliizzaa1.github.io"]}})

conversation_state = {
    "greeting_done": False,
    "product_mentioned": False,
    "price_mentioned": False,
    "closing_attempted": False
}

def get_conversation_filename(telegram_user_id):
    """Возвращает путь к файлу с историей диалога для пользователя Telegram."""
    os.makedirs('conversations', exist_ok=True)
    return os.path.join('conversations', f'{telegram_user_id}.json')

@app.route('/start_call', methods=['POST'])
def start_call():
    """ Больше не нужен, так как мы используем Telegram User ID. 
        Можно удалить этот маршрут или оставить пустым, если он используется на фронтенде. 
    """
    return jsonify({"message": "Call started"})

@app.route('/end_call', methods=['POST'])
def end_call():
    """Завершает диалог."""
    user_id = session.pop('user_id', None)
    if not user_id:
        return jsonify({"message": "No active call"}), 400

    # (опционально) удаление файла с историей диалога
    conversation_filename = get_conversation_filename(user_id)
    if os.path.exists(conversation_filename):
       os.remove(conversation_filename)

    return jsonify({"message": "Call ended"})

@app.route('/delete_conversation', methods=['POST'])
async def delete_conversation(): # добавила async
    telegram_user_id = request.form.get('telegram_user_id')
    if not telegram_user_id:
        return jsonify({"error": "Telegram User ID is missing"}), 400

    conversation_filename = get_conversation_filename(telegram_user_id)
    with open(conversation_filename, 'r', encoding='utf-8') as f:
                conversation_history = json.load(f)
    print(conversation_history)
    conversation_history = format_conversation(conversation_history)
    conversation_history = await get_report(conversation_history)
    await send_end_call_message(bot=bot, user_id=telegram_user_id, text=conversation_history, duration=0)
    if os.path.exists(conversation_filename):
        os.remove(conversation_filename)
        return jsonify({"message": "Conversation deleted"}), 200
    else:
        return jsonify({"message": "Conversation not found"}), 404

@app.route('/test', methods=['GET'])
def test():
    logging.info("Test endpoint called")
    return jsonify({"message": "Server is working!"})

#@app.after_request
#def after_request(response):
#    response.headers.add('Access-Control-Allow-Origin', '*')
#    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
#    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
#    return response

def generate_audio(text):
  print("Генерирую речь...")
  tts = gTTS(text=text, lang='ru') 

  # Используем BytesIO для сохранения аудио в памяти
  with io.BytesIO() as memory_buffer: 
    tts.write_to_fp(memory_buffer)
    memory_buffer.seek(0) 
    audio_data = memory_buffer.read()
  
  print("Речь сгенерирована")
  return audio_data


@app.route('/recognize_speech', methods=['POST'])
async def handle_speech():
    """Обрабатывает речь пользователя, получает ответ бота 
       и сохраняет историю диалога в файл, используя Telegram User ID.
    """
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files['audio']
    telegram_user_id = request.form.get('telegram_user_id')  # Получаем Telegram User ID из FormData
    request_id = int(request.form.get('requestId'))
    person_characteristics = request.form.get('characteristics')
    
    print("Получены характеристики:", person_characteristics) 

    if audio_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if not telegram_user_id:
        return jsonify({"error": "Telegram User ID is missing"}), 400

    if audio_file:
        user_speech = recognize_speech_from_file(audio_file)
        if user_speech is None:
            return jsonify({"error": "Ошибка распознавания речи"}), 500

        conversation_filename = get_conversation_filename(telegram_user_id)
        try:
            with open(conversation_filename, 'r', encoding='utf-8') as f:
                conversation_history = json.load(f)
        except FileNotFoundError:
            conversation_history = []

        conversation_history.append({"role": "user", "content": "пользователь-инвестиционный консультант:" + user_speech})

        # Получение ответа от бота
        bot_response = await get_response(conversation_history, person_characteristics)
        print('_______________________', bot_response)
        if bot_response.strip().upper() == "СБРОС":
            #  Выполняем действия по завершению звонка 

            return jsonify({
                "user_speech": user_speech,
                "bot_response": "Звонок завершен клиентом.", #  Ответ для фронтенда
                "audio_data": None,  #  Можно отправить сигнал тишины
                "requestId": request_id,
                "callEnded": True  #  Флаг для фронтенда
            }), 200 

        conversation_history.append({"role": "assistant", "content": 'бот-потенциальный клиент:'+ bot_response})

        with open(conversation_filename, 'w', encoding='utf-8') as f:
            json.dump(conversation_history, f, indent=4, ensure_ascii=False)

        audio_data = generate_audio(bot_response)
        audio_data_base64 = base64.b64encode(audio_data).decode('utf-8')

        response = make_response(jsonify({
            "user_speech": user_speech,
            "bot_response": bot_response,
            "audio_data": f"data:audio/wav;base64,{audio_data_base64}",
            "requestId": request_id 
        }))

        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
        #response.headers['Access-Control-Allow-Credentials'] = 'true'

        return response, 200

    return jsonify({"error": "Invalid file"}), 400

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
